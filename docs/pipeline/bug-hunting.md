# Pipeline Bug-Hunting Cheatsheet

> **Purpose:** Actionable audit of suspicious code paths in the extraction pipeline. Scan the tables, pick a finding, open the referenced file:line, verify, and decide what to fix.
>
> **Companion doc:** [`internals.md`](./internals.md) — the deep technical reference. This doc tells you *what looks wrong*; the internals doc tells you *how the code actually works*.
>
> **History vs. current state:** [`AUDIT.md`](../audit/AUDIT.md) logs bugs that were already fixed. This doc lists code that is currently in production and should be reviewed.

---

## Severity Legend

| Marker | Meaning |
|---|---|
| **[CRITICAL]** | Data loss, silent corruption, or user-visible incorrectness. Fix before the SoftwareX submission. |
| **[SUSPECT]** | Behaviour looks wrong on inspection but hasn't been observed failing. Needs a test case to confirm. |
| **[FRAGILE]** | Works today but depends on assumptions that aren't enforced. Will break when something upstream changes. |

All findings are ordered by risk within each section. Every entry includes `file:line` for direct navigation.

---

## Section 1 — CRITICAL Findings

### 1.1 Parallel mode: `ready()` → `.get(timeout=0)` race swallows worker errors

**File:** `python/modules/pipeline_orchestrator.py:1085-1092`

```python
# pipeline_orchestrator.py:1085
for pmid in newly_done:
    info = in_flight.pop(pmid)
    idx = info["idx"]
    ctx = info["ctx"]
    try:
        payload = info["async_result"].get(timeout=0)
    except Exception as e:
        payload = {"error": str(e)}
```

**Problem.** Between `ready() == True` (line 1071) and `.get(timeout=0)` (line 1090), the worker process can crash. The bare `except Exception` swallows the real error and produces a generic `{"error": str(e)}` payload with no traceback. Worker segfaults, OOM kills, and `AssertionError`s inside `GeneInfoPipeline` all look identical to the caller.

**Impact.** Debugging a worker crash requires reproducing it locally because the production logs have no stack trace.

**Fix.** Log `traceback.format_exc()` and the exception *type* before wrapping. Consider a separate `TimeoutError` branch so you can distinguish hangs from crashes.

---

### 1.2 Pool restart resets per-paper timeout clock

**File:** `python/modules/pipeline_orchestrator.py:1169-1176`

```python
# pipeline_orchestrator.py:1169
worker_pool.terminate()
worker_pool.join(timeout=10)
worker_pool = mp.Pool(processes=pool_size)
logging.info(f"AI worker pool recreated: {pool_size} processes")

for pmid, info in list(in_flight.items()):
    ctx = info["ctx"]
    ctx["submitted_at"] = time.time()   # ← clock reset
```

**Problem.** When a timeout triggers a pool restart, every in-flight paper gets `submitted_at = time.time()`. The 600-second per-paper budget restarts from zero. If a paper hangs a second time on the new pool, timeout detection fires 600s later — 20 minutes of stalled pipeline on a pathological paper.

**Impact.** A single bad paper can stall the pipeline for `AI_PER_PAPER_TIMEOUT_SECONDS × retries`. Worst case with 3 restarts: 30 minutes per paper.

**Fix.** Track an `original_submitted_at` that never resets, or a `retry_count` that caps at 1. After one restart, if the same paper hangs again, mark it as a permanent timeout and skip.

---

### 1.3 Pool restart leaves stale `in_flight` entries

**File:** `python/modules/pipeline_orchestrator.py:1174-1196`

**Problem.** After `worker_pool.terminate()`, the code iterates `in_flight` and re-submits each paper to the new pool. But the restart path only re-submits papers whose timeout *didn't* fire. Papers that are neither timed out nor ready get re-submitted and stay in `in_flight` — correct. Papers that were ready but not yet harvested (lines 1142-1167) get harvested *before* the restart. That ordering is fragile: if `_finalize_paper_result()` raises for a harvested-but-ready paper, the code continues to `terminate()` anyway, and the in-flight dict still contains entries pointing to async results on a dead pool.

**Impact.** Memory leak of `ctx` objects (each holds `paper_text` which can be 1+ MB). Accumulates with every pool restart over a long run.

**Fix.** Wrap the ready-harvest loop (lines 1142-1167) in a try/except that cleans `in_flight` on failure. Or restructure: do ALL harvesting (including timeouts) before touching the pool.

---

### 1.4 Variant dedup aggregation silently loses empty variants

**File:** `python/modules/pipeline_orchestrator.py:1563-1565`

```python
# pipeline_orchestrator.py:1563
def _agg_variants(series):
    vals = {str(v) for v in series if str(v).strip()}
    return "; ".join(sorted(vals))
```

**Problem.** The aggregation drops any variant that is empty or whitespace. A gene with both a variant row and a gene-level row (variant=`""`) will be merged into a single row with just the variant name, losing the signal that the gene was *also* extracted at the gene level. Downstream `_compute_row_confidence()` can't distinguish "gene-only evidence" from "variant-only evidence" post-dedup.

**Impact.** Confidence tier may shift from MEDIUM to LOW for genes that had dual evidence.

**Fix.** Either emit `"(gene-level)"` as a sentinel for empty variants, or track gene-level evidence in a separate column preserved through dedup.

---

### 1.5 Dedup wrapped in swallow-all try/except

**File:** `python/modules/pipeline_orchestrator.py:1573-1574`

```python
# pipeline_orchestrator.py:1573
    except Exception as e:
        logging.warning(f"Deduplication step skipped due to error: {e}")
```

**Problem.** If `groupby(...).agg(...)` raises (e.g., dtype mismatch in group keys, empty DataFrame edge case), the entire dedup step is skipped. The warning goes to stderr; the CSV still writes. Users get duplicates with no visible error.

**Impact.** Silent duplicate rows in production output. Users might not notice until they run stats downstream.

**Fix.** At minimum, record the skip in the debug artifact and surface it via `LOG:{"level":"error", ...}`. Better: validate dtypes explicitly before `groupby`.

---

### 1.6 Citation match threshold hardcoded

**File:** `python/modules/gene_validator.py:704`

```python
# gene_validator.py:704
if best_ratio < 0.85:
    prose_failure = (False, best_ratio, f"No dense match found (best ratio: {best_ratio:.2f})")
```

**Problem.** The 0.85 dense-match threshold is a magic number. LLMs sometimes produce citations that are light paraphrases (synonyms, passive voice, reordered clauses) which never reach 0.85. These valid citations get marked invalid, flagging the row as REVIEW.

**Impact.** False REVIEW tier. A known pain point with stochastic LLM compliance (see `docs/audit/AUDIT.md` C19, C22).

**Fix.** Add `CITATION_MATCH_RATIO_THRESHOLD = 0.85` to `config.py`. Run a sweep across the benchmark papers to find the empirical curve (precision vs. recall at thresholds 0.70–0.95) and document the choice.

---

### 1.7 Citation word overlap threshold hardcoded

**File:** `python/modules/gene_validator.py:690`

```python
# gene_validator.py:690
if len(common) / len(cit_set) < 0.6:
    continue
```

**Problem.** 0.6 is a pre-filter for the dense match above. It's the same magic-number issue, and it interacts with line 704: lower this and you pay a finer search cost; raise it and you miss citations that use synonyms.

**Fix.** `CITATION_WORD_OVERLAP_THRESHOLD = 0.6` in config, sweep on benchmark.

---

### 1.8 `isResultPayload` accepts any object

**File:** `src/main/python-bridge.ts:25-27`

```typescript
// python-bridge.ts:25
function isResultPayload(p: unknown): p is { local_path?: string; metadata_path?: string; excel_path?: string; json_path?: string; error?: string } {
  return typeof p === 'object' && p !== null
}
```

**Problem.** The type guard only checks that `p` is an object. A Python bug that emits `RESULT:{}` or `RESULT:{"random":"data"}` would pass the guard, and the code at lines 169-177 would persist `result_path = null, metadata_path = null, ...` with status `completed`. The job shows success but opens to nothing.

**Impact.** User sees a "Completed" job in History with no artifacts. Has to inspect logs to realise what happened.

**Fix.** Require at least one of `local_path | error` to be a string. Reject anything else with a log entry and mark the job `failed`.

---

### 1.9 RESULT vs. cancel micro-race

**File:** `src/main/python-bridge.ts:156-161`

```typescript
// python-bridge.ts:156
const raw = JSON.parse(line.slice(7))
if (!isResultPayload(raw)) {
  console.error('[python-bridge] Invalid RESULT payload:', line.slice(0, 200))
} else {
  const job = getJob(jobId)
  if (job?.status === 'cancelled') {
    continue
  }
```

**Problem.** The check-then-act sequence (`getJob → continue`) is NOT atomic with the `updateJob` call in `cancelPipeline`. If RESULT arrives after `cancelPipeline` set status but before the scheduler yields to this callback, the code correctly skips. But if RESULT arrives *during* `cancelPipeline`'s own `updateJob` call, there's a window where `getJob` returns status='running' and the RESULT is processed, overwriting the cancel.

**Impact.** Microscopic window in practice. Mostly theoretical because Node.js callbacks are single-threaded. BUT: better-sqlite3 is synchronous, so the `updateJob` in `cancelPipeline` completes before returning — meaning the risk window only exists if `cancelPipeline` hasn't been called yet when RESULT arrives. That's a different bug (order of operations on user input).

**Fix.** Move the `getJob` check into a helper that also claims the state transition atomically. Alternatively: always check the pipeline status BEFORE processing the RESULT fields, and reject if not 'running'.

---

### 1.10 Grounding check can be bypassed for mixed-source figure genes

**File:** `python/modules/gemini_extractor.py:1455-1479`

**Problem.** The figure-specific grounding check (light check: search figure captions) only runs when `sources == {"llm_figure"}`. A gene that was found by BOTH `llm_figure` AND `deterministic_lexicon` has `sources = {"llm_figure", "deterministic_lexicon"}`, which fails the set equality. It falls through to the standard grounding check (line 1444) which searches the full paper text. If the deterministic lexicon found the gene as a raw match but the gene has no prose context, the grounding check might still pass because the lexicon match is itself textual evidence.

**Impact.** Genes that exist in the paper only as a bare symbol in a table or legend (no molecular context) can pass grounding when they should be flagged as low-context.

**Fix.** For any gene with `llm_figure` in sources, apply the figure-caption check as a mandatory AND gate in addition to prose grounding. Or track a "has_prose_context" flag separately.

---

## Section 2 — SUSPECT Findings

### 2.1 HIGH confidence tier unreachable if `val_conf < 0.85`

**File:** `python/modules/pipeline_orchestrator.py:79-93`

**Problem.** `_compute_row_confidence` returns LOW if `val_conf < 0.85` before it can evaluate the HIGH branch. HIGH requires `gene_source == "both"` AND a valid citation — but if validation confidence didn't hit 0.85, the row has already returned LOW. Some dual-source genes with `val_conf = 0.8` that have verified citations land in LOW when they should be at least MEDIUM.

**Fix.** Reorder: check dual-source corroboration first. If both NER and LLM agree AND citation is valid, promote to HIGH regardless of val_conf (as long as it's above some floor, e.g., 0.5).

---

### 2.2 HGNC API fallback has no circuit breaker

**File:** `python/modules/gene_validator.py:216-250`

**Problem.** Every failed local lookup tries the HGNC REST API. If HGNC is down (503) or slow (8s+), every one of 2000 gene validations pays the timeout. 2000 × 8s = 4.5 hours stalled on a single paper.

**Fix.** Circuit breaker: after N consecutive failures, stop trying HGNC for M seconds. Use MyGene.info as the immediate fallback.

---

### 2.3 Figure URL dedup loses multi-panel figure detail

**File:** `python/modules/full_text_fetcher.py:354-413`

**Problem.** Figure URL dedup uses only the URL string. PMC multi-panel figures (1A, 1B, 1C) sometimes share the same image URL with different panel labels. Dedup by URL alone drops panels 1B and 1C.

**Fix.** Key the dedup by `(url, label)` tuple. Or track panel count separately and include it in the debug artifact.

---

### 2.4 Semantic Scholar per-PMID rate limit

**File:** `python/modules/pubmed_data_collector.py:364-385`

**Problem.** The Semantic Scholar fallback loops over unresolved PMIDs one at a time with a 200ms sleep. For 1000 unresolved PMIDs that's 3+ minutes of pure wait.

**Fix.** Semantic Scholar supports batch queries (up to 500 PMIDs per request). Rewrite the fallback to batch.

---

### 2.5 `PARALLEL_ANALYSIS` string coercion accepts any truthy value

**File:** `src/main/python-bridge.ts:93` + `python/modules/config.py:154`

```typescript
// python-bridge.ts (around line 93, inside env:)
PARALLEL_ANALYSIS: settings.parallelAnalysis ? 'true' : 'false',
```

```python
# config.py:154
PARALLEL_ANALYSIS = os.getenv("PARALLEL_ANALYSIS", "false").lower() == "true"
```

**Problem.** This one is fine (explicit string comparison). But several other config lines use `bool(os.getenv(...))` patterns elsewhere in the codebase. Those would treat any non-empty string as True, including `"false"`, `"0"`, `"no"`. Grep for `bool(os.environ` and `bool(os.getenv` to audit.

**Fix.** Use the `.lower() == "true"` idiom consistently across `config.py`.

---

### 2.6 Validation fallback trusts pre-validation on empty result

**File:** `python/modules/gemini_extractor.py:1505-1549` (`_run_validation_and_normalize`)

**Problem.** If `_apply_gene_validation_heuristics()` filters out all associations AND `ENABLE_STRICT_VALIDATION_GATE=False`, the code falls back to `pre_validation_associations`. This trusts the raw LLM output after it *failed* gene validation. Only safe with strict gate off, but worth a second look: the gate-off branch should probably still apply SOME floor (e.g., must exist in HGNC at any confidence) rather than taking raw LLM output.

**Fix.** Even with strict gate off, require each association to have `validation_source != "unresolved"`. That's a weaker floor but prevents "ABCDEF" from reaching the CSV.

---

### 2.7 `Medline.parse()` silently drops malformed records

**File:** `python/modules/pubmed_data_collector.py:222-228`

**Problem.** Biopython's `Medline.parse()` skips records it can't parse. No exception is raised. Papers with corrupted metadata (rare but possible with very old NCBI entries) simply vanish from the result set.

**Fix.** Count the expected vs. actual returned PMIDs from Medline and log a warning if they differ. This is a signal, not a fix.

---

### 2.8 Sequential mode polling loop burns CPU on slow workers

**File:** `python/modules/pipeline_orchestrator.py:1244-1251`

**Problem.** Sequential mode uses a 200ms polling loop around `async_result.ready()` instead of `async_result.get(timeout=N)`. This adds up-to-200ms detection lag per timeout, and burns CPU during the check_cancellation cycles.

**Fix.** Use `async_result.get(timeout=AI_PER_PAPER_TIMEOUT_SECONDS)` inside a try/except TimeoutError. Cancel check moves to a signal handler or a separate thread.

---

### 2.9 `_finalize_paper_result` assumes PubTator results exist

**File:** `python/modules/pipeline_orchestrator.py:409-517` (approximate)

**Problem.** The code checks `if pmid in pubtator_results` before enrichment. If `ENABLE_PUBTATOR_EXTRACTION=False`, `pubtator_results` is empty for all PMIDs, and the `Gene Source` / `NCBI Gene ID` columns are silently omitted from the output. Users who disable PubTator think those columns should be blank, not missing.

**Fix.** Always initialize the columns with empty strings so downstream code and users see a consistent schema.

---

## Section 3 — FRAGILE Contracts

### 3.1 `_write_split_output` silently drops renamed user columns

**File:** `python/modules/pipeline_orchestrator.py:217-290` (approximate)

**Contract assumed:** user_cols names match DataFrame column names.

**What breaks it:** If a downstream method renames columns (e.g., strips whitespace, lowercases), the filter `[c for c in user_cols if c in df_clean.columns]` drops the renamed columns. They still appear in the metadata CSV but not the primary CSV. Schema mismatch between the two files goes undetected.

**Fix.** Validate column set parity between primary and metadata CSVs at write time. Log a warning on mismatch.

---

### 3.2 `validate_citations` collapses "empty" and "mismatched" into the same result

**File:** `python/modules/gene_validator.py:541-582` (approximate)

**Contract assumed:** Callers can distinguish "no citation provided" from "citation provided but not in paper".

**What breaks it:** Both cases return a zero-confidence result. No way to tell them apart in the debug artifact.

**Fix.** Add a `validation_reason` field: `"empty" | "not_found" | "matched_prose" | "matched_table"`.

---

### 3.3 JATS XML parser conflates invalid XML with empty article

**File:** `python/modules/full_text_fetcher.py:499-617` (approximate)

**Contract assumed:** Caller can distinguish parse error from "valid but empty".

**What breaks it:** Both return `(None, [], [])`. A real parse error is silent. If PMC's JATS XML schema changes, the fetcher silently degrades to abstract-only for every paper.

**Fix.** Raise on parse error; return `("", [], [])` on valid-but-empty.

---

### 3.4 PubTator PMID extraction tries multiple response fields

**File:** `python/modules/pubtator_tool.py:204-208`

**Contract assumed:** The PubTator3 API response has one of `pmid`, `id`, or `_id` containing the PMID.

**What breaks it:** If PubTator changes the response schema, the extraction silently returns None and the paper is dropped from the result dict. No warning. Caller sees an empty result map.

**Fix.** Raise on unrecognized schema. At minimum, log at ERROR level.

---

### 3.5 `_finalize_paper_result` assumes `paper_df` has `Gene/Group` column

**File:** `python/modules/pipeline_orchestrator.py:538-539` (approximate)

**Contract assumed:** `GeneInfoPipeline.run_pipeline()` always returns a DataFrame with `Gene/Group` column (even empty).

**What breaks it:** An edge case in `_run_detail_extraction` that returns `pd.DataFrame()` (the empty-no-columns case) — the caller hits KeyError on `.dropna().nunique()`.

**Fix.** Normalize the empty return to have the expected columns. Or check `if "Gene/Group" in paper_df.columns` first.

---

## Section 4 — Silent Failure Modes (consolidated)

Every `try/except` below catches an error without surfacing it. Grep for them and decide which should re-raise.

| File:line | What's caught | What's lost | Should be |
|---|---|---|---|
| `pipeline_orchestrator.py:1091-1092` | Worker `.get()` exception | Traceback, exception type | Log type + traceback; distinguish timeout from crash |
| `pipeline_orchestrator.py:1573-1574` | `groupby(...).agg(...)` failure | Dedup entirely | Emit LOG:error; record in debug artifact |
| `gemini_extractor.py:1346-1349` | Second-pass LLM extraction failure | 2nd-pass results | Log at warn level (already done); continue OK |
| `gemini_extractor.py:1510-1511` | `_apply_gene_validation_heuristics` failure | All validation | Re-raise; no safe fallback |
| `gene_validator.py:109-110` (approximate) | Local HGNC DB load failure | Fast local validation | Fail explicitly; don't silently fall back to API |
| `full_text_fetcher.py:179,223,240,257` (approximate) | PDF/Excel/ZIP extraction failures | Supplementary content | Distinguish "unreadable" from "doesn't exist" |
| `pubmed_data_collector.py:284-286` (approximate) | Batch fetch exception | Partial batch results | Either fail batch or continue — current behavior is ambiguous |
| `python-bridge.ts:131-133` | PROGRESS parse failure | Progress stats | Already logs to console; consider bubbling to UI |
| `python-bridge.ts:149-151` | LOG parse failure | Log line | Console-only; OK for LOG but not PROGRESS |
| `python-bridge.ts:180-182` | RESULT parse failure | Entire result | Mark job failed, don't just log |

---

## Section 5 — Hardcoded Constants That Should Be Config

| File:line | Current value | Proposed flag | Notes |
|---|---|---|---|
| `gene_validator.py:704` | 0.85 | `CITATION_MATCH_RATIO_THRESHOLD` | See 1.6 |
| `gene_validator.py:690` | 0.6 | `CITATION_WORD_OVERLAP_THRESHOLD` | See 1.7 |
| `gemini_extractor.py:254` (approx) | 240 chars | *already is* `EVIDENCE_SNIPPET_MAX_CHARS` | Confirmed in config:114 — OK |
| `gemini_extractor.py:272` (approx) | 80 chars lookback | `EVIDENCE_SNIPPET_LOOKBACK_CHARS` | New |
| `gemini_extractor.py:276` (approx) | 220 chars lookahead | `EVIDENCE_SNIPPET_LOOKAHEAD_CHARS` | New |
| `gemini_extractor.py:777` (approx) | 20 PubTator genes | `PUBTATOR_PROMPT_MAX_GENES` | New; currently truncates silently |
| `pipeline_orchestrator.py:79,88` | 0.85 validation conf floor | `CONFIDENCE_THRESHOLD_FOR_LOW` | See 2.1 |
| `pubtator_tool.py:226` (approx) | 0.5s batch sleep | `PUBTATOR_BATCH_SLEEP_SECONDS` | New |
| `pubtator_tool.py:452,474` (approx) | 0.1s NCBI API sleep | `NCBI_API_SLEEP_SECONDS` | New |
| `pubmed_data_collector.py:289` (approx) | 0.4s fetch sleep | `PUBMED_FETCH_SLEEP_SECONDS` | New |
| `full_text_fetcher.py:202-204` (approx) | 200 row CSV limit | `SUPPLEMENTARY_CSV_MAX_ROWS` | New |
| `full_text_fetcher.py:213-214` (approx) | 2 sheet Excel limit | `SUPPLEMENTARY_EXCEL_MAX_SHEETS` | New |
| `full_text_fetcher.py:230` (approx) | 10 file ZIP limit | `SUPPLEMENTARY_ZIP_MAX_FILES` | New |

**Note:** Line numbers marked `(approx)` come from the exploration phase and should be verified against current code before filing config-flag work. Use `grep -n` to confirm.

---

## Section 6 — Race Conditions & Concurrency

### 6.1 Parallel polling loop dict mutation windows
`pipeline_orchestrator.py:1065-1198` — The loop modifies `in_flight` from multiple branches (newly_done, timed_out, restart). Snapshot iteration (`list(in_flight.items())`) mitigates but doesn't eliminate the issue.

### 6.2 Sequential mode timeout detection lag
`pipeline_orchestrator.py:1244-1249` — Up to 200ms lag between timeout expiry and detection due to polling interval.

### 6.3 Worker pool `join(timeout=10)` can leak processes
`pipeline_orchestrator.py:1170,1267,1351` — If all 4 workers take >10s to die (possible if they're stuck in an uninterruptible system call), `join` returns but the zombie processes remain. On a long run with multiple restarts, zombies accumulate.

### 6.4 RESULT line delivered after cancel status set
`python-bridge.ts:159-161` — See 1.9.

### 6.5 PROGRESS stats still increment after cancel
`python-bridge.ts:119-125,234` — Python may emit a final PROGRESS line after receiving SIGTERM but before exit. The bridge processes it and increments `stats.gemini_api_calls`, even though the job is cancelled.

---

## Section 7 — Missing Validation Gates

| File:function | Missing check | Consequence |
|---|---|---|
| `pipeline_orchestrator.py:_prepare_paper_inputs` | No check that `content_dict[pmid]` has "content" key before `.get("content", "")` | Empty paper_text triggers minimal row, no log |
| `pipeline_orchestrator.py:_run_pipeline_worker` | Worker args not validated before pickle | OOM/hang if figure_inputs or paper_text exceed memory |
| `gene_validator.py:resolve_gene_symbol` | No biotype cross-check | Pseudogenes pass validation |
| `gene_validator.py:validate_gene_variant` | Regex patterns compiled at init but never self-tested | Regex bugs surface mid-run |
| `full_text_fetcher.py:_extract_text_and_figures_from_pmc_xml` | XML parse error returns `(None, [], [])` | Indistinguishable from valid-empty |
| `pubmed_data_collector.py:fetch_paper_details` | No check that response is MEDLINE format | HTML error pages parsed by `Medline.parse()` |

---

## Section 8 — Multiprocessing Pickling Hazards

### 8.1 `GeneInfoPipeline` state pickled across process boundary
`pipeline_orchestrator.py:109-141` — Worker args include raw text, columns, figure bytes. `GeneInfoPipeline` holds regex compilations. Pickling validates nothing at submit time; errors only surface when the child process tries to rebuild the object.

### 8.2 Figure bytes pickling cost
`pipeline_orchestrator.py:1045-1055` — Figure inputs include base64-encoded image bytes. Multi-panel figures at high resolution can exceed 5 MB per figure × 3 figures per paper = 15 MB per submit. On a 32-bit Python build, pickle limits become relevant.

### 8.3 In-flight context accumulation after pool restart
`pipeline_orchestrator.py:1056,1188` — After pool restart, in_flight dict entries are replaced but `ctx` objects are retained via closure. Long runs with multiple restarts accumulate memory.

---

## Section 9 — How to Verify a Fix

### Unit tests
Location: `python/tests/test_*.py`

Run: `cd python && source .venv/bin/activate && python -m pytest -v`

Expected: 65/65 pass. If you add a fix, add a test that *would have failed before the fix*.

### Integration tests
Location: `python/tests/test_pipeline_integration.py`

Run: `cd python && source .venv/bin/activate && python -m pytest tests/test_pipeline_integration.py -v`

Expected: 11/11 pass. These run the full pipeline on cached fixtures; they catch regressions but not all edge cases.

### Smoke test
Run: `/verify` (project slash command)

What it does: TS typecheck + Python module imports + a minimal extraction test.

### Benchmark
Location: `python/scripts/benchmark_runner.py`

Run: `python scripts/benchmark_runner.py --pmids 17463248`

Use this to measure precision/recall impact of a fix on a single known-good paper before running the full 24-paper sweep.

### Manual verification
For finding 1.6 (hardcoded citation threshold): run `benchmark_runner.py` with `CITATION_MATCH_RATIO_THRESHOLD` at 0.70, 0.80, 0.85, 0.90 and plot the precision/recall curve.

For finding 2.2 (circuit breaker): use a fixture-backed HGNC 503 response path and verify the pipeline does not stall.

---

## Cross-References

- **Architecture overview:** [`internals.md` Part 1](./internals.md#part-1--architecture-overview)
- **Stage 5 (Gemini) deep dive:** [`internals.md` Part 7](./internals.md#part-7--stage-5-gemini-extraction)
- **Config flag reference:** [`internals.md` Part 10](./internals.md#part-10--configuration-flag-reference)
- **Historical bugs:** [`AUDIT.md`](../audit/AUDIT.md)
- **Project rules:** [`AGENTS.md`](../../AGENTS.md)

---

## Next Actions (if you want to triage now)

Start with these in order:

1. **1.6 + 1.7** — Hardcoded citation thresholds. Easiest to fix; makes the next two easier to debug.
2. **1.4** — Variant dedup loss. Small fix, affects confidence tiers directly.
3. **1.2 + 1.3** — Pool restart bugs. Parallel mode is new feature; fix before it ships widely.
4. **1.1** — Worker error swallowing. Improves observability for everything else.
5. **1.8 + 1.9 + 1.10** — Trust boundary bugs in the bridge and grounding check.

Skip for now:
- Section 2 (SUSPECT) — only if you have time or get a reproducer
- Section 5 (hardcoded constants) — file as a config cleanup sprint
- Section 8 (pickling hazards) — only matters for parallel mode with large papers
