# Live Gemini Function Trace - PMID 41017238

Date: 2026-04-26

This report records a live ResearchShop pipeline run with Gemini enabled and
function execution tracing turned on. The run used PMID `41017238`, "The
Etiopathogenesis of Kawasaki Disease: Evolving Understanding of Diverse
Triggers."

No API key or secret value is stored in this report.

## Run Artifacts

Output directory:

`/tmp/rs_trace_41017238_live_fns`

Important artifacts:

- Final CSV: `/tmp/rs_trace_41017238_live_fns/final_enriched_results_d7793f49.csv`
- Final JSON: `/tmp/rs_trace_41017238_live_fns/final_enriched_results_d7793f49.json`
- Metadata CSV: `/tmp/rs_trace_41017238_live_fns/final_enriched_results_d7793f49_metadata.csv`
- Candidate audit: `/tmp/rs_trace_41017238_live_fns/candidate_audit_6b2d3f9e.json`
- Drop debug: `/tmp/rs_trace_41017238_live_fns/drop_debug_c455284b.json`
- Persisted stage trace: `/tmp/rs_trace_41017238_live_fns/trace_41017238.json`
- Raw live event stream: `/tmp/rs_trace_41017238_live_fns/live_events.jsonl`

## Run Summary

- Papers found: 1
- Papers screened: 1
- Papers analyzed: 1
- Final rows: 24
- Tables extracted: 5
- Figures extracted from PMC XML: 2
- Gemini API calls: 3
- Runtime: 61 seconds
- Citation grounding: 92/92 citation fields grounded after evidence backfill
- Strict gate drops: 1 (`LOX1`, below final validation threshold)
- Validation drops: 5 deterministic-only candidates

Final output groups:

| Association group | Rows |
|---|---:|
| Biomarker/Response Signal | 10 |
| Other Candidate Signal | 7 |
| Primary Genetic Association | 3 |
| Mechanistic/Pathway Signal | 3 |
| Figure-Derived Signal | 1 |

Final output association types:

| Association type | Rows |
|---|---:|
| `mechanistic_or_biomarker_gene` | 7 |
| `animal_model_gene` | 7 |
| `susceptibility_gene` | 3 |
| `biomarker_response_gene` | 3 |
| `mechanistic_pathway_gene` | 3 |
| `figure_derived_gene` | 1 |

Confidence:

| Confidence | Rows |
|---|---:|
| HIGH | 3 |
| MEDIUM | 19 |
| REVIEW | 2 |

Final genes:

`AIM2`, `BCL10`, `CARD9`, `CASP3`, `CD14`, `CXCL16`, `EGFR`, `F2`,
`FCGR2A`, `HMGB1`, `ITPKC`, `MALT1`, `MYD88`, `NLRP3`, `NOD1`, `RAG1`,
`RIPK2`, `S100A1`, `TLR2`, `TLR4`, `TLR9`, `TNF`, `TREM1`, `ZBP1`.

## Observed Pipeline Flow

The persisted trace captured 20 stage nodes:

| Order | Node | What happened |
|---:|---|---|
| 1 | `user_selection` | One mandatory PMID selected. |
| 2 | `pubmed_metadata` | PubMed metadata retrieved for PMID `41017238`. |
| 3 | `full_text_fetch` | PMC efetch succeeded; content length 63,309 chars; 2 figures; 5 tables. |
| 4 | `text_cleaning` | Prepared text was normalized and kept ASCII-compatible. |
| 5 | `pubtator_ner` | PubTator found `ITPKC`, `CASP3`, and `FCGR2A`. |
| 6 | `citation_fetch` | Citation record fetched for the paper. |
| 7 | `deterministic_scan` | Deterministic HGNC scan found candidate genes in full text. |
| 8 | `figure_analysis` | Gemini image/caption analysis found 4 figure associations. |
| 9 | `pubtator_merge` | PubTator genes merged into the candidate set. |
| 10 | `candidate_meta` | Candidate accumulator captured for audit/debug. |
| 11 | `grounding_check` | 30 candidates grounded; 2 figure-derived candidates dropped. |
| 12 | `hgnc_validation` | Candidate symbols resolved through validation. |
| 13 | `low_confidence_gate` | No low-confidence validation drops. |
| 14 | `corroboration_gate` | 5 deterministic-only candidates dropped. |
| 15 | `detail_extraction` | Gemini detail extraction returned 25 rows. |
| 16 | `row_merge` | Rows merged by gene/variant. |
| 17 | `evidence_backfill` | 1 sparse row was backfilled from local evidence. |
| 18 | `strict_gate` | `LOX1` dropped below the final validation threshold. |
| 19 | `citation_validation` | 92/92 citation fields grounded. |
| 20 | `evidence_gate` | No additional evidence-gate drops. |

## Candidate Lifecycle

The candidate audit reports 32 total candidates. Important drops:

- `IFI16`, `CRP`, `NLRP10`, `CD68`, and `CD36` were dropped as
  `deterministic_uncorroborated`.
- `TLR` and `OLR1` were figure-derived or broad/alias-like candidates dropped
  during grounding.
- `LOX1` survived into detail extraction but was dropped by the strict gate
  because validation confidence was `0.0`.

This is a healthy pattern overall: broad deterministic and figure-derived
candidates are explored, but the validation and grounding gates prevent most
weak candidates from reaching the final CSV.

## Function Trace Findings

The raw live stream contains 6,404 lines:

- Stage events: 20
- Function call events: 3,193
- Function return events: 3,191
- Total function events: 6,384

Top function-event sources:

| Function | Events |
|---|---:|
| `_as_string_set` | 1,508 |
| `_clean_text` | 512 |
| `_gene_key` | 426 |
| `_normalize_empty_placeholder` | 400 |
| `_get_hgnc_aliases_for_gene` | 324 |
| `_refresh_candidate_cache` | 322 |
| `_infer_candidate_association_type` | 322 |
| `_extract_numbers` | 254 |
| `_as_sorted_strings` | 241 |
| `_candidate_terms_for_row` | 162 |
| `_normalize_gene_symbol` | 132 |
| `_normalize_unicode_slashes` | 96 |
| `_normalize_citation_drift` | 96 |
| `_citation_exists_in_paper` | 92 |
| `_calculate_citation_confidence` | 92 |

Function events with a semantic `stage_id`:

| Stage | Function events |
|---|---:|
| `hgnc_validation` | 1,036 |
| `citation_validation` | 670 |
| `detail_extraction` | 530 |
| `pubtator_merge` | 432 |
| `grounding_check` | 254 |
| `post_validation` | 250 |
| `evidence_gate` | 98 |
| `figure_analysis` | 52 |
| `context_validation` | 4 |
| `deterministic_scan` | 2 |

3,056 function events had no `stage_id`. Most of those are outside explicit
`pipeline_tracer.stage(...)` contexts, especially full-text fetching, PubMed
metadata, citation fetch, PubTator fetch, and final output/enrichment plumbing.

## What Is Working

### Stage 5 now has understandable lifecycle visibility

The run shows a clear candidate lifecycle:

1. PubTator anchors the strongest primary genes.
2. Deterministic scan expands the candidate set.
3. Figure analysis can add figure-only candidates.
4. Grounding removes broad or unsupported terms.
5. HGNC validation resolves symbols.
6. Corroboration removes deterministic-only weak candidates.
7. Gemini writes user-facing fields only after candidate pruning.
8. Local evidence backfill and citation validation repair or reject weak rows.

That is the right direction for an open-source reader: candidate discovery and
LLM synthesis are no longer collapsed into one opaque "Gemini extractor" idea.

### Citation validation improved materially

This run reached 92/92 grounded citation fields after backfill. That is better
than earlier runs on the same paper, where the final output had ungrounded
placeholders or missing fields. The new table citation index/cache is doing
useful work.

### Figure-derived candidates are now visible

The final CSV includes `S100A1` as a `Figure-Derived Signal` with `REVIEW`
confidence and a note that it is figure-only. This is a reasonable presentation:
the signal is not hidden, but it is also not over-promoted as text-grounded
evidence.

## Problems Found

### 1. Function tracing is not self-contained from the CLI

`--trace-functions` only produces function events when `TRACE_LIVE_FILE` is set.
The live viewer sets this automatically, but the CLI does not. Running only
`--trace-pmid ... --trace-functions` writes a stage trace but no function events.

Recommended fix:

- In `pipeline/run_pipeline.py`, when `--trace-functions` is passed and
  `TRACE_LIVE_FILE` is not already set, default it to
  `{output_dir}/live_events.jsonl`.

### 2. Persisted trace drops function events

`live_events.jsonl` has 6,384 function events, but
`trace_41017238.json` stores only the 20 stage nodes. This happens because the
final trace merge indexes only events with `node_id`; `fn_call` and `fn_return`
events have no `node_id`.

Recommended fix:

- Keep `nodes` as-is for viewer compatibility.
- Add a compact `function_events` array or a separate
  `trace_41017238_functions.jsonl` path to the persisted artifact.
- Record function event summary counts in `trace_41017238.json` even if the full
  event stream stays external.

### 3. Many function events lack `stage_id`

3,056 function events had `stage_id: null`. This makes the function trace harder
to use because early fetch/parse work and final output work cannot be grouped by
stage.

Recommended fix:

- Wrap major non-Stage-5 regions in `pipeline_tracer.stage(...)`:
  `pubmed_metadata`, `full_text_fetch`, `pubtator_ner`, `citation_fetch`,
  `ncbi_enrichment`, and `output_writer`.

### 4. Stage IDs are sometimes broader than node IDs

The persisted trace correctly has nodes such as `low_confidence_gate`,
`corroboration_gate`, `strict_gate`, `citation_validation`, and `evidence_gate`.
However, their `stage_id` values can be broader context labels such as
`hgnc_validation`, `detail_extraction`, or `post_validation`.

Recommended fix:

- Use nested or narrower `pipeline_tracer.stage(...)` contexts around each
  semantic gate so function events and node labels match.

### 5. Candidate audit final group counts are stale

The final CSV has meaningful association groups, but the paper-level
`final_association_group_counts` in the candidate audit says all 25 final
associations are `Other Candidate Signal`. The `final_associations` snapshot is
being built before row-level association policy has assigned the final types.

Recommended fix:

- Build final association counts from the emitted DataFrame rows, or update the
  final association snapshot after row-level association type inference.

### 6. `F2` is still a false-positive risk

The `F2` review row appears to be driven by biochemical text about
`F2-isoprostanes`, not a real gene-specific finding. It is marked `REVIEW`,
which is safer than a confident row, but it still reaches the final output.

Recommended fix:

- Add a deterministic gene-symbol guard for biochemical compounds where the gene
  symbol is only a prefix in a longer biochemical term.
- Keep this narrow and context-sensitive. Do not add a broad static blocklist of
  common short symbols.

### 7. `animal_model_gene` needs a clearer group

Seven rows are classified as `animal_model_gene` but grouped as
`Other Candidate Signal`. That makes the result harder to read, because animal
model evidence is a real category rather than miscellaneous residue.

Recommended fix:

- Add a dedicated group such as `Animal Model Signal`, or map
  `animal_model_gene` into `Mechanistic/Pathway Signal` with explicit wording.

### 8. NCBI enrichment still hammers rate limits

After final extraction, NCBI enrichment produced repeated 429 warnings and only
filled metadata for 9/24 genes. This is not a correctness blocker because final
gene rows already exist, but it slows runs and makes logs noisy.

Recommended fix:

- Batch where the API allows it.
- Cache symbol-to-metadata responses across rows and runs.
- Prefer local HGNC metadata for stable display fields before remote enrichment.
- Add backoff when 429s start, rather than continuing the same request cadence.

## Stage 5 Simplification Opportunities

### Candidate normalization is still too chatty

The function trace shows repeated helper churn:

- `_as_string_set`: 1,508 events
- `_gene_key`: 426 events
- `_normalize_empty_placeholder`: 400 events
- `_refresh_candidate_cache`: 322 events
- `_infer_candidate_association_type`: 322 events

Some of that is expected, but the repetition suggests candidate normalization is
happening multiple times after every accumulator mutation.

Recommended direction:

- Keep early text normalization in `content_preparation.py`.
- Keep candidate-specific gene/variant normalization in Stage 5.
- Make candidate metadata immutable after discovery where possible.
- Refresh cached terms only when a candidate changes, not across the whole
  accumulator repeatedly.

### Citation normalization is now cached, but table work still dominates

`_citation_exists_in_paper` and `_calculate_citation_confidence` ran 92 times
each, matching the number of citation field checks. That is acceptable, but
`_extract_numbers` still fired 254 times.

Recommended direction:

- Keep the table citation index.
- Add a precomputed numeric-token cache per citation field or per table row if
  table-heavy papers become a bottleneck.

### Function tracer noise set should be updated

Several helpers are high-frequency and usually not useful in a human trace:
`_as_string_set`, `_gene_key`, `_normalize_empty_placeholder`,
`_as_sorted_strings`, and `_extract_numbers`.

Recommended direction:

- Move these into `_FN_TRACER_NOISE`.
- Keep value capture on higher-level functions such as
  `_run_candidate_discovery`, `_run_grounding_check`,
  `_run_validation_and_normalize`, `_run_detail_extraction`,
  `_add_citation_validation_metadata`, and `_apply_evidence_gate`.

## Recommended Next Backlog

1. Make CLI `--trace-functions` create `live_events.jsonl` automatically.
2. Persist function events or a compact function-event summary alongside
   `trace_<pmid>.json`.
3. Wrap non-Stage-5 phases in semantic `pipeline_tracer.stage(...)` contexts.
4. Align `stage_id` with specific gate node IDs inside Stage 5.
5. Fix candidate audit final group counts to reflect final emitted rows.
6. Add a narrow `F2-isoprostane`-style compound-prefix guard.
7. Give `animal_model_gene` a real result group.
8. Cache or throttle NCBI enrichment to avoid repeated 429s.
9. Reduce function-tracer noise around tiny candidate normalization helpers.
10. Keep early paper-text normalization in `content_preparation.py`; keep
    candidate gene/variant normalization in Stage 5, but cache it per candidate.

