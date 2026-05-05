# Pipeline Domain Table

This table is the current source-of-truth map from pipeline domains to code. It
is intentionally concrete: every row names the function or code block that owns
the operation, its main input, its output, and what the operation does.

## Backend Pipeline

| Domain | Operation | Function name | Input | Output | Description |
|---|---|---|---|---|---|
| `paper_selection` | CLI setup | `pipeline/run_pipeline.py:main()` / `_configure_trace_env()` | CLI args, `GEMINI_API_KEY`, `ENTREZ_EMAIL`, optional trace flags | Parsed pipeline args, config/env initialized | Validates required secrets, configures trace env vars, parses JSON PMIDs/authors/columns, then calls the orchestrator. |
| `paper_selection` | Merge requested papers | `pipeline/modules/pipeline_orchestrator.py:run_complete_pipeline()` | `query`, `specific_pmids`, `specific_authors` | `initial_pmids`, `mandatory_pmids` | Builds the candidate PMID set from explicit PMIDs, author search, and query search. |
| `oa_filter` | OA gate for mandatory PMIDs | `full_text_fetcher._get_pmcid_for_pmid()` inside `run_complete_pipeline()` | Explicit/author PMIDs | OA-only `mandatory_pmids`, excluded non-OA count | Enforces the OA-only product policy before full-text work. PMIDs without a PMCID are excluded. |
| `paper_selection` | Query search | `pubmed_data_collector.search_pubmed()` | PubMed query, relevance count | Query PMID list | Runs PubMed search with app-specific query logic and OA filter when enabled. |
| `paper_selection` | Author search | `pubmed_data_collector.search_pubmed_by_author()` | Author names | Author-derived PMID list | Finds papers for each requested author and treats them as mandatory candidates before OA gating. |
| `paper_selection` | PubMed metadata fetch | `pubmed_data_collector.fetch_paper_details()` | Deduplicated PMIDs | `paper_details` dict | Fetches title, abstract, authors, DOI, journal, year, affiliations, and metadata quality flags. |
| `paper_reading` | Full-text fetch batch | `full_text_fetcher.run_fetching()` | PMIDs, gzipped pickle output path | `content_dict.pkl.gz` | Fetches PMC/Europe PMC full text for each PMID and serializes extracted content for the orchestrator. |
| `paper_reading` | PMCID lookup | `full_text_fetcher._get_pmcid_for_pmid()` | PMID | PMCID or `None` | Resolves PubMed IDs to PMC IDs before PMC XML retrieval. |
| `paper_reading` | PMC XML fetch | `full_text_fetcher._fetch_pmc_efetch()` | PMID, PMCID | `ContentExtractionResult` | Retrieves PMC JATS XML and invokes extraction. Europe PMC fallback is handled by the fetcher path. |
| `paper_reading` | XML text/figure/table parse | `full_text_fetcher._extract_text_and_figures_from_pmc_xml()` / `pubmed_xml_parser.parse_pmc_text_and_figures()` | JATS XML bytes, article URL | Full text, figure dicts, `StructuredTable[]` | Parses body text and figure metadata through the pubmed-parser adapter first, with ResearchShop fallback extraction. Tables remain ResearchShop-owned. |
| `paper_reading` | Content cleanup and quality | `full_text_fetcher._clean_and_validate_content()` | Raw extracted text, source URL | Clean text, quality metadata | Normalizes paper-level text and rejects/flags unusable content. |
| `paper_reading` | Fetch report | `full_text_fetcher.generate_fetch_report()` | `content_dict` | Per-PMID fetch report rows | Builds forensic fetch diagnostics for debug artifacts. |
| `candidate_discovery` | PubTator NER | `PubTatorTool.extract_from_pmids()` | Scraped PMIDs | PubTator gene/variant results by PMID | Gets high-precision gene and variant candidates from PubTator3 BioC JSON. |
| `paper_selection` | Citation counts | `pubmed_data_collector.fetch_citation_counts_with_fallback()` | Scraped PMIDs | Citation records by PMID | Fetches iCite counts first and fills missing counts from Semantic Scholar fallback. |
| `paper_selection` | Paper ordering | Inline block in `run_complete_pipeline()` | Scraped PMIDs, citation counts, mandatory PMIDs | `pmids_to_process` | Orders mandatory PMIDs first, then remaining scraped papers by citation count. |
| `paper_selection` | Forensic abstract scoring | `abstract_screener.has_genetic_content()` / `screen_papers_with_decisions()` | Title, abstract, threshold | Forensic screening decisions | Scores abstracts for diagnostics only. It no longer filters selected papers out of the run. |
| `paper_reading` | Per-paper evidence package | `_prepare_paper_inputs()` | `content_dict`, `paper_details`, PubTator results | Paper analysis package with text, abstract, figures, tables, `PreparedPaperContent` | Collects all evidence for one paper and builds normalized paper/table indexes before extraction. |
| `detail_extraction` | Extraction worker run | `_run_pipeline_worker()` | Paper analysis package, user column descriptions | Records, debug artifact, Gemini API call count | Runs one per-paper extraction coordinator in the worker pool and converts the resulting DataFrame to record dicts. |

## Per-Paper Domains

| Domain | Operation | Function name | Input | Output | Description |
|---|---|---|---|---|---|
| `paper_reading` | Context window check | `PaperAnalysisPipeline._validate_and_prepare_paper_text()` | Full paper text, model context settings | Context validation dict, possibly shortened `paper_text` | Estimates token usage and truncates lower-priority sections only when required by model context limits. |
| `candidate_discovery` | Optional abstract LLM pass | `GeminiClientMixin.extract_gene_names_from_abstract()` | Title/abstract | Candidate associations | Optional Gemini pass on abstract/title for recall. |
| `candidate_discovery` | Optional full-text LLM pass | `GeminiClientMixin.extract_gene_names()` | Full paper text | Candidate associations | Optional Gemini pass over the paper text. Free-tier defaults generally keep this off. |
| `candidate_discovery` | Optional recall retry | `GeminiClientMixin.extract_gene_names(temperature=0.4)` | Full paper text | Additional candidate associations | Optional higher-recall second LLM pass. |
| `candidate_discovery` | Deterministic HGNC scan | `CandidateMixin.extract_deterministic_candidates()` | Paper text, HGNC symbols/aliases | Deterministic candidate associations | Finds explicit HGNC-style mentions without an LLM call. |
| `candidate_discovery` | Optional figure LLM analysis | `FigureMixin.extract_gene_names_from_figures()` | Figure metadata, downloadable image bytes | Figure-derived candidate associations | Uses Gemini vision on PMC figures when enabled and when images download successfully. |
| `candidate_discovery` | PubTator merge | `CandidateMixin._ingest_associations(..., source="pubtator")` | PubTator gene symbols | Candidate metadata entries | Adds PubTator candidates into the shared per-paper candidate map. |
| `candidate_discovery` | Candidate accumulator refresh | `_ingest_associations()` / `_refresh_associations_from_meta()` | Candidate associations from all sources | `candidate_meta`, `self.associations` | Maintains one canonical per-paper candidate map keyed by `(gene, variant)` with source/provenance metadata. |
| `validation` | Grounding check | `PaperAnalysisPipeline._run_grounding_check()` | `candidate_meta`, paper text, figure captions | Grounded candidate associations | Drops candidates whose gene/alias/raw label is not grounded in the paper or figure evidence. |
| `validation` | HGNC validation and normalization | `PaperAnalysisPipeline._run_validation_and_normalize()` / `GeneValidator.validate_associations()` | Grounded candidate associations | Canonical genes, validation results, normalized candidate metadata | Resolves genes to HGNC/local validation, normalizes gene/variant values, and stores validation confidence. |
| `validation` | Low-confidence gate | Inline block in `_run_validation_and_normalize()` | Validation results | Candidate metadata with low-confidence drops | Drops obviously weak gene resolutions before later gates. |
| `validation` | Corroboration gate | Inline block in `_run_validation_and_normalize()` | Candidate sources and association type | Candidate metadata with deterministic-only drops | Rejects gene-only candidates that have only deterministic lexical support unless a rescue/corroboration rule applies. |
| `detail_extraction` | Detail extraction LLM call | `GeminiClientMixin.extract_gene_info()` | Validated candidates, paper text, user column schema | Row dicts with user-requested fields | Single Gemini detail call that fills researcher-facing columns for each candidate. |
| `detail_extraction` | Row merge | `EvidenceMixin._merge_duplicate_gene_rows()` | Detail extraction rows | One merged row per gene/variant where possible | Consolidates duplicate Gemini rows for the same candidate. |
| `detail_extraction` | Evidence backfill | `EvidenceMixin._backfill_sparse_row_evidence()` | Detail rows, paper text, user column descriptions | Rows with missing evidence fields backfilled | Fills sparse citation/evidence fields from grounded paper snippets without changing the candidate set. |
| `validation` | Validation metadata | `MetadataMixin._add_validation_metadata()` | Detail DataFrame, validation results | DataFrame with confidence/source/suggestion columns | Adds internal validation confidence and diagnostic metadata. |
| `validation` | Candidate provenance metadata | `MetadataMixin._add_candidate_provenance_metadata()` | Detail DataFrame, `candidate_meta` | DataFrame with source, association type/group, gate metadata | Adds provenance and association policy fields consumed by outputs and audits. |
| `validation` | Strict validation gate | Inline block in `PaperAnalysisPipeline._run_post_validation()` | DataFrame with `validation_confidence` | Filtered DataFrame, strict gate drops | Applies the final medical-accuracy threshold (`FINAL_VALIDATION_MIN_CONFIDENCE`, currently 0.7). |
| `validation` | Citation validation | `MetadataMixin._add_citation_validation_metadata()` | DataFrame, normalized paper/table text | Citation-validity metadata | Validates extracted citation text against normalized paper/table evidence when enabled. |
| `validation` | Evidence gate | `EvidenceMixin._apply_evidence_gate()` | DataFrame, user column descriptions | Evidence-filtered DataFrame, evidence gate drops | Drops rows that lack sufficient grounded evidence in required fields. |
| `validation` | Context metadata | `MetadataMixin._add_context_metadata()` | Final per-paper DataFrame, context validation dict | DataFrame with context/truncation metadata | Records whether truncation happened and why. |

## Final Orchestration And Output

| Domain | Operation | Function name | Input | Output | Description |
|---|---|---|---|---|---|
| `output_writing` | Enrich paper rows | `_finalize_paper_result()` | Worker payload, PubMed metadata, citations, PubTator results | Per-paper DataFrame, debug artifact | Adds paper metadata, citation counts, PubTator/NCBI IDs, figure counts, confidence labels, and debug information. |
| `output_writing` | Accumulate run results | `_accumulate_result()` | Per-paper DataFrame, run stats | `all_results_df`, updated stats | Appends paper rows to the run-level DataFrame and updates extracted-gene counters. |
| `validation` | NCBI Gene enrichment | `NCBIGeneTool.enrich_gene_symbols()` | Unique emitted gene symbols plus available NCBI Gene IDs | NCBI gene metadata | Adds full name, aliases, chromosome, and missing NCBI Gene IDs. |
| `output_writing` | Apply NCBI metadata columns | `_apply_ncbi_metadata_columns()` | Final DataFrame, NCBI metadata map | DataFrame with NCBI metadata columns | Writes enrichment values onto emitted rows with uppercase-keyed lookup. |
| `output_writing` | Top-N policy | Inline block in `run_complete_pipeline()` | `all_results_df`, `top_n_cited`, minimal rows | Selected full rows plus appended minimal rows | Keeps up to N full-review PMIDs while preserving metadata-only rows for papers without final genes. |
| `output_writing` | Deduplication | Inline groupby block in `run_complete_pipeline()` | DataFrame rows by PMID/gene/user fields | Deduplicated DataFrame with aggregated variants | Merges duplicate rows that have identical user-facing fields and aggregates variant names. |
| `output_writing` | Column reorder | Inline block in `run_complete_pipeline()` | Deduplicated DataFrame | Final ordered DataFrame | Places gene/provenance columns first, user columns next, metadata/diagnostic columns last. |
| `output_writing` | Primary/metadata/Excel/JSON outputs | `_write_split_output()` | Final ordered DataFrame, output path, user column list | CSV, metadata CSV, XLSX, JSON paths | Writes the researcher-facing CSV, full metadata CSV, Excel workbook, and JSON output. |
| `output_writing` | Candidate audit artifact | `write_candidate_audit_artifact()` nested in `run_complete_pipeline()` | Final rows, per-paper debug artifacts | `candidate_audit_*.json` | Persists candidate lifecycle, gate drops, and final association summaries. |
| `output_writing` | Drop-debug artifact | `write_drop_debug_artifact()` nested in `run_complete_pipeline()` | Pipeline stats, paper debug, screening/fetch reports | `drop_debug_*.json` | Persists forensic diagnostics for failed or dropped candidates. |
| `output_writing` | Frontend result event | `run_pipeline.py:main()` | Orchestrator result dict | `RESULT:{json}` stdout line | Sends output paths and run stats back to Electron or the viewer server. |

## Trace Coverage Notes

| Domain / operation family | Trace status | Notes |
|---|---|---|
| PubMed metadata, full-text fetch, text cleaning, PubTator, citation fetch | Captured | These have compact trace events in `pipeline_orchestrator.py`. |
| Per-paper candidate discovery and gates | Captured | These have semantic `pipeline_tracer.stage(...)` contexts and many compact capture events. The API name is retained for trace compatibility. |
| NCBI enrichment | Function-context only | Wrapped in `pipeline_tracer.stage("ncbi_enrichment")`, but it does not yet emit a compact payload node. |
| Top-N policy, deduplication, column reorder | Not yet compact-captured | These are real output-writing operations, but the viewer should either mark them as inline output policy or add explicit capture events. |
| Output writer | Captured | `_write_split_output()` and audit/debug artifact paths are captured in `output_writer`. |
