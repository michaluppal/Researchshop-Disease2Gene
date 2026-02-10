# modules/pipeline_orchestrator.py

import os
import uuid
import time
import logging
import pandas as pd
import pickle
import gzip
from tqdm import tqdm
import json
import signal
import sys
from .progress_tracker import get_tracker, PipelineProgressTracker

from . import pubmed_data_collector, full_text_fetcher, config
from .gemini_extractor import GeneInfoPipeline
from .variant_normalizer import normalize_variants_in_dataframe
from .abstract_screener import has_genetic_content

# Global variable to track current pipeline state for graceful shutdown
_pipeline_state = {
    "output_path": None,
    "all_results_df": None,
    "minimal_rows": None,
    "collected_rows": None,
    "full_rows_pmids": None,
    "top_n_cited": None,
    "column_descriptions": None,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(module)s] - %(message)s",
)


def _run_pipeline_worker(text, cols, api_key, q, intermediate_q=None, pre_discovered_associations=None):
    """Top-level worker function for multiprocessing (must be picklable).
    
    Args:
        text: Paper text
        cols: Column descriptions
        api_key: Gemini API key
        q: Final result queue
        intermediate_q: Optional queue for intermediate results (gene count after Step 1)
        pre_discovered_associations: Optional pre-discovered associations
    """
    try:
        # Ensure the API key is available inside the child process
        from . import config as _config  # type: ignore
        import logging
        import pandas as pd

        _config.GEMINI_API_KEY = api_key

        inst = GeneInfoPipeline(text)
        
        # Step 0: Context validation
        context_validation = inst._validate_and_prepare_paper_text()
        if context_validation["failed"]:
            q.put({"error": "Context validation failed"})
            return
        
        # Step 1: Extract gene names (discovery)
        inst.extract_gene_names()
        
        # If full-text extraction found nothing but we have pre-discovered associations, use those as fallback
        if not inst.associations and pre_discovered_associations:
            inst.associations = pre_discovered_associations
        
        # Send intermediate result: gene count after Step 1
        if intermediate_q is not None:
            actual_gene_count = len(inst.associations)
            intermediate_q.put({"step": 1, "gene_count": actual_gene_count})
            logging.info(f"Step 1 complete: {actual_gene_count} genes discovered")
        
        # Step 2: Normalize associations (ensure gene-level associations)
        try:
            existing_pairs = set()
            genes_present = set()
            normalized = []
            for assoc in inst.associations:
                if isinstance(assoc, dict):
                    g = (assoc.get("gene") or "").strip()
                    v = assoc.get("variant") or ""
                else:
                    g, v = assoc
                g_up = g.strip().upper()
                v_norm = (v or "").strip()
                if isinstance(v_norm, str) and v_norm.upper() in {"N/A", "NA", "NONE"}:
                    v_norm = ""
                existing_pairs.add((g_up, v_norm))
                genes_present.add(g_up)
                normalized.append({"gene": g, "variant": v_norm})
            
            for g_up in genes_present:
                if (g_up, "") not in existing_pairs:
                    normalized.append({"gene": g_up, "variant": ""})
            
            inst.associations = normalized
        except Exception as e:
            logging.debug(f"Failed to ensure gene-level associations: {e}")
        
        # Step 3: Apply heuristics to validate extracted genes
        inst._apply_gene_validation_heuristics()
        
        # Step 4: Extract detailed info for validated associations
        extracted_info = inst.extract_gene_info(cols)
        
        # Step 5: Build final DataFrame
        if extracted_info:
            df = pd.DataFrame(extracted_info)
            inst._add_validation_metadata(df)
            
            # Only add citation validation if enabled
            if _config.ENABLE_CITATION_VALIDATION:
                inst._add_citation_validation_metadata(df)
            
            inst._add_context_metadata(df, context_validation)
            q.put({"records": df.to_dict(orient="records")})
        else:
            q.put({"records": []})
    except Exception as e:
        q.put({"error": str(e)})


def _create_unique_filepath(filename_base, extension):
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{filename_base}_{unique_id}.{extension}"
    return os.path.join(config.OUTPUT_DIR, filename)


def _save_incremental_results(
    all_results_df, minimal_rows, output_path, collected_rows, full_rows_pmids,
    top_n_cited, column_descriptions
):
    """
    Save results incrementally. Called after each paper or on interruption.
    This ensures we don't lose progress if the pipeline fails.
    """
    import csv
    from .variant_normalizer import normalize_variants_in_dataframe
    
    # Combine current results
    if all_results_df.empty:
        if minimal_rows:
            temp_df = pd.DataFrame(minimal_rows)
        else:
            temp_df = pd.DataFrame()
    else:
        temp_df = all_results_df.copy()
        
        # Add minimal rows for papers without results
        if minimal_rows:
            minimal_df = pd.DataFrame(minimal_rows)
            # Only add minimal rows for PMIDs not already in results
            existing_pmids = set(temp_df["PMID"].astype(str).unique())
            new_minimal = [
                mr for mr in minimal_rows 
                if str(mr["PMID"]) not in existing_pmids
            ]
            if new_minimal:
                temp_df = pd.concat([temp_df, pd.DataFrame(new_minimal)], ignore_index=True)
    
    if temp_df.empty:
        logging.warning("No results to save")
        return
    
    # Normalize variants if column exists
    if "Variant Name" in temp_df.columns:
        normalize_variants_in_dataframe(temp_df)
    
    # Reorder columns (simplified version of final ordering)
    core_columns = [
        "Gene/Group", "Variant Name", "PMID", "Study Title", "Authors",
        "Publication Year", "Journal Name", "Author Affiliations", "Citations", "Abstract"
    ]
    
    # Get user columns and metadata columns
    metadata_suffixes = [
        "_citation_valid", "_citation_confidence", "_citation_details",
        "validation_confidence", "validation_source", "validation_suggestions",
        "context_flash_fits", "context_pro_fits", "context_original_tokens",
        "context_modifications",
    ]
    
    user_columns_raw = [
        col for col in temp_df.columns
        if isinstance(col, str)  # Ensure column name is a string
        and col not in core_columns
        and not any(col.endswith(suffix) or col == suffix for suffix in metadata_suffixes)
    ]
    
    user_columns_list = []
    used = set()
    for col in user_columns_raw:
        if col in used:
            continue
        citation_col = f"{col} Citation"
        user_columns_list.append(col)
        if citation_col in temp_df.columns:
            user_columns_list.append(citation_col)
            used.add(citation_col)
        used.add(col)
    
    metadata_columns = [
        col for col in temp_df.columns
        if isinstance(col, str)  # Ensure column name is a string
        and any(col.endswith(suffix) or col == suffix for suffix in metadata_suffixes)
    ]
    
    # Build final column order
    final_column_order = []
    for col in core_columns:
        if col in temp_df.columns:
            final_column_order.append(col)
    final_column_order.extend(user_columns_list)
    final_column_order.extend(metadata_columns)
    
    # Reorder and save
    temp_df = temp_df[[col for col in final_column_order if col in temp_df.columns]]
    temp_df.to_csv(
        output_path, index=False, encoding="utf-8", quoting=csv.QUOTE_NONNUMERIC
    )
    logging.info(f"Incremental save: {len(temp_df)} rows saved to {output_path}")


def _sanitize_user_columns(user_columns: dict) -> dict:
    """Rename user-provided columns that collide with reserved/core names.

    Ensures the keys sent to the extractor are unique and do not overlap with
    core columns like 'Gene/Group', 'PMID', etc. If a collision is detected,
    the column is renamed to 'User: <name>'.
    """
    if not user_columns:
        return {}

    reserved_core = {
        "Gene/Group",
        "Variant Name",
        "PMID",
        "Study Title",
        "Authors",
        "Publication Year",
        "Journal Name",
        "Author Affiliations",
        "Citations",
        "Abstract",
        # Internal identifiers occasionally surfaced
        "gene_name",
        "variant_name",
    }

    out: dict = {}
    used: set = set()
    for raw_key, desc in user_columns.items():
        key = (raw_key or "").strip()
        if not key:
            continue
        # Avoid direct collisions with reserved core or already-used keys
        candidate = key
        if candidate in reserved_core or candidate in used:
            candidate = f"User: {candidate}"
        # If still collides, append numeric suffix until unique
        suffix = 2
        while candidate in reserved_core or candidate in used:
            candidate = f"{key} ({suffix})"
            suffix += 1
        out[candidate] = desc
        used.add(candidate)
    return out


def _ensure_unique_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DataFrame has uniquely named columns by suffixing duplicates.

    Pandas reindexing requires unique column names; this function disambiguates
    duplicates by appending " (2)", "(3)", ... in appearance order.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    cols = list(df.columns)
    seen_counts: dict[str, int] = {}
    new_cols: list[str] = []
    for c in cols:
        count = seen_counts.get(c, 0)
        if count == 0:
            new_cols.append(c)
        else:
            new_cols.append(f"{c} ({count+1})")
        seen_counts[c] = count + 1
    df.columns = new_cols
    return df


def run_complete_pipeline(
    query,
    specific_pmids,
    specific_authors,
    user_columns,
    top_n_cited,
    max_results=None,
    progress_callback=None,
    job_id=None,
):
    """
    Runs the complete pipeline with the provided parameters.
    """
    logging.info("--- STARTING COMPLETE PIPELINE RUN ---")
    start_time = time.time()
    metrics: dict = {"t_start": start_time}
    try:
        config.validate_runtime_configuration()
    except Exception as e:
        logging.critical(f"Runtime configuration validation failed: {e}")
        raise

    # Initialize progress tracker
    tracker = get_tracker()
    tracker.start_time = time.time()

    def report_progress(stage, pct):
        if progress_callback:
            progress_callback(stage, pct)
        logging.info(f"Progress: {stage} ({pct}%)")

    report_progress("Initializing pipeline", 0)
    init_timer = tracker.start_step("Initialization", "Setting up pipeline")
    init_timer.stop()  # Initialization is quick, stop immediately

    # Step 1 & 2: Get PMIDs and Details
    report_progress("Searching PubMed", 10)
    search_timer = tracker.start_step("PubMed Search", "Querying PubMed database")
    t_search_start = time.time()
    logging.info("STEP 1 & 2: Gathering and fetching details for all PMIDs...")
    initial_pmids = set()
    mandatory_pmids = set(specific_pmids)  # Start with explicit PMIDs
    author_pmids = set()

    if specific_authors:
        for author in specific_authors:
            author_results = pubmed_data_collector.search_pubmed_by_author(
                author, max_results=200
            )  # Keep your default max
            initial_pmids.update(author_results)
            author_pmids.update(author_results)

    mandatory_pmids |= author_pmids  # Union all author-derived PMIDs as mandatory

    # Always include explicitly requested PMIDs
    if mandatory_pmids:
        initial_pmids.update(mandatory_pmids)

    if query:
        # Strategy: get the most relevant (configurable), then later rank those by citations
        relevant_count = (
            max_results
            if max_results is not None
            else getattr(config, "PUBMED_RELEVANT_COUNT", 200)
        )
        query_results = pubmed_data_collector.search_pubmed(query, relevant_count)
        logging.info(f"PubMed search for '{query}' returned {len(query_results)} PMIDs")
        initial_pmids.update(query_results)

    metrics["search_pubmed_s"] = round(time.time() - t_search_start, 3)
    search_timer.stop()

    report_progress("Fetching paper details", 20)
    details_timer = tracker.start_step(
        "Fetch Paper Details", f"Fetching metadata for {len(initial_pmids)} papers"
    )
    t_details_start = time.time()

    # Add progress bar for paper details fetching
    paper_details = {}
    with tqdm(total=len(initial_pmids), desc="Fetching paper details") as pbar:
        # Fetch in batches with progress updates
        batch_size = 50
        for i in range(0, len(initial_pmids), batch_size):
            batch = list(initial_pmids)[i : i + batch_size]
            batch_details = pubmed_data_collector.fetch_paper_details(batch)
            paper_details.update(batch_details)
            pbar.update(len(batch))
    logging.info(
        f"Fetched details for {len(paper_details)} papers from {len(initial_pmids)} initial PMIDs"
    )
    metrics["fetch_details_s"] = round(time.time() - t_details_start, 3)
    details_timer.stop()

    # Step 3: Fetch Full Text first for relevance-selected PMIDs
    report_progress("Fetching full text", 30)
    t_fulltext_start = time.time()
    logging.info("STEP 3: Fetching full text for relevance-selected PMIDs...")
    pmids_to_fetch = list(paper_details.keys())
    logging.info(f"Preparing to fetch full text for {len(pmids_to_fetch)} PMIDs")
    content_dict_path = _create_unique_filepath("content_dict", "pkl.gz")
    # Use prioritized fetching to prioritize PMC open access papers
    full_text_fetcher.run_fetching_prioritized(pmids_to_fetch, content_dict_path)
    metrics["fetch_fulltext_s"] = round(time.time() - t_fulltext_start, 3)

    report_progress("Processing fetched content", 45)
    try:
        with gzip.open(content_dict_path, "rb") as f:
            content_dict = pickle.load(f)
    except Exception:
        logging.warning("Content dictionary is empty. No papers could be fetched.")
        return None

    # Keep only PMIDs successfully scraped
    scraped_pmids = list(content_dict.keys())
    if not scraped_pmids:
        logging.warning(
            "No scraped papers available after full-text step. Falling back to minimal rows from PubMed metadata."
        )
        # Build minimal rows for initial PMIDs using PubMed details and citation counts
        try:
            # Fetch citations for all initial candidates
            all_candidate_pmids = list(paper_details.keys())
            citations_dict = pubmed_data_collector.fetch_semantic_citation_counts(
                all_candidate_pmids
            )

            # Rank by citations desc and take top_n_cited
            # Sort by citation count (descending), then by PMID (ascending) for deterministic tie-breaking
            ranked = sorted(
                all_candidate_pmids,
                key=lambda p: (
                    -citations_dict.get(p, 0),  # Primary: descending citations
                    int(p),  # Secondary: ascending PMID (chronological)
                ),
            )
            selected = ranked[:top_n_cited] if top_n_cited else ranked

            minimal_rows_only = []
            for pmid in selected:
                base_info = paper_details.get(pmid, {})
                minimal_rows_only.append(
                    {
                        "Gene/Group": "",
                        "Variant Name": "",
                        "PMID": pmid,
                        "Study Title": base_info.get("title", "N/A"),
                        "Authors": ", ".join(base_info.get("authors", [])),
                        "Publication Year": base_info.get("year", "N/A"),
                        "Journal Name": base_info.get("journal", "N/A"),
                        "Author Affiliations": "; ".join(
                            base_info.get("affiliations", [])
                        ),
                        "Citations": citations_dict.get(pmid, 0),
                        "Abstract": base_info.get("abstract", "No abstract available"),
                    }
                )

            all_results_df = pd.DataFrame(minimal_rows_only)

            # Save immediately (no user columns beyond core ones yet)
            output_path = _create_unique_filepath("final_enriched_results", "csv")
            all_results_df.to_csv(output_path, index=False, encoding="utf-8")
            report_progress("Completed", 100)
            logging.info(
                f"--- PIPELINE FINISHED WITH MINIMAL ROWS IN {time.time() - start_time:.2f} SECONDS ---"
            )
            return {"local_path": output_path}
        except Exception as e:
            logging.error(f"Fallback to minimal rows failed: {e}")
            return None

    # Step 4: Fetch Citations only for scraped PMIDs and select top for AI
    report_progress("Fetching citation counts", 50)
    citations_timer = tracker.start_step(
        "Fetch Citation Counts", f"Fetching citations for {len(scraped_pmids)} papers"
    )
    t_citations_start = time.time()
    logging.info(
        "STEP 4: Fetching citations for scraped PMIDs and selecting top papers..."
    )

    # Add progress bar for citation fetching
    citations_dict = {}
    with tqdm(total=len(scraped_pmids), desc="Fetching citation counts") as pbar:
        # Fetch in batches
        batch_size = 100
        for i in range(0, len(scraped_pmids), batch_size):
            batch = scraped_pmids[i : i + batch_size]
            batch_citations = pubmed_data_collector.fetch_semantic_citation_counts(
                batch
            )
            citations_dict.update(batch_citations)
            pbar.update(len(batch))
    metrics["fetch_citations_s"] = round(time.time() - t_citations_start, 3)
    citations_timer.stop()

    scraped_details = {
        pmid: info for pmid, info in paper_details.items() if pmid in scraped_pmids
    }
    all_papers_df = pd.DataFrame.from_dict(scraped_details, orient="index")
    if "citations" not in all_papers_df.columns:
        all_papers_df["citations"] = 0
    for pmid, count in citations_dict.items():
        if pmid in all_papers_df.index:
            all_papers_df.at[pmid, "citations"] = count

    report_progress("Selecting top papers", 60)
    # Build processing order: mandatory (if scraped) keep first (original order), then remaining by citations desc
    scraped_set = set(all_papers_df.index)
    ordered_mandatory = [p for p in list(mandatory_pmids) if p in scraped_set]
    remaining_df = (
        all_papers_df.drop(ordered_mandatory, errors="ignore")
        if ordered_mandatory
        else all_papers_df
    )
    ranked_remaining = remaining_df.sort_values(
        by="citations", ascending=False
    ).index.tolist()
    pmids_to_process = ordered_mandatory + ranked_remaining
    logging.info(
        f"Prepared {len(pmids_to_process)} scraped PMIDs for AI analysis (mandatory first, then ranked by citations)."
    )

    # Abstract Pre-Screening: Skip papers unlikely to contain genetic content
    # Skip screening if ALL papers are user-provided (mandatory)
    # Abstract screening is only useful when filtering search results
    all_papers_are_mandatory = (
        mandatory_pmids
        and len(mandatory_pmids) > 0
        and set(pmids_to_process).issubset(mandatory_pmids)
    )

    if all_papers_are_mandatory:
        logging.info(
            f"Skipping abstract screening: all {len(pmids_to_process)} papers are user-provided (mandatory processing)"
        )
        metrics["screen_abstracts_s"] = 0.0
        metrics["screen_passed"] = len(pmids_to_process)
        metrics["screen_rejected"] = 0
        # pmids_to_process remains unchanged - all papers proceed
    elif getattr(config, "ENABLE_ABSTRACT_SCREENING", True):
        report_progress("Screening abstracts", 65)
        screening_timer = tracker.start_step(
            "Abstract Screening", f"Screening {len(pmids_to_process)} papers"
        )
        t_screen_start = time.time()
        logging.info(
            "STEP 4.5: Pre-screening papers by abstract content (keyword-based filtering)..."
        )

        threshold = getattr(config, "ABSTRACT_SCREENING_THRESHOLD", 5)
        prescreened_pmids = []
        rejected_pmids = []

        # Add progress bar for abstract screening
        with tqdm(total=len(pmids_to_process), desc="Screening abstracts") as pbar:
            for pmid in pmids_to_process:
                base_info = paper_details.get(pmid, {})
                title = base_info.get("title", "")
                abstract = base_info.get("abstract", "")

                should_process, confidence, details = has_genetic_content(
                    abstract, title, threshold
                )

                if (
                    should_process or pmid in mandatory_pmids
                ):  # Always include mandatory PMIDs
                    prescreened_pmids.append(pmid)
                else:
                    rejected_pmids.append(pmid)
                    logging.debug(
                        f"PMID {pmid} rejected by abstract screening: {details.get('reason', 'low score')}"
                    )
                pbar.update(1)

        logging.info(
            f"Abstract screening: {len(prescreened_pmids)}/{len(pmids_to_process)} passed ({len(prescreened_pmids)/len(pmids_to_process)*100:.1f}%), {len(rejected_pmids)} rejected"
        )
        metrics["screen_abstracts_s"] = round(time.time() - t_screen_start, 3)
        screening_timer.stop()
        metrics["screen_passed"] = len(prescreened_pmids)
        metrics["screen_rejected"] = len(rejected_pmids)
        pmids_to_process = prescreened_pmids
    else:
        # Abstract screening disabled via config
        logging.info("Abstract screening disabled via config")
        metrics["screen_abstracts_s"] = 0.0
        metrics["screen_passed"] = len(pmids_to_process)
        metrics["screen_rejected"] = 0

    # Apply top_n_cited limit after abstract screening
    if top_n_cited and len(pmids_to_process) > top_n_cited:
        logging.info(
            f"Limiting AI analysis to top {top_n_cited} papers (requested) from {len(pmids_to_process)} that passed screening"
        )
        pmids_to_process = pmids_to_process[:top_n_cited]

    if not pmids_to_process:
        logging.warning(
            "All papers were rejected by abstract screening. Falling back to minimal rows."
        )
        # Build minimal rows for all scraped PMIDs
        minimal_rows_only = []
        for pmid in scraped_pmids[:top_n_cited]:
            base_info = paper_details.get(pmid, {})
            minimal_rows_only.append(
                {
                    "Gene/Group": "",
                    "Variant Name": "",
                    "PMID": pmid,
                    "Study Title": base_info.get("title", "N/A"),
                    "Authors": ", ".join(base_info.get("authors", [])),
                    "Publication Year": base_info.get("year", "N/A"),
                    "Journal Name": base_info.get("journal", "N/A"),
                    "Author Affiliations": "; ".join(base_info.get("affiliations", [])),
                    "Citations": citations_dict.get(pmid, 0),
                    "Abstract": base_info.get("abstract", "No abstract available"),
                }
            )
        all_results_df = pd.DataFrame(minimal_rows_only)
        output_path = _create_unique_filepath("final_enriched_results", "csv")
        all_results_df.to_csv(output_path, index=False, encoding="utf-8")
        report_progress("Completed", 100)
        logging.info(
            f"--- PIPELINE FINISHED WITH MINIMAL ROWS IN {time.time() - start_time:.2f} SECONDS ---"
        )
        return {"local_path": output_path}

    report_progress("Analyzing papers with AI", 70)
    ai_timer = tracker.start_step(
        "AI Analysis", f"Analyzing {len(pmids_to_process)} papers with Gemini"
    )
    t_ai_start = time.time()
    # Step 5: Process each paper using the GeneInfoPipeline class
    logging.info("STEP 5: Analyzing papers with Gemini using the GeneInfoPipeline...")
    all_results_df = pd.DataFrame()
    # Sanitize user columns to avoid collisions with core fields
    column_descriptions = _sanitize_user_columns(user_columns)

    total_papers = len(pmids_to_process)
    collected_rows = []
    full_rows_pmids = set()
    minimal_rows = []
    enable_abstract_discovery = getattr(config, "ENABLE_ABSTRACT_GENE_DISCOVERY", True)
    
    # Create output file path at the start for incremental saving
    output_path = _create_unique_filepath("final_enriched_results", "csv")
    _pipeline_state["output_path"] = output_path
    _pipeline_state["all_results_df"] = all_results_df
    _pipeline_state["minimal_rows"] = minimal_rows
    _pipeline_state["collected_rows"] = collected_rows
    _pipeline_state["full_rows_pmids"] = full_rows_pmids
    _pipeline_state["top_n_cited"] = top_n_cited
    _pipeline_state["column_descriptions"] = column_descriptions
    logging.info(f"Incremental saving enabled - results will be saved to: {output_path}")
    
    # Set up signal handlers for graceful shutdown
    def save_and_exit(signum, frame):
        """Save current results and exit gracefully on interruption"""
        logging.warning(f"Pipeline interrupted (signal {signum}) - saving current results...")
        try:
            _save_incremental_results(
                _pipeline_state["all_results_df"],
                _pipeline_state["minimal_rows"],
                _pipeline_state["output_path"],
                _pipeline_state["collected_rows"],
                _pipeline_state["full_rows_pmids"],
                _pipeline_state["top_n_cited"],
                _pipeline_state["column_descriptions"]
            )
            logging.info(f"Results saved to: {_pipeline_state['output_path']}")
        except Exception as e:
            logging.error(f"Error saving results on interruption: {e}")
        sys.exit(0)
    
    try:
        signal.signal(signal.SIGINT, save_and_exit)  # Ctrl+C
        signal.signal(signal.SIGTERM, save_and_exit)  # Termination signal
    except ValueError:
        # signal only works in main thread; skip when running from Flask/GUI
        pass

    for i, pmid in enumerate(tqdm(pmids_to_process, desc="Processing papers")):
        # Report progress for AI analysis phase (70-95%)
        ai_progress = 70 + int((i / total_papers) * 25)
        report_progress("Analyzing papers with AI", ai_progress)

        content = content_dict.get(pmid, {})
        paper_text = content.get("content", "")
        if not paper_text:
            # No extracted content: create a minimal row so the study is still represented
            base_info = paper_details.get(pmid, {})
            minimal_rows.append(
                {
                    "Gene/Group": "",
                    "Variant Name": "",
                    "PMID": pmid,
                    "Study Title": base_info.get("title", "N/A"),
                    "Authors": ", ".join(base_info.get("authors", [])),
                    "Publication Year": base_info.get("year", "N/A"),
                    "Journal Name": base_info.get("journal", "N/A"),
                    "Author Affiliations": "; ".join(base_info.get("affiliations", [])),
                    "Citations": citations_dict.get(pmid, 0),
                    "Abstract": base_info.get("abstract", "No abstract available"),
                }
            )
            continue

        # Two-Stage Gemini Pipeline
        # Stage 1: Abstract-based gene discovery (minimal token usage)
        base_info = paper_details.get(pmid, {})
        abstract = base_info.get("abstract", "")
        title = base_info.get("title", "")
        associations_from_abstract = []

        # Check if this is a user-provided PMID (mandatory processing)
        is_mandatory_pmid = pmid in mandatory_pmids

        # Skip abstract discovery entirely for user-provided PMIDs (waste of API calls)
        if (
            enable_abstract_discovery
            and abstract
            and len(abstract) > 50
            and not is_mandatory_pmid
        ):
            try:
                # Quick gene discovery on abstract only (saves 99%+ tokens vs full text)
                from .gemini_extractor import GeneInfoPipeline as AbstractPipeline

                abstract_pipeline = AbstractPipeline("", abstract_text=abstract)
                associations_from_abstract = (
                    abstract_pipeline.extract_gene_names_from_abstract(title)
                )

                # Skip full-text analysis ONLY if:
                # 1. No genes found in abstract AND
                # 2. This is NOT a user-provided PMID (mandatory processing)
                if not associations_from_abstract and not is_mandatory_pmid:
                    logging.info(
                        f"PMID {pmid}: No genes found in abstract - skipping expensive full-text analysis"
                    )
                    minimal_rows.append(
                        {
                            "Gene/Group": "",
                            "Variant Name": "",
                            "PMID": pmid,
                            "Study Title": title,
                            "Authors": ", ".join(base_info.get("authors", [])),
                            "Publication Year": base_info.get("year", "N/A"),
                            "Journal Name": base_info.get("journal", "N/A"),
                            "Author Affiliations": "; ".join(
                                base_info.get("affiliations", [])
                            ),
                            "Citations": citations_dict.get(pmid, 0),
                            "Abstract": abstract,
                        }
                    )
                    continue  # Skip full-text analysis - saved ~50K tokens!
                elif not associations_from_abstract and is_mandatory_pmid:
                    logging.info(
                        f"PMID {pmid}: No genes found in abstract, but proceeding to full-text analysis (user-provided PMID - mandatory processing)"
                    )
                    # Don't skip - proceed to full-text analysis below

                logging.info(
                    f"PMID {pmid}: Abstract discovery found {len(associations_from_abstract)} genes - proceeding to full-text extraction"
                )
            except Exception as e:
                logging.warning(
                    f"PMID {pmid}: Abstract gene discovery failed ({e}), falling back to full-text discovery"
                )
                associations_from_abstract = []  # Fallback to full-text discovery

        # Stage 2: Full-text extraction with Pro model (only if genes found or abstract discovery disabled)
        paper_df = pd.DataFrame()
        try:
            import multiprocessing as mp

            result_queue = mp.Queue()
            intermediate_queue = mp.Queue()  # For intermediate results (gene count after Step 1)

            # Use abstract discoveries for full-text extraction
            pre_discovered = associations_from_abstract

            # Two-phase timeout approach:
            # Phase 1: Short timeout for Step 1 (discovery) - 60s
            # Phase 2: After Step 1, recalculate timeout for Step 2+3 based on actual genes
            
            # Phase 1: Initial timeout for Step 1 (discovery)
            step1_timeout = 60  # 60 seconds for gene discovery
            
            # Phase 2: Base timeout for Step 2+3 (validation + detailed extraction)
            base_timeout_step2_3 = 120  # 2 minutes base time for validation + detailed extraction
            time_per_batch = 25  # Seconds per batch (conservative estimate)
            batch_threshold = getattr(config, "GENE_BATCH_THRESHOLD", 8)
            safety_margin = 2.0  # 100% safety buffer

            # Estimate genes based on paper length (rough heuristic: ~1 gene per 2000 chars)
            # This is only used for initial logging - actual timeout will be recalculated after Step 1
            estimated_genes = max(
                len(associations_from_abstract) if associations_from_abstract else 0,
                len(paper_text) // 2000,  # Rough estimate: 1 gene per 2000 chars
            )
            estimated_batches = max(
                1, (estimated_genes + batch_threshold - 1) // batch_threshold
            )

            logging.info(
                f"PMID {pmid}: Two-phase timeout approach - "
                f"Phase 1 (Step 1): {step1_timeout}s, "
                f"Phase 2 (Step 2+3): will be recalculated after Step 1 completes "
                f"(estimated {estimated_genes} genes, {estimated_batches} batches, "
                f"paper length: {len(paper_text)} chars)"
            )

            proc = mp.Process(
                target=_run_pipeline_worker,
                args=(
                    paper_text,
                    column_descriptions,
                    config.GEMINI_API_KEY,
                    result_queue,
                    intermediate_queue,  # Pass intermediate queue for Step 1 results
                    pre_discovered,  # pass composed pre-discovered associations (may be None/empty)
                ),
            )
            proc.start()

            # Phase 1: Wait for Step 1 (discovery) to complete
            proc.join(timeout=step1_timeout)
            if proc.is_alive():
                # Check if Step 1 completed and we got intermediate results
                actual_gene_count = None
                if not intermediate_queue.empty():
                    intermediate_result = intermediate_queue.get()
                    if isinstance(intermediate_result, dict) and intermediate_result.get("step") == 1:
                        actual_gene_count = intermediate_result.get("gene_count")
                        logging.info(
                            f"PMID {pmid}: Step 1 complete - {actual_gene_count} genes discovered "
                            f"(estimated {estimated_genes})"
                        )
                
                # If Step 1 didn't complete, wait a bit more (process might be slow)
                if actual_gene_count is None:
                    # Wait a bit more for Step 1 to complete
                    remaining_step1_time = 30  # Give it 30 more seconds
                    proc.join(timeout=remaining_step1_time)
                    if not intermediate_queue.empty():
                        intermediate_result = intermediate_queue.get()
                        if isinstance(intermediate_result, dict) and intermediate_result.get("step") == 1:
                            actual_gene_count = intermediate_result.get("gene_count")
                            logging.info(
                                f"PMID {pmid}: Step 1 complete (delayed) - {actual_gene_count} genes discovered"
                            )
                
                # Phase 2: Recalculate timeout for Step 2+3 based on actual genes
                step2_3_timeout = None
                if actual_gene_count is not None:
                    # Use actual gene count to calculate timeout for Step 2+3
                    actual_batches = max(1, (actual_gene_count + batch_threshold - 1) // batch_threshold)
                    step2_3_timeout = int(
                        base_timeout_step2_3 + (actual_batches * time_per_batch * safety_margin)
                    )
                    # Cap at reasonable maximum (30 minutes) and minimum (2 minutes)
                    step2_3_timeout = max(120, min(step2_3_timeout, 1800))
                    
                    logging.info(
                        f"PMID {pmid}: Phase 2 timeout recalculated: {step2_3_timeout}s "
                        f"(actual {actual_gene_count} genes, {actual_batches} batches)"
                    )
                    
                    # Wait for remaining steps (Step 2+3) with recalculated timeout
                    proc.join(timeout=step2_3_timeout)
                else:
                    # Step 1 didn't complete or didn't send intermediate result
                    # Use conservative timeout based on estimated genes
                    estimated_batches = max(1, (estimated_genes + batch_threshold - 1) // batch_threshold)
                    step2_3_timeout = int(
                        base_timeout_step2_3 + (estimated_batches * time_per_batch * safety_margin)
                    )
                    step2_3_timeout = max(120, min(step2_3_timeout, 1800))
                    
                    logging.warning(
                        f"PMID {pmid}: Step 1 didn't complete or send intermediate result, "
                        f"using fallback timeout: {step2_3_timeout}s "
                        f"(estimated {estimated_genes} genes, {estimated_batches} batches)"
                    )
                    proc.join(timeout=step2_3_timeout)
                
                # Check if process is still alive after Phase 2
                if proc.is_alive():
                    proc.terminate()
                    proc.join()
                    logging.warning(
                        f"AI analysis timed out for PMID {pmid} after two-phase timeout "
                        f"(Step 1: {step1_timeout}s, Step 2+3: {step2_3_timeout}s); skipping"
                    )
                else:
                    # Process completed successfully
                    if not result_queue.empty():
                        payload = result_queue.get()
                        if isinstance(payload, dict) and payload.get("error"):
                            logging.error(
                                f"AI analysis error for PMID {pmid}: {payload['error']}"
                            )
                            paper_df = pd.DataFrame()
                        elif (
                            isinstance(payload, dict) and payload.get("records") is not None
                        ):
                            paper_df = pd.DataFrame(
                                payload["records"]
                            )  # reconstruct DataFrame
            else:
                # Process completed during Phase 1 (very fast - unlikely but possible)
                if not result_queue.empty():
                    payload = result_queue.get()
                    if isinstance(payload, dict) and payload.get("error"):
                        logging.error(
                            f"AI analysis error for PMID {pmid}: {payload['error']}"
                        )
                        paper_df = pd.DataFrame()
                    elif (
                        isinstance(payload, dict) and payload.get("records") is not None
                    ):
                        paper_df = pd.DataFrame(
                            payload["records"]
                        )  # reconstruct DataFrame
        except Exception as e:
            logging.error(f"Failed AI analysis for PMID {pmid}: {e}")
            paper_df = pd.DataFrame()

        # Rename columns to match user requirements
        paper_df = paper_df.rename(
            columns={"gene_name": "Gene/Group", "variant_name": "Variant Name"}
        )  # Optional: Include variant if extracted

        base_info = paper_details.get(pmid, {})
        paper_df["PMID"] = pmid
        paper_df["Study Title"] = base_info.get("title", "N/A")
        paper_df["Authors"] = ", ".join(base_info.get("authors", []))
        paper_df["Publication Year"] = base_info.get("year", "N/A")
        paper_df["Journal Name"] = base_info.get("journal", "N/A")
        paper_df["Author Affiliations"] = "; ".join(base_info.get("affiliations", []))
        paper_df["Citations"] = citations_dict.get(
            pmid, 0
        )  # Kept for reference, can drop if not needed

        # Use actual paper data for basic fields instead of AI extraction
        # ALWAYS add abstract to all rows, regardless of whether column exists
        abstract_text = base_info.get("abstract", "No abstract available")
        if "Abstract" not in paper_df.columns:
            paper_df["Abstract"] = abstract_text
        else:
            paper_df["Abstract"] = abstract_text

        # Fallback: if AI produced no rows, stage a minimal row to append later
        if paper_df.empty:
            minimal_row = {
                "Gene/Group": "",
                "Variant Name": "",
                "PMID": pmid,
                "Study Title": base_info.get("title", "N/A"),
                "Authors": ", ".join(base_info.get("authors", [])),
                "Publication Year": base_info.get("year", "N/A"),
                "Journal Name": base_info.get("journal", "N/A"),
                "Author Affiliations": "; ".join(base_info.get("affiliations", [])),
                "Citations": citations_dict.get(pmid, 0),
                "Abstract": base_info.get("abstract", "No abstract available"),
            }
            minimal_rows.append(minimal_row)
            
            # Update global state for signal handlers
            _pipeline_state["all_results_df"] = all_results_df
            _pipeline_state["minimal_rows"] = minimal_rows
            _pipeline_state["collected_rows"] = collected_rows
            _pipeline_state["full_rows_pmids"] = full_rows_pmids
            
            # Incremental save: Save even minimal rows so we track all processed papers
            try:
                _save_incremental_results(
                    all_results_df, minimal_rows, output_path,
                    collected_rows, full_rows_pmids, top_n_cited, column_descriptions
                )
            except Exception as e:
                logging.warning(f"Failed to save incremental results: {e} (will retry at end)")
        else:
            # Defensively ensure unique column names before concatenation
            paper_df = _ensure_unique_columns(paper_df)
            all_results_df = _ensure_unique_columns(all_results_df)
            all_results_df = pd.concat([all_results_df, paper_df], ignore_index=True)
            collected_rows.append(pmid)
            full_rows_pmids.add(pmid)
            
            # Update global state for signal handlers
            _pipeline_state["all_results_df"] = all_results_df
            _pipeline_state["minimal_rows"] = minimal_rows
            _pipeline_state["collected_rows"] = collected_rows
            _pipeline_state["full_rows_pmids"] = full_rows_pmids
            
            # Incremental save: Save after each paper is processed
            # This ensures we don't lose progress if pipeline fails or is interrupted
            try:
                _save_incremental_results(
                    all_results_df, minimal_rows, output_path,
                    collected_rows, full_rows_pmids, top_n_cited, column_descriptions
                )
            except Exception as e:
                logging.warning(f"Failed to save incremental results: {e} (will retry at end)")

    if all_results_df.empty:
        if minimal_rows:
            logging.warning("AI produced no rows; falling back to minimal rows only.")
            all_results_df = pd.DataFrame(minimal_rows)
        else:
            logging.warning("No results were extracted by the pipeline.")
            report_progress("Completed", 100)
            return None

    # Enforce desired output policy:
    # - Include up to 'desired' fully reviewed studies (AI-produced rows) first
    # - Append minimal rows for remaining scraped PMIDs at the end (do not count toward N)
    desired = top_n_cited
    if desired:
        # Order full-review PMIDs by processing order
        ordered_full = []
        for pmid in collected_rows:
            if pmid in full_rows_pmids and pmid not in ordered_full:
                ordered_full.append(pmid)
        selected_full_list = ordered_full[:desired]
        selected_full_set = set(selected_full_list)

        # Keep only rows for selected full-review PMIDs (up to N)
        full_df = all_results_df[
            all_results_df["PMID"].isin(selected_full_set)
        ].reset_index(drop=True)

        # Build minimal rows for PMIDs that had no full rows (in original processing order)
        minimal_append = []
        selected_full_or_minimal_pmids = set(selected_full_set)
        for mr in minimal_rows:
            if mr["PMID"] in selected_full_or_minimal_pmids:
                continue
            minimal_append.append(mr)
            selected_full_or_minimal_pmids.add(mr["PMID"])

        if minimal_append:
            all_results_df = pd.concat(
                [full_df, pd.DataFrame(minimal_append)], ignore_index=True
            )
        else:
            all_results_df = full_df

    metrics["ai_analysis_s"] = round(time.time() - t_ai_start, 3)
    ai_timer.stop()

    report_progress("Finalizing results", 95)
    finalize_timer = tracker.start_step(
        "Finalize Results", "Processing and saving final results"
    )

    # Normalize variant names to standard format
    if not all_results_df.empty and "Variant Name" in all_results_df.columns:
        normalize_variants_in_dataframe(all_results_df)

    # De-duplicate: If multiple rows within the same PMID and gene have identical user fields, aggregate variant names
    try:
        if not all_results_df.empty:
            core_cols = [
                "PMID",
                "Gene/Group",
                "Variant Name",
                "Study Title",
                "Authors",
                "Publication Year",
                "Journal Name",
                "Author Affiliations",
                "Citations",
            ]
            # Identify user columns (including their citation pairs) that are not core or metadata
            metadata_suffixes = [
                "_citation_valid",
                "_citation_confidence",
                "_citation_details",
                "validation_confidence",
                "validation_source",
                "validation_suggestions",
                "context_flash_fits",
                "context_pro_fits",
                "context_original_tokens",
                "context_modifications",
            ]

            user_cols = [
                c
                for c in all_results_df.columns
                if c not in core_cols
                and not any(c.endswith(s) or c == s for s in metadata_suffixes)
            ]

            # Grouping keys exclude 'Variant Name' so we can aggregate it when other fields are identical
            group_keys = [
                "PMID",
                "Gene/Group",
                "Study Title",
                "Authors",
                "Publication Year",
                "Journal Name",
            ] + user_cols

            # Only dedup rows that actually have a gene (skip minimal rows lacking gene info)
            has_gene_mask = all_results_df["Gene/Group"].fillna("") != ""
            df_full = all_results_df[has_gene_mask].copy()
            df_minimal = all_results_df[~has_gene_mask].copy()

            if not df_full.empty:
                agg_map = {
                    c: "first"
                    for c in df_full.columns
                    if c not in group_keys + ["Variant Name"]
                }

                # Aggregate variant names: unique; sorted; semicolon-joined
                def _agg_variants(series):
                    vals = {str(v) for v in series if str(v).strip()}
                    return "; ".join(sorted(vals))

                agg_map["Variant Name"] = _agg_variants

                df_full = df_full.groupby(group_keys, dropna=False, as_index=False).agg(
                    agg_map
                )

                # Recombine full and minimal, preserving original order later via sort key
                all_results_df = pd.concat([df_full, df_minimal], ignore_index=True)
    except Exception as e:
        logging.warning(f"Deduplication step skipped due to error: {e}")

    # Ensure unique columns before reordering to prevent reindex errors
    all_results_df = _ensure_unique_columns(all_results_df)

    # Reorder columns for better readability
    # Core columns first, then user-defined columns paired with their citations, then metadata at the end
    core_columns = [
        "Gene/Group",
        "Variant Name",
        "PMID",
        "Study Title",
        "Authors",
        "Publication Year",
        "Journal Name",
        "Author Affiliations",
        "Citations",
    ]

    # User-defined columns (exclude core and metadata columns)
    metadata_suffixes = [
        "_citation_valid",
        "_citation_confidence",
        "_citation_details",
        "validation_confidence",
        "validation_source",
        "validation_suggestions",
        "context_flash_fits",
        "context_pro_fits",
        "context_original_tokens",
        "context_modifications",
    ]

    user_columns_raw = [
        col
        for col in all_results_df.columns
        if isinstance(col, str)  # Ensure column name is a string
        and col not in core_columns
        and not any(
            col.endswith(suffix) or col == suffix for suffix in metadata_suffixes
        )
    ]
    # Pair user columns with their citation columns if present
    user_columns_list = []
    used = set()
    for col in user_columns_raw:
        if col in used:
            continue
        citation_col = f"{col} Citation"
        user_columns_list.append(col)
        if citation_col in all_results_df.columns:
            user_columns_list.append(citation_col)
            used.add(citation_col)
        used.add(col)

    # Metadata columns at the end
    metadata_columns = [
        col
        for col in all_results_df.columns
        if isinstance(col, str)  # Ensure column name is a string
        and any(col.endswith(suffix) or col == suffix for suffix in metadata_suffixes)
    ]

    # Build final column order
    final_column_order = []
    for col in core_columns:
        if col in all_results_df.columns:
            final_column_order.append(col)
    final_column_order.extend(user_columns_list)
    final_column_order.extend(metadata_columns)

    all_results_df = all_results_df[final_column_order]

    # Step 6: Save final results (incremental save already done, but do final save with all processing)
    # Use QUOTE_NONNUMERIC to properly quote all non-numeric fields (prevents comma issues in Author/Affiliation fields)
    import csv

    # Final save (incremental saves already happened, but this ensures final state is saved)
    all_results_df.to_csv(
        output_path, index=False, encoding="utf-8", quoting=csv.QUOTE_NONNUMERIC
    )
    logging.info(f"Final results saved to: {output_path}")

    finalize_timer.stop()
    report_progress("Completed", 100)

    # Log comprehensive performance summary
    tracker.log_summary()

    total_s = time.time() - start_time
    metrics["total_s"] = round(total_s, 3)
    metrics["pmids_initial"] = len(initial_pmids)
    metrics["pmids_scraped"] = len(scraped_pmids)
    metrics["pmids_ai_processed"] = len(collected_rows)
    logging.info(json.dumps({"metrics": metrics}))
    return {"local_path": output_path, "metrics": metrics}
