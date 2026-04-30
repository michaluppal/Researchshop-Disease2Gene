# Pipeline Flow Knowledge - PMID 41017238

This note records the observed ResearchShop pipeline flow from the interactive
pipeline viewer for PMID `41017238`, then turns the trace into concrete cleanup
and optimization targets.

The viewer credentials were configured in the local server memory only. No API
key is stored in this report or committed to the repository.

## Source Artifacts

Fresh current-code run:

- Live function trace: `publication/figures/pipeline-viewer/live_runs/run_41017238_1777163632/live_events.jsonl`
- Persisted stage trace: `publication/figures/pipeline-viewer/live_runs/run_41017238_1777163632/trace_41017238.json`
- Debug artifact: `publication/figures/pipeline-viewer/live_runs/run_41017238_1777163632/drop_debug_61562945.json`
- Output rows: `publication/figures/pipeline-viewer/live_runs/run_41017238_1777163632/final_enriched_results_e832ffe7.json`
- Output CSV/XLSX: `final_enriched_results_e832ffe7.csv`, `final_enriched_results_e832ffe7.xlsx`
- Content artifact: `content_dict_84bc0628.pkl.gz`

The immediately prior current-code run,
`run_41017238_1777163359`, exposed a Stage 5 refactor import bug:
`No module named 'modules.stage5.gene_validator'`. That was fixed in
`pipeline/modules/stage5/metadata.py` by importing `gene_validator` from the
parent `modules` package instead of the `stage5` package.

Older comparison artifact:

- `publication/figures/pipeline-viewer/live_runs/run_41017238_1776713406`

That older run predates the Stage 5 package split and uses
`modules.gemini_extractor` names in function events. The fresh run uses
`modules.stage5.*`.

## Run Summary

The run processed one mandatory PMID: `41017238`, "The Etiopathogenesis of
Kawasaki Disease: Evolving Understanding of Diverse Triggers."

Observed facts:

- PubMed metadata was complete: title, authors, journal, DOI, year, abstract.
- PMC full text fetch succeeded through `pmc_efetch`.
- Extracted content length was `60,914` characters.
- Full text extraction found `5` structured tables and `0` figures for this article.
- PubTator found `ITPKC`, `CASP3`, and `FCGR2A`.
- Deterministic HGNC scanning found `29` grounded candidate genes.
- Stage 5 made `1` Gemini API call in this run: the detail extraction call.
- Detail extraction returned `24` rows; final output emitted `23` rows.
- Five deterministic-only candidates were dropped as `deterministic_uncorroborated`.
- One row, `LOX1`, was dropped by the strict gate because validation confidence was `0.0`.
- Final output contained `23` rows: 3 high-confidence susceptibility genes, 19 medium-confidence mechanistic/pathway genes, and 1 review row.

Final high-confidence genes:

- `ITPKC`
- `CASP3`
- `FCGR2A`

Final review row:

- `F2`, because the row relied on an auto-snippet placeholder and citation validation could not find that placeholder in the paper.

## Current Pipeline Logic

The current run is best understood as a conservative fetch-and-gate pipeline
plus one LLM synthesis step:

1. Collect the user-selected PMID.
2. Fetch PubMed metadata.
3. Resolve PMCID and fetch PMC JATS XML.
4. Parse body text and structured tables.
5. Normalize/clean text.
6. Fetch PubTator genes.
7. Fetch citation counts.
8. Build paper input for Stage 5.
9. Run deterministic HGNC scan.
10. Merge PubTator genes into the candidate accumulator.
11. Ground candidates against paper text.
12. Validate candidates against HGNC/local gene rules.
13. Drop low-confidence candidates.
14. Drop uncorroborated deterministic-only gene-level candidates.
15. Send surviving candidates plus paper text/tables/user columns to Gemini detail extraction.
16. Merge duplicate gene rows.
17. Backfill sparse evidence from local paper snippets.
18. Add validation/provenance/citation/context metadata.
19. Apply strict and evidence gates.
20. Enrich final rows with PubTator/NCBI metadata and citation counts.
21. Write CSV, metadata CSV, JSON, XLSX, and debug artifacts.

## Observed Stage Flow

The live trace captured the following stage nodes.

| Order | Stage | Observed result | Representative functions |
|---:|---|---|---|
| 1 | `user_selection` | 1 mandatory PMID selected | `run_complete_pipeline`, `pipeline_tracer.capture` |
| 2 | `pubmed_metadata` | 1 record retrieved in `953 ms` | `fetch_paper_details`, `_normalize_pubmed_record`, `_extract_year`, `_extract_doi` |
| 3 | `full_text_fetch` | PMC XML fetched in `2,962 ms`; 60,914 chars; 5 tables; 0 figures | `run_fetching`, `_process_single_pmid`, `_get_pmcid_for_pmid`, `_fetch_pmc_efetch`, `_extract_text_and_figures_from_pmc_xml` |
| 4 | `text_cleaning` | Content normalized and quality-scored | `_clean_and_validate_content`, `_assess_content_quality`, `generate_fetch_report` |
| 5 | `pubtator_ner` | 3 genes returned in `935 ms` | `extract_from_pmids`, `_parse_document` |
| 6 | `citation_fetch` | Citation count fetched in `637 ms` | `fetch_citation_counts_with_fallback`, `fetch_icite_citation_counts`, `_extract_icite_citation_count` |
| 7 | `deterministic_scan` | 29 HGNC candidates found in `102 ms` | `extract_deterministic_candidates`, `_normalize_gene_symbol` |
| 8 | `pubtator_merge` | PubTator genes merged into candidate metadata | `_ingest_associations`, `_refresh_associations_from_meta` |
| 9 | `candidate_meta` | Candidate accumulator captured | `_summarise_sources`, `_collect_debug_artifact` |
| 10 | `grounding_check` | Candidate mentions checked against text and aliases | `_run_grounding_check`, `_candidate_terms_for_row`, `_find_evidence_snippet`, `_get_hgnc_aliases_for_gene` |
| 11 | `hgnc_validation` | 29 candidates resolved/validated | `validate_associations`, `validate_gene_variant`, `resolve_gene_symbol`, `_validate_gene_hgnc` |
| 12 | `low_confidence_gate` | Broken resolutions removed early | `_apply_gene_validation_heuristics` |
| 13 | `corroboration_gate` | 5 deterministic-only candidates rejected; many pathway candidates retained by context | `_deterministic_gene_context_evidence`, `_apply_gene_validation_heuristics` |
| 14 | `detail_extraction` | One Gemini call returned 24 rows in `10,598 ms` | `extract_gene_info`, `_format_table_summary_for_prompt`, `_generate_content_text`, `_can_make_gemini_call` |
| 15 | `row_merge` | Duplicate gene rows consolidated | `_merge_duplicate_gene_rows` |
| 16 | `evidence_backfill` | Sparse rows patched from local snippets | `_backfill_sparse_row_evidence`, `_find_gene_specific_snippet`, `_build_snippet` |
| 17 | `strict_gate` | `LOX1` removed below validation threshold | `_run_post_validation`, `_add_validation_metadata`, `_add_candidate_provenance_metadata` |
| 18 | `citation_validation` | Citation fields checked against paper text/tables | `_add_citation_validation_metadata`, `_citation_exists_in_paper`, `_calculate_citation_confidence` |
| 19 | `evidence_gate` | 23 rows retained and passed to orchestrator finalization | `_apply_evidence_gate`, `_row_has_user_evidence`, `_count_user_evidence_cells` |

The persisted `trace_41017238.json` still contains only the first 6 nodes:
`user_selection`, `pubmed_metadata`, `full_text_fetch`, `text_cleaning`,
`pubtator_ner`, and `citation_fetch`. The live stream contains the full Stage 5
sequence above. This mismatch is a viewer/tracing bug.

## Function Inventory

The current trace observed `2,470` function calls across `114` unique
`module.function` pairs. The full event stream is the source of truth for every
call/return event; this table lists every unique function observed in the run.

| Module | Function | Calls |
|---|---|---:|
| `modules.abstract_screener` | `decisions_to_dicts` | 1 |
| `modules.abstract_screener` | `has_genetic_content` | 2 |
| `modules.abstract_screener` | `screen_papers_with_decisions` | 1 |
| `modules.full_text_fetcher` | `_assess_content_quality` | 1 |
| `modules.full_text_fetcher` | `_clean_and_validate_content` | 1 |
| `modules.full_text_fetcher` | `_extract_structured_tables_from_pmc_xml` | 1 |
| `modules.full_text_fetcher` | `_extract_supplementary_urls_from_pmc_xml` | 1 |
| `modules.full_text_fetcher` | `_extract_text_and_figures_from_pmc_xml` | 1 |
| `modules.full_text_fetcher` | `_fetch_pmc_efetch` | 1 |
| `modules.full_text_fetcher` | `_get_pmcid_for_pmid` | 2 |
| `modules.full_text_fetcher` | `_process_single_pmid` | 1 |
| `modules.full_text_fetcher` | `generate_fetch_report` | 1 |
| `modules.full_text_fetcher` | `is_good_quality` | 1 |
| `modules.full_text_fetcher` | `run_fetching` | 1 |
| `modules.gene_validator` | `_build_local_alias_index` | 1 |
| `modules.gene_validator` | `_calculate_citation_confidence` | 44 |
| `modules.gene_validator` | `_citation_exists_in_paper` | 44 |
| `modules.gene_validator` | `_compile_variant_patterns` | 1 |
| `modules.gene_validator` | `_extract_numbers` | 87 |
| `modules.gene_validator` | `_find_gene_in_table_rows` | 59 |
| `modules.gene_validator` | `_is_valid_gene` | 29 |
| `modules.gene_validator` | `_load_local_hgnc_database` | 1 |
| `modules.gene_validator` | `_normalize_citation_drift` | 88 |
| `modules.gene_validator` | `_normalize_unicode_slashes` | 88 |
| `modules.gene_validator` | `_validate_gene_hgnc` | 29 |
| `modules.gene_validator` | `estimate_token_count` | 1 |
| `modules.gene_validator` | `get_gene_biotype` | 24 |
| `modules.gene_validator` | `resolve_gene_symbol` | 29 |
| `modules.gene_validator` | `validate_associations` | 1 |
| `modules.gene_validator` | `validate_gene_variant` | 29 |
| `modules.gene_validator` | `validate_table_citation` | 13 |
| `modules.pipeline_orchestrator` | `_accumulate_result` | 1 |
| `modules.pipeline_orchestrator` | `_agg_variants` | 23 |
| `modules.pipeline_orchestrator` | `_aggregate_strict_gate_drops` | 1 |
| `modules.pipeline_orchestrator` | `_compute_row_confidence` | 23 |
| `modules.pipeline_orchestrator` | `_create_unique_filepath` | 3 |
| `modules.pipeline_orchestrator` | `_ensure_unique_columns` | 9 |
| `modules.pipeline_orchestrator` | `_fill_sheet` | 2 |
| `modules.pipeline_orchestrator` | `_finalize_paper_result` | 1 |
| `modules.pipeline_orchestrator` | `_get_citation_record` | 1 |
| `modules.pipeline_orchestrator` | `_is_gemini_quota_error` | 1 |
| `modules.pipeline_orchestrator` | `_prepare_paper_inputs` | 1 |
| `modules.pipeline_orchestrator` | `_sanitize_user_columns` | 1 |
| `modules.pipeline_orchestrator` | `_unique_preserve_order` | 2 |
| `modules.pipeline_orchestrator` | `_write_excel_output` | 1 |
| `modules.pipeline_orchestrator` | `_write_json_output` | 1 |
| `modules.pipeline_orchestrator` | `_write_split_output` | 1 |
| `modules.pipeline_orchestrator` | `get_aliases` | 23 |
| `modules.pipeline_orchestrator` | `get_chromosome` | 23 |
| `modules.pipeline_orchestrator` | `get_full_name` | 23 |
| `modules.pipeline_orchestrator` | `get_gene_source` | 23 |
| `modules.pipeline_orchestrator` | `get_ncbi_gene_id` | 20 |
| `modules.pipeline_orchestrator` | `get_ncbi_id` | 23 |
| `modules.pipeline_orchestrator` | `write_drop_debug_artifact` | 1 |
| `modules.pubmed_data_collector` | `_as_list` | 3 |
| `modules.pubmed_data_collector` | `_extract_doi` | 1 |
| `modules.pubmed_data_collector` | `_extract_icite_citation_count` | 1 |
| `modules.pubmed_data_collector` | `_extract_year` | 1 |
| `modules.pubmed_data_collector` | `_normalize_pubmed_record` | 1 |
| `modules.pubmed_data_collector` | `fetch_citation_counts_with_fallback` | 1 |
| `modules.pubmed_data_collector` | `fetch_icite_citation_counts` | 1 |
| `modules.pubmed_data_collector` | `fetch_paper_details` | 1 |
| `modules.pubmed_xml_parser` | `_clean_text` | 254 |
| `modules.pubmed_xml_parser` | `_coerce_xml_bytes` | 1 |
| `modules.pubmed_xml_parser` | `_temporary_nxml` | 2 |
| `modules.pubmed_xml_parser` | `parse_pubmed_parser_paragraph_text` | 1 |
| `modules.pubtator_tool` | `_parse_document` | 1 |
| `modules.pubtator_tool` | `enrich_gene_symbols` | 1 |
| `modules.pubtator_tool` | `extract_from_pmids` | 1 |
| `modules.pubtator_tool` | `get_gene_by_symbol` | 23 |
| `modules.pubtator_tool` | `get_gene_metadata` | 16 |
| `modules.stage5.candidates` | `_as_sorted_strings` | 133 |
| `modules.stage5.candidates` | `_as_string_set` | 272 |
| `modules.stage5.candidates` | `_candidate_terms_for_row` | 80 |
| `modules.stage5.candidates` | `_get_hgnc_aliases_for_gene` | 80 |
| `modules.stage5.candidates` | `_ingest_associations` | 2 |
| `modules.stage5.candidates` | `_normalize_empty_placeholder` | 96 |
| `modules.stage5.candidates` | `_normalize_gene_symbol` | 61 |
| `modules.stage5.candidates` | `_refresh_associations_from_meta` | 2 |
| `modules.stage5.candidates` | `extract_deterministic_candidates` | 1 |
| `modules.stage5.context` | `_validate_and_prepare_paper_text` | 1 |
| `modules.stage5.evidence` | `_apply_evidence_gate` | 1 |
| `modules.stage5.evidence` | `_backfill_sparse_row_evidence` | 1 |
| `modules.stage5.evidence` | `_build_snippet` | 1 |
| `modules.stage5.evidence` | `_count_user_evidence_cells` | 23 |
| `modules.stage5.evidence` | `_deterministic_gene_context_evidence` | 26 |
| `modules.stage5.evidence` | `_fill_missing_requested_fields` | 1 |
| `modules.stage5.evidence` | `_find_evidence_snippet` | 29 |
| `modules.stage5.evidence` | `_find_gene_specific_snippet` | 1 |
| `modules.stage5.evidence` | `_merge_duplicate_gene_rows` | 1 |
| `modules.stage5.evidence` | `_peers_present_in` | 1 |
| `modules.stage5.evidence` | `_row_has_user_evidence` | 24 |
| `modules.stage5.evidence` | `_sentence_for_match` | 40 |
| `modules.stage5.evidence` | `_term_patterns` | 44 |
| `modules.stage5.evidence` | `_window_for_match` | 40 |
| `modules.stage5.gemini_client` | `_can_make_gemini_call` | 1 |
| `modules.stage5.gemini_client` | `_format_table_summary_for_prompt` | 1 |
| `modules.stage5.gemini_client` | `_generate_content_text` | 1 |
| `modules.stage5.gemini_client` | `extract_gene_info` | 1 |
| `modules.stage5.metadata` | `_add_candidate_provenance_metadata` | 1 |
| `modules.stage5.metadata` | `_add_citation_validation_metadata` | 1 |
| `modules.stage5.metadata` | `_add_context_metadata` | 1 |
| `modules.stage5.metadata` | `_add_validation_metadata` | 1 |
| `modules.stage5.metadata` | `_collect_debug_artifact` | 1 |
| `modules.stage5.metadata` | `_norm_gene` | 343 |
| `modules.stage5.metadata` | `_norm_variant` | 47 |
| `modules.stage5.pipeline` | `_apply_gene_validation_heuristics` | 1 |
| `modules.stage5.pipeline` | `_run_candidate_discovery` | 1 |
| `modules.stage5.pipeline` | `_run_detail_extraction` | 1 |
| `modules.stage5.pipeline` | `_run_grounding_check` | 1 |
| `modules.stage5.pipeline` | `_run_post_validation` | 1 |
| `modules.stage5.pipeline` | `_run_validation_and_normalize` | 1 |
| `modules.stage5.pipeline` | `_summarise_sources` | 1 |
| `modules.stage5.pipeline` | `run_pipeline` | 1 |

## Deep Analysis

### 1. The live trace is richer than the persisted trace

The browser observed Stage 5 nodes from `deterministic_scan` through
`evidence_gate`, but `trace_41017238.json` contains only the first 6
orchestrator-side nodes. This makes the static "load trace.json" workflow much
less useful than live mode.

Likely cause: worker-side trace partials are not reliably flushed into
`{OUTPUT_DIR}/.trace_partials` before the final trace is assembled.

Recommended fix: set an explicit `TRACE_OUT_DIR` env var for traced runs, and
make worker partial flushing use that env var when process-local tracer state is
not initialized.

### 2. The static graph no longer matches the active pipeline

The viewer still shows abstract LLM discovery, full-text LLM discovery, recall
retry, and figure analysis nodes. The fresh current-code run did not execute
those as trace nodes. The active flow for this PMID is deterministic scan,
PubTator merge, gates, then one Gemini detail extraction call.

Recommended fix: split the viewer into "current active path" and "legacy or
optional path" nodes, or have the graph generated from a stage registry instead
of hand-maintained static HTML.

### 3. The current flow is cheaper, but the result is now high-recall

The move to one detail extraction call is good for free-tier Gemini users. It
also changes the clinical behavior: deterministic/pathway candidates can survive
into final rows if Gemini fills plausible details. For a review paper like this,
that produced 23 rows, including many mechanistic or pathway genes that are not
the same class as the 3 PubTator-backed susceptibility genes.

Recommended fix: make association intent explicit. For example, separate
`susceptibility_gene`, `mechanistic_pathway_gene`, `biomarker`, and
`animal_model_gene` rows, or expose a mode that defaults final CSV output to
high-confidence human genetics while keeping mechanistic candidates in a
candidate audit artifact.

### 4. Candidate audit should become first-class

The debug artifact already contains candidate sources, grounding snippets,
validation outcomes, deterministic context reasons, drops, and final
associations. That is the most useful artifact for understanding why a row
appeared or disappeared, but it is hidden as `drop_debug_*.json`.

Recommended fix: write a stable `candidate_audit_{run_id}.json` or CSV and add
a viewer/results entrypoint. Keep the final CSV conservative, but make the
candidate path inspectable.

### 5. Normalization and alias lookup are hot spots

The trace shows many repeated pure operations:

- `_norm_gene`: 343 calls
- `_as_string_set`: 272 calls
- `_clean_text`: 254 calls
- `_as_sorted_strings`: 133 calls
- `_normalize_empty_placeholder`: 96 calls
- `_candidate_terms_for_row`: 80 calls
- `_get_hgnc_aliases_for_gene`: 80 calls

Recommended fix: cache per-run derived values on the candidate metadata object.
For example, compute normalized gene, normalized variant, alias terms, and
candidate search terms once per candidate and reuse them in grounding,
validation, evidence, and metadata.

### 6. Citation validation repeats expensive text normalization

Citation validation called `_normalize_unicode_slashes` and
`_normalize_citation_drift` 88 times each, plus `_extract_numbers` 87 times and
table citation validation 13 times. This is acceptable for one paper, but it
will scale poorly across large result sets.

Recommended fix: pre-normalize paper text and table text once, cache normalized
row citation strings, and short-circuit empty/placeholder citations before
running numeric/table checks.

### 7. Orchestrator enrichment is row-oriented and noisy

Finalization repeats PubTator/NCBI lookups for every row:
`get_gene_source`, `get_ncbi_id`, `get_full_name`, `get_aliases`, and
`get_chromosome` each ran 23 times. This logic lives inside
`_finalize_paper_result()`, which makes traces noisy and hides enrichment policy
inside the orchestrator.

Recommended fix: extract a `GeneRowEnricher` or pure `enrich_gene_rows()`
helper. Build a per-run metadata cache keyed by gene symbol, then map rows
through that cache.

### 8. Figure parsing needs a stronger validation set

This PMID produced 5 structured tables but 0 figures. That may be correct for
this article, but it means the run does not validate the figure URL/download
path or the PubMed parser caption adapter. The older report claimed 2 figures
for the same PMID, so this deserves a direct XML/browser comparison before we
trust it.

Recommended fix: keep this PMID for Stage 5 flow validation, but add at least
one figure-rich PMC article to the parser/figure-ground-truth skill. The viewer
should show whether figure captions, `graphic_ref`, URL candidates, CDN fallback,
download status, and image dimensions all work.

### 9. Function tracing still lacks stage ownership

Function events are useful, but they are not attached to their parent stage. The
viewer can infer approximate grouping by time, but not reliably, especially
across worker processes.

Recommended fix: add `stage_id` to every `fn_call` and `fn_return` event. A
small tracer context manager around each `pipeline_tracer.capture(...)` block
would be enough.

## Optimization Backlog

1. Fix persisted trace completeness for Stage 5 worker nodes.
2. Add `stage_id` to function events.
3. Update the viewer graph so current active stages and optional/legacy stages are distinct.
4. Promote candidate audit output to a stable artifact and viewer panel.
5. Add association intent/type to final rows and gates.
6. Cache per-candidate normalized terms and HGNC aliases.
7. Cache normalized citation/table text during citation validation.
8. Extract orchestrator gene-row enrichment into a batch/cache helper.
9. Add a figure-rich PMID to the parser/figure ground-truth validation skill.

## Implementation Pass On `codex/optimise`

This branch addresses the first wave of the backlog without changing the
research output schema beyond adding an explicit `Association Type` column:

- Trace persistence now uses `TRACE_OUT_DIR` so worker partials do not depend on
  process-local tracer state. The final merge also reads the live event stream
  as a safety net, preserving Stage 5 nodes that were visible in the browser.
- Function events now carry `stage_id` from explicit tracer stage contexts. The
  function viewer renders the stage as a chip, making Stage 5 helper traffic
  groupable by semantic step instead of timestamp windows.
- The viewer labels optional Gemini discovery passes as optional, so the static
  graph better matches the current free-tier default path.
- Candidate provenance is promoted into a stable `candidate_audit_*.json`
  artifact alongside `drop_debug_*.json`.
- Candidate metadata now caches materialized source lists, raw labels, HGNC
  alias terms, and candidate search terms once per run.
- Citation validation pre-normalizes paper text once and reuses row-level
  citation checks instead of normalizing the same text for every field.
- Orchestrator PubTator and NCBI row enrichment moved into batch helpers.
- The parser gold-standard skill now requires a maintained figure-rich PMID;
  `41169353` is marked as the current multi-figure fixture.

## Suggested Verification For Next Refactor

- Run the pipeline viewer with `Trace fns` enabled on PMID `41017238`.
- Confirm `live_events.jsonl` and `trace_41017238.json` contain the same Stage 5 nodes.
- Confirm function events include `stage_id`.
- Confirm final CSV separates susceptibility genes from mechanistic/pathway genes.
- Run a figure-rich PMID and verify caption extraction, URL candidates, CDN fallback, downloaded image count, and image dimensions.
- Run existing focused tests:
  - `pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_pipeline_orchestrator.py -v --tb=short`
  - `pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_figure_extraction.py -v --tb=short`
  - `pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_evidence_backfill.py -v --tb=short`
  - `pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_grounding_rescue.py -v --tb=short`
