# Pipeline Internals — Deep Technical Reference

> **Status.** Maintainer technical notes, not the canonical architecture contract.
> Use [`pipeline-contract.md`](./pipeline-contract.md) as the source of truth for current pipeline domains, boundaries, and invariants.
>
> **Purpose.** Function-level deep dive into the ResearchShop extraction pipeline. Read this to understand historical state flow, implementation details, and places where failures can be silent. Some line numbers and architecture narrative may lag behind the active contract.
>
> **Companion docs:**
> - [`pipeline-contract.md`](./pipeline-contract.md) — canonical architecture source.
> - [`bug-hunting.md`](./bug-hunting.md) — actionable audit cheatsheet. This doc tells you how the code works; that one tells you where it's suspect.
> - [`../../.codex/rules/memory-pipeline.md`](../../.codex/rules/memory-pipeline.md) — domain-level overview for Codex sessions. This doc goes deeper.
> - [`../audit/AUDIT.md`](../audit/AUDIT.md) — historical bug log.
> - [`../../AGENTS.md`](../../AGENTS.md) — project routing file.

---

## Table of Contents

- [Part 0 — How to Read This Doc](#part-0--how-to-read-this-doc)
- [Part 1 — Architecture Overview](#part-1--architecture-overview)
- [Part 2 — Entry Points](#part-2--entry-points)
- [Part 3 — `paper_selection`: PubMed Search & Citation Ranking](#part-3--paper_selection-pubmed-search--citation-ranking)
- [Part 4 — `paper_selection`: Gene Relevance Scoring](#part-4--paper_selection-gene-relevance-scoring)
- [Part 5 — `paper_reading`: Full-Text Fetch](#part-5--paper_reading-full-text-fetch)
- [Part 6 — `candidate_discovery`: PubTator NER](#part-6--candidate_discovery-pubtator-ner)
- [Part 7 — Per-Paper Analysis Package](#part-7--per-paper-analysis-package)
- [Part 8 — `validation`: Gene Validation](#part-8--validation-gene-validation)
- [Part 9 — `output_writing`: Orchestration And Output Writing](#part-9--output_writing-orchestration-and-output-writing)
- [Part 10 — Configuration Flag Reference](#part-10--configuration-flag-reference)
- [Part 11 — Data Contracts Between Domains](#part-11--data-contracts-between-domains)
- [Part 12 — State Lifecycle](#part-12--state-lifecycle)
- [Part 13 — Prompt Engineering](#part-13--prompt-engineering)

---

## Part 0 — How to Read This Doc

**The pipeline in one sentence.** User selects PubMed papers in the Electron UI → main process spawns a Python subprocess → Python fetches full text, runs NER + LLM extraction + validation → writes CSV/Excel/JSON artifacts → main process reads the RESULT line and persists artifact paths in SQLite.

**Where it starts.** `pipeline/run_pipeline.py` (spawned by `app/src/main/python-bridge.ts`).
**Where it ends.** A multi-file artifact bundle under `data/output/` plus a row in `jobs.db`.

**Main invariants** (things the pipeline assumes but does not always enforce):
1. Every paper processed by `PaperAnalysisPipeline` is independent. No cross-paper state.
2. Secrets flow only via environment variables, never CLI args.
3. Every gene that reaches the CSV has `validation_confidence >= FINAL_VALIDATION_MIN_CONFIDENCE` (default 0.7) UNLESS `ENABLE_STRICT_VALIDATION_GATE=False`.
4. Every gene that reaches the CSV has been grounded in the paper text UNLESS `ENABLE_GROUNDING_CHECK=False`.
5. Every LLM call has `thinking_budget=0` to avoid preview-model hangs (C20).

**Navigation.** Use Ctrl+F on section titles. Every function reference uses `file:line` — paste into a terminal as `$EDITOR file:line` (VS Code, Sublime, etc.) to jump directly.

**Code snippets.** All code blocks are real excerpts from current source, not pseudocode. The first line is a comment with `file:line`. Some snippets are abbreviated with `...` — check the referenced lines for the full version.

---

## Part 1 — Architecture Overview

> **Canonical source:** [`pipeline-contract.md`](./pipeline-contract.md). The diagram below is retained as a useful implementation snapshot, but architecture changes should be made against the contract and then reflected here only where the technical notes remain useful.

### The 7 domains

```
User types query in UI (renderer)
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ paper_selection: PubMed search                       │
│ pubmed_data_collector.py                             │
│ → Entrez query + iCite citation ranking              │
│ → OA query constraint when enabled                   │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ paper_selection: Gene relevance scoring (UI-side)    │
│ geneRelevanceScorer.ts (renderer)                    │
│ → User sees relevance badges in paper selection      │
│ → User clicks "Add to Pipeline"                      │
└──────────────────────────────────────────────────────┘
       │  (IPC: pipeline:start)
       ▼
┌──────────────────────────────────────────────────────┐
│ python-bridge.ts spawns Python subprocess           │
│ env: GEMINI_API_KEY, ENTREZ_EMAIL, PARALLEL_ANALYSIS │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ run_pipeline.py                                      │
│ → parse args, emit PROGRESS/LOG/RESULT to stdout     │
│ → invoke pipeline_orchestrator.run_complete_pipeline │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ paper_reading: Full-text fetch                       │
│ full_text_fetcher.py                                 │
│ → PMC JATS XML primary → Europe PMC fallback         │
│ → pubmed_parser adapter for paragraphs + figures     │
│ → Parse sections, figures, tables                    │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ candidate_discovery: PubTator NER                    │
│ pubtator_tool.py                                     │
│ → Batch API calls (10 PMIDs each)                    │
│ → High-precision gene symbols (precision floor)      │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ candidate_discovery + detail_extraction + validation │
│ Per-paper extraction (worker pool)                   │
│ paper_analysis.pipeline.PaperAnalysisPipeline        │
│ → Abstract + 2-pass full-text + figures + PubTator   │
│ → Grounding check → gene validation → detail extract │
│ → Strict gate → citation validation → evidence gate  │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ validation: Gene validation                          │
│ gene_validator.py                                    │
│ → HGNC local → HGNC API → MyGene.info → fuzzy        │
│ → Citation validation (dense match + encoding norm)  │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ output_writing: Orchestration & CSV output           │
│ pipeline_orchestrator.py                             │
│ → Aggregate worker results                           │
│ → Compute HIGH/MEDIUM/LOW/REVIEW confidence tiers    │
│ → Deduplicate by (gene, pmid)                        │
│ → Write primary CSV + metadata CSV + Excel + JSON    │
│ → Emit RESULT line                                   │
└──────────────────────────────────────────────────────┘
       │  (RESULT line)
       ▼
┌──────────────────────────────────────────────────────┐
│ python-bridge.ts parses RESULT                       │
│ → persist artifact paths in jobs.db                  │
│ → IPC broadcast to renderer                          │
│ → renderer navigates to Results page                 │
└──────────────────────────────────────────────────────┘
```

### Two process models

**Sequential (default).** One paper at a time. Worker pool exists but only one `apply_async` is in flight. Safer for free-tier Gemini keys (15 RPM limit).

**Parallel (`PARALLEL_ANALYSIS=true`).** Multiple papers in flight. Pool size from `AI_WORKER_POOL_SIZE` (default 2, max 4). Workers share the Gemini API quota. Faster for paid keys.

The sequential/parallel branching is in `pipeline_orchestrator.py` around line 988 — `if config.PARALLEL_ANALYSIS:`.

### Three trust tiers

1. **PubTator (precision floor).** Biomedical NER, high precision, lower recall. Genes it finds are almost certainly real.
2. **Gemini (recall ceiling).** LLM extraction, high recall, lower precision. Can hallucinate. Guarded by grounding check + confidence gate + evidence gate.
3. **Gene Validator (final gate).** HGNC + remote APIs + fuzzy match. Determines `validation_confidence`, which gates whether a row reaches the CSV.

Everything in the pipeline is a tension between these three. The safeguards (grounding check, strict gate, evidence gate) exist to keep the LLM's recall from turning into hallucination.

### What breaks if a domain is removed

- **No `paper_selection`:** obvious, nothing to process.
- **No UI relevance scoring inside `paper_selection`:** users submit irrelevant papers, wasting Gemini quota.
- **No `paper_reading`:** no extraction-ready full text; the run can only emit metadata-only rows.
- **No PubTator inside `candidate_discovery`:** precision floor removed. LLM-only output; hallucination risk up.
- **No `detail_extraction`:** no user-defined fields, just a candidate gene list.
- **No `validation`:** invalid/misspelled genes reach output.
- **No `output_writing`:** no CSV, no aggregation, no confidence tiers.

---

## Part 2 — Entry Points

### 2.1 `pipeline/run_pipeline.py` — CLI entry

Entire file is 74 lines. Reading it gives you the full shape of the Python entry point.

```python
# run_pipeline.py:12
def main():
    parser = argparse.ArgumentParser(description='ResearchShop Pipeline')
    parser.add_argument('--query', type=str, default='')
    parser.add_argument('--pmids', type=str, default='[]', help='JSON array of PMIDs')
    parser.add_argument('--authors', type=str, default='[]', help='JSON array of author names')
    parser.add_argument('--columns', type=str, default='{}', help='JSON object of column name->description')
    parser.add_argument('--top-n', type=int, default=10)
    parser.add_argument('--output-dir', type=str, required=True)
    args = parser.parse_args()
```

**Secrets via env only.** `run_pipeline.py:24-32`:

```python
# run_pipeline.py:24
gemini_api_key = os.environ.get('GEMINI_API_KEY', '').strip()
entrez_email = os.environ.get('ENTREZ_EMAIL', '').strip()

if not gemini_api_key:
    print('RESULT:' + json.dumps({'error': 'GEMINI_API_KEY environment variable is not set'}), flush=True)
    sys.exit(1)
if not entrez_email:
    print('RESULT:' + json.dumps({'error': 'ENTREZ_EMAIL environment variable is not set'}), flush=True)
    sys.exit(1)
```

Note: these checks are on the secrets at the very start. If either is missing, the pipeline emits a RESULT line and exits with code 1. The bridge parses the RESULT line and marks the job failed.

**Emit protocol.** `run_pipeline.py:46-52`:

```python
# run_pipeline.py:46
def progress_callback(stage, pct, stats):
    msg = json.dumps({"stage": stage, "percent": pct, "stats": stats})
    print(f"PROGRESS:{msg}", flush=True)

def log_callback(level, msg, detail=None):
    payload = json.dumps({"level": level, "msg": msg, "detail": detail})
    print(f"LOG:{payload}", flush=True)
```

All three message types (`PROGRESS:`, `LOG:`, `RESULT:`) are newline-delimited JSON with a type prefix. Python always uses `flush=True` to ensure the bridge sees complete lines.

**Result handling.** `run_pipeline.py:54-70`:

```python
# run_pipeline.py:54
try:
    result = run_complete_pipeline(
        query=args.query,
        specific_pmids=pmids,
        specific_authors=authors,
        user_columns=columns,
        top_n_cited=args.top_n,
        progress_callback=progress_callback,
        log_callback=log_callback,
    )
    if result:
        print(f"RESULT:{json.dumps(result)}", flush=True)
    else:
        print(f"RESULT:{json.dumps({'error': 'No results produced'})}", flush=True)
except Exception as e:
    print(f"RESULT:{json.dumps({'error': str(e)})}", flush=True)
    sys.exit(1)
```

The RESULT dict (when successful) contains `local_path`, `metadata_path`, `excel_path`, `json_path`, and `debug_path`. See [`pipeline_orchestrator.py:1363-1369`](#part-9--output_writing-orchestration-and-output-writing).

### 2.2 `app/src/main/python-bridge.ts` — Electron side

**Type guards.** `python-bridge.ts:18-27`:

```typescript
// python-bridge.ts:18
// Payload type guards for Python stdout protocol
function isProgressPayload(p: unknown): p is { stage: string; percent: number; stats: Record<string, number> } {
  return typeof p === 'object' && p !== null && 'stage' in p && 'percent' in p
}
function isLogPayload(p: unknown): p is { level: string; msg: string; detail?: string | null } {
  return typeof p === 'object' && p !== null && 'level' in p && 'msg' in p
}
function isResultPayload(p: unknown): p is { local_path?: string; metadata_path?: string; excel_path?: string; json_path?: string; error?: string } {
  return typeof p === 'object' && p !== null
}
```

> **⚠️ See [`bug-hunting.md` §1.8](./bug-hunting.md#18-isresultpayload-accepts-any-object)** — the RESULT guard is too permissive. It accepts `{}` as a valid result.

**Spawn.** `python-bridge.ts:63-99`:

```typescript
// python-bridge.ts:63
export function startPipeline(jobId: string, args: PipelineArgs): void {
  const settings = getSettings()
  const pythonPath = getPythonPath()
  const pythonDir = getPythonDir()
  const scriptPath = join(pythonDir, 'run_pipeline.py')
  ...
  currentProcess = spawn(pythonPath, spawnArgs, {
    cwd: pythonDir,
    env: {
      ...process.env,
      GEMINI_API_KEY: settings.geminiApiKey,
      ENTREZ_EMAIL: settings.entrezEmail,
      PARALLEL_ANALYSIS: settings.parallelAnalysis ? 'true' : 'false',
    }
  })
  updateJob(jobId, {
    status: 'running',
    error: null,
    completed_at: null
  })
```

**Stdout parsing.** `python-bridge.ts:104-184`. Three branches:

- `PROGRESS:` lines (line 111) → extract `stats.gemini_api_calls`, compute delta, write to usage store, broadcast to renderer.
- `LOG:` lines (line 135) → enrich with timestamp, broadcast to renderer.
- `RESULT:` lines (line 152) → if cancelled, drop. If error, mark job failed. Otherwise, persist `local_path`, `metadata_path`, `excel_path`, `json_path` and mark completed.

**Cancellation.** `python-bridge.ts:231-242`:

```typescript
// python-bridge.ts:231
export function cancelPipeline(): boolean {
  if (currentProcess) {
    if (currentJobId) {
      updateJob(currentJobId, {
        status: 'cancelled',
        completed_at: new Date().toISOString()
      })
    }
    return currentProcess.kill('SIGTERM')
  }
  return false
}
```

The bridge stays single-flight until the child process actually emits `close` or `error`. `currentProcess` and `currentJobId` are NOT cleared here — they're cleared in the `close` handler at line 210-211. This prevents a new run from starting while the old process is still draining (see [`AUDIT.md` C23 §2026-04-07](../audit/AUDIT.md)).

### 2.3 `app/src/main/ipc-handlers.ts` — Pipeline IPC

The pipeline-related handlers are:
- `pipeline:start` → calls `startPipeline(jobId, args)` from python-bridge
- `pipeline:cancel` → calls `cancelPipeline()`
- `gemini:getDailyUsage` → reads from usage-store
- `results:load` → reads a CSV file, applies `validateOutputPath()` sandboxing

### 2.4 `src/preload/index.ts` — Typed IPC boundary

The preload exposes `window.api.pipeline.*` methods matching the handlers above. Every IPC call is type-checked against the `ElectronAPI` interface at line 15+.

### 2.5 IPC Protocol Contract

| Message | Format | Required fields | Optional fields |
|---|---|---|---|
| PROGRESS | `PROGRESS:{"stage": str, "percent": int, "stats": {...}}\n` | stage, percent | stats.gemini_api_calls, stats.papers_analyzed, stats.genes_extracted |
| LOG | `LOG:{"level": str, "msg": str, "detail": str\|null}\n` | level, msg | detail |
| RESULT | `RESULT:{"local_path"?: str, "metadata_path"?: str, "excel_path"?: str, "json_path"?: str, "error"?: str}\n` | — (none enforced) | all of the above |

**Gotcha:** Python always uses `flush=True` on print calls. If you add a new emit point, don't forget the flush — otherwise lines can buffer and the bridge will see them out of order or truncated.

---

## Part 3 — `paper_selection`: PubMed Search & Citation Ranking

### 3.1 Module: `pubmed_data_collector.py`

**Primary entry:** `collect_papers_from_query()` (check line numbers with grep; file is 457 lines).

**Flow:**
1. Build Entrez query, append OA filter if enabled.
2. `search_pubmed()` → returns list of PMIDs.
3. `fetch_paper_details()` → batches PMIDs, fetches Medline records.
4. `fetch_citation_counts_with_fallback()` → iCite primary, Semantic Scholar fallback.
5. Sort by citation count, return top-N.

### 3.2 OA filter

Appended to the Entrez query when `ENABLE_OA_FILTER=True` (config.py:23).
The annotation is `"loattrfull text[sb]"` which restricts results to papers with PMC full-text availability. This is a **pre-filter**: papers behind paywalls never reach the pipeline.

### 3.3 Citation ranking chain

**Primary: iCite (NIH).** Stable, batch API. Returns citation counts for PMIDs that iCite has indexed (NIH-published or NIH-funded).

**Fallback: Semantic Scholar.** Used for PMIDs that iCite doesn't have (older papers, non-NIH). One-at-a-time with 200ms sleep between calls.

> **⚠️ See [`bug-hunting.md` §2.4](./bug-hunting.md#24-semantic-scholar-per-pmid-rate-limit)** — for 1000+ unresolved PMIDs, the per-call sleep adds 3+ minutes.

### 3.4 Candidate widening (query-mode only)

`PUBMED_RELEVANT_COUNT=200` is the real candidate-widening mechanism. Query-mode runs pull
up to 200 candidate PMIDs from PubMed before citation ranking trims the pool to the user's
requested top-N. User-curated PMID lists are taken 1:1 — no widening is performed.

There is **no** "4× overfetch factor". `ANALYSIS_OVERFETCH_FACTOR` appeared in older docs and
in `config.py` but was never referenced anywhere in the pipeline (orphaned). The symbol was
removed in the `docs/audit/final-audit.md` F1 sweep; the 4× claim is a myth that should not be propagated.

The UI's 500-PMID cap (`TopicResultsModal.tsx`) is independent of this — it limits how many
search results the modal fetches/renders, not how many get analysed.

### 3.5 Failure modes

- **Entrez rate limit.** No explicit backoff; relies on `REQUEST_TIMEOUT=30` (config.py:52) to surface failures.
- **iCite outage.** Falls through to Semantic Scholar silently. If both fail, papers are unranked (random order from Entrez).
- **Malformed Medline records.** `Biopython.Medline.parse()` silently drops unparseable records. See [`bug-hunting.md` §2.7](./bug-hunting.md#27-medlineparse-silently-drops-malformed-records).

---

## Part 4 — `paper_selection`: Gene Relevance Scoring

### 4.1 UI-side scoring

Since 2026-03-02 this moved from the Python pipeline to the Electron renderer. The primary implementation is `app/src/renderer/utils/geneRelevanceScorer.ts`.

**Trigger point:** `TopicResultsModal.tsx` fetches abstracts via `pubmed:fetch-abstracts` IPC, then scores each paper client-side.

**Output:** `{ score, tier, geneSymbols, topKeywords, hasMolecularContext }`.

**Tiers:** high (≥10), medium (≥5), low (1–4), none (≤0).

**UI behaviour:**
- High/medium auto-selected
- Low/none hidden by default, toggleable via "Show all"
- Green "Gene content" badge for high-relevance
- Amber "Low relevance" badge for hidden papers when shown

### 4.2 Python screener is pass-through

`abstract_screener.py` still exists but `pipeline_orchestrator.py` only uses it for forensic logging. Every paper the user submits is passed through to the pipeline regardless of screener score. The Python screener is retained for:
1. Benchmarking (running the old screener against a gold standard)
2. Debug artifacts (`drop_debug_{hash}.json` records the score)

**Rationale:** genomics researchers hand-pick papers for analysis. Silent post-submission filtering is bad UX. The old behaviour (pre-2026-03-02) silently dropped papers the user had explicitly selected.

### 4.3 Molecular context precision gate

In `abstract_screener.py` and mirrored in `geneRelevanceScorer.ts`: papers with gene-like symbols (e.g., "IL6", "CRP") but no molecular terms (mutation, variant, sequencing, etc.) receive a penalty. This prevents clinical outcome papers that mention lab values from scoring as gene-relevant.

---

## Part 5 — `paper_reading`: Full-Text Fetch

### 5.1 Module: `full_text_fetcher.py` (1036 lines)

**Primary entry:** `fetch_full_texts()` or similar (grep for the exported function). Returns per-paper dict with sections, figures, tables.

### 5.2 Strategy chain

1. **PMC Entrez efetch** → structured JATS XML (preferred).
2. **Europe PMC fullTextXML** → fallback OA endpoint if `ENABLE_EUROPE_PMC_FALLBACK=True` (config.py:60).
3. **`pubmed_parser` adapter** → parses body paragraphs and figure metadata from the XML; ResearchShop's existing parser remains the fallback and still owns tables, supplementary files, cleaning, and output normalization.
3. **Supplementary files** → CSV/Excel/ZIP parsing if `ENABLE_SUPPLEMENTARY_EXTRACTION=True` (config.py:64). Max 3 files, 200 KB each.

### 5.3 Section parsing

JATS XML is parsed into text sections by combining ResearchShop's abstract/table/supplement handling with `pubmed_parser` body paragraph extraction. If the adapter returns no useful body text, the existing JATS traversal is used as fallback.

The section keys match `paper_analysis/context.py:ContextMixin._SECTION_HEADER_PATTERNS` so downstream truncation can drop sections by name.

### 5.4 Figure extraction

- PMC figure captions/labels/graphic refs parsed with `pubmed_parser`; ResearchShop still builds URL candidates, resolves PMC CDN fallbacks, and downloads images
- Image downloaded if `ENABLE_FIGURE_ANALYSIS=True` (default false)
- Capped at `FIGURE_MAX_IMAGES_PER_PAPER=1` by default
- Max bytes per image: `FIGURE_IMAGE_MAX_BYTES=5MB` (config.py:72)

> **⚠️ See [`bug-hunting.md` §2.3](./bug-hunting.md#23-figure-url-dedup-loses-multi-panel-figure-detail)** — multi-panel figures (1A, 1B, 1C) that share a URL get deduped to a single entry.

### 5.5 Greek letter transliteration (W1 fix)

Pre-W1 bug: non-ASCII characters were stripped, destroying Greek letters in variant strings (α-globin, β-thalassemia). W1 fix transliterates α→alpha, β→beta, γ→gamma, etc. Lives inside the JATS XML text extraction path.

### 5.6 OA-only by design

No paywall bypass, no Playwright. Paywalled papers are excluded from extraction; if no OA full text can be fetched, the run emits metadata-only rows. This is intentional:
1. Legal clarity (no TOS violation)
2. Reliability (no flaky browser automation)
3. Explicit user consent (they know what the tool can and cannot fetch)

Query-mode widening (`PUBMED_RELEVANT_COUNT=200`, see §3.4) partially compensates for the loss by giving citation ranking a larger candidate pool to pick top-$N$ from.

### 5.7 Failure modes

- **PMC JATS 404.** Falls through to Europe PMC. If both fail, the paper has no extraction-ready full text.
- **Section parsing failure.** Returns raw concatenated text, losing structural signals (can't drop sections by priority).
- **JATS parse error.** Returns `(None, [], [])` — indistinguishable from valid-but-empty. See [`bug-hunting.md` §3.3](./bug-hunting.md#33-jats-xml-parser-conflates-invalid-xml-with-empty-article).

---

## Part 6 — `candidate_discovery`: PubTator NER

### 6.1 Module: `pubtator_tool.py` (620 lines)

**Primary entry:** `extract_from_pmids(pmids: List[str]) -> Dict[str, Tuple[List[PubTatorGene], List[PubTatorVariant]]]`.

### 6.2 Batching

Default batch size: `PUBTATOR_BATCH_SIZE=10` (config.py:93). Each batch hits the PubTator3 BioC API:

`https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids=...`

### 6.3 Silent batch loss (W10)

Parse errors on individual papers in a batch are silently skipped. Affected PMIDs produce no PubTator results but the pipeline continues. This is documented in `docs/audit/AUDIT.md` as a known, accepted limitation.

### 6.4 Role in hybrid architecture

PubTator provides the precision floor:
- Genes it finds get source label `pubtator`
- LLM can add more genes with source `llm_text`, `llm_abstract`, `llm_figure`
- Genes found by BOTH get source `both` (highest trust)
- The `_compute_row_confidence` function uses `Gene Source == "both"` as a precondition for HIGH tier

### 6.5 NCBI Gene enrichment

`ENABLE_NCBI_ENRICHMENT=True` (config.py:96). After extraction, each gene is enriched with NCBI Gene metadata (full name, chromosome, aliases). Optional but default-on.

### 6.6 Failure modes

- **PubTator API 503.** Pipeline continues with LLM-only extraction (lower precision).
- **Response schema change.** Multi-field PMID extraction fallback means schema changes cause silent data loss. See [`bug-hunting.md` §3.4](./bug-hunting.md#34-pubtator-pmid-extraction-tries-multiple-response-fields).

---

## Part 7 — Per-Paper Analysis Package

### 7.1 Package: `pipeline/modules/paper_analysis/`

This package owns the per-paper extraction flow. `pipeline/modules/gemini_extractor.py` remains only as
a backward-compatible shim exporting legacy aliases to `PaperAnalysisPipeline`.

### 7.2 Class lifecycle

```python
# paper_analysis/pipeline.py:PaperAnalysisPipeline.__init__
def __init__(self, paper_text, abstract_text="", pubtator_genes=None, figure_inputs=None, table_inputs=None):
    self.paper_text = paper_text              # mutable; truncated by context validation
    self.original_paper_text = paper_text     # immutable backup
    self.abstract_text = abstract_text
    self.associations = []                    # list of {gene, variant} dicts
    self.candidate_meta = {}                  # key → provenance metadata
    ...
    self.client = genai.Client(api_key=config.GEMINI_API_KEY)
    self.gene_validator = GeneValidator()
    self.context_validator = ContextWindowValidator()
```

State lifecycle through one paper:
1. `__init__` — instance state set
2. `_validate_and_prepare_paper_text` — may truncate `self.paper_text`
3. `_run_candidate_discovery` — RESETS `candidate_meta`, `associations`, drops lists
4. `_run_grounding_check` — filters `self.associations` in place, mutates `candidate_meta[].validation_outcome`
5. `_run_validation_and_normalize` — replaces `self.associations`
6. `_run_detail_extraction` — produces `extracted_info` list (not stored on self)
7. `_run_post_validation` — returns DataFrame

**Important:** All domains above happen within a single `run_pipeline()` call. The worker pool creates a new `PaperAnalysisPipeline` instance per paper, so state never leaks across papers.

### 7.3 The `candidate_meta` dict

```python
# Key: (gene_upper, variant_upper) tuple
# Value:
{
    "gene": str,                           # canonical HGNC symbol
    "variant": str,                        # normalized variant string
    "sources": Set[str],                   # {"llm_text", "pubtator", "deterministic_lexicon", "llm_figure", "llm_abstract"}
    "normalization_applied": str,          # e.g. "BNP->NPPB (biomarker_resolution)"
    "raw_gene_labels": Set[str],           # original strings from extraction (for grounding)
    "validation_confidence": float,        # 0.0–1.0
    "validation_source": str,              # "hgnc_local", "hgnc_api", "mygene", "fuzzy", etc.
    "validation_outcome": str,             # "passed", "rejected_ungrounded", "rejected_low_confidence", etc.
}
```

This dict is the single source of truth for provenance. Every gate decision (grounding, validation, evidence) writes to `validation_outcome` so the debug artifact can explain why a candidate was dropped.

### 7.4 The 4 module-level prompt constants

Prompt constants live in `pipeline/modules/paper_analysis/prompts.py`:

- `_GENE_DISCOVERY_INSTRUCTION_ABSTRACT` (lines 25-42) — abstract-level discovery
- `_GENE_DISCOVERY_INSTRUCTION_FULLTEXT` (lines 44-59) — full-text discovery
- `_FIGURE_ANALYSIS_INSTRUCTION` (lines 61-68) — figure multimodal analysis
- `_DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS` (lines 70-86) — `detail_extraction` rules (9 accumulated rules)

**Do NOT change wording without evaluating hallucination impact.** Each rule exists for a specific failure mode (see Part 13).

### 7.5 The 4 LLM extraction methods

#### 7.5.1 `extract_gene_names_from_abstract()` (lines ~645-750)

Abstract-only pass. Cheap, runs before full-text extraction.

- Max 2 retries
- Retry delay: 3 seconds
- Response format: JSON schema with `associations: [{gene, variant}]`
- Output merged into `candidate_meta` with source `llm_abstract`

Used to catch natural-language gene references (e.g., abstract says "IL-6" while full text says "interleukin-6").

#### 7.5.2 `extract_gene_names()` (lines ~752-870)

Full-text pass. Runs TWICE in `_run_candidate_discovery`:
1. First call: `temperature=0.0` (greedy)
2. Second call: `temperature=0.4` (sampling)

**Why two passes.** Gemini inference is not bit-reproducible; two greedy passes often return identical sequences. Temperature=0.4 forces the model to sample from different completions, catching genes the greedy pass missed.

- Max 3 retries
- Exponential backoff: 5s → 10s → 20s
- Full text truncated to fit context window (see 7.9)

#### 7.5.3 `extract_gene_names_from_figures()` (lines ~973-1167)

Multimodal. One LLM call per figure (capped at `FIGURE_MAX_IMAGES_PER_PAPER=1` by default).

- Max 3 retries per figure
- Rate-limit aware: parses `retry-after` header from 429 responses
- Inter-call delay: `FIGURE_INTER_CALL_DELAY_SECONDS=4` (default)

Genes extracted here get source `llm_figure` and are subject to a lighter grounding check (figure caption text match) rather than the full prose grounding.

#### 7.5.4 `extract_gene_info()` (lines ~1169-1315)

`detail_extraction`. All validated candidates go into ONE LLM call.

- Prompt includes all user-defined columns with descriptions
- Prompt includes all validated gene-variant associations
- Prompt includes full paper text + optional structured tables
- Prompt ends with `_DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS` (the 9 rules)
- Max 3 retries, exponential backoff

**Gotcha.** Because all genes go in one prompt, the detail extraction can exceed the context window on gene-dense papers. The 80% threshold in `_validate_and_prepare_paper_text` tries to prevent this by truncating sections in priority order before `detail_extraction` runs.

### 7.6 The 5 run_pipeline sub-methods (post-refactor)

After the 2026-04-07 refactor (C24), `run_pipeline()` is a 25-line orchestrator:

```python
# paper_analysis/pipeline.py:PaperAnalysisPipeline.run_pipeline
def run_pipeline(self, column_descriptions):
    context_validation = self._validate_and_prepare_paper_text()
    if context_validation["failed"]:
        return pd.DataFrame()

    self._run_candidate_discovery()
    self._run_grounding_check()
    self._run_validation_and_normalize()

    extracted_info = self._run_detail_extraction(column_descriptions)
    if not extracted_info:
        return pd.DataFrame()

    df = pd.DataFrame(extracted_info)
    if "variant_name" in df.columns:
        df["variant_name"] = df["variant_name"].apply(self._normalize_variant_value)
    return self._run_post_validation(df, column_descriptions, context_validation)
```

#### 7.6.1 `_run_candidate_discovery()` (~line 1361)

`candidate_discovery`. Resets state and runs all discovery sources:
1. Reset `candidate_meta`, `dropped_candidates`, `strict_gate_drops`, `evidence_gate_drops`, `associations`
2. Abstract discovery (`extract_gene_names_from_abstract`) if enabled
3. Full-text pass 1 at temperature=0.0
4. Full-text pass 2 at temperature=0.4 (wrapped in try/except — failures don't abort)
5. Deterministic lexicon extraction (HGNC symbol regex)
6. Figure analysis if `ENABLE_FIGURE_ANALYSIS`
7. PubTator merge (union with existing candidates)

#### 7.6.2 `_run_grounding_check()` (~line 1430)

`validation` grounding gate. Two paths:
- `sources == {"llm_figure"}` → light check: search figure captions for the gene name
- Otherwise → full prose grounding via `_find_evidence_snippet`

Genes not grounded are marked `validation_outcome = "rejected_ungrounded"` and dropped from `self.associations`.

> **⚠️ See [`bug-hunting.md` §1.10](./bug-hunting.md#110-grounding-check-can-be-bypassed-for-mixed-source-figure-genes)** — genes with both `llm_figure` and other sources bypass the figure-specific check.

#### 7.6.3 `_run_validation_and_normalize()` (~line 1504)

`validation`. Runs `_apply_gene_validation_heuristics()` (which calls the gene validator), then normalizes to one gene-level row per gene.

Has a fallback path: if validation filters out all associations AND `ENABLE_STRICT_VALIDATION_GATE=False`, restores the pre-validation list. See [`bug-hunting.md` §2.6](./bug-hunting.md#26-validation-fallback-trusts-pre-validation-on-empty-result).

#### 7.6.4 `_run_detail_extraction()` (~line 1551)

`detail_extraction`. Calls `extract_gene_info()`, merges duplicate rows, generates fallback rows if extraction returned empty, runs evidence backfill.

**Fallback row logic:** if the LLM returned no rows but associations exist (e.g., all genes were in tables, no prose to extract), emit minimal `{gene_name, variant_name}` rows with empty user columns. Marks `detail_extraction_status = "association_only_fallback_no_rows"`.

#### 7.6.5 `_run_post_validation()` (~line 1597)

`validation`. Adds metadata columns, applies strict gate, citation validation, evidence gate, context metadata.

**Strict gate:** drops rows where `validation_confidence < FINAL_VALIDATION_MIN_CONFIDENCE` (default 0.7). Logs each drop to `strict_gate_drops` for the debug artifact.

**Citation validation:** adds `{col}_citation_valid` boolean columns for each user column. See [`_add_citation_validation_metadata`](#731-citation-validation).

**Evidence gate:** drops rows with insufficient non-empty evidence cells. Per-source thresholds:
- LLM sources: `EVIDENCE_MIN_NONEMPTY_CELLS_LLM_TEXT=0` (trusted)
- Deterministic: `EVIDENCE_MIN_NONEMPTY_CELLS_DETERMINISTIC=1`
- Mixed: `EVIDENCE_MIN_NONEMPTY_CELLS=1`

### 7.7 Helper methods

| Method | Line | Purpose |
|---|---|---|
| `_ingest_associations` | ~541 | Merge new associations into `candidate_meta` with provenance tracking |
| `_candidate_terms_for_row` | ~206 | Build grounding lookup terms (canonical + HGNC aliases) |
| `_find_evidence_snippet` | ~246 | 240-char window fuzzy match in paper text |
| `_merge_duplicate_gene_rows` | ~284 | Collapse duplicate `detail_extraction` rows by (gene, variant) |
| `_backfill_sparse_row_evidence` | ~323 | Fill empty Key Finding rows with auto-snippets |
| `_apply_evidence_gate` | ~365 | Drop rows below per-source evidence thresholds |
| `_collect_debug_artifact` | ~434 | Build the drop_debug JSON blob |
| `_normalize_gene_symbol` | ~522 | Resolve raw label to canonical HGNC (with biomarker resolution) |
| `extract_deterministic_candidates` | ~596 | HGNC symbol regex matching, 120-candidate cap |

### 7.8 The grounding check deep dive

The grounding check is the primary hallucination filter. For each candidate:

1. If the gene was found ONLY by `llm_figure`: search figure captions for the gene name or its raw labels. Substring match, case insensitive, no word boundaries.

2. Otherwise: `_candidate_terms_for_row()` builds a list of search terms:
   - Canonical HGNC symbol
   - Up to 15 HGNC aliases + prev_symbols
   - Raw labels from the LLM (e.g., "BNP" for NPPB)
   
   Then `_find_evidence_snippet()` tries to find any of these terms in the paper text (within a 240-char window). If found: grounded. If not: dropped.

**Why raw labels matter.** When the LLM extracts "BNP" (a protein name), `_normalize_gene_symbol` resolves it to the gene symbol "NPPB". The paper mentions "BNP" but not "NPPB". If grounding checked only canonical symbols, NPPB would be dropped. Raw labels keep the original string in the search set.

### 7.9 Context window handling

**Entry:** `_validate_and_prepare_paper_text()` (~line 2068).

**Logic:**
1. Estimate token count from `self.paper_text`.
2. Compare to `GEMINI_FLASH_CONTEXT_LIMIT × CONTEXT_SAFETY_MARGIN` (0.8 × 1M = 800K).
3. If under threshold: return as-is.
4. If between 80% and 95%: drop sections in priority order until under 80%.
5. If still over 95%: set `self._context_warning` for the user-visible warning.

**Drop priority:** `["methods", "supplementary", "discussion", "conclusion", "introduction"]`. Abstract and results are never dropped.

**Section splitting:** `_split_paper_into_named_sections()` (line 2035). Post-C24 fix concatenates duplicate section keys instead of overwriting.

### 7.10 Figure pipeline

| Method | Purpose |
|---|---|
| `_build_gemini_image_part` (~872) | Wrap image bytes in Gemini SDK Part object |
| `_resolve_pmc_cdn_url` (~883) | Scrape PMC HTML for CDN blob URL fallback |
| `_fetch_figure_image` (~891) | Download with size/type safeguards |

The image bytes are pickled when the worker function is invoked. For large multi-panel figures, this can be >5 MB per figure.

### 7.11 Retry logic summary

| Method | Max retries | Initial delay | Backoff |
|---|---|---|---|
| `extract_gene_names_from_abstract` | 2 | 3s | none |
| `extract_gene_names` | 3 | 5s | ×2 exponential |
| `extract_gene_names_from_figures` | 3 | dynamic (retry-after header) | per-call delay |
| `extract_gene_info` | 3 | 5s | ×2 exponential |

All retries use `client.models.generate_content_stream()`. Streaming means partial responses on network issues; the retry logic reconstructs from fresh state (F1 fix).

---

## Part 8 — `validation`: Gene Validation

### 8.1 Module: `gene_validator.py` (1122 lines)

Two main classes: `GeneValidator` and `ContextWindowValidator`.

### 8.2 The 4 validation sources

`GeneValidator.resolve_gene_symbol(candidate)` tries sources in order:

1. **Local HGNC JSON** (44,943 genes bundled at `pipeline/data/reference/hgnc_genes.json`) — fast, offline.
2. **HGNC REST API** — authoritative for recent changes.
3. **MyGene.info** — comprehensive alias database.
4. **Fuzzy match** — suggests similar symbols for review.

Returns `(canonical_symbol, source_tag)` where source_tag is `"hgnc_local" | "hgnc_api" | "mygene_symbol" | "mygene_alias" | "unresolved"`.

LRU cached with `maxsize=5000` at line ~141.

> **⚠️ See [`bug-hunting.md` §2.2](./bug-hunting.md#22-hgnc-api-fallback-has-no-circuit-breaker)** — no circuit breaker on HGNC API failures.

### 8.3 `get_gene_biotype()`

Returns HGNC `locus_type` for a resolved symbol. Still populated even though biotype filtering was removed 2026-04-08 — the column is informational.

### 8.4 Citation validation

**Entry:** `validate_citations(df, user_cols)` around line 541.

Validates each `{col}_Citation` field exists in the paper text. Adds `{col}_citation_valid` boolean columns.

**Core matcher:** `_citation_exists_in_paper(citation, paper_text)` around line 655.

```python
# Pseudo-flow:
# 1. Normalize both strings (Unicode slashes, Greek letters, mu variants)
# 2. Tokenize into word lists
# 3. Slide a window across paper_words matching citation_words
# 4. For each window with >= 60% word overlap:
#      → run SequenceMatcher.ratio() for fine match
# 5. If best ratio >= 0.85: matched. Else: not matched.
# 6. If matched: verify gene context (gene symbol within ±1500 chars of match)
```

**Encoding normalization:** `_normalize_unicode_slashes()` handles:
- U+2044, U+2215, U+FF0F, U+29F8 (Unicode slash variants)
- LaTeX Greek commands (`\upmu`, `\alpha`, etc.)
- ASCII `mu ` prefix regex
- U+00B5 → μ unification

Applied to BOTH citation and paper text before matching (C22). Never normalize only one side.

**The 0.85 threshold** is hardcoded. See [`bug-hunting.md` §1.6](./bug-hunting.md#16-citation-match-threshold-hardcoded).

### 8.5 Variant patterns

12+ HGVS regex patterns for: amino acid substitution, coding variant, genomic variant, frameshift, splice site, indel, deletion, duplication, insertion, copy number, complex/fusion.

Compiled at module import. Not self-tested — a regex bug would only surface when a variant hits the pattern mid-run.

### 8.6 `ContextWindowValidator`

Estimates token count from paper text length. Rough heuristic: `tokens ≈ chars / 4`. Used by `_validate_and_prepare_paper_text` to check if truncation is needed.

Pre-W3 bug: token estimation was wildly wrong. Fixed to use a reasonable ratio.

### 8.7 Failure modes

- Local HGNC load failure → silent fallback to API. See [`bug-hunting.md` §4](./bug-hunting.md#section-4--silent-failure-modes-consolidated).
- HGNC API timeout → falls through to MyGene.
- MyGene timeout → returns `unresolved`.
- All sources fail → gene gets `validation_confidence=0.0`, dropped by strict gate.

---

## Part 9 — `output_writing`: Orchestration And Output Writing

### 9.1 Module: `pipeline_orchestrator.py` (1686 lines)

Main entry: `run_complete_pipeline()` around line 500+. Coordinates all domains, manages the worker pool, writes output artifacts.

### 9.2 `_compute_row_confidence()` — the full decision tree

```python
# pipeline_orchestrator.py:27-101
def _compute_row_confidence(row: dict, user_cols: list) -> tuple:
    # Guard: empty gene name is never a valid extraction
    if not str(row.get("Gene/Group", "") or "").strip():
        return "REVIEW", "No genes extracted"

    val_conf = float(row.get("validation_confidence", 0) or 0)
    gene_source = str(row.get("Gene Source", "") or "")
    candidate_source = str(row.get("Candidate Source", "") or "")
    context_mods = str(row.get("context_modifications", "") or "")
    has_full_text = "no_oa_full_text" not in context_mods

    # Citation signals — check all user columns
    any_valid = False
    any_false = False
    all_empty = True
    for col in user_cols:
        citation_text = str(row.get(f"{col} Citation", "") or "")
        if citation_text:
            all_empty = False
        valid_flag = row.get(f"{col}_citation_valid")
        if valid_flag is True:
            any_valid = True
        elif valid_flag is False:
            any_false = True

    is_figure_only = (
        "llm_figure" in candidate_source
        and "llm_text" not in candidate_source
        and "pubtator" not in candidate_source
        and "deterministic_lexicon" not in candidate_source
    )

    # REVIEW: citation mismatch or figure-only source
    if (any_false and not any_valid) or is_figure_only:
        return "REVIEW", ...

    # LOW: no full text or borderline confidence
    if not has_full_text:
        return "LOW", "Abstract only"
    if val_conf < 0.85:
        return "LOW", "Low confidence"

    # HIGH: corroborated by multiple sources AND verified citation
    if gene_source == "both" and any_valid:
        return "HIGH", ""

    # MEDIUM: default (passed gates, citation stochastic or absent)
    return "MEDIUM", ...
```

**The decision tree:**
1. Empty gene → REVIEW
2. Citation mismatch OR figure-only → REVIEW
3. No full text → LOW
4. `val_conf < 0.85` → LOW
5. Both sources (NER+LLM) AND valid citation → HIGH
6. Everything else → MEDIUM

> **⚠️ See [`bug-hunting.md` §2.1](./bug-hunting.md#21-high-confidence-tier-unreachable-if-val_conf--085)** — HIGH is unreachable for `val_conf < 0.85` even with dual source corroboration.

### 9.3 Worker pool

**Creation:** `mp.Pool(processes=pool_size)` where `pool_size = AI_WORKER_POOL_SIZE` (default 2, capped at 4).

**Persistent workers:** workers stay alive across papers. First paper pays the import cost; subsequent papers reuse the warm process.

**Worker function:** `_run_pipeline_worker(text, cols, pubtator_genes, figure_inputs, abstract_text, table_inputs)` around line 109.

```python
# pipeline_orchestrator.py:109
def _run_pipeline_worker(text, cols, pubtator_genes=None, figure_inputs=None, abstract_text=None, table_inputs=None):
    try:
        inst = PaperAnalysisPipeline(
            text,
            abstract_text=abstract_text or "",
            pubtator_genes=pubtator_genes,
            figure_inputs=figure_inputs,
            table_inputs=table_inputs,
        )
        df = inst.run_pipeline(cols)
        return {
            "records": df.to_dict(orient="records"),
            "debug": inst._collect_debug_artifact(),
            "gemini_api_calls": inst._paper_api_calls,
        }
    except Exception as e:
        import traceback
        logging.error(f"Pipeline worker error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}
```

Every worker invocation creates a fresh `PaperAnalysisPipeline` instance. No state leaks across papers.

### 9.4 Sequential mode

One `apply_async` in flight at a time. Polls `ready()` with 200ms sleep. Checks cancellation between polls.

> **⚠️ See [`bug-hunting.md` §2.8](./bug-hunting.md#28-sequential-mode-polling-loop-burns-cpu-on-slow-workers)** — 200ms detection lag per timeout.

### 9.5 Parallel mode

Multiple `apply_async` in flight. Main loop:

```python
# pipeline_orchestrator.py:1065
while in_flight:
    check_cancellation()

    newly_done = [
        pmid
        for pmid, info in list(in_flight.items())
        if info["async_result"].ready()
    ]
    timed_out = []
    for pmid, info in list(in_flight.items()):
        if pmid in newly_done:
            continue
        elapsed = time.time() - info["ctx"]["submitted_at"]
        if elapsed > config.AI_PER_PAPER_TIMEOUT_SECONDS:
            timed_out.append(pmid)

    if not newly_done and not timed_out:
        time.sleep(0.2)
        continue
    ...
```

Harvest ready results, handle timeouts (may trigger pool restart), submit next paper.

> **⚠️ See [`bug-hunting.md` §1.1, §1.2, §1.3](./bug-hunting.md#section-1--critical-findings)** — multiple critical bugs in this loop: silent error swallowing, timeout clock reset on restart, in-flight dict leaks.

### 9.6 Cancellation flow

**From the UI:** `pipeline:cancel` IPC → `cancelPipeline()` → `SIGTERM` to child.

**Inside Python:** the orchestrator calls `check_cancellation()` at strategic points. This function raises `JobCancelledException` when... actually, inspection shows the cancellation signal flows through a stop file or environment variable. Grep for the implementation.

**On cancel, mid-run:**
- Harvest any already-ready results (don't waste completed work)
- Write a partial CSV if possible (depends on the cancellation point)
- Emit `RESULT:{"error": "Cancelled by user"}` — bridge marks job cancelled

### 9.7 CSV output

**Primary entry:** `_write_split_output()` around line 217.

**Produces 4 artifacts:**
1. **Primary CSV** (`final_enriched_results_{uuid}.csv`) — user-facing columns + confidence
2. **Metadata CSV** — full diagnostic/validation columns for audit
3. **Excel workbook** — two sheets: Results + Metadata, with confidence color coding
4. **JSON file** — same data in structured format

The RESULT line returns all four paths as `local_path`, `metadata_path`, `excel_path`, `json_path`.

### 9.8 Deduplication

After extraction, duplicate rows (same gene, same PMID) are merged by `groupby(gene + pmid).agg(first)`. Variant names are merged into a semicolon-joined unique list.

> **⚠️ See [`bug-hunting.md` §1.4, §1.5](./bug-hunting.md#14-variant-dedup-aggregation-silently-loses-empty-variants)** — variant dedup loses empty variants, and the whole step is wrapped in a swallow-all try/except.

### 9.9 Final output schema

Columns in the primary CSV (typical):

| Column | Source | Notes |
|---|---|---|
| `Gene/Group` | canonical HGNC symbol | from validator |
| `Variant Name` | HGVS or empty | normalized |
| `{user_col}` | from `detail_extraction` | user-defined |
| `{user_col} Citation` | direct quote | verbatim |
| `validation_confidence` | 0.0–1.0 | from validator |
| `Confidence` | HIGH/MEDIUM/LOW/REVIEW | from `_compute_row_confidence` |
| `Confidence Note` | explanation | human-readable |
| `Gene Source` | pubtator/llm_text/both | for HIGH tier gate |
| `Candidate Source` | full source list | for figure-only detection |
| `Study Title`, `Authors`, `Publication Year`, `Journal Name`, `PMID` | metadata | from `paper_selection` |

---

## Part 10 — Configuration Flag Reference

All flags from `pipeline/modules/config.py`. Grouped by purpose.

### 10.1 API & auth

| Flag | Default | Purpose |
|---|---|---|
| `ENTREZ_EMAIL` | env | Required for NCBI Entrez |
| `GEMINI_API_KEY` | env | Required for Gemini |
| `ENTREZ_API_KEY` | env | Optional; raises NCBI rate limit |
| `NCBI_API_KEY` | env | Optional; for NCBI Gene enrichment |

### 10.2 PubMed search

| Flag | Default | Purpose |
|---|---|---|
| `PUBMED_SORT` | `"relevance"` | Entrez sort option |
| `PUBMED_RELEVANT_COUNT` | `200` | Max candidates before filtering |
| `ENABLE_OA_FILTER` | `True` | Restrict to OA papers |
| `ENABLE_PUBLICATION_TYPE_FILTER` | `True` | Exclude reviews, editorials, etc. |

### 10.3 Full-text fetching

| Flag | Default | Purpose |
|---|---|---|
| `ENABLE_EUROPE_PMC_FALLBACK` | `True` | Use Europe PMC if PMC JATS fails |
| `ENABLE_PLAYWRIGHT_FALLBACK` | `False` | **DEAD CODE** — removed in F5 |
| `ENABLE_SUPPLEMENTARY_EXTRACTION` | `True` | Parse supplementary CSV/Excel/ZIP |
| `SUPPLEMENTARY_MAX_FILES` | `3` | Cap on supplementary files per paper |
| `SUPPLEMENTARY_MAX_CHARS` | `200000` | Char limit per supplementary file |

### 10.4 `paper_selection` relevance scoring

| Flag | Default | Purpose |
|---|---|---|
| `ENABLE_ABSTRACT_SCREENING` | `True` | Pass-through mode (forensic logging only) |
| `ABSTRACT_SCREENING_THRESHOLD` | `5` | Retained for benchmark compatibility |

### 10.5 PubTator NER

| Flag | Default | Purpose |
|---|---|---|
| `ENABLE_PUBTATOR_EXTRACTION` | `True` | Run PubTator NER during `candidate_discovery` |
| `PUBTATOR_BATCH_SIZE` | `10` | PMIDs per API batch |
| `ENABLE_NCBI_ENRICHMENT` | `True` | Enrich with NCBI Gene metadata |

### 10.6 Gemini extraction

| Flag | Default | Purpose |
|---|---|---|
| `GEMINI_CONFIG["gene_extraction_model"]` | `"gemini-2.5-flash-lite"` | Candidate discovery model |
| `GEMINI_CONFIG["data_extraction_model"]` | `"gemini-2.5-flash-lite"` | Detail extraction model |
| `GEMINI_CONFIG["temperature"]` | `0.0` | Default sampling temperature |
| `ENABLE_ABSTRACT_GENE_DISCOVERY` | `False` | Optional abstract-only Gemini candidate discovery |
| `ENABLE_FIGURE_ANALYSIS` | `False` | Optional multimodal figure candidate discovery |
| `FIGURE_MAX_IMAGES_PER_PAPER` | `1` | Cap on figures per paper |
| `FIGURE_IMAGE_MAX_BYTES` | `5 MB` | Per-image size limit |

### 10.7 Hybrid pipeline gates

| Flag | Default | Purpose |
|---|---|---|
| `ENABLE_GROUNDING_CHECK` | `True` | Drop hallucinated genes |
| `ENABLE_DETERMINISTIC_CANDIDATES` | `True` | Run HGNC symbol regex extraction |
| `DETERMINISTIC_MAX_CANDIDATES` | `120` | Cap on deterministic extraction |
| `DETERMINISTIC_REQUIRE_CORROBORATION_FOR_GENE_ONLY` | `True` | Drop deterministic-only gene-only rows |
| `ENABLE_BIOMARKER_NORMALIZATION` | `True` | Resolve biomarker names to gene symbols |

### 10.8 Validation gates

| Flag | Default | Purpose |
|---|---|---|
| `ENABLE_GENE_VALIDATION` | `True` | Run HGNC validation |
| `GENE_VALIDATION_MIN_CONFIDENCE` | `0.4` | Early gate threshold |
| `ENABLE_STRICT_VALIDATION_GATE` | `True` | Drop low-confidence rows from final output |
| `FINAL_VALIDATION_MIN_CONFIDENCE` | `0.7` | **Medical accuracy threshold — do not lower** |
| `ENABLE_EVIDENCE_BACKFILL` | `True` | Auto-fill Key Finding from grounded snippets |
| `EVIDENCE_SNIPPET_MAX_CHARS` | `240` | Snippet window size |
| `ENABLE_STRICT_EVIDENCE_GATE` | `True` | Drop rows with insufficient evidence |
| `EVIDENCE_MIN_NONEMPTY_CELLS` | `1` | Default evidence threshold |
| `EVIDENCE_MIN_NONEMPTY_CELLS_LLM_TEXT` | `0` | LLM rows trusted without backfill |
| `EVIDENCE_MIN_NONEMPTY_CELLS_DETERMINISTIC` | `1` | Deterministic needs corroboration |

### 10.9 Citation validation

| Flag | Default | Purpose |
|---|---|---|
| `ENABLE_CITATION_VALIDATION` | `True` | Validate citations exist in paper |
| `CITATION_MIN_CONFIDENCE` | `0.7` | Threshold for valid citations |
| `CITATION_MIN_LENGTH` | `10` | Minimum citation length |
| `ENABLE_TABLE_CITATIONS` | `True` | Fallback to table-cell citations |
| `TABLE_MIN_DATA_CELLS` | `4` | Minimum cells for a "data" table |
| `TABLE_MAX_PER_PAPER` | `20` | Cap on tables included in prompt |

### 10.10 Context windows

| Flag | Default | Purpose |
|---|---|---|
| `GEMINI_FLASH_CONTEXT_LIMIT` | `1000000` | Flash model token limit |
| `GEMINI_PRO_CONTEXT_LIMIT` | `2000000` | Pro model token limit |
| `CONTEXT_SAFETY_MARGIN` | `0.8` | Use 80% of limit |
| `ENABLE_CONTEXT_CHECKING` | `True` | Validate context windows before LLM calls |

### 10.11 AI processing

| Flag | Default | Purpose |
|---|---|---|
| `AI_PER_PAPER_TIMEOUT_SECONDS` | `600` | Per-paper worker timeout |
| `AI_WORKER_POOL_SIZE` | `2` | Pool size, capped at 4 |
| `PARALLEL_ANALYSIS` | `False` | Enable in-flight parallel mode |

### 10.12 Forensic

| Flag | Default | Purpose |
|---|---|---|
| `ENABLE_FORENSIC_ARTIFACTS` | `True` | Write drop_debug JSON artifacts |
| `FORENSIC_INCLUDE_SCREENING` | `True` | Include screening decisions |
| `FORENSIC_INCLUDE_FETCH_OUTCOMES` | `True` | Include fetch outcomes |

---

## Part 11 — Data Contracts Between Domains

### 11.1 `paper_selection`: PubMed → UI scoring

**Object:** Per-paper dict:

```python
{
    "pmid": str,
    "title": str,
    "abstract": str,
    "authors": List[str],
    "journal": str,
    "doi": str,
    "year": int,
    "citation_count": int,
    "pmc": str,  # PMC ID if available
}
```

**Contract:** Non-enforced. Missing fields degrade gracefully (empty strings, zeros).

**Breakage point:** If `pmid` is missing or empty, the paper is silently dropped in the UI.

### 11.2 `paper_selection` → `paper_reading` (UI → Python pipeline)

**Object:** List of PMIDs passed via `--pmids` CLI arg (JSON string).

**Contract:** Every PMID must be a non-empty string of digits.

**Breakage point:** `json.loads(args.pmids)` will accept anything valid-JSON. Non-string entries cause downstream errors.

### 11.3 `paper_reading` → `candidate_discovery` (Full text → PubTator)

**Object:** `content_dict[pmid]` dict:

```python
{
    "content": str,              # full text
    "abstract": str,
    "sections": Dict[str, str],
    "figures": List[Dict],
    "tables": List[Dict],
    "fetch_outcome": str,        # "pmc_jats", "europe_pmc", "no_oa_full_text"
}
```

**Contract:** `content` key must exist. Empty string is OK only as a no-full-text signal; per-paper analysis will emit a metadata-only row instead of running extraction.

**Breakage point:** See [`bug-hunting.md` §7](./bug-hunting.md#section-7--missing-validation-gates) — `_prepare_paper_inputs` doesn't check for the `content` key.

### 11.4 `candidate_discovery` → `detail_extraction` (PubTator → Gemini)

**Object:** Arguments to `_run_pipeline_worker`:

```python
(
    text: str,                         # paper_text
    cols: Dict[str, str],              # user column descriptions
    pubtator_genes: List[str],         # symbols from PubTator
    figure_inputs: List[Dict],         # figure metadata with image bytes
    abstract_text: str,                # paper abstract
    table_inputs: List[Dict],          # structured tables
)
```

**Contract:** All arguments are picklable across multiprocessing boundary.

**Breakage point:** `figure_inputs` contains raw image bytes. Large multi-panel figures can blow the pickle buffer. See [`bug-hunting.md` §8.2](./bug-hunting.md#82-figure-bytes-pickling-cost).

### 11.5 Per-paper analysis → `output_writing` (Worker → Orchestrator)

**Object:** Worker return value:

```python
{
    "records": List[Dict],             # from df.to_dict(orient="records")
    "debug": Dict,                     # debug artifact
    "gemini_api_calls": int,           # usage count
}
```

Or on error:

```python
{"error": str}
```

**Contract:** Either `records` is present (success) or `error` is present (failure). Never both.

**Breakage point:** See [`bug-hunting.md` §1.1](./bug-hunting.md#11-parallel-mode-ready---gettimeout0-race-swallows-worker-errors) — the silent error wrapping can produce error payloads that look identical to real failures.

### 11.6 `output_writing` → Electron (Python → bridge)

**Object:** RESULT line JSON:

```python
{
    "local_path": str,             # primary CSV
    "metadata_path": str,          # metadata CSV
    "excel_path": str,             # Excel workbook
    "json_path": str,              # structured JSON
    "debug_path": str,             # drop_debug artifact
    # OR on error:
    "error": str,
}
```

**Contract:** Either success paths or error. The bridge's `isResultPayload` is too permissive (see [`bug-hunting.md` §1.8](./bug-hunting.md#18-isresultpayload-accepts-any-object)).

---

## Part 12 — State Lifecycle

### 12.1 `PaperAnalysisPipeline` instance state across one paper

```
__init__ called
   │
   ├─ paper_text = input
   ├─ candidate_meta = {}        (will be reset in _run_candidate_discovery)
   ├─ associations = []          (will be reset in _run_candidate_discovery)
   ├─ _paper_api_calls = 0       (incremented on each LLM call)
   ├─ client = genai.Client(...)
   └─ gene_validator = GeneValidator()
   │
run_pipeline called
   │
   ├─ _validate_and_prepare_paper_text
   │    └─ may truncate self.paper_text
   │
   ├─ _run_candidate_discovery
   │    ├─ RESET candidate_meta, associations, drops
   │    ├─ extract_gene_names_from_abstract → append to associations
   │    ├─ extract_gene_names (pass 1) → append
   │    ├─ extract_gene_names (pass 2, temp=0.4) → append
   │    ├─ extract_deterministic_candidates → append
   │    ├─ extract_gene_names_from_figures → append
   │    └─ merge PubTator genes → append
   │
   ├─ _run_grounding_check
   │    └─ filter associations in place; mutate candidate_meta validation_outcome
   │
   ├─ _run_validation_and_normalize
   │    ├─ _apply_gene_validation_heuristics → mutate associations
   │    ├─ fallback to pre_validation if all filtered out AND strict gate off
   │    └─ normalize to one gene-level row per gene
   │
   ├─ _run_detail_extraction (returns extracted_info, NOT stored on self)
   │    ├─ extract_gene_info → LLM call
   │    ├─ _merge_duplicate_gene_rows
   │    ├─ fallback rows if empty
   │    └─ _backfill_sparse_row_evidence
   │
   ├─ _run_post_validation (takes df, returns filtered df)
   │    ├─ _add_validation_metadata
   │    ├─ _add_candidate_provenance_metadata
   │    ├─ strict gate drops (append to strict_gate_drops)
   │    ├─ _add_citation_validation_metadata
   │    ├─ _apply_evidence_gate (append to evidence_gate_drops)
   │    └─ _add_context_metadata
   │
Worker returns
   │
   └─ {records, debug, gemini_api_calls}
      │
      └─ Instance garbage collected (no state persists to next paper)
```

### 12.2 Job state machine (Electron side)

```
┌────────┐    startPipeline    ┌────────┐
│ queued │ ─────────────────▶  │running │
└────────┘                     └────────┘
                                 │  │  │
                   RESULT (ok)   │  │  │ RESULT (error)
                                 ▼  │  ▼
                            ┌─────────┐   ┌────────┐
                            │completed│   │ failed │
                            └─────────┘   └────────┘
                                 ▲  ▲
                                 │  │
                            close(0) │
                                     │
              cancel → status='cancelled' → close(any)
                                     │
                                     ▼
                              ┌──────────┐
                              │cancelled │
                              └──────────┘
```

**Who transitions:**

| Transition | Trigger | Code location |
|---|---|---|
| `queued → running` | `startPipeline` after spawn | `python-bridge.ts:95-99` |
| `running → completed` | RESULT line, no error | `python-bridge.ts:169-176` |
| `running → failed` | RESULT line with error | `python-bridge.ts:162-168` |
| `running → failed` | close(code≠0) while status='running' | `python-bridge.ts:197-202` |
| `running → cancelled` | User clicks Cancel | `python-bridge.ts:234-237` |
| `cancelled → terminal` | close handler ensures completed_at | `python-bridge.ts:203-207` |

**Invariant:** Once a job reaches `cancelled`, the RESULT handler refuses to change it (line 158-160).

### 12.3 Multiprocessing isolation

Each worker is a separate OS process. No shared memory. Data flows via pickle across the process boundary:

- **In:** text, cols, pubtator_genes, figure_inputs, abstract_text, table_inputs
- **Out:** records (list of dicts), debug dict, gemini_api_calls int

Workers hold their own:
- `PaperAnalysisPipeline` instance (fresh per paper)
- `GeneValidator` instance (cached HGNC DB)
- `genai.Client` instance
- Python module imports

Shared (read-only):
- `config` module (all flags read from process env on import)
- `hgnc_genes.json` (each worker loads its own copy)

### 12.4 Worker pool restart

When a timeout fires:

1. Harvest any already-ready results from in-flight dict
2. Mark the timed-out paper as `kind=timeout` in ordered_results
3. `worker_pool.terminate()` — kills all workers
4. `worker_pool.join(timeout=10)` — waits for cleanup
5. `worker_pool = mp.Pool(processes=pool_size)` — new pool
6. Re-submit remaining in-flight papers to the new pool with `submitted_at = time.time()` (clock reset!)

See [`bug-hunting.md` §1.2](./bug-hunting.md#12-pool-restart-resets-per-paper-timeout-clock) — the clock reset can cause indefinite hangs on pathological papers.

---

## Part 13 — Prompt Engineering

### 13.1 The 4 prompt constants

All four live in `pipeline/modules/paper_analysis/prompts.py` as module-level constants.

### 13.2 `_GENE_DISCOVERY_INSTRUCTION_ABSTRACT` (lines 25-42)

Purpose: abstract-level gene discovery.

Key rules:
- Focus on HUMAN protein-coding genes
- Exclude model organism genes unless mapped to human orthologs
- Only include non-coding RNA genes if primary finding
- Use official HGNC symbols (e.g., IL6 not interleukin-6)
- **CRITICAL DISAMBIGUATION**: distinguish molecular-level gene study from clinical lab measurements

### 13.3 `_GENE_DISCOVERY_INSTRUCTION_FULLTEXT` (lines 44-59)

Purpose: full-text gene discovery.

Similar to abstract version but with:
- Added "growth factors, receptors" to the extraction targets
- Focuses on what's "discussed" rather than "mentioned"

### 13.4 `_FIGURE_ANALYSIS_INSTRUCTION` (lines 61-68)

Purpose: multimodal figure analysis.

Very short. Key constraint: "Do not guess genes that are not explicitly shown."

### 13.5 `_DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS` (lines 70-86)

Purpose: `detail_extraction`. The accumulated rules.

Each rule exists for a specific failure mode that was observed in production:

1. **Use exact values from Associations JSON** — prevent the LLM from inventing new gene names during `detail_extraction`
2. **Empty variant_name → empty string** — prevent "null"/"N/A" placeholders
3. **Each gene is INDEPENDENT** — prevents the LLM from leaving rows empty because "the same fact applies to gene A"
4. **One gene-only row per gene** — ensures every gene has a base row
5. **Variant rows: only variant-specific details** — prevents repetition
6. **Do NOT repeat sentences across variant rows of same gene** — de-repetition
7. **Citation format** — separate field
8. **No placeholder text** — empty string only
9. **Gene/variant name format** — just the name
10. **Separate answers from citations**
11. **VERBATIM NUMBERS AND UNITS** — no unit conversion, rounding, or substitution
12. **NO ELLIPSIS IN CITATIONS** — verbatim quote only
13. **CITATION SOURCE PRIORITY** — prose from Results/Discussion/Methods first; tables only if no prose
14. **GENE-NAMED CITATIONS** — every citation must include a sentence naming the gene or its alias

### 13.6 The clinical-vs-molecular disambiguation story (C18)

A FDA auditor flagged the original static blocklist approach. The blocklist blocked ESR, AST, CRP, etc. as known clinical biomarkers that get confused with genes. BUT:

- ESR1 is a real breast cancer gene
- PSA/KLK3 is a real prostate gene
- ACE is a real hypertension gene
- GOT1/AST is a real liver genetics gene

A blocklist couldn't distinguish "ESR as lab value" from "ESR1 as gene". Replaced with a prompt disambiguation clause that reads sentence context:

> "Do NOT extract abbreviations that are used solely as clinical laboratory measurements or diagnostic test results (e.g., 'ESR 78 mm/h' is a lab value, not the ESR1 gene; 'AST 120 U/L' is a liver function test, not the GOT1 gene; 'CRP 45 mg/L' is an inflammatory marker measurement, not the CRP gene). If a paper discusses both the clinical measurement AND the gene/protein at a molecular level, only extract it as a gene if the paper explicitly discusses it at the molecular level."

**Tradeoff.** The LLM clause is stochastic — not 100% reliable. The corroboration gate (PubTator + evidence gate) provides a hard backstop: clinical-only extractions fall to `deterministic_lexicon`-only and get dropped by the evidence gate.

### 13.7 Thinking mode disabled (C20)

Gemini preview models have thinking enabled by default. For 12k-token `detail_extraction` prompts, this caused hangs >600s.

Fix: set `thinking_budget=0` on ALL `GenerateContentConfig` calls. This is checked in every LLM method in `pipeline/modules/paper_analysis/gemini_client.py`.

### 13.8 Why no static clinical blocklist

See 13.6. The FDA auditor story is documented in `docs/audit/AUDIT.md` at the C18 entry.

### 13.9 `detail_extraction` instruction accumulation

The 14 rules in `_DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS` accumulate. Each new constraint is appended without removing previous ones. Current count is 14. At higher counts, prompt engineering yields diminishing returns and a post-extraction validation schema becomes more reliable.

---

## Appendix A — Test Locations

| Test type | Location | Count | How to run |
|---|---|---|---|
| Unit | `pipeline/tests/test_*.py` | ~50 | `python -m pytest tests/ -v` |
| Integration | `pipeline/tests/test_pipeline_integration.py` | 11 | `python -m pytest tests/test_pipeline_integration.py -v` |
| Smoke | `/verify` slash command | n/a | TS typecheck + Python imports |
| Benchmark | `pipeline/scripts/benchmark_runner.py` | 24 papers | `python scripts/benchmark_runner.py --all --runs 3` |

All tests run from the `pipeline/` directory with the venv activated. Total runtime: ~4-5 minutes for the full suite.

## Appendix B — Debug Artifacts

Every pipeline run produces a debug artifact at `{output_dir}/drop_debug_{hash}.json`. Contents:

```json
{
    "status": "completed" | "metadata_only_*",
    "papers": [
        {
            "pmid": str,
            "screening_decision": {...},
            "fetch_outcome": {...},
            "candidates": {...},           // candidate_meta dict
            "strict_gate_drops": [...],
            "evidence_gate_drops": [...],
            "gemini_api_calls": int,
        }
    ]
}
```

This is the single best source of truth for post-mortem analysis. When a paper produces unexpected output, read the debug artifact first.

## Appendix C — Files Changed History

For each core file, see its git history for the change timeline:

```bash
git log --oneline pipeline/modules/paper_analysis/ pipeline/modules/gemini_extractor.py
git log --oneline pipeline/modules/pipeline_orchestrator.py
git log --oneline pipeline/modules/gene_validator.py
git log --oneline app/src/main/python-bridge.ts
```

Key refactor: commit `df674fe` (2026-04-07) — pre-package readability refactor + two bug fixes (section dict overwrite, evidence gate log).

---

## Cross-References

- [`bug-hunting.md`](./bug-hunting.md) — actionable audit cheatsheet
- [`../../.codex/rules/memory-pipeline.md`](../../.codex/rules/memory-pipeline.md) — domain-level routing for Codex
- [`AUDIT.md`](../audit/AUDIT.md) — historical bug log
- [`AGENTS.md`](../../AGENTS.md) — project routing file
