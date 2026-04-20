# Final Audit

> Findings discovered while tracing the pipeline end-to-end, co-documented with the project owner.
> Each entry: **what we expected → what we found → why it matters → suggested action.**
> Each entry also ends with an **Implementation notes** block — session-continuity context
> so the finding can be picked up and fixed later without rediscovering prior analysis.

---

## Priority tier guide

Findings are grouped into six priority tiers. **Priority reflects fix urgency** —
how soon the finding should be addressed — which is a different axis from the
**severity** column (how badly the bug hurts users or correctness if unfixed).

| Tier | Meaning | Typical effort |
|---|---|---|
| **P0** | Trust-critical — user sees wrong or missing data today. Fix before next user-visible milestone. | S–M |
| **P1** | Correctness improvement with a clear, scoped fix. Ship as a batch. | XS–S |
| **P2** | Documentation / external accuracy. Matters for the SoftwareX paper reviewers. | XS–S |
| **P3** | Efficiency. Not wrong, just wasteful. | M |
| **P4** | Architectural evolution / bigger project. Needs design discussion. | L |
| **P5** | Tracer/viewer tooling quality. Low-impact, high-yield quick wins. | XS |

**Effort scale:** XS = ≤ 30 min, S = a few hours, M = a day, L = multi-day / multi-file.

**Status values:**
- ⬜ TODO — not started
- 🛠 IN PROGRESS — code in flight, tests pending
- ✅ DONE — shipped and verified

---

## Findings Index (by priority)

Newest findings (F11, F12) surfaced during the PMID 41017238 audit. See
[`docs/audit_pmid_41017238.md`](docs/audit_pmid_41017238.md) for the full run review.

### P0 — Trust-critical

| # | Status | Effort | Finding | Area |
|---|---|---|---|---|
| [F11](#f11--auto-snippet-fallback-is-indistinguishable-from-llm-extracted-content) | ✅ DONE | S | Auto-snippet fallback indistinguishable from LLM-extracted content | Detail-extraction fallback path |
| [F3](#f3--doi-and-pmc-id-inputs-are-silently-dropped-from-user-defined-lists) | ⬜ TODO | M | DOI / PMC IDs silently dropped from specific-papers paste-box | `SmartInput.tsx` entry |
| [F2](#f2--all-papers-are-oa-is-not-actually-enforced-on-all-entry-paths) | ⬜ TODO | S–M | OA invariant not enforced on specific-PMIDs entry path | `SmartInput.tsx` + orchestrator |

### P1 — Correctness improvements with clear fixes

| # | Status | Effort | Finding | Area |
|---|---|---|---|---|
| [F12](#f12--per-row-key-finding-can-be-literally-identical-across-multiple-genes) | ⬜ TODO | S | Identical `Key Finding` excerpt across multiple gene rows | `_backfill_sparse_row_evidence` |
| [F10a](#f10--post-validation-silent-failures-citation-false-negatives-fuzzy-match-drops-opaque-evidence-thresholds) | ⬜ TODO | S | Citation validator false negatives on formatting drift / auto-snippet | `_citation_exists_in_paper` |
| [F10b](#f10--post-validation-silent-failures-citation-false-negatives-fuzzy-match-drops-opaque-evidence-thresholds) | ⬜ TODO | S | Strict-gate drops silent (mouse-convention / fuzzy resolutions) | `_run_post_validation` |
| [F10c](#f10--post-validation-silent-failures-citation-false-negatives-fuzzy-match-drops-opaque-evidence-thresholds) | ⬜ TODO | S | Per-tier evidence thresholds not visible to operator | `_apply_evidence_gate` + UI |
| [F8a](#f8--grounding-check-silent-failure-modes-truncation-interaction-and-fuzzy-pattern-blind-spots) | ⬜ TODO | M | Truncation × grounding — genes in abstract but not truncated body | `_run_grounding_check` |
| [F8b](#f8--grounding-check-silent-failure-modes-truncation-interaction-and-fuzzy-pattern-blind-spots) | ⬜ TODO | XS | Fuzzy pattern blind spot: `IL(6)`, `IL.6` | `_find_evidence_snippet` |
| [F8c](#f8--grounding-check-silent-failure-modes-truncation-interaction-and-fuzzy-pattern-blind-spots) | ⬜ TODO | XS | `_run_grounding_check` docstring scope clarification | `_run_grounding_check` |
| [F6](#f6--greek-letter-transliteration-is-asymmetric-between-body-and-abstract) | ⬜ TODO | S | Greek letter transliteration asymmetric abstract ↔ body | `_prepare_paper_inputs` |

### P2 — Documentation accuracy

| # | Status | Effort | Finding | Area |
|---|---|---|---|---|
| [F1](#f1--the-4-overfetch-factor-does-not-exist-in-code) | ⬜ TODO | S | "4× overfetch factor" claim in 6+ docs — doesn't exist in code | Docs + paper draft + `config.py` |

### P3 — Efficiency

| # | Status | Effort | Finding | Area |
|---|---|---|---|---|
| [F4](#f4--redundant-fetches-across-the-uipipeline-boundary) | ⬜ TODO | M–L | Redundant fetches across UI/pipeline boundary | `python-bridge.ts` IPC contract |

### P4 — Architectural evolution

| # | Status | Effort | Finding | Area |
|---|---|---|---|---|
| [F7](#f7--batched-detail-extraction-has-known-artefacts-offer-per-gene--context-caching-as-a-user-option) | ⬜ TODO | L | Offer per-gene + context-caching detail extraction as user option | Stage 5 Gemini detail extraction |
| [F9](#f9--corroboration-gate-cant-distinguish-table-only-genes-from-biomarker-abbreviations) | ⬜ TODO | M–L | Corroboration gate can't distinguish table-only genes from biomarker FPs | JATS parser + corroboration gate |
| [F5](#f5--pubtator-response-has-more-annotation-types-than-we-consume) | ⬜ TODO | M | PubTator's Chemical/Disease/Species annotations discarded | `pubtator_tool._parse_document` |

### P5 — Tracer / viewer tooling quality

| # | Status | Effort | Finding | Area |
|---|---|---|---|---|
| [L1](#p5-l1--orchestrator-helpers-observed-name-only-on-watchlist) | ⬜ TODO | XS | 7 orchestrator helpers observed name-only in viewer (watchlist additions) | `pipeline_tracer._FN_TRACER_VALUE_CAPTURE` |
| [L2](#p5-l2--_collect_debug_artifact-high-value-missing-from-watchlist) | ⬜ TODO | XS | `_collect_debug_artifact` missing from watchlist (highest-value single add) | `pipeline_tracer._FN_TRACER_VALUE_CAPTURE` |
| [M3](#p5-m3--function-events-not-linked-to-stage-markers) | ⬜ TODO | S | Function events not linked to stage markers (time-window alignment lossy) | `pipeline_tracer.capture` |
| [L3](#p5-l3--ncbi-enrichment-rate-limit-silent) | ⬜ TODO | S | NCBI enrichment rate-limit silently produces empty columns | NCBI enrichment in orchestrator |

**Note on severity vs priority:** a MEDIUM-severity finding in a quick-fix tier (e.g. F8b)
ranks above a HIGH-severity finding in a harder tier (e.g. F4 efficiency), because
batching quick wins preserves momentum and builds confidence. Severity remains documented
in each entry's body.

---

## F12 — Per-row `Key Finding` can be literally identical across multiple genes

**Date:** 2026-04-20
**Source:** Audit of PMID 41017238 run (`docs/audit_pmid_41017238.md`).
**Severity:** MEDIUM. Semantic misrepresentation in the CSV — 3 rows of apparently
gene-specific evidence are actually one sentence repeated three times.

### What we expected

Each row in the output CSV represents one `(gene, variant)` pair with evidence specific
to that gene.

### What we found

On the PMID 41017238 run, all three output rows (ITPKC, CASP3, FCGR2A) have the
*identical* `Key Finding` excerpt:

> "Furthermore, genetic polymorphisms associated with KD, such as ITPKC, CASP3, and
> FCGR2A, contribute to immune activation by promoting inflammasome activation,
> pyroptosis and antibody dependent enhancement (ADE), thereby intensifying…"

This came from `_backfill_sparse_row_evidence` (evidence backfill) which runs when the
LLM detail-extraction step fails or produces empty rows. The backfill does keyword
search across the paper for each row, looking for a sentence that mentions the gene.
Because the paper has exactly one summary sentence that names all three genes together,
all three rows get the same snippet.

The CSV then presents this as three rows of gene-specific evidence when it's really one
co-mention sentence × three genes.

### Why it matters

- **Misleading**: A downstream consumer looking at the CSV sees "3 rows, 3 genes, 3
  citations" and treats this as three independent findings. It's one finding.
- **Inflates perceived evidence**: In automated analyses, a paper with 1 co-mention
  sentence for 3 genes scores the same as a paper with 3 separate gene-specific
  sentences.
- **Not unique to quota failure**: could happen any time the LLM returns an empty array
  and keyword fallback fires; review papers that list many genes in one sentence are
  structurally prone to this.

### Suggested action

Two possible strategies — pick one:

- [ ] **Per-gene snippet search.** When backfilling a row for gene X, require the
      candidate sentence to contain gene X specifically (or X's HGNC alias), not just
      any gene from the candidate list. If no sentence mentions X alone, leave the cell
      empty and mark the row with a `no_specific_evidence` flag.
- [ ] **Deduplicate after backfill.** When backfill produces identical snippets across
      multiple rows, merge them into one row with aggregated variant names
      (`Gene = "ITPKC; CASP3; FCGR2A"`) and mark with `merged_from_co_mention`. This is
      unusual — the output would have N−2 rows instead of N — but it's honest.
- [ ] Related to F7's per-gene architecture; if detail extraction goes per-gene, this
      specific failure can't happen because each gene's call produces gene-specific
      content.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P1 tier.

**Code location:** `pipeline/modules/gemini_extractor.py::_backfill_sparse_row_evidence`
(~line 325). The function currently picks ONE target column (defaults to "Key Finding")
and fills it with `_find_evidence_snippet(self._candidate_terms_for_row(gene, variant))`.
`_candidate_terms_for_row` includes gene aliases — but on a review paper where multiple
genes are co-mentioned in one sentence, the first sentence hit is the same for all
genes.

**Recommended approach:** per-gene exact-match requirement.
- In `_find_evidence_snippet`, add a `require_exact_gene_in_match: bool = False` flag.
- When called from `_backfill_sparse_row_evidence`, require the matched snippet to
  contain the gene symbol (or one of its aliases) as a whole word — not just that any
  candidate_term matched.
- If no exact-match sentence exists, leave the cell empty and mark the row with
  something like `row["backfill_skipped_no_gene_specific_match"] = True`.

**Alternative approach — row merging:** when identical snippets end up on multiple
rows, merge into one aggregated row with `Gene = "ITPKC; CASP3; FCGR2A"`,
`Variant = ""`. This is unusual for downstream consumers (row count ≠ gene count) but
honest. Would need a new column `merged_from_co_mention: True`.

**Do not do:** truncate/obfuscate the snippet to make the rows look different. The
duplication isn't cosmetic — it's evidence about the paper's prose structure and should
be surfaced accurately.

**Dependency on F7:** if per-gene architecture ships first (F7), F12 becomes moot — each
gene's LLM call produces gene-specific content by construction and fallback only fires
per-gene, not across a batch.

**Testing after fix:** re-run the PMID 41017238 case with Gemini quota exhausted. Three
rows should no longer share the same Key Finding excerpt — either each gene gets its
own sentence, or rows with no gene-specific sentence are marked `backfill_skipped`.

---

## F11 — Auto-snippet fallback is indistinguishable from LLM-extracted content

**Date:** 2026-04-20
**Source:** Audit of PMID 41017238 run (`docs/audit_pmid_41017238.md`).
**Severity:** HIGH. Trust erosion — users can't tell whether a row was LLM-analysed or
assembled from keyword search on the paper text.

### What we expected

Rows in the output CSV are produced by Gemini's detail extraction (Section 14 of
`docs/pipeline-understanding.md`) — the LLM reads the paper, understands the gene's
context, and produces content for each user column (e.g., `Key Finding`,
`Disease Association`).

When the LLM fails, the pipeline has a graceful fallback: `_run_detail_extraction`
emits skeleton rows, and `_backfill_sparse_row_evidence` populates `Key Finding` via
keyword search over the paper. This is documented in `docs/pipeline-understanding.md`
§14.3–14.4.

### What we found

The fallback is completely invisible in the output. A row produced by Gemini looks
identical to a row produced by keyword fallback:

- `gene_name`, `variant_name`: HGNC-validated regardless
- `validation_confidence`: 1.0 regardless (it's the gene-identity confidence, not
  content-extraction confidence)
- `Confidence` tier: computed the same way regardless
- `Key Finding`: non-empty string regardless (LLM synthesis OR keyword snippet)
- `Disease Association`: empty in the fallback case (LLM would have filled it)

**The only hint** that fallback ran is:
- `Disease Association` being empty (but it's already empty for genes the LLM couldn't
  find context for — not distinguishable from fallback)
- `Confidence Note` containing "Citation text not found in paper" — but that's
  F10a's SequenceMatcher rejection, which fires even on legitimate LLM citations
  with encoding drift

There's **no row-level marker** that says "this row's Key Finding came from keyword
fallback, not LLM understanding."

### Why it matters

1. **Researcher trust**: a user scanning the CSV sees three genes with
   `Confidence = HIGH` and a `Key Finding` string and reasonably assumes the LLM
   understood each gene's role. On this run, it didn't — Gemini 429'd on every call.
2. **Downstream analysis contamination**: if the CSV is fed into meta-analysis or
   benchmarking, rows with fallback evidence are treated as equivalent to LLM-extracted
   rows. The pipeline's F1/precision numbers get inflated by fallback content.
3. **Silent quality degradation**: the operator running the pipeline has no
   top-level signal that "Gemini quota ran out, switched to fallback mode, results are
   degraded."
4. **`detail_extraction_status` is recorded but never surfaced**: the per-paper debug
   artifact contains `"detail_extraction_status": "association_only_fallback_no_rows"`,
   but this doesn't propagate to any output column or UI banner.

### Suggested action

- [ ] **Per-row `extraction_mode` column.** Values: `"llm"`, `"keyword_fallback"`,
      `"skeleton"` (skeleton = no content at all). Always written; never empty. Operator
      can filter `extraction_mode = "keyword_fallback"` to find degraded rows.
- [ ] **Per-row `llm_status` column.** Values: `"success"`, `"rate_limited"`, `"timeout"`,
      `"malformed_response"`, `"quota_exhausted"`. When Gemini fails, the specific
      error is already in the subprocess's log — lift it into the row.
- [ ] **UI-level banner.** When the run finishes and `detail_extraction_status` is
      anything other than "completed", show a warning banner on the Results page:
      *"Detail extraction fell back to keyword matching for N/M rows due to LLM
      errors. Content may be lower quality than expected."*
- [ ] **Downgrade confidence for fallback rows.** Today `Confidence` ignores extraction
      mode. A row produced by keyword fallback should at most be `LOW`/`REVIEW` even if
      its HGNC validation is 1.0.

### Cross-references

- This was the root cause of the apparent M2/F10a "citation not found" on the
  PMID 41017238 run: the auto-snippet is from the paper, but SequenceMatcher ≥ 0.85
  fails to match it back; the resulting `Confidence Note = "Citation text not found"`
  was misleading — it implied the *gene* had no backing when actually the citation
  *validator* just couldn't re-find the text. After this fix those rows show
  `"LLM failed; auto-snippet fallback (…)"` instead.
- F7 (per-gene detail extraction) would reduce the likelihood of fallback firing
  because per-gene calls are independent — one gene hitting a rate-limit wouldn't take
  down the others.

### Implementation notes (session continuity)

**Status:** ✅ DONE — 2026-04-20 (branch `dev/cleanup`, not yet committed at time of writing).

**Files modified:**
- `pipeline/modules/gemini_extractor.py` — 4 sites:
  1. `extract_gene_info` success path — tag each Gemini row with `"extraction_mode": "llm"`
  2. `extract_gene_info` retry-exhausted fallback — tag `"skeleton"` + `"detail_extraction_error": str(e)[:300]`
  3. `_run_detail_extraction` secondary skeleton fallback — same tagging
  4. `_backfill_sparse_row_evidence` — set `row["evidence_backfilled"] = True` when a cell is populated
- `pipeline/modules/pipeline_orchestrator.py` — 2 sites:
  1. `_compute_row_confidence` — new early branch: if `extraction_mode == "skeleton"`, force `REVIEW` tier with error cause in the note. Distinguishes "auto-snippet fallback" (backfill ran) from "no content" (nothing populated). Runs *before* other tier logic. Defaults to legacy behaviour when field absent (backward-compatible).
  2. `_write_split_output::primary_cols` — added `"extraction_mode"` and `"evidence_backfilled"` between `Confidence Note` and `context_modifications`. Primary CSV now self-describes.

**Verification performed:**
- Both .py files AST-parse cleanly.
- Unit-level smoke test of `_compute_row_confidence` covering: healthy LLM row (HIGH unchanged), skeleton no-backfill (REVIEW + "no content" note), skeleton + backfill (REVIEW + "auto-snippet fallback" note), legacy no-field row (HIGH unchanged), empty gene guard (REVIEW — fires first).
- End-to-end test: 2-row DataFrame (1 LLM, 1 skeleton+backfill) through `_write_split_output` — primary CSV contains the new columns, values correct, tiers correctly split into HIGH vs REVIEW.

**What's not in this patch (scoped separately):**
- UI-level banner in `Results.tsx` that warns when a run finished with any `extraction_mode="skeleton"` rows. Electron-side change; would read the CSV's new column and render a top-of-page notice.
- A `llm_status` column with richer error taxonomy (`rate_limited` / `timeout` / `malformed_response` / `quota_exhausted`). The current fix stores the raw error string in `detail_extraction_error` — sufficient for humans, less structured for automated filtering.
- Prompt caching / per-gene architecture (F7) that would reduce how often fallback fires in the first place.

**Backward compatibility notes:**
- Rows from pre-fix runs have no `extraction_mode` field → `_compute_row_confidence` defaults to `"llm"` semantics → HIGH/MEDIUM/LOW as before.
- `primary_cols_present = [c for c in primary_cols if c in df_clean.columns]` filters missing columns, so old runs without these fields produce a narrower CSV (no regression).
- The metadata CSV gets everything regardless — new columns appear there too automatically.

**Gotchas for next time:**
- The error string from Gemini's 429 response is long (~3 KB with the full `details[]` array). We cap to 300 chars at capture time so it fits in a CSV cell. Don't remove the cap.
- `extraction_mode` is a row-level tag. Future F7 per-gene mode will have each row independently succeed/fail — keep this field per-row, not per-run.

---

## F10 — Post-validation silent failures: citation false negatives, fuzzy-match drops, opaque evidence thresholds

**Date:** 2026-04-19
**Source:** Tracing Step 4 (`_run_post_validation`) in Section 15 of
`pipeline-understanding.md`.
**Severity:** Mixed. Three distinct silent failure modes in the final three gates.
One is a trust-erosion bug (F10a), one is a known-accepted trade-off worth
documenting (F10b), one is a UX/debuggability issue (F10c).

### Context — what post-validation does

Three checks run in sequence on the detail-extracted DataFrame:

1. **Strict validation gate** — drop if `validation_confidence < 0.7`
2. **Citation validation** — annotate every `{col, col Citation}` pair with
   validity, confidence, details. Doesn't drop.
3. **Evidence gate** — drop if non-empty cells below per-source threshold

Each has a specific silent failure mode worth documenting separately.

### F10a — Citation validator false negatives on formatting drift

**What we expected:** a citation that's a verbatim quote from the paper is marked
`citation_valid=True`.

**What we found:** [`_citation_exists_in_paper`](pipeline/modules/gene_validator.py) uses
`difflib.SequenceMatcher` with a **hardcoded ratio threshold of 0.85** to verify that
the LLM-extracted citation text appears in the paper. On papers with any of the
following, the matcher returns < 0.85 and the citation is flagged invalid **even
when the quote is genuinely in the paper**:

- **Soft hyphens and line-break hyphenation.** PMC XML sometimes preserves
  word-break hyphens (`suscep-\ntibility`) that the LLM correctly quotes without the
  hyphen (`susceptibility`). Character-level diff pushes ratio below 0.85.
- **Figure-caption drift.** Figure captions in JATS XML have whitespace-normalised
  rendering that differs subtly from how the LLM quotes the same caption.
- **Em-dash / en-dash reconciliation.** Greek transliteration in the body (Section 4.4)
  handles some Unicode glyphs but not all; the LLM sometimes normalises en-dashes in
  its quote that remain unnormalised in the body (or vice versa).
- **Typesetting artefacts from old PDF-derived XML.** Ligatures (`fi`, `fl`),
  mid-sentence spaces, and publisher-specific entity encoding.

**Why it matters:** `citation_valid=False` shows up in the final CSV — an operator
reviewing the output sees "this citation is not backed" and loses trust in the
extraction, even when the extraction is correct. The evidence gate doesn't drop the
row for this (it counts cell populate-ness, not citation validity), but the UX
degradation is real.

**Why this is particularly painful:** the C19 fix (logged in `memory-decisions.md`)
addressed citation validation *crashing silently* (every row tagged "No validation
performed" because of a TypeError). The fix made validation run — but made the 0.85
threshold's false-negative rate visible to users, who hadn't seen it before because
it was hidden behind the crash.

**Suggested action:**
- [ ] **Preprocess both sides before SequenceMatcher.** Collapse whitespace aggressively
      (including soft hyphens and line-break hyphenation), unify dashes, strip
      common typesetting artefacts. The encoding-normalisation pass in `_normalize_unicode_slashes`
      (C22) is a template for this — extend it to include these new cases.
- [ ] **Consider lowering the threshold to 0.80** and re-characterising on the benchmark
      set. Trade-off: might accept more false positives (fuzzy matches where the quote
      isn't actually in the paper). Worth measuring the precision/recall shift.
- [ ] **Expose the threshold as a config flag** (`CITATION_SIMILARITY_MIN_RATIO`), so
      future tuning doesn't require code edits.
- [ ] **Better `citation_details` messaging** — currently says "not found in paper,"
      which implies the quote is absent. A message like "matched at 0.82 ratio, below
      0.85 threshold — likely formatting drift" would let operators distinguish a real
      false-quote from a near-miss.

### F10b — Strict gate drops mouse-convention symbols and fuzzy resolutions (accepted trade-off — document explicitly)

**What we expected:** the strict validation gate at 0.7 confidence is a medical-accuracy
threshold that drops low-confidence matches.

**What we found:** the gate silently drops two categories of legitimate extractions:

1. **Mouse-convention symbols mapped to human genes.** When a paper uses title-case
   mouse convention (`Brca1`) to refer to the human gene (common in comparative
   genomics and cross-species studies), `gene_validator.resolve_gene_symbol` flags
   `potential_murine_symbol` in `validation_source` and returns confidence 0.5.
   The 0.7 strict gate drops these. Documented in `memory-decisions.md` 2026-02-28 as
   "Mouse symbol flag is informational, not blocking" — but the strict gate *is*
   blocking on it.
2. **Fuzzy-matched aliases.** A paper using an old / non-canonical alias that only
   resolves via fuzzy matching (`MYH-9` for `MYH9`, older literature) can return at
   0.5–0.6. Dropped.

**Why this is not a bug:** CLAUDE.md explicitly marks `FINAL_VALIDATION_MIN_CONFIDENCE=0.7`
as a medical-accuracy decision, not a performance knob. The trade-off is
intentionally biased toward precision over recall.

**Why it's worth flagging:** the trade-off isn't documented in the operator-facing
output. An operator looking at the CSV sees "47 genes extracted," has no idea that 3
legitimate mouse-convention mentions and 2 alias-fuzzy-matches were dropped at this
gate. For mouse-model papers and cross-species reviews, this could be a meaningful
blind spot.

**Suggested action:**
- [ ] **Surface strict-gate drops to the operator.** Add a "Dropped by strict
      validation" section to the metadata CSV or a UI banner on the results page
      listing the dropped genes with their confidence and `validation_source` tags.
      The data is already in `self.strict_gate_drops` — it just doesn't reach the UI.
- [ ] **Reconsider the mouse-symbol path.** The explicit `potential_murine_symbol`
      flag is informational by design, but it *interacts* with the strict gate to
      produce an unintentional drop. Either: (a) bump confidence for mouse-convention
      resolutions that clearly map to a valid human HGNC symbol, or (b) carve out
      a secondary CSV section for "flagged for review" genes that didn't make the
      strict cutoff but aren't outright hallucinations.

### F10c — Evidence gate's per-tier thresholds are not user-visible

**What we expected:** a row is either sufficient or insufficient.

**What we found:** whether a row with 0 non-empty cells survives depends entirely on
its `sources` set, which the operator never sees. Specifically:

- A row with `{llm_text}` source and 0 cells survives (`min_cells = 0`).
- A row with `{deterministic_lexicon}` source and 0 cells drops (`min_cells = 1`).
- A row with `{pubtator}` source and 0 cells drops (`min_cells = 1` via mixed default).

The operator looking at `drop_debug_{hash}.json` sees
`{reason: "insufficient_user_evidence", source_tier: "deterministic", evidence_cells: 0, min_required: 1}`
— but only if they know to look, and even then the logic isn't obvious.

**Why it matters:** debuggability. When an operator asks "why did TP53 not reach my
CSV?" and the answer is "because it was only found by the deterministic scanner, and
the evidence gate requires 1 non-empty cell for non-LLM sources, and the detail call
didn't produce any user-column content for it," that's a non-obvious chain of events.
Researchers investigating false negatives for the SoftwareX paper would hit this wall.

**Why it's design-intentional:** the per-tier thresholds encode a real trust model
(the LLM's act of naming a gene is evidence; a lexicon match alone isn't). But the
model is invisible to the user.

**Suggested action:**
- [ ] **UI surfacing of drop reasons.** Results page could expose a "Why are some
      genes missing?" affordance that summarises drops by gate (grounding,
      corroboration, strict, evidence) with counts and a representative example
      each.
- [ ] **Document the per-tier logic in the user-facing README or a Help tooltip.**
      Currently it's buried in `gemini_extractor.py` with a code comment.
- [ ] **Consider making at least one tier threshold user-configurable.** Precision
      users (clinical, publication) might want `EVIDENCE_MIN_NONEMPTY_CELLS_LLM_TEXT=1`
      to require at least some content extraction per LLM-surfaced gene; recall users
      (exploratory review) might want `EVIDENCE_MIN_NONEMPTY_CELLS_DETERMINISTIC=0`
      to include table-only genes that F9 already flagged.

### Cross-references

- **F10a** compounds with **F6** (Greek-letter asymmetry): both are encoding-drift
  failures at different layers. Fixing them together (a unified, symmetric
  normalisation pipeline that runs on both sides of every comparison) would close
  multiple paths at once.
- **F10a** is also the failure mode that made F11's auto-snippet rows show
  `"Citation text not found in paper"` — F11 now overrides that misleading note for
  skeleton rows, but the underlying F10a threshold issue remains for legitimate LLM
  rows with formatting drift.
- **F10c** overlaps with **F9** (table-only genes): both would benefit from making
  per-tier logic user-visible so researchers can opt into different trust models
  per use case.

### Implementation notes (session continuity)

**Status:** all three ⬜ TODO. P1 tier.

#### F10a — SequenceMatcher threshold

**Code location:** `pipeline/modules/gene_validator.py::_citation_exists_in_paper`
(~line 636). Step 2 of the function uses `difflib.SequenceMatcher` with a hardcoded
threshold of 0.85. Already runs through `_normalize_unicode_slashes` (C22 sprint)
which handles slashes, LaTeX Greek, ASCII mu prefix, U+00B5/U+03BC unification.

**Additional normalisations needed (extend `_normalize_unicode_slashes` OR add a
sibling function that runs on both citation and paper_text):**
- Soft hyphens + line-break hyphenation: `suscep-\ntibility` → `susceptibility`
- Em-dash / en-dash variants to ASCII hyphen (em-dash U+2014 is already stripped, but
  en-dash U+2013 slips through sometimes)
- Ligatures `fi`, `fl` → `fi`, `fl`
- Non-breaking hyphen U+2011 → `-`

**Threshold decisions:**
- Consider lowering to 0.80 and re-characterising on the benchmark set
  (`pipeline/data/benchmark/`). Risk: more false positives.
- Expose as config: `CITATION_SIMILARITY_MIN_RATIO = 0.85` in `config.py` — cheap.

**Better `_details` messaging:** current "not found in paper" is ambiguous.
Distinguish: `"no similar text in paper"` (ratio < 0.5), `"near-miss match 0.82 <
0.85 threshold"` (ratio ∈ [0.5, 0.85)), `"found but gene not in window"` (ratio ≥ 0.85
but gene context gate failed).

#### F10b — Surfacing strict-gate drops

**Data already exists:** `self.strict_gate_drops` is populated in
`_run_post_validation` (`pipeline/modules/gemini_extractor.py`, ~line 1797).

**Fix:** include this list in the drop_debug artifact's operator-facing section, AND
add a summary column to the primary CSV (or a banner in the UI) when any rows were
dropped: `strict_gate_drops_count: N` at the run level.

**Particular attention to:** mouse-convention symbol flag
(`potential_murine_symbol` in `validation_source`). These currently resolve at 0.5
confidence and get dropped by the 0.7 strict gate. Options:
- Bump confidence for mouse-convention → human HGNC mappings
- OR carve out a secondary CSV section for "flagged for review" genes

#### F10c — Per-tier evidence thresholds

**Location:** `_apply_evidence_gate` in `gemini_extractor.py`. Three env vars:
`EVIDENCE_MIN_NONEMPTY_CELLS_LLM_TEXT = 0`, `EVIDENCE_MIN_NONEMPTY_CELLS_DETERMINISTIC = 1`,
`EVIDENCE_MIN_NONEMPTY_CELLS = 1`.

**Fix options (do all three are cheap):**
1. Add these values to the per-run stats/metadata so they appear in output artefacts.
2. Document in the user-facing README/Help tooltip on the Results page.
3. Expose as settings (already covered by F7's precision/recall dial concept).

---

## F9 — Corroboration gate can't distinguish table-only genes from biomarker abbreviations

**Date:** 2026-04-19
**Source:** Tracing Step 2's corroboration gate in Section 13 of
`pipeline-understanding.md`.
**Severity:** Collateral damage on a specific paper class — table-heavy Results-only
gene reporting. Real but bounded.

### What we expected

The corroboration gate exists to filter clinical-biomarker abbreviations that the
deterministic scanner catches but the LLM correctly refuses to extract (per the C18
disambiguation clause, confirmed in C21). A candidate tagged only with
`deterministic_lexicon` source and no variant → dropped as uncorroborated.

### What we found

The gate cannot distinguish two semantically opposite cases that produce the same
`sources` set:

| Case | Why it happens | What should happen |
|---|---|---|
| **(a) Biomarker false positive.** `ESR1` appears in a clinical paper discussing "ESR 78 mm/h" lab values. LLM correctly identifies this as a lab value and refuses extraction. Deterministic scanner picks it up because the literal token `ESR1` is somewhere in the text. | LLM disambiguation clause working as intended | Drop ✅ |
| **(b) Real table-only gene.** A gene panel paper mentions `NUDT15` only in a Results table with no accompanying prose discussion. The LLM, which typically skips table-heavy prose, misses it. Deterministic scanner picks it up from the table token. | LLM skipped the table (known Gemini behaviour on structured data) | Keep ❌ **dropped anyway** |

Both produce `sources == {deterministic_lexicon}` and `variant == ""`. The gate treats
them identically.

### Why it matters

Pharmacogenomics guideline papers, gene-panel cancer papers, and certain CPIC-style
drug-gene tables routinely report gene findings in structured tables without prose
elaboration. Examples from the project benchmark:

- **PMID 35152405** (CPIC guideline for statins — SLCO1B1/ABCG2/CYP2C9). Several dose-
  adjustment guideline genes appear only in Table 2 with no surrounding prose.
- **Pan-cancer oncoprint papers.** Commonly a supplementary table of "genes with
  significant mutations" that the prose summarises only generically ("the top 30
  drivers").

On these papers, the gate silently drops real genes. The operator sees "47 → 43
after corroboration gate" with no indication whether the 4 drops were false positives
(the gate's intent) or false negatives (table-only genes).

### Why it's not easy to fix

The trade-off is structural:

- **Tighten the gate** (e.g., require 2+ sources for *all* candidates) → drops more
  real genes on every paper, not fewer.
- **Loosen the gate** (e.g., allow deterministic-only to pass) → reintroduces
  biomarker false positives. This was the whole reason C9/C18/C14 were added.
- **Context-aware distinction** — detect whether the deterministic-only token is in a
  table-cell context or a prose-sentence context. The JATS parser currently concatenates
  table text into the body stream without structural markers (Section 6), so there's
  no "in a table" signal at this stage.

### Suggested action

Not a single-fix issue. Consider in order of increasing ambition:

- [ ] **Immediate:** log dropped candidates with enough context (surrounding snippet
      from paper text) that the operator can spot false negatives in `drop_debug_{hash}.json`.
      Current drop record has `{gene, variant, reason, confidence}` — adding a
      snippet would make post-hoc review tractable.
- [ ] **Medium:** preserve table-vs-prose provenance in the JATS parser (Section 6).
      Annotate each text span with a source-element tag (`<body>`, `<table-wrap>`,
      `<caption>`). Then add a `table_context` signal to deterministic-scan output.
      Genes only found in tables could be given a different source tag
      (`deterministic_lexicon_table`) that's allowed to pass when accompanied by a
      concurrent PubTator hit, even without LLM backing.
- [ ] **Ambitious:** per the F7 architectural discussion — per-gene detail extraction
      with context caching would let the LLM be prompted specifically about a
      table-token gene with a focused "is this a real gene mention?" check. This is
      the "use the LLM as a tie-breaker" path and it would naturally subsume this
      gate's job.
- [ ] Verify on the benchmark: run PMID 35152405 and a pan-cancer paper from the
      gold-standard set. If `rejected_uncorroborated_deterministic` drops contain any
      entries that match the gold standard, this finding is confirmed reproducible.

### Cross-reference

F9 is a sibling to **F5** (PubTator unused annotations). If PubTator's `Disease` or
`Chemical` annotations were consumed (F5's suggestion), a candidate appearing in a
table adjacent to a PubTator-tagged disease mention could be given a soft corroboration
boost. Solving F5 would weaken F9's sharp edge.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P4 tier — M–L effort.

**Manifestation confirmed by PMID 41017238 audit:** 26 of 29 candidates dropped —
including plausibly Kawasaki-relevant NLRP3, TLR4, TLR2, TNF, MYD88, CD14, HMGB1.
The gate is doing its designed job (preventing biomarker FPs) but on a review paper
with broad inflammation content the cost is high.

**Short-term palliative (can ship without structural changes):** when the LLM text-pass
specifically failed (not just "empty"), temporarily loosen the corroboration gate to
allow deterministic-only candidates through with a clear tag — e.g.
`extraction_mode_upstream = "deterministic_only_under_llm_failure"`. This prevents
the "Gemini 429 + corroboration gate = lose all deterministic candidates" cascade from
burning the whole run's recall.

**Structural fix:** preserve table-vs-prose provenance in JATS parser. Annotate each
text span with its source element (`<body>`, `<table-wrap>`, `<caption>`). Then
deterministic scan output can include `found_in: ["body"|"table"|"caption"]`.
Corroboration gate becomes aware of context — a gene only in tables adjacent to a
PubTator-tagged disease (F5 integration) can be given corroboration credit.

**Files:** `pipeline/modules/full_text_fetcher.py::_extract_text_and_figures_from_pmc_xml`
(JATS parser), `pipeline/modules/gemini_extractor.py::extract_deterministic_candidates`
(scanner), and the corroboration block inside `_apply_gene_validation_heuristics`.

**Before shipping:** add dropped-snippet context to `drop_debug` so the operator can
inspect *why* a specific gene was dropped — paragraph around the token, plus the
sources set. Data is already mostly there in `candidate_meta`.

---

## F8 — Grounding check silent failure modes: truncation interaction and fuzzy pattern blind spots

**Date:** 2026-04-19
**Source:** Tracing Step 1.6 (`_run_grounding_check`) in Section 12 of
`pipeline-understanding.md`.
**Severity:** Mixed. Three sub-findings — one structural bug, one narrow matching gap,
one design choice worth documenting explicitly.

### Context — what the grounding check is

Step 1.6 of the Gemini extractor drops candidates whose gene / alias / raw-label
doesn't appear in the paper text. Primary hallucination filter. See Section 12 of
`docs/pipeline-understanding.md` for mechanics.

### F8a — Truncation × grounding interaction (structural)

**What we expected:** candidates found in the abstract would be grounded against text
that includes the abstract.

**What we found:** if `_validate_and_prepare_paper_text`
([`gemini_extractor.py:2068`](pipeline/modules/gemini_extractor.py:2068)) truncates the
paper (Section 9.1) — dropping Methods, Supplementary, Discussion, Conclusion, or
Introduction to fit the 80% context threshold — the grounding check then runs against
the **truncated** `self.paper_text`.

Consequence: a gene that is:
- Found by the abstract pass (`source: llm_abstract`), because it appears in the
  abstract, AND
- Mentioned in the paper *only in a section that was truncated* (e.g., Methods or
  Supplementary),

…will be dropped by the grounding check, because the terms don't appear in the retained
body. The abstract block is preserved in JATS parsing, so the gene might still match
there — but if the raw label differs between abstract wording and the abstract's JATS
rendition, it can silently fail.

**Why it's real but rare:** most meaningful gene mentions appear in results or
discussion sections, and both are preserved unless the paper is extraordinarily long.
The bite case is supplementary-heavy papers (gene panels, genome-wide association
studies), where key gene lists sometimes live only in the supp.

**Suggested action:**
- [ ] During grounding, also search the *original* untruncated text (the PMC-returned
      body + abstract, stored before truncation) as a secondary pass. Keep the primary
      search on the truncated text to avoid rehydrating dropped sections into later
      evidence snippets.
- [ ] Failing that: log a warning when a candidate is dropped that *would* have
      matched in an untruncated search, so the operator at least knows truncation is
      biting.

### F8b — Fuzzy pattern blind spot

**What we expected:** the fuzzy pattern in
[`_find_evidence_snippet`](pipeline/modules/gemini_extractor.py:246) tolerates common
gene-symbol punctuation variants (`IL-6`, `IL_6`, `IL 6`, `IL/6`).

**What we found:** the fuzzy separator class is hardcoded to `[\s\-_\/]*`. It
**doesn't** cover:

- Parentheses: `IL(6)`, a formatting quirk in some typeset papers
- Periods: `IL.6`, rare but seen in bibliographic abbreviations
- Em-dash / en-dash: `IL—6`, `IL–6`, common in older typeset PDFs where OCR or
  publisher conversion maps hyphens to dashes
- Non-breaking hyphen (U+2011): visually identical to `-` but not matched

**Why it matters:** after Greek transliteration and ASCII coercion (Section 4.4, F6),
Greek letters are gone, but Unicode dashes in the body **survive** the cleaning step
because they're already ASCII-range (actually, the em-dash `—` is U+2014 and *is*
stripped by the cleaner — but en-dash `–` U+2013 and hyphen-minus `-` have different
behaviour across different cleaning paths). A gene symbol joined by an em-dash in the
source survives as joined by a space after cleaning, which the fuzzy pattern *does*
match. But en-dash `–` is U+2013, above the ASCII range, and gets stripped to a space
in `_clean_and_validate_content`. So dashes are largely fine — the real blind spot is
parentheses and periods in abbreviation conventions.

**Suggested action:**
- [ ] Extend the fuzzy separator class to `[\s\-_\/\.\(\)]*`. Low-risk change; the
      strict pattern still requires word boundaries, so we can't accidentally match
      across unrelated words.
- [ ] Add a test case: `IL(6)`, `IL.6`, `il 6` — should all ground against canonical
      `IL6`.

### F8c — No variant verification (design choice, documented for clarity)

**What we found:** the grounding check verifies the gene's presence in paper text,
but **not the variant's**. A row with `gene=BRCA1, variant=rs80357906` passes
grounding if `BRCA1` appears anywhere, regardless of whether `rs80357906` actually
exists in the paper.

**Why this is intentional:** variant verification is handled later by the citation
validator in `gene_validator.validate_citations` and by the evidence gate's per-source
thresholds (`_apply_evidence_gate`). Grounding's narrow job is "is this gene
hallucinated?"; variant realism is a separate concern.

**Why it's worth documenting:** the function's name (`_run_grounding_check`) suggests
it does full verification. Future contributors touching this code might assume
variants are checked here and skip adding variant-specific validation elsewhere.
A one-line comment would prevent that.

**Suggested action:**
- [ ] Add a docstring clarification: *"Grounding checks gene presence only. Variant
      presence is validated by the citation gate and evidence gate downstream."*
- [ ] No code change required — the separation of concerns is defensible.

### Cross-reference

F8 overlaps with **F6** (Greek letter asymmetry) on one surface: the grounding check is
where F6's asymmetry materialises into silent drops. F6 is the root cause (abstract
preserves Greek, body transliterates); F8a/b are the grounding-check-specific
consequences. Keep both entries; they live at different layers.

### Implementation notes (session continuity)

**Status:** all three ⬜ TODO. P1 tier.

#### F8a — Truncation × grounding interaction

**Problem recap:** `_validate_and_prepare_paper_text` truncates by dropping sections in
order (methods → supp → discussion → conclusion → intro) when paper > 80% of context
limit. `_run_grounding_check` then runs against the truncated `self.paper_text`.
Genes found in the abstract but only text-present in a dropped section get silently
dropped at grounding.

**Code locations:**
- Truncation: `pipeline/modules/gemini_extractor.py::_validate_and_prepare_paper_text` (~line 2311)
- Grounding: `pipeline/modules/gemini_extractor.py::_run_grounding_check` (~line 1542)

**Preferred fix:** before truncation, save a reference to the full text as
`self._paper_text_untruncated`. Grounding check first tries against truncated text
(cheap); if a candidate fails, retries against untruncated text. Log any
"would-have-matched-in-untruncated" drops as a warning so the operator knows
truncation bit.

**Alternative (cheaper):** just log the warning; don't rescue. Lets operators know
truncation caused the drop without rehydrating the dropped text into downstream steps.

**Edge case:** the paper is small enough that truncation never fires (PMID 41017238 was
11k tokens, under the 80% threshold). Fix only bites on long papers. Testing should
use a paper that triggers truncation (>80% of 1M-token Flash context = pan-cancer /
supplement-heavy studies).

#### F8b — Fuzzy pattern blind spot

**Trivial fix.** In `pipeline/modules/gemini_extractor.py::_find_evidence_snippet`
(~line 263), the fuzzy pattern uses `[\s\-_\/]*` as the separator class. Extend to
`[\s\-_\/\.\(\)]*` to cover `IL(6)`, `IL.6`, `IL(6)`. Word-boundary guards keep
false-positive risk at zero.

**Test after fix:** grep trace for any candidate that failed the strict pattern but
matched the new fuzzy pattern. Low risk of false positives because the lookahead/
lookbehind `(?<![A-Za-z0-9])` and `(?![A-Za-z0-9])` bracket the match.

#### F8c — Docstring clarification

**Trivial.** Add one-line note to `_run_grounding_check` docstring:
*"Verifies gene presence only. Variant presence is validated downstream by the
citation validator and evidence gate."* No code change.

---

## F7 — Batched detail extraction has known artefacts — offer per-gene + context caching as a user option

**Date:** 2026-04-19
**Source:** Architectural discussion after tracing Sections 8–9 of `pipeline-understanding.md`.
**Severity:** Evolution opportunity. Current pipeline works; known failure modes in
`AUDIT.md` (C22 sprint) can be reduced or eliminated by a structural change.

### What the pipeline does today

**One** Gemini call fills in the user's column schema for **all** candidate gene–variant
pairs on a paper. The prompt contains:

- The accumulated candidate list as JSON (`[{gene_name, variant_name}, ...]`)
- The full paper text (post-truncation)
- The 9 accumulated CRITICAL INSTRUCTIONS in `_DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS`
- Per-column descriptions + per-column citation-field asks

Gemini returns an array of rows. One API call per paper, regardless of how many genes
were found. See [`gemini_extractor.py:1169`](pipeline/modules/gemini_extractor.py:1169).

### Known failure modes that stem from batching

Documented in the C22 citation sprint ([`docs/AUDIT.md`](docs/AUDIT.md), 2026-02-25):

1. **Citation cross-contamination.** Gemini summarises Gene A's Key Finding in
   non-verbatim form, can't find a matching sentence, and cites the nearest statistical
   sentence — which sometimes belongs to Gene B. Patched with "GENE-NAMED CITATIONS"
   instruction and widened ±1500-char gene-context window in `_citation_exists_in_paper`,
   but not eliminated structurally.
2. **Row cross-repetition.** Gemini copies the same Key Finding across multiple variant
   rows of the same gene (or between genes discussed adjacently). Motivated
   instructions #1 ("Each gene is INDEPENDENT") and #9 ("Do NOT repeat same sentence
   across variant rows").
3. **Attention split.** A paper with 30 candidate genes forces Gemini to extract 30 sets
   of column values in a single response. Attention-per-gene degrades as the candidate
   count rises.
4. **Stochastic citation compliance (L16).** Per-paper citation coverage fluctuates 0/8
   to 8/8 across runs — the batched call sometimes complies with the quoting
   instructions, sometimes doesn't. Per-gene calls would average this out across 20
   independent decisions rather than amplifying through a single coupled decision.

Several of the 9 CRITICAL INSTRUCTIONS in the Stage 3 prompt exist **solely** because of
batching. Per-gene calls would make those instructions unnecessary and reduce
prompt-length drift over time.

### Why this is a user decision, not an architectural one

The two designs have opposite cost/quality curves:

| Dimension | Batched (current) | Per-gene (proposed) | Per-gene + context caching (hybrid) |
|---|---|---|---|
| Calls per paper (20 genes) | 1 | 20 | 20 (but cached paper text) |
| Input tokens per paper (~50k paper) | ~50k | ~1,000k | ~50k + ~20×small prompt ≈ ~70k |
| Free-tier rate impact (15 RPM) | Minor | **Severe** — ~0.75 papers/min | Moderate |
| Citation cross-contamination | Real, partially patched | Structurally impossible | Structurally impossible |
| Cross-gene context | Preserved | Lost | Lost |
| Attention per gene | Degrades with N | Full | Full |
| Prompt complexity | Heavy (9 instructions) | Minimal | Minimal |
| Failure isolation | Batch-level | Per-gene | Per-gene |

For a home/academic user running the free Gemini tier, per-gene without caching is
prohibitively expensive and hits the 15 RPM wall quickly. For a user running with a paid
API key on clinical / publication-grade extraction, per-gene (ideally hybrid) is
worth the trade.

**Therefore: neither design is universally superior. Make it a user-facing setting.**

### Proposed implementation

**Settings UI addition** — extend the existing Performance section in
[`Settings.tsx`](app/src/renderer/pages/Settings.tsx) where `parallelAnalysis` already
lives. Three-way choice:

```
Extraction mode
  ○ Economy — one detail call per paper (default, free-tier friendly)
  ○ Precision — one detail call per gene (best quality, ~15–20× more API calls)
  ○ Hybrid — one detail call per gene with context caching (best quality, moderate cost, requires paid tier)
```

**Threading the setting through the stack** — same pattern as `parallelAnalysis`
(see `memory-sessions.md` 2026-04-07):

1. `settings-store.ts` — add `extractionMode: "economy" | "precision" | "hybrid"`.
2. `preload/index.ts` — expose via `window.api.settings`.
3. `useSettings.ts` — React hook.
4. `python-bridge.ts` — pass as env var `EXTRACTION_MODE`.
5. `config.py` — read at module load.
6. `gemini_extractor.py` — branch in `extract_gene_info()`:
   - Economy: existing batched call (unchanged).
   - Precision: loop over `self.associations`, one call per gene with the paper text
     re-sent each time. Collect results into the same output DataFrame structure.
   - Hybrid: on first gene, call Gemini `CachedContent.create()` with the paper text
     + CRITICAL INSTRUCTIONS ([docs](https://ai.google.dev/gemini-api/docs/caching)).
     Subsequent per-gene calls reference the `cached_content` ID. TTL scoped to the
     worker's paper (few minutes — well under the 5-minute min).
7. **Merge the results identically downstream** — the detail-extraction output has the
   same shape regardless of mode, so grounding check, corroboration gate, evidence
   gate, and CSV writer are unchanged.

### What changes and what doesn't

**Changes:** `extract_gene_info()` branches. The 9 CRITICAL INSTRUCTIONS could be
trimmed in precision/hybrid mode — instructions #1, #3, #9 (the row-repetition ones)
become no-ops per-gene. But keep them in economy mode unchanged.

**Does not change:** candidate discovery (Steps 0.5, 1, 1b, 1.1, 1.25, 1.5), grounding
check, corroboration gate, evidence gate, validation, CSV output. Those all consume
`self.associations` and the resulting rows — mode-agnostic.

### Risks and caveats

- **Cached-context TTL and eviction.** Gemini context caching has a minimum 5-minute
  TTL. If a paper's extraction finishes in under 5 minutes (likely), the cache is paid-
  for even after we're done. On a many-paper run this averages out; on a 1-paper run
  it's wasted cost. Mitigation: documentation, not code.
- **Parallelism interaction.** `parallelAnalysis` (Codex-era feature, already shipped)
  parallelises *papers*. Per-gene mode could also parallelise *genes within a paper*,
  but 15 RPM rate limits on free tier would make this counterproductive. Scope this
  as a future enhancement.
- **Output row count.** Economy mode sometimes collapses multiple variant rows of the
  same gene into one row when Gemini lazy-fills across rows. Per-gene mode will emit
  strictly one row per `(gene, variant)` pair. This is *better* behaviour but would be
  a visible diff in benchmark outputs — flag in `AUDIT.md` when the mode is introduced.
- **Cache security.** Cached content is scoped to the API key. Users with multiple keys
  (research lab sharing) would get separate caches. Not a security issue, just a
  cost-sharing nuance.

### Suggested action

- [ ] Land in two phases to de-risk:
  - **Phase 1:** Ship *precision* mode (per-gene, no caching). Simplest diff. Validates
    the branching logic in `extract_gene_info` and the settings plumbing.
  - **Phase 2:** Ship *hybrid* (per-gene with context caching). Layered on top of the
    Phase 1 branching.
- [ ] Before shipping: run both modes on the benchmark set (`pipeline/data/benchmark/`)
      and compute F1 / citation coverage / Cohen's κ. This is the argument for F7 in
      the SoftwareX paper ("user-selectable extraction modes with characterised
      precision/cost trade-off"). A real table comparing the three modes would be a
      publication-worthy figure.
- [ ] Trim redundant CRITICAL INSTRUCTIONS in precision/hybrid mode. Specifically
      instructions #1, #9 (row-independence, row-repetition) can be removed — keep
      the disambiguation clause, verbatim numbers, gene-named citations.
- [ ] Add a user warning in the UI when the selected mode + API key combination is
      likely to hit rate limits (e.g., precision mode + free-tier Gemini + >5 papers).

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P4 tier — L effort. Largest single item in the audit list.

**Why this is both architectural and pragmatic:** the pipeline's current reliance on
ONE big batched Gemini call per paper is the root cause of multiple observed
pathologies — F10a (citation cross-contamination drove its creation via the C22
sprint), F11 (quota failure → all rows lose context together), F12 (co-mention
snippet duplicated across rows), several of the 9 CRITICAL INSTRUCTIONS in the Stage 3
prompt exist solely to mitigate batching artefacts.

**Two-phase plan** (ship incrementally):

**Phase 1 — Precision mode** (per-gene, no caching).
- New setting in `Settings.tsx` Performance section, mirroring the existing
  `parallelAnalysis` wiring (see `memory-sessions.md` 2026-04-07 for the pattern).
- Settings plumbing: `settings-store.ts` → `preload/index.ts` → `useSettings.ts` →
  `python-bridge.ts` (as env var) → `config.py` (as flag).
- In `gemini_extractor.py::extract_gene_info`, branch on the mode. Economy = current
  batched call (unchanged). Precision = loop over `self.associations`, one Gemini
  call per gene, each with full paper text + JUST that one gene's `{gene, variant}` in
  the Associations JSON.

**Phase 2 — Hybrid mode** (per-gene + Gemini context caching).
- On first gene of a paper, call `genai.CachedContent.create()` with the paper text +
  CRITICAL INSTRUCTIONS. TTL scoped tight (Gemini's minimum is 5 min — accept the
  waste on fast runs).
- Subsequent per-gene calls reference the `cached_content` ID. Dramatically reduces
  token cost — only the gene-specific portion is paid per call.
- See [Gemini context caching docs](https://ai.google.dev/gemini-api/docs/caching) —
  the API has been stable for this for a while.

**Trim redundant CRITICAL INSTRUCTIONS in precision/hybrid mode:**
Instructions #1 (gene independence), #9 (no-row-repetition) exist solely because of
batching. Remove them when `extraction_mode != "economy"`. Keep disambiguation clause,
verbatim numbers, gene-named citations.

**Risks to flag in the UI:**
- Free-tier Gemini with precision + >5 papers will hit daily quota fast (20 req/day,
  precision = ~1 req/gene/paper).
- Cache TTL of 5 min means the full-paper context expires quickly on slow runs.

**Before shipping:** run both modes on the benchmark (`pipeline/data/benchmark/`) and
compute F1 / citation coverage / Cohen's κ per mode. This is publication-worthy data
for SoftwareX — "user-selectable extraction modes with characterised precision/cost
trade-off."

---

## F6 — Greek letter transliteration is asymmetric between body and abstract

**Date:** 2026-04-19
**Source:** Tracing how paper text reaches Gemini at the abstract pass (Section 8).
**Severity:** Potential silent extraction loss at the grounding check. Needs empirical
verification — not yet confirmed as reproducible in a real run.

### What we expected

The W1 fix in `AUDIT.md` made Greek letters work correctly in paper text by transliterating
them (`α → alpha`, `β → beta`, `μ → mu`) before downstream stages see the content. This is
medical-accuracy-critical — haematology papers discuss α-globin, β-thalassemia, γ-heavy
chain constantly.

The implicit assumption: **every copy of a paper's text seen by Gemini is cleaned the
same way.**

### What we found

The cleaning is applied in exactly one place —
[`full_text_fetcher._clean_and_validate_content`](pipeline/modules/full_text_fetcher.py:676)
— which only runs on the paper **body text** path (PMC JATS XML / Europe PMC). It does
**not** run on abstracts.

The abstract that Gemini sees in Step 0.5 (abstract pass) comes from a different source:
`paper_details[pmid]["abstract"]`, populated by
[`pubmed_data_collector.fetch_paper_details`](pipeline/modules/pubmed_data_collector.py:249)
from the Medline `AB` field. That path never calls `_clean_and_validate_content` and has
no Greek-letter transliteration of its own.

So for the same paper, within the same run, Gemini sees:

| Surface | Greek letters |
|---|---|
| Abstract (Step 0.5) | **Raw** — `α-globin`, `β-thalassemia`, `μg` |
| Body text (Step 1 / 1b / 1.25) | **Transliterated** — `alpha-globin`, `beta-thalassemia`, `mug` |

### Why it matters

The LLM itself is robust to this — Gemini treats `α-globin` and `alpha-globin` as
semantically equivalent, and the final gene symbol `HBA1` is emitted either way. So the
**discovery** side is probably fine.

The risk is in the **grounding check**
([`gemini_extractor.py:1447`](pipeline/modules/gemini_extractor.py:1447) — the primary
hallucination filter documented in `memory-pipeline.md` §Stage 5). Per that doc:

> *Uses canonical symbol + all HGNC aliases + raw LLM labels (e.g., "BNP" for NPPB).*
> *Do not check only the canonical symbol — raw labels are essential.*

If Gemini picks up `HBA1` from the abstract and emits the raw label `α-globin` (because
that's what the abstract said), the grounding check then searches the **body text**,
which has been transliterated to `alpha-globin`. The search for `α-globin` in
`alpha-globin`-cleaned text can fail — silently dropping a correctly-extracted gene.

This is the exact failure mode the grounding check was designed to catch for hallucinated
genes, misfiring on real ones because of text-normalisation drift between two code paths.

### Why it's marked "unconfirmed"

Two mitigations that may absorb most real-world occurrences:

1. **Gemini normalises in its output.** When the abstract says `α-globin`, Gemini often
   returns raw_label as `HBA1` (already canonical) rather than the Greek form — so there's
   no Greek mismatch to fail against.
2. **HGNC aliases are checked too.** The grounding check walks all aliases for `HBA1`
   (`HBA-A1`, `HBH`, etc.). At least one of those is usually ASCII-safe and will match.

So the failure mode is likely rare but real — and it's the kind of rare-but-real failure
that bites haematology papers specifically, which is exactly the population W1 was
supposed to protect.

### Suggested action

- [ ] **Verify with a known-good paper.** Pick a haematology paper with α-globin /
      β-thalassemia in the abstract (PMID 28077840 or similar). Run it through the
      pipeline with debug logging on `self.dropped_candidates`. Check whether any
      legitimately-extracted gene was dropped by the grounding check for reasons that
      trace back to Greek-letter mismatch.
- [ ] **If confirmed, apply `_clean_and_validate_content` to abstracts too** — either in
      `fetch_paper_details` or at the `_prepare_paper_inputs` boundary. Symmetry between
      the two text surfaces is the correct fix; trying to handle it inside the grounding
      check would be more complex and more fragile.
- [ ] **If unconfirmed after realistic testing**, document the asymmetry in
      `memory-pipeline.md` as a known limitation rather than a bug, so future Claude
      sessions don't have to rediscover this trail.
- [ ] Separate, smaller todo: step 3 of the cleaning (`[^\x00-\x7F\t\n]+`) strips *any*
      non-ASCII — not just Greek. German umlauts in author names (if they appear in the
      body text as cited reference), non-Latin transliteration, emoji. Usually fine,
      worth noting because it's aggressive.

### Implementation notes (session continuity)

**Status:** ⬜ TODO (unconfirmed in production). P1 tier — S effort.

**Verify first:** before fixing, reproduce on a haematology paper. Candidate PMIDs:
28077840 (α-thalassemia), any paper discussing β-globin or γ-heavy chain in the
abstract. Run with `--trace-pmid`, inspect `drop_debug.json` for any
`rejected_ungrounded` drops whose `raw_gene_labels` contain Greek letters. If no
drops fit this pattern, downgrade this finding to "documented limitation" rather than
a real bug.

**Fix if confirmed:**
- Apply `_clean_and_validate_content` to `abstract_text` in
  `pipeline/modules/pipeline_orchestrator.py::_prepare_paper_inputs` (~line 392), OR in
  `pubmed_data_collector._normalize_pubmed_record` (~line 82) as the abstract is first
  extracted from the Medline AB field.
- Cheapest: at `_prepare_paper_inputs`, do `abstract = _clean_and_validate_content(abstract, url="")[0]`
  before passing to the worker.
- Cleaner: in `_normalize_pubmed_record`, apply Greek transliteration + ASCII coercion
  to the abstract text consistently with what happens to body text. This ensures
  every downstream consumer sees the same normalisation.

**Cross-reference:** F10a (encoding drift in citation validator) has overlapping cause —
a unified normaliser that runs on every text surface (abstract, body, citation candidate)
would close both F6 and F10a.

---

## F5 — PubTator response has more annotation types than we consume

**Date:** 2026-04-19
**Source:** Reading `_parse_document` in `pubtator_tool.py` while tracing Stage 4.
**Severity:** Untapped resource, not a bug. Flag for future feature work.

### What we expected

For each batch of PMIDs, PubTator3 returns a BioC JSON document per paper. Our parser
walks the `passages[].annotations[]` list and keeps what's relevant.

### What we found

PubTator3 annotates multiple entity types per document:
`Gene`, `DNAMutation`, `ProteinMutation`, `SNP`, `Chemical`, `Disease`, `Species`,
`CellLine`, and a few minor types. Our parser
([`pubtator_tool.py:243–293`](pipeline/modules/pubtator_tool.py:243)) keeps only:

```python
if ann_type == "gene":                          # → PubTatorGene
elif ann_type in ("variant", "snp", "mutation"): # → PubTatorVariant
# everything else: silently discarded
```

We're paying the full API cost (one batched call fetches all types), NCBI serialises the
whole document, and the parser drops `Chemical`, `Disease`, `Species`, `CellLine` on the
floor.

### Why it matters

This is not a correctness bug — the pipeline's output is gene-and-variant-centric and
rightly so. But the discarded annotations are structured, high-precision, and directly
relevant to extraction quality in several ways:

1. **Pharmacogenomics extraction quality.** Papers like the CPIC guideline PMID 35152405
   (SLCO1B1 / CYP2C9 / ABCG2 for statins) need drug ↔ gene linkage. PubTator's `Chemical`
   annotations would tell us "simvastatin," "rosuvastatin," "warfarin" appear in the text
   — priceless context for the Gemini prompt and for validation.
2. **Gene-disease association context.** `Disease` annotations identify the clinical
   phenotype the gene is being discussed in. Could feed the "Condition" column in the
   extraction schema with zero extra tokens.
3. **Species filter.** `Species` annotations let us distinguish "this gene is discussed in
   the context of mouse studies" vs. "human patient cohort." Currently the pipeline relies
   on HGNC validation to flag mouse-convention symbols *after* extraction (see
   `memory-decisions.md` 2026-02-28 "Mouse symbol flag is informational"). Upstream
   `Species` context would be cheaper and more reliable.
4. **Free data.** The annotations are already in the response body. Adding parsers for
   them is a dozen lines and zero additional API calls.

### Suggested action

Not urgent. Noted here so it's not rediscovered later:

- [ ] Extend `_parse_document` to also collect `PubTatorChemical`, `PubTatorDisease`,
      `PubTatorSpecies` dataclasses (same pattern as `PubTatorGene`).
- [ ] Thread them through `HybridExtractionResult` alongside the existing gene/variant
      lists.
- [ ] Optional downstream uses to evaluate:
      - Feed `Disease` and `Chemical` names into the Gemini Stage 3 prompt as context
        anchors for the "Condition" and "Drug" columns (if user schema has them).
      - Use `Species` annotations as a soft signal in gene validation (e.g., if a paper's
        `Species` list is `Mus musculus` only, raise murine-symbol confidence lower).
      - Expose as optional columns in the CSV for researchers who want them.
- [ ] Cheap to add; ship only when there's a concrete consumer for it — don't add data
      to the pipeline that nothing reads.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P4 tier — M effort. Low urgency, high ceiling.

**Don't ship this without a concrete consumer.** Adding data the pipeline doesn't
read is dead weight. Ship alongside one of:
- F9 fix — PubTator's `Disease` / `Chemical` annotations feed the corroboration gate
  to distinguish table-only genes that have context vs ones that don't.
- A per-column user schema change — e.g., a "Drug" column in the user schema would
  immediately benefit from `Chemical` annotations as seed data.

**Code location:** `pipeline/modules/pubtator_tool.py::_parse_document` (~line 231).
Current code only branches on `ann_type in ("gene", "variant", "snp", "mutation")`.

**Minimal extension:**
```python
# Add new dataclasses alongside PubTatorGene and PubTatorVariant:
@dataclass
class PubTatorChemical: text: str; identifier: Optional[str]; locations: List[Dict]
@dataclass
class PubTatorDisease: text: str; identifier: Optional[str]; locations: List[Dict]
@dataclass
class PubTatorSpecies: text: str; taxon_id: Optional[str]; locations: List[Dict]
```

Then branch in `_parse_document`: `elif ann_type == "chemical"`,
`elif ann_type == "disease"`, `elif ann_type == "species"`. Thread through
`HybridExtractionResult` as new fields.

**Cost:** zero additional API calls — this data is already in the BioC JSON response
we pay for. Pure parsing.

---

## F4 — Redundant fetches across the UI/pipeline boundary

**Date:** 2026-04-19
**Source:** End-to-end per-PMID fetch inventory (Section 5 of `pipeline-understanding.md`).
**Severity:** Efficiency bug. Wastes API quota, slows pipeline start, risks NCBI rate limits
on large batches.

### What we expected

When the user is browsing papers in `TopicResultsModal`, the UI already fetches metadata,
abstracts, and citation counts for every paper on the current page. A sensible system would
pass that data forward when the user clicks **Run**, so the pipeline can start with what
the UI already paid for.

### What we found

**Nothing is handed forward.** Only PMIDs cross the UI → pipeline boundary (see Section 1
of `pipeline-understanding.md`). The pipeline re-fetches everything from scratch, often
from *different* endpoints of the *same* service. For a paper the user just looked at, the
pipeline hits:

| Data | UI already fetched via | Pipeline re-fetches via | Format change |
|---|---|---|---|
| PubMed metadata (title, journal, authors, year, DOI, PMC) | NCBI `esummary.fcgi` (JSON) | NCBI `efetch.fcgi?rettype=medline` (Medline text) | JSON → Medline text |
| Abstract | NCBI `efetch.fcgi?rettype=abstract&retmode=xml` (XML) | Extracted from the same Medline response above | XML → text |
| Citation count | NIH iCite `/api/pubs` (JSON) | NIH iCite `/api/pubs` (JSON) — lazy, only when ranking or fallback | **Same endpoint, same format, same service** |

Three separate parsers handle what is essentially the same bibliographic record. The second
iCite call is especially wasteful — identical URL, identical params, identical response,
fetched again because the pipeline has no channel to receive the UI's copy.

### Concrete cost per run

For a **10-PMID user-curated run** (a typical "I want to extract genes from these papers"
workflow):

- UI fetches during selection: **3 calls** (esummary, efetch-abstracts, iCite — all batched)
- Pipeline re-fetches on start: **2 calls** for the same data (efetch Medline, iCite). Plus
  8 that genuinely couldn't have been prefetched (PMC XML, supplementary, figures, PubTator).

For a **100-PMID run** the redundant calls stay at 2 (both batched), but each one now covers
100 PMIDs — so the real cost is "~5 seconds of cold-start latency" and "2× the NCBI quota
burn on metadata."

For NCBI's default rate limit of 3 req/sec (no API key), this doesn't throttle. With the
`ENTREZ_API_KEY` ceiling of 10 req/sec, still fine. But the same pattern applied to every
pipeline stage is cumulative — the pipeline currently starts with an unnecessary round-trip
to a service it will hit many more times.

### Why it matters

1. **Fast-run degradation.** Every UX that encourages "quick re-runs" (re-queue a paper,
   retry failed extractions, compare runs) pays the redundant cost each time.
2. **Free-tier user impact.** Users without an `ENTREZ_API_KEY` are capped at 3 req/sec.
   The redundant metadata fetch is one of those three slots, during the critical
   pipeline-start moment where responsiveness matters most.
3. **Hidden inconsistency risk.** The UI's esummary JSON and the pipeline's Medline text
   return overlapping but **not identical** field sets (e.g. esummary's `pubtype` array vs.
   Medline's `PT` field; esummary's truncated `authors[0..3]` vs. Medline's full `AU` list).
   Any code that *thinks* it's comparing "the same paper as the UI showed" against what
   the pipeline processed has to reconcile two formats.
4. **Contradicts F3's fix path.** If we want to implement DOI → PMID resolution (F3),
   doing it in the UI now and passing the resolved PMID forward is cheaper than making the
   pipeline do it too.

### Suggested action

Two reasonable strategies — pick one, don't half-do it:

- **(A) Forward the UI's data.** Extend the `startPipeline(args)` IPC contract
  ([`python-bridge.ts:64`](app/src/main/python-bridge.ts:64)) to accept a pre-fetched
  metadata bundle (`{ [pmid]: { title, journal, doi, pmc, citations } }`), serialise it to
  a temp file, pass the path via env var, and let the pipeline consume it in place of the
  esummary/iCite refetches. Bonus: lets the pipeline skip the metadata fetch entirely when
  the UI provided everything.
  - Pro: one-off metadata fetch per paper per session, cleanest.
  - Con: requires adding a data channel; must handle stale data if user waits a long time
    between selecting and running (realistically not a concern — titles/authors don't change).

- **(B) Accept the redundancy, but only within the pipeline.** Pick one endpoint in the
  pipeline and stick with it. Currently the pipeline uses Medline text (#4) to get metadata
  and also reads abstract from PMC JATS XML (#5). Simpler: use efetch-XML like the UI
  does, parse once, use everywhere. Eliminates the Medline parser and one redundancy inside
  the pipeline, even if UI and pipeline still both hit NCBI.
  - Pro: much smaller change; no new IPC plumbing.
  - Con: doesn't remove the UI → pipeline duplicate, only the pipeline-internal one.

- [ ] Decide which (A or B) matches the project's priorities.
- [ ] If (A): add a small invalidation rule — if the PMID bundle is older than, say,
      24 hours, refetch. Cheap safety net.
- [ ] Either way: the second iCite call inside the pipeline (#10 in Section 5.2) is the
      single clearest win. UI has already fetched this for every paper on screen. Even
      without full bundle-forwarding, a `citationCounts` map in `startPipeline` args
      would eliminate one entire fetch stage.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P3 tier — M–L effort. Efficiency only, not correctness.

**Recommended minimal fix — Strategy B first, then consider A:**

- **Strategy B (smaller scope, immediate benefit):** eliminate the pipeline-internal
  duplication. Currently `fetch_paper_details` uses Medline text and the abstract also
  gets extracted from PMC JATS XML. Pick one and use everywhere:
  - `pubmed_data_collector.fetch_paper_details` — switch to esummary JSON (same as UI)
    for consistency. Drop Medline parsing.
  - OR keep Medline but refactor `_normalize_pubmed_record` to be the single source of
    truth and feed the UI from it.
- **Strategy A (cleanest but bigger):** extend the IPC contract.
  - `app/src/main/python-bridge.ts::startPipeline` accepts a `pre_fetched` bundle.
  - Serialise to a JSON file in the run's output dir, path passed via env var.
  - `pipeline_orchestrator` reads the file if present, skips the corresponding
    fetches.

**Cheapest immediate win (ship before either strategy):** the 2nd iCite call in the
pipeline. Pass UI's `{pmid → citation_count}` map through `startPipeline` args.
Pipeline's `fetch_citation_counts_with_fallback` checks the map first, falls back to
iCite API only for PMIDs not in the map.

**Subtle risk:** staleness. UI fetches happen when the user is browsing; pipeline
runs later (possibly much later if the user dwells). For titles/authors this is fine
(they don't change). For citation counts, this might be fine too (monthly update
cadence from iCite). Document the staleness acceptance.

**Data point for planning:** on PMID 41017238, the pipeline spent ~1s each on
`fetch_paper_details` and `fetch_icite_citation_counts`. Not a lot. The win is
visible mainly on large multi-paper runs.

---

## F3 — DOI and PMC ID inputs are silently dropped from user-defined lists

**Date:** 2026-04-19
**Source:** Walking through a realistic paste-box input end-to-end.
**Severity:** Silent data loss at an entry boundary. UX correctness bug.

### What we expected

The "Specific Papers" paste box
([`SmartInput.tsx`](app/src/renderer/components/SmartInput.tsx)) explicitly advertises
support for four identifier formats in its placeholder text:

> *"Paste PMIDs, DOIs, PMC IDs, or PubMed URLs"*

…with examples including `DOI: 10.1234/example`. The parser recognises all four types and
the validated-papers UI displays them all. A user has every reason to expect all four to
reach the pipeline.

### What we found

Only PMID-classified entries reach the pipeline. The drop happens in two places:

1. [`SmartInput.tsx:184`](app/src/renderer/components/SmartInput.tsx:184) —
   `useValid()` returns only `papers.filter(p => p.pmid)`.
2. [`QueryBuilder.tsx:164`](app/src/renderer/pages/QueryBuilder.tsx:164) —
   `specificPapers.map(p => p.pmid).filter(Boolean)` strips again.

No reverse lookup is attempted. DOI → PMID and PMC → PMID conversions both exist as trivial
NCBI API calls (`esearch?term={doi}[AID]` and `elink` respectively) but neither is wired in.

Concrete trace with `PMC9035072` and `10.1038/nature12373` pasted:
- Parser tags them `pmc` and `doi` — correctly identified.
- `fetchDetails` is only called for `pmid`-typed entries, so no metadata lookup happens.
- The UI's validated-papers list shows both (with URLs to PMC/doi.org), implying they're accepted.
- On **"Use these"**, both are silently dropped because they lack `.pmid`.
- The pipeline never sees them.

### Why it matters

1. **UI/behaviour mismatch.** The placeholder says the input accepts DOIs and PMC IDs. The
   code parses them. The validated-papers panel displays them. They appear to be selected.
   They aren't processed. This is the worst-case UX outcome: the system looks like it's
   working and silently fails.
2. **DOIs are how researchers cite papers.** A biomedical researcher building a list from
   a published reference section will most naturally paste DOIs. This path is probably used
   more than raw PMIDs.
3. **Compounds with F2.** Even if a user works around this by pasting only PMIDs, they can
   still feed paywalled PMIDs unchecked (F2). Entry-path validation across the specific-
   papers flow is generally under-enforced.

### Suggested action

- [ ] Implement reverse lookup in `SmartInput.validate()`:
  - DOI → PMID via NCBI esearch `term={doi}[AID]` (single-call, fast, already rate-limited
    on the main process side)
  - PMC ID → PMID via NCBI esummary on `db=pmc` or elink
  - If lookup fails (paper not in PubMed), surface it in the existing `invalid` list with a
    clear reason ("DOI not found in PubMed" / "PMC not indexed in PubMed").
- [ ] Alternatively — and more honestly in the short term — **strip DOI/PMC from the
      placeholder text and parser** until the backend supports them. Better to refuse input
      than accept-and-drop.
- [ ] After fixing, verify `useValid()` and `QueryBuilder`'s merge both consume all items,
      not just those with a `.pmid` field.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P0 tier — M effort.

**Code locations:**
- UI parser: `app/src/renderer/components/SmartInput.tsx` — `parseIdentifiers()`
  recognises 4 types (PMID/DOI/PMC/URL) but `validate()` only resolves PMID-typed
  entries via `window.api.pubmed.fetchDetails`.
- Drop site #1: `SmartInput.tsx::useValid` (~line 184) — `papers.filter(p => p.pmid)`.
- Drop site #2: `QueryBuilder.tsx` (~line 164) — second filter on the merge.

**Recommended fix — reverse lookup in `SmartInput.validate()`:**
- DOI → PMID: NCBI esearch with `term={doi}[AID]`. One call per DOI.
  - Example: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=10.1038%2Fnature12373[AID]&retmode=json`
- PMC → PMID: `elink.fcgi?dbfrom=pmc&db=pubmed&id={PMCID}` or esummary on db=pmc.

**IPC additions needed:**
- New `pubmed:resolve-doi` handler in `app/src/main/ipc-handlers.ts` (wraps the esearch call).
- New `pubmed:resolve-pmc` handler (wraps the elink call).
- Preload exposes as `window.api.pubmed.resolveDoi` and `.resolvePmc`.

**Fallback (if backend work is blocked):** strip DOI / PMC / URL from the placeholder
text and the parser. Better to refuse the input than accept-and-drop. One-line
placeholder edit + remove the doi/pmc branches in `parseIdentifiers()`.

**Validation after fix:**
- Paste mixed input: `12345678\nDOI:10.1038/nature12373\nPMC9035072`. All three
  should resolve to PMIDs (or surface a clear "not in PubMed" error for that one).
- `useValid()` should pass all three PMIDs to the pipeline.

**Cross-reference:** F2 (OA invariant) and F3 both live in SmartInput's entry path.
Consider fixing together — the DOI→PMID lookup and the OA-check can share one IPC
round trip.

---

## F2 — "All papers are OA" is not actually enforced on all entry paths

**Date:** 2026-04-19
**Source:** Tracing paper selection paths vs. the OA filter.
**Severity:** Architectural invariant violation. Silently degrades extraction quality.

### What we expected (and what the code assumes)

The project principle — repeated in code, docs, and the SoftwareX paper — is that the pipeline
is **OA-only**: every paper reaching full-text extraction has freely available full text.
The pipeline's architecture depends on this:

- [`pipeline/modules/full_text_fetcher.py:1–14`](pipeline/modules/full_text_fetcher.py) opens
  with an explicit guarantee:
  > *"Since the PubMed search step filters to open-access papers only (ENABLE_OA_FILTER=True),
  > every PMID that reaches this module is guaranteed to have free full text."*

  On the strength of that guarantee, Playwright, Trafilatura, paywall detection, and
  publisher-specific scrapers were all removed as "unreachable dead code" (F5 in `AUDIT.md`).

### What we found

The guarantee holds for **two of three** entry paths. The third silently bypasses it.

| Entry path | OA filter applied? | Where |
|---|---|---|
| Topic search (query) | ✅ Yes | `search_pubmed()` appends `"loattrfull text"[sb]` ([`pubmed_data_collector.py:169–182`](pipeline/modules/pubmed_data_collector.py:169)) |
| Author search | ✅ Yes | `search_pubmed_by_author()` delegates to `search_pubmed()` ([`pubmed_data_collector.py:244`](pipeline/modules/pubmed_data_collector.py:244)) |
| **Specific PMIDs (paste box)** | ❌ **No** | [`SmartInput.tsx`](app/src/renderer/components/SmartInput.tsx) calls `pubmed:fetchDetails` but never gates on the `pmc` field; the PMIDs flow straight to `mandatory_pmids` ([`pipeline_orchestrator.py:685`](pipeline/modules/pipeline_orchestrator.py:685)) and are explicitly exempt from filtering |

A user pasting a paywalled PMID (e.g. NEJM, old papers pre-PMC deposit) gets that paper
accepted into the run with no warning. When it reaches `full_text_fetcher`:

- Both OA endpoints (PMC efetch, Europe PMC) return nothing
- The fetcher returns an empty `ContentExtractionResult` with
  `extraction_method="no_oa_full_text"` ([`full_text_fetcher.py:934–945`](pipeline/modules/full_text_fetcher.py:934))
- A `logger.warning` is emitted — not surfaced in the UI's main log stream
- The paper contributes empty content to downstream stages; the user sees a "fetch failed"
  count but not *why*

### Why it matters

1. **The architectural claim underpinning Playwright removal is false.** F5 in AUDIT.md
   justified deleting the paywall-handling code because "the OA filter upstream makes this
   unreachable." That filter doesn't cover the specific-PMIDs path, so the code was reachable
   — the removal happens to be OK only because the failure mode is "silently produce nothing"
   rather than "crash."
2. **Silent quality degradation.** A researcher pasting a list of key papers for a review
   may have no idea that some of them were dropped to abstract-only. This is exactly the
   "silent failure at screening" failure mode flagged as unacceptable in `CLAUDE.md`.
3. **The UI signal already exists but isn't enforced.** `TopicResultsModal` uses the `pmc`
   field as an OA proxy for badge colour — the same check could gate `SmartInput`.
4. **Existing precedent confirms the problem.** The benchmark gold standard notes PMID
   21076407 as "paywalled → 0 genes extracted" (memory-sessions.md). That paper is in the
   benchmark precisely because someone pasted its PMID without the OA gate stopping it.

### Suggested action

- [ ] Decide the enforcement point. Options:
  - **UI gate (preferred):** `SmartInput.tsx` rejects pasted PMIDs where `fetchDetails`
    returns no `pmc` field, with a clear "not open-access" error. Mirrors the topic-search
    badge logic.
  - **Pipeline gate:** `pipeline_orchestrator.py` filters `specific_pmids` by `pmc`
    presence after `fetch_paper_details`. Less friendly — user only learns mid-run.
  - **Both:** UI prevents the common case, pipeline as defence-in-depth.
- [ ] Decide whether author search should use a stricter OA check too (currently relies on
      `[Author]` + `loattrfull text[sb]`, which is correct but worth re-confirming).
- [ ] If the rejection is a hard "no," the orchestrator/full-text fetcher should also
      explicitly surface `no_oa_full_text` papers to the UI (not just a warning) so the user
      knows which papers contributed nothing.
- [ ] Revise `full_text_fetcher.py`'s opening comment — the guarantee claim is currently
      wrong and future contributors will rely on it.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P0 tier — S–M effort. Ship with F3 as a single SmartInput pass.

**Preferred approach — UI-level gate in `SmartInput.tsx`:**
After `fetchDetails()` resolves each pasted PMID, check each entry's `pmc` field.
Mirror the topic-search modal's logic: absence of `pmc` → "Abstract only" badge.
For the paste box, escalate: show an error chip next to the PMID saying
*"Paywalled — not open access. Removed from selection."*

**Implementation sketch:**
```typescript
// inside validate(), after fetchDetails resolves:
const oaItems = validPapers.filter(p => p.pmc || !p.pmid);  // keep non-PMID rows
const paywalledItems = validPapers.filter(p => p.pmid && !p.pmc);
setInvalid([...unknowns.map(u => u.original),
            ...paywalledItems.map(p => `PMID ${p.pmid} — not open access`)]);
setPapers(oaItems);
```

**Backup gate at pipeline level** (defence in depth):
In `pipeline_orchestrator.py::run_complete_pipeline`, after `fetch_paper_details`,
filter `specific_pmids` to those with a `pmc` field populated. Log dropped PMIDs with
a clear "excluded — not open access" reason and surface the count in pipeline_stats.

**Also fix the misleading comment:** `pipeline/modules/full_text_fetcher.py:1–14`
currently states the OA guarantee as if enforced. Revise to note the one bypass path
and reference F2.

**Cross-reference:** part of the same entry-path hardening as F3. Plan a single
"SmartInput entry hardening" task that does both.

**Don't ship without:** a clear user-visible indication when a pasted PMID is
rejected for OA reasons. Silently dropping would be worse than the current silent
downgrade.

---

## F1 — The "4× overfetch factor" does not exist in code

**Date:** 2026-04-19
**Source:** Tracing the handoff from user paper selection → `pipeline_orchestrator.run_pipeline()`.
**Severity:** Documentation inaccuracy. No runtime impact. Affects publication correctness.

### What we expected

Documentation in multiple places claims the pipeline applies a 4× overfetch factor — "if the
user asks for 10 papers, 40 are analysed" — to compensate for paywalled papers and failed
extractions.

References asserting this:
- [`.claude/rules/memory-decisions.md:164`](.claude/rules/memory-decisions.md:164) —
  "mitigated by overfetch factor (4x)"
- [`docs/pipeline-internals.md:369`](docs/pipeline-internals.md:369) —
  "`ANALYSIS_OVERFETCH_FACTOR=4` … fetches and analyzes 40 candidates"
- [`docs/pipeline-internals.md:1122`](docs/pipeline-internals.md:1122) — config table
- [`docs/reports/pipeline-report.tex:319`](docs/reports/pipeline-report.tex:319)
- [`publication/sections/02_description.tex:14`](publication/sections/02_description.tex:14) —
  "an overfetch factor of 4× ensures sufficient open-access papers reach extraction"
- [`publication/working/MEETING_NOTES_2026-03-09.md:219`](publication/working/MEETING_NOTES_2026-03-09.md:219)
- Several Elicit-research notes in `publication/working/elicit_research/`

### What we found

- `ANALYSIS_OVERFETCH_FACTOR = 4` is defined in
  [`pipeline/modules/config.py:158`](pipeline/modules/config.py:158), but
  **not referenced anywhere else in the codebase** (grep confirmed: single occurrence).
- The only candidate-widening mechanism that actually runs is
  `PUBMED_RELEVANT_COUNT = 200` in
  [`pipeline_orchestrator.py:710`](pipeline/modules/pipeline_orchestrator.py:710),
  which pulls up to 200 candidates from PubMed — **independent of `top_n`, not a multiplier**.
  It only fires when the user provides a search query.
- For a user-curated PMID list,
  [`pipeline_orchestrator.py:685`](pipeline/modules/pipeline_orchestrator.py:685) treats
  every `specific_pmid` as `mandatory_pmids`. All are included, none are added. 1:1.

### Why it matters

1. **Publication accuracy.** `02_description.tex` makes a claim about system behaviour that
   the system does not implement. Reviewers running the code would find this out.
2. **Design rationale drift.** The memory-decisions entry frames overfetching as a deliberate
   mitigation for OA paywalls (~40–60% of PubMed). If the team ever *needs* that mitigation,
   they'd assume it's already in place — and it isn't.
3. **Conceptually incoherent for curated lists.** Overfetching a hand-picked list would defeat
   the point of user curation. The code correctly does not do this; the docs confusingly imply
   it would.

### Suggested action

- [ ] Decide: implement the overfetch, or remove the claim.
  - If implementing: only applies to query-mode runs; `specific_pmids` must remain 1:1.
  - If removing: it's likely the right call — `PUBMED_RELEVANT_COUNT=200` already gives a
    substantial candidate pool on query-mode, and PMID-mode should trust the user.
- [ ] Update `publication/sections/02_description.tex` before submission.
- [ ] Remove/correct references in `memory-decisions.md`, `docs/pipeline-internals.md`,
      `docs/reports/pipeline-report.tex`, `publication/working/*`.
- [ ] Either delete `ANALYSIS_OVERFETCH_FACTOR` from `config.py` or wire it up — don't leave
      orphaned config.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P2 tier — S effort. Doc-only cleanup, no code behaviour changes.

**Decision already taken during audit:** remove the claim. `PUBMED_RELEVANT_COUNT=200`
is the real candidate-widening mechanism; `specific_pmids` are always 1:1. The
overfetch-factor story was never implemented and doesn't match user intuition for
curated lists.

**Exact edits needed** (search for "overfetch" globally first to catch anything
added since this audit):

| File | Line / section | Edit |
|---|---|---|
| `.claude/rules/memory-decisions.md` | :164 | Strike "mitigated by overfetch factor (4x)". Add note that OA-gap mitigation is via `PUBMED_RELEVANT_COUNT=200`. |
| `docs/pipeline-internals.md` | :369, :1122 | Remove the ANALYSIS_OVERFETCH_FACTOR description. Replace with accurate description of `PUBMED_RELEVANT_COUNT`. |
| `docs/reports/pipeline-report.tex` | :319, :609 | Same edits; this is the PDF version of pipeline-internals. |
| `publication/sections/02_description.tex` | :14 | **Must be fixed before submission.** Rewrite the one-liner that claims the 4× factor. |
| `publication/working/MEETING_NOTES_2026-03-09.md` | :219 | Historical note — mark as superseded rather than rewriting. |
| `publication/working/elicit_research/03_semantic_search.md` | :60, :70 | Frame as "RS's candidate-widening via `PUBMED_RELEVANT_COUNT`" rather than "overfetch factor". |
| `publication/working/elicit_research/04_search_vs_vectordb.md` | :48, :56 | Same. |
| `publication/working/elicit_research/06_keyword_search.md` | :46 | Same. |
| `pipeline/modules/config.py` | :158 | Delete `ANALYSIS_OVERFETCH_FACTOR = int(os.getenv("ANALYSIS_OVERFETCH_FACTOR", "4"))`. |

**Verification after fix:** `grep -r "overfetch\|ANALYSIS_OVERFETCH" .` should return
only historical references in `Final_Audit.md` (this file) and
`memory-sessions.md` (session log — leave historical entries intact).

**Cross-reference:** F2/F3 (specific-PMIDs entry hardening) is orthogonal — both are
about user-curated lists but F1 is purely cosmetic docs cleanup.

---

## P5-L1 — Orchestrator helpers observed name-only, add to watchlist

**Date:** 2026-04-20
**Source:** PMID 41017238 audit (Section 3 function coverage matrix).
**Severity:** LOW (tool quality). Fix delivers higher-value rows in the interactive viewer.

### What we found

Seven orchestrator-side functions are captured in the function trace (green-checked
in the viewer's row list) but without `arg_values` / `return_value` because they're not in
`_FN_TRACER_VALUE_CAPTURE`. Each does meaningful per-row transformation worth inspecting:

1. `pipeline_orchestrator._finalize_paper_result` — adds Gene Source, NCBI ID, full name,
   aliases, chromosome per row. First-class candidate; the "shape" of each output row.
2. `pipeline_orchestrator._get_citation_record` — resolves PMID → iCite/SemanticScholar
   record per row.
3. `pipeline_orchestrator._write_split_output` — returns the 4 output-artefact paths.
4. `pipeline_orchestrator._run_pipeline_worker` — the boundary between orchestrator
   and worker. Seeing its args lets the viewer show exactly what went into the worker
   for a given paper.
5. `pipeline_orchestrator.get_gene_source`, `get_ncbi_id`, `get_full_name`,
   `get_aliases`, `get_chromosome` — nested closures inside `_finalize_paper_result`.
   Called once per row; would surface per-row enrichment values.
6. `pipeline_orchestrator._agg_variants` — variant-string joiner used in dedup.

### Suggested action

- [ ] Add to `pipeline/modules/pipeline_tracer.py::_FN_TRACER_VALUE_CAPTURE`:
  `_finalize_paper_result`, `_get_citation_record`, `_write_split_output`,
  `_run_pipeline_worker`, `get_gene_source`, `get_ncbi_id`, `get_full_name`,
  `get_aliases`, `get_chromosome`, `_agg_variants`.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P5 tier — XS effort. One-file edit.

Just append the 10 names to the frozenset in `pipeline_tracer.py`. No other changes
needed; the tracer machinery already handles any function by name. Next run will
capture values for these rows.

Caveat: the 5 nested getter closures (`get_gene_source` etc.) may have `self`-like
closure-captured variables. The tracer's `skip self/cls` guard will filter those out;
actual per-row values will still be captured.

Cross-reference: ship together with L2 (one commit, one watchlist diff).

---

## P5-L2 — `_collect_debug_artifact` high-value missing from watchlist

**Date:** 2026-04-20
**Source:** PMID 41017238 audit.
**Severity:** LOW (tool quality). Single highest-value addition to the watchlist.

### What we found

`gemini_extractor._collect_debug_artifact` (line 436) returns the complete
`candidate_meta` state at end-of-run — every candidate's full provenance, drop reason,
normalisation applied, raw labels, sources set, validation_outcome. It's the same data
that gets written to `drop_debug_*.json`.

In the viewer, clicking this row today shows only the function name and types. Adding
it to the watchlist would surface the whole candidate lifecycle in one JSON blob —
effectively turning one click into a full extraction post-mortem.

### Suggested action

- [ ] Add `"_collect_debug_artifact"` to `_FN_TRACER_VALUE_CAPTURE`.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P5 tier — XS effort. Single-line addition.

The `summarise()` helper will handle the return value gracefully — it's a dict; max
sizes will cap output at ~30 candidate previews. If a run has more than 30 candidates,
the viewer shows a previewed sample with length counts, not the full list. That's OK
because the full data still lives in `drop_debug_*.json` on disk.

Ship together with L1 — one `_FN_TRACER_VALUE_CAPTURE` edit, 11 names added total.

---

## P5-M3 — Function events not linked to stage markers

**Date:** 2026-04-20
**Source:** PMID 41017238 audit trace coverage analysis.
**Severity:** LOW (tool quality / debuggability).

### What we found

The tracer emits two kinds of events to the same live file:
- Stage markers via `pipeline_tracer.capture(node_id, ...)` — one per pipeline stage
- Function events via `sys.setprofile` — one `fn_call` / `fn_return` per function

The viewer currently groups function events into stage windows by timestamp, which is
lossy. A function call that fires 50 ms after the `detail_extraction` stage marker but
before the next stage gets attributed to `detail_extraction` — usually correct, but
edge cases like overlapping worker+orchestrator events get misattributed.

The audit analysis reported `hgnc_validation`, `low_confidence_gate`,
`detail_extraction`, `row_merge` as "empty stages" when in reality the function calls
for those stages WERE captured — they just landed in a neighbouring window.

### Suggested action

- [ ] Add a `stage_id` field to every `fn_call` / `fn_return` event, populated from a
      tracer-level stack that `capture()` pushes/pops. Update the viewer to group by
      stage_id instead of time windows.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P5 tier — S effort.

**Code location:** `pipeline/modules/pipeline_tracer.py`. Add a module-level
`_current_stage` variable set to None. Modify `capture()` to accept an optional
`scope="enter"|"exit"` param — entering a stage pushes its node_id onto a stack;
exiting pops. The `_profile` callback reads the current stage and includes it on
emitted events.

**Viewer-side:** `publication/figures/pipeline-viewer/index.html` — the stage-windowing
logic in the function view should key off `event.stage_id` when present, fall back to
timestamp grouping when absent (for backward compatibility with old trace files).

**Non-goal:** don't try to link worker-side function events to stage markers that
fired in the orchestrator. Separate process, separate stacks. Workers should have
their own stage flow — currently they don't, and that's a bigger change scoped to
F7 (per-gene architecture would natively have per-gene stage markers).

---

## P5-L3 — NCBI enrichment rate-limit silent

**Date:** 2026-04-20
**Source:** PMID 41017238 audit — `"NCBI enrichment: Added metadata for 1/3 genes"`
logged during NCBI Gene rate-limit.
**Severity:** LOW. Silent quality degradation in an enrichment column.

### What we found

`NCBIGeneTool.enrich_gene_symbols` calls NCBI eutils (`esummary.fcgi?db=gene`) per
gene symbol. These calls are rate-limited separately from PubMed eutils — hitting 429
during enrichment produces empty `Gene Full Name`, `Gene Aliases`, `Chromosome` columns
for the affected rows, with no indication why.

On the PMID 41017238 run, 2 of 3 genes got rate-limited and the columns are blank in
the output CSV.

### Suggested action

- [ ] Add a `ncbi_enrichment_status` column per row. Values: `"enriched"`,
      `"rate_limited"`, `"not_found"`, `"skipped"`. Similar to F11's
      `extraction_mode` approach.

### Implementation notes (session continuity)

**Status:** ⬜ TODO. P5 tier — S effort.

**Code location:** `pipeline/modules/pubtator_tool.py::NCBIGeneTool.enrich_gene_symbols`
and the call site in `pipeline_orchestrator.py::_finalize_paper_result`.

**Simple fix:** `enrich_gene_symbols` returns a dict mapping gene symbol →
`NCBIGeneMetadata | None`. In `_finalize_paper_result`, when looking up a gene's
enrichment, record whether the lookup returned metadata or was None/missing, and
surface that as a column.

**Better fix (if we also ship F11-style):** differentiate "rate-limited this run"
(retry next run) from "NCBI has no entry" (won't help to retry). The 429 path in
`enrich_gene_symbols` should tag the row as `rate_limited`; a 200-with-no-result as
`not_found`.

**Cross-reference:** F11 solved the analogous problem for the LLM detail extraction.
The pattern is the same — per-row status column exposing what went wrong with each
data source.

---

## Session handoff notes (for future Claude sessions)

This block captures state that would be painful to rediscover after context compaction.

### Active branch

**`dev/cleanup`** — branched from `main` at commit `b2eb8f5`. Uncommitted changes as
of F11 ship include modifications to `pipeline/modules/gemini_extractor.py` and
`pipeline/modules/pipeline_orchestrator.py`.

### What's on disk but not yet committed

```
M Final_Audit.md                             (this doc + F11/F12 + priority restructure)
M pipeline/modules/gemini_extractor.py       (F11 extraction_mode tagging)
M pipeline/modules/pipeline_orchestrator.py  (F11 confidence + CSV col; earlier worker tracer install + Pool.join fix)
?? docs/audit_pmid_41017238.md               (audit report)
?? python/                                   (stale leftover from python/→pipeline/ rename in commit 16308cf; .DS_Store + .pytest_cache only; safe to ignore)
```

### Recommended next session batch

**Batch 1 — quick wins (~1 hour, all XS–S):**
1. **P5-L1 + P5-L2** — single watchlist edit in `pipeline_tracer.py`, 11 names
2. **F8b** — extend fuzzy separator class in `_find_evidence_snippet`
3. **F8c** — docstring clarification on `_run_grounding_check`
4. **F1** — global sed over the 8 files listed under F1 implementation notes, delete
   orphaned `ANALYSIS_OVERFETCH_FACTOR` from `config.py`

**Batch 2 — higher-impact P0/P1 (~2–3 hours):**
1. **F12** — per-gene snippet search in `_backfill_sparse_row_evidence`
2. **F10a** — pre-validate snippets from our own backfill
3. **F10b** — surface `strict_gate_drops` in metadata CSV

**Batch 3 — entry-path hardening:**
1. **F2** + **F3** together — single SmartInput pass that adds DOI/PMC resolution
   and OA gate

### Key file paths (for quick navigation)

- Tracer watchlist: `pipeline/modules/pipeline_tracer.py::_FN_TRACER_VALUE_CAPTURE`
- Tracer noise blocklist: `pipeline/modules/pipeline_tracer.py::_FN_TRACER_NOISE`
- Confidence scoring: `pipeline/modules/pipeline_orchestrator.py::_compute_row_confidence`
- CSV output: `pipeline/modules/pipeline_orchestrator.py::_write_split_output`
- Paper entry UI: `app/src/renderer/components/SmartInput.tsx`
- Settings IPC chain (F7 sketch): `app/src/main/settings-store.ts` →
  `preload/index.ts` → `useSettings.ts` → `python-bridge.ts` → `config.py`
- Audit report: `docs/audit_pmid_41017238.md`
- Pipeline narrative: `docs/pipeline-understanding.md`
- Interactive viewer: `publication/figures/pipeline-viewer/index.html` + `serve.py`

### Known-good verification commands

```bash
# Pipeline Python files parse cleanly
python3 -c "import ast; [ast.parse(open(f).read(), filename=f) for f in [
    'pipeline/modules/gemini_extractor.py',
    'pipeline/modules/pipeline_orchestrator.py',
    'pipeline/modules/pipeline_tracer.py',
    'pipeline/run_pipeline.py',
]]; print('all OK')"

# Viewer HTML's embedded JS parses (requires node)
node -e "new Function(require('fs').readFileSync('publication/figures/pipeline-viewer/index.html','utf8').match(/<script>([\\s\\S]*)<\\/script>/)[1])" && echo "JS OK"

# _compute_row_confidence smoke test (see F11 implementation notes)
pipeline/.venv/bin/python -c "
import sys; sys.path.insert(0, 'pipeline')
from modules.pipeline_orchestrator import _compute_row_confidence
print(_compute_row_confidence({'Gene/Group': 'X', 'extraction_mode': 'skeleton', 'detail_extraction_error': '429'}, ['x']))
# should print: ('REVIEW', 'LLM failed; no content (429)')
"
```

### Context from previous sessions

- **Worker-level function tracing was added** ~2026-04-20 21:10 (in `_run_pipeline_worker`) —
  without it the trace goes silent during Gemini phase. Verified working in the
  21:32 run of PMID 41017238.
- **Viewer noise blocklist** currently includes 13 entries — XML walkers, poll loops
  (`check_cancellation`, `report_progress`, `emit_log`), tracer self-refs, dunders,
  generator frames, `to_dict`. Removing any of these would flood the trace.
- **Gemini free-tier daily cap** is 20 req/day on `gemini-3-flash`. Every test
  against the live pipeline consumes that budget. Budget often exhausted by end of
  testing session; wait 24 h for reset.
- **The demo trace** at `publication/figures/pipeline-viewer/demo_trace.json` has
  synthetic values pre-populated so the viewer can be exercised without a live run
  or API key.
