# modules/pipeline_orchestrator.py

import logging
import os
import time
import uuid

import pandas as pd

from . import config, pipeline_tracer, pubmed_data_collector
from .abstract_screener import has_genetic_content
from .analysis_runner import run_paper_analysis, run_pipeline_worker as _run_pipeline_worker
from .association_policy import (
    ASSOCIATION_GROUP_ORDER,
    association_group_for_type,
)
from .paper_reading import fetch_oa_full_text_and_pubtator, prepare_paper_inputs
from .pipeline_artifacts import (
    RunArtifactWriter,
    candidate_audit_rows_by_pmid as _artifact_candidate_audit_rows_by_pmid,
    candidate_audit_summary as _artifact_candidate_audit_summary,
)
from .paper_selection import select_papers_and_fetch_metadata
from .pipeline_state import PipelineEmitters, PipelineRunState
from .pubtator_tool import NCBIGeneTool
from .result_enrichment import (
    accumulate_result as _accumulate_result,
    apply_ncbi_metadata_columns as _apply_ncbi_metadata_columns,
    apply_pubtator_row_enrichment as _apply_pubtator_row_enrichment,
    aggregate_strict_gate_drops as _aggregate_strict_gate_drops,
    finalize_paper_result as _finalize_paper_result,
    get_citation_record as _get_citation_record,
)


def _compute_row_confidence(row: dict, user_cols: list) -> tuple:
    """Compute a single confidence signal per output row.

    Returns (level, note) where level is HIGH/MEDIUM/LOW/REVIEW.

    - HIGH:   Gene corroborated by both PubTator NER + Gemini LLM, AND at least
              one citation verified in paper text. Strongest evidence tier.
    - MEDIUM: Gene passed all validation gates (confidence >= 0.85, grounding
              check, strict gate) but lacks full corroboration. Typical cases:
              LLM-only gene (PubTator missed it), corroborated gene without a
              validated citation (LLM stochastically omitted citations), or
              single-source gene with a valid citation.
    - LOW:    Abstract-only paper (no full text available) or validation
              confidence below 0.85 (borderline HGNC match).
    - REVIEW: Citation text not found in paper (mismatch), gene extracted
              only from figures with no prose source, OR row was produced by
              skeleton/auto-snippet fallback because Gemini failed (F11).
              Requires manual check.
    """
    # Guard: empty gene name is never a valid extraction
    if not str(row.get("Gene/Group", "") or "").strip():
        return "REVIEW", "No genes extracted"

    # F11: Extraction-mode check runs before any other tier logic — a skeleton
    # row can't be HIGH/MEDIUM/LOW even if the gene's HGNC validation is 1.0,
    # because the LLM didn't read the paper's context for this gene. The row
    # exists to preserve the gene identity, not as an actual extraction result.
    extraction_mode = str(row.get("extraction_mode", "") or "").strip()
    if extraction_mode == "skeleton":
        err = str(row.get("detail_extraction_error", "") or "").strip()
        err_short = (err[:80] + "…") if len(err) > 80 else err
        evidence_backfilled = bool(row.get("evidence_backfilled", False))
        if evidence_backfilled:
            note = "LLM failed; auto-snippet fallback" + (f" ({err_short})" if err_short else "")
        else:
            note = "LLM failed; no content" + (f" ({err_short})" if err_short else "")
        # F12: surface peer-gene context when the backfill snippet was a co-mention
        # rather than a gene-specific sentence.
        if row.get("evidence_specificity") == "co_mention":
            co_mentioned = str(row.get("co_mentioned_genes") or "").strip()
            if co_mentioned:
                note += f" | co-mention with {co_mentioned.replace(';', ', ')}"
        return "REVIEW", note

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
        note = (
            "Figure-only gene — no prose citation available"
            if is_figure_only
            else "Citation text not found in paper"
        )
        return "REVIEW", note

    # LOW: no full text or borderline confidence
    if not has_full_text:
        return "LOW", "Abstract only"
    if val_conf < 0.85:
        return "LOW", "Low confidence"

    # HIGH: corroborated by multiple sources AND verified citation
    if gene_source == "both" and any_valid:
        return "HIGH", ""

    # MEDIUM: default (passed gates, citation stochastic or absent)
    if all_empty:
        note = ""
    elif not any_valid:
        note = "No citation"
    else:
        note = ""
    # F12: defensively surface peer-gene context when a backfilled row lands
    # outside the skeleton branch (e.g. LLM returned content but evidence
    # gate pulled a co-mention snippet). Guarded on both flags so future
    # writers of evidence_specificity can't trigger this branch without the
    # causal chain — the only current writer is _backfill_sparse_row_evidence.
    if row.get("evidence_backfilled") and row.get("evidence_specificity") == "co_mention":
        co_mentioned = str(row.get("co_mentioned_genes") or "").strip()
        if co_mentioned:
            suffix = f"co-mention with {co_mentioned.replace(';', ', ')}"
            note = f"{note} | {suffix}" if note else suffix
    return "MEDIUM", note


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(module)s] - %(message)s"
)


def _validate_gemini_call_budget() -> None:
    max_calls = int(getattr(config, "GEMINI_MAX_CALLS_PER_PAPER", 0) or 0)
    if 0 < max_calls < 2:
        raise ValueError(
            "Invalid GEMINI_MAX_CALLS_PER_PAPER="
            f"{max_calls}: full-text paper analysis requires at least 2 Gemini "
            "calls per paper (mandatory full-text candidate discovery + detail "
            "extraction). Set GEMINI_MAX_CALLS_PER_PAPER=0 for unlimited or >=2."
        )


def _create_unique_filepath(filename_base, extension):
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{filename_base}_{unique_id}.{extension}"
    return os.path.join(config.OUTPUT_DIR, filename)


def _write_excel_output(
    df_clean: "pd.DataFrame",
    df_meta: "pd.DataFrame",
    excel_path: "os.PathLike",
) -> None:
    """Write a two-sheet Excel workbook: Results (clean) + Metadata (full).

    Sheet 1 'Results': clean researcher-facing columns with Confidence color coding.
    Sheet 2 'Metadata': full diagnostic/validation columns for auditing.
    Silently skips if openpyxl is not installed.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        logging.warning(
            "openpyxl not installed — Excel output skipped. "
            "Install with: pip install openpyxl"
        )
        return

    _CONFIDENCE_FILLS = {
        "HIGH": "D4EDDA",
        "MEDIUM": "FFF9C4",
        "LOW": "FFE0B2",
        "REVIEW": "FCE4EC",
    }

    def _fill_sheet(ws, df: "pd.DataFrame", sheet_title: str, apply_conf_color: bool) -> None:
        ws.title = sheet_title
        headers = list(df.columns)
        conf_col_idx = (headers.index("Confidence") + 1) if (apply_conf_color and "Confidence" in headers) else None
        header_font = Font(bold=True)
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.alignment = Alignment(wrap_text=False)
        for row_idx, row in enumerate(df.itertuples(index=False), start=2):
            for col_idx, value in enumerate(row, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=str(value) if value is not None else "")
                if conf_col_idx and col_idx == conf_col_idx:
                    hex_color = _CONFIDENCE_FILLS.get(str(value))
                    if hex_color:
                        cell.fill = PatternFill(fill_type="solid", fgColor=hex_color)
        ws.freeze_panes = "A2"
        # Auto-size columns (sample first 100 rows for speed)
        for col_idx, header in enumerate(headers, start=1):
            col_letter = get_column_letter(col_idx)
            sample_rows = range(2, min(ws.max_row + 1, 102))
            max_len = max(
                len(str(header)),
                max((len(str(ws.cell(row=r, column=col_idx).value or "")) for r in sample_rows), default=0),
            )
            ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

    wb = Workbook()
    _fill_sheet(wb.active, df_clean, "Results", apply_conf_color=True)
    _fill_sheet(wb.create_sheet("Metadata"), df_meta, "Metadata", apply_conf_color=False)
    if "Association Group" in df_clean.columns:
        for group, group_df in df_clean.groupby("Association Group", dropna=False, sort=False):
            group_name = str(group or "Unclassified")
            safe_title = "".join(ch for ch in group_name if ch not in r'[]:*?/\\')[:31]
            if safe_title and safe_title not in wb.sheetnames:
                _fill_sheet(
                    wb.create_sheet(safe_title),
                    group_df,
                    safe_title,
                    apply_conf_color=True,
                )
    wb.save(excel_path)


def _write_json_output(df_clean: "pd.DataFrame", json_path: "os.PathLike") -> None:
    """Write the clean results as a JSON array of records."""
    df_clean = _ensure_unique_columns(df_clean.copy())
    df_clean.to_json(json_path, orient="records", indent=2, force_ascii=False)


def _unique_preserve_order(items: list) -> list:
    """Return items with duplicates removed while preserving first appearance."""
    seen = set()
    unique = []
    for item in items:
        if item in seen:
            continue
        unique.append(item)
        seen.add(item)
    return unique


def _write_split_output(
    df: "pd.DataFrame",
    output_path: "os.PathLike",
    user_cols: list,
) -> tuple:
    """Write primary CSV, metadata CSV, Excel workbook, and JSON file.

    Primary CSV: Gene, Variant, [user cols], Confidence, Confidence Note,
                 PMID, Title, Year, Journal, Authors, Citations, DOI
    Metadata CSV: PMID, Gene/Group, Variant Name + all diagnostic/validation columns
    Excel: two-sheet workbook (Results + Metadata), Confidence cells color-coded
    JSON: primary CSV data as an array of records

    Both CSV files share PMID + Gene/Group as join keys and have identical row order.

    Args:
        df: Full results DataFrame with all columns.
        output_path: Destination path for the primary CSV (.csv extension).
        user_cols: List of user-defined column names (without Citation pairs).

    Returns:
        (primary_path, metadata_path, excel_path, json_path) as strings.
    """
    from pathlib import Path

    output_path = Path(output_path)
    df = _ensure_unique_columns(df.copy())

    # Compute confidence flags row-by-row
    confidence_rows = [
        _compute_row_confidence(row, user_cols)
        for row in df.to_dict("records")
    ]
    df = df.copy()
    df["Confidence"] = [r[0] for r in confidence_rows]
    df["Confidence Note"] = [r[1] for r in confidence_rows]
    if "Association Type" in df.columns and "Association Group" not in df.columns:
        df["Association Group"] = df["Association Type"].apply(association_group_for_type)
    if "Association Group" in df.columns:
        df["_association_group_order"] = df["Association Group"].map(
            lambda group: ASSOCIATION_GROUP_ORDER.get(str(group or ""), 99)
        )
        sort_cols = [
            col
            for col in ["_association_group_order", "Confidence", "PMID", "Gene/Group"]
            if col in df.columns
        ]
        df = df.sort_values(by=sort_cols, kind="stable").drop(
            columns=["_association_group_order"]
        )

    # --- Primary CSV (clean researcher-facing) ---
    rename_map = {
        "Gene/Group": "Gene",
        "Variant Name": "Variant",
        "Study Title": "Title",
        "Publication Year": "Year",
        "Journal Name": "Journal",
    }
    df_clean = df.rename(columns=rename_map)
    df_clean = _ensure_unique_columns(df_clean)

    primary_cols = (
        ["Gene", "Variant"]
        + [c for c in user_cols if c in df_clean.columns]
        + [
            "Confidence", "Confidence Note", "Association Group", "Association Type",
            # F11: extraction_mode (llm / skeleton) and evidence_backfilled
            # visible in the primary CSV so researchers can see fallback
            # rows at a glance instead of having to consult the metadata CSV.
            "extraction_mode", "evidence_backfilled", "evidence_specificity",
            "context_modifications",  # what sections were truncated per gene row
        ]
        + ["PMID", "Title", "Year", "Journal", "Authors", "Citations", "DOI"]
    )
    primary_cols_present = _unique_preserve_order([c for c in primary_cols if c in df_clean.columns])
    df_primary = df_clean[primary_cols_present]
    df_primary = _ensure_unique_columns(df_primary)
    df_primary.to_csv(output_path, index=False)

    # --- Metadata CSV (full transparency, same row order as primary) ---
    meta_path = output_path.with_name(output_path.stem + "_metadata.csv")
    join_keys = ["PMID", "Gene/Group", "Variant Name"]
    remaining = [c for c in df.columns if c not in join_keys]
    meta_cols_present = _unique_preserve_order([c for c in join_keys + remaining if c in df.columns])
    df_meta = df[meta_cols_present]
    df_meta = _ensure_unique_columns(df_meta)
    df_meta.to_csv(meta_path, index=False)

    # --- Excel workbook (Results + Metadata sheets) ---
    excel_path = output_path.with_suffix(".xlsx")
    _write_excel_output(df_primary, df_meta, excel_path)

    # --- JSON (primary data as records) ---
    json_path = output_path.with_suffix(".json")
    _write_json_output(df_primary, json_path)

    return str(output_path), str(meta_path), str(excel_path), str(json_path)


def _candidate_audit_rows_by_pmid(df: "pd.DataFrame") -> dict:
    """Summarize emitted final rows for candidate-audit final counts."""
    return _artifact_candidate_audit_rows_by_pmid(df)


def _candidate_audit_summary(papers: list[dict]) -> dict:
    """Build run-level audit counts from emitted final rows."""
    return _artifact_candidate_audit_summary(papers)


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
        # Primary output names after researcher-facing renames.
        "Gene",
        "Variant",
        "Title",
        "Year",
        "Journal",
        "Confidence",
        "Confidence Note",
        "Association Group",
        "Association Type",
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
    if not isinstance(df, pd.DataFrame):
        return df
    cols = list(df.columns)
    seen_counts: dict[str, int] = {}
    new_cols: list[str] = []
    for c in cols:
        count = seen_counts.get(c, 0)
        if count == 0:
            new_cols.append(c)
        else:
            new_cols.append(f"{c} ({count + 1})")
        seen_counts[c] = count + 1
    df.columns = new_cols
    return df


def _prepare_paper_inputs(pmid, content_dict, paper_details, pubtator_results):
    return prepare_paper_inputs(pmid, content_dict, paper_details, pubtator_results)


def run_complete_pipeline(
    query,
    specific_pmids,
    specific_authors,
    user_columns,
    top_n_cited,
    progress_callback=None,
    log_callback=None,
):
    """
    Runs the complete pipeline with the provided parameters.

    Args:
        log_callback: Optional callback(level, msg, detail) for structured log events.
                      Levels: "info" (user-facing), "debug" (technical), "warn", "error"
    """
    logging.info("--- STARTING COMPLETE PIPELINE RUN ---")
    state = PipelineRunState(
        query=query or "",
        specific_pmids=list(specific_pmids or []),
        specific_authors=list(specific_authors or []),
        user_columns=dict(user_columns or {}),
        top_n_cited=top_n_cited,
    )
    start_time = state.start_time
    emitters = PipelineEmitters(state, progress_callback, log_callback)
    emit_log = emitters.emit_log
    check_cancellation = emitters.check_cancellation
    report_progress = emitters.report_progress
    _validate_gemini_call_budget()

    # Local aliases keep the legacy code path stable while the state object
    # makes run-level data flow visible for future extraction modules.
    pipeline_stats = state.pipeline_stats
    paper_debug_artifacts = state.paper_debug_artifacts
    forensic_screening = state.forensic_screening
    fetch_report = state.fetch_report
    artifact_writer = RunArtifactWriter(
        create_filepath=_create_unique_filepath,
        emit_log=emit_log,
        logger=logging,
    )

    def build_minimal_row(pmid, base_info, citation_records, gene_group="", variant_name=""):
        citation = _get_citation_record(pmid, citation_records)
        return {
            "Gene/Group": gene_group,
            "Variant Name": variant_name,
            "Candidate Source": "",
            "Normalization Applied": "",
            "Validation Outcome": "",
            "Association Type": "",
            "Association Group": "Review Needed",
            "Dropped By Gate": "",
            "PMID": pmid,
            "DOI": base_info.get("doi", ""),
            "Study Title": base_info.get("title", "N/A"),
            "Authors": ", ".join(base_info.get("authors", [])),
            "Publication Year": base_info.get("year", "N/A"),
            "Journal Name": base_info.get("journal", "N/A"),
            "Author Affiliations": "; ".join(base_info.get("affiliations", [])),
            "Citations": citation["count"],
            "Citation Source": citation["source"],
            "Citation Retrieved At": citation["retrieved_at"],
            "iCite Citations": citation["icite_count"],
            "Semantic Scholar Citations": citation["semantic_scholar_count"],
            "Figure Count": 0,
            "Figure Analysis Enabled": bool(getattr(config, "ENABLE_FIGURE_ANALYSIS", True)),
            "Abstract": base_info.get("abstract", "No abstract available"),
            "Metadata Completeness": base_info.get("_metadata_completeness", 0),
            "Metadata Warnings": "; ".join(base_info.get("_metadata_warnings", [])),
        }

    def write_drop_debug_artifact(status: str, output_csv_path: str = ""):
        """
        Persist per-run candidate/drop diagnostics to JSON for trust debugging.

        Includes forensic data when available: screening decisions, fetch outcomes,
        and table extraction statistics.
        """
        return artifact_writer.write_drop_debug_artifact(
            status=status,
            query=query,
            specific_pmids=specific_pmids,
            specific_authors=specific_authors,
            top_n_cited=top_n_cited,
            output_csv_path=output_csv_path,
            paper_debug_artifacts=paper_debug_artifacts,
            pipeline_stats=pipeline_stats,
            forensic_screening=forensic_screening,
            fetch_report=fetch_report,
        )

    def write_candidate_audit_artifact(output_csv_path: str = ""):
        """
        Persist candidate lifecycle as a stable first-class artifact.

        This is a cleaner consumer-facing subset of drop_debug: one paper record
        per PMID with candidate provenance, gate drops, and final associations.
        """
        return artifact_writer.write_candidate_audit_artifact(
            all_results_df=all_results_df,
            paper_debug_artifacts=paper_debug_artifacts,
            output_csv_path=output_csv_path,
        )

    report_progress("Initializing pipeline", 0)
    emit_log("info", "Initializing pipeline")

    # If tracing is enabled, point the tracer at the output dir so workers write partials there
    if pipeline_tracer.is_enabled():
        pipeline_tracer.set_output_dir(os.path.join(config.OUTPUT_DIR, ".trace_partials"))
        emit_log("info", f"Pipeline tracing enabled for PMID {pipeline_tracer.target_pmid()}")
        # Function-level tracing is installed here and inside each worker. Stage
        # contexts add stage_id to call/return events so the viewer can group
        # noisy function streams by semantic pipeline stage.
        if pipeline_tracer.function_tracer_enabled():
            pipeline_tracer.install_function_tracer()
            emit_log("info", "Function-level tracing active (orchestrator process)")

    paper_selection = select_papers_and_fetch_metadata(
        query=query,
        specific_pmids=specific_pmids,
        specific_authors=specific_authors,
        top_n_cited=top_n_cited,
        report_progress=report_progress,
        emit_log=emit_log,
        check_cancellation=check_cancellation,
    )
    initial_pmids = paper_selection.initial_pmids
    mandatory_pmids = paper_selection.mandatory_pmids
    paper_details = paper_selection.paper_details
    state.initial_pmids = set(initial_pmids)
    state.mandatory_pmids = set(mandatory_pmids)
    state.paper_details = paper_details
    pipeline_stats["papers_excluded_not_oa"] = paper_selection.papers_excluded_not_oa

    paper_reading = fetch_oa_full_text_and_pubtator(
        paper_details=paper_details,
        report_progress=report_progress,
        emit_log=emit_log,
        check_cancellation=check_cancellation,
        pipeline_stats=pipeline_stats,
    )
    if paper_reading is None:
        return None
    content_dict = paper_reading.content_dict
    scraped_pmids = paper_reading.scraped_pmids
    pubtator_results = paper_reading.pubtator_results
    fetch_report.extend(paper_reading.fetch_report)
    state.content_dict = content_dict
    state.scraped_pmids = scraped_pmids
    state.pubtator_results = pubtator_results

    if not scraped_pmids:
        emit_log("warn", "No full text available, falling back to metadata-only results")
        logging.warning(
            "No scraped papers available after full-text step. Falling back to minimal rows from PubMed metadata."
        )
        # Build minimal rows for initial PMIDs using PubMed details and citation counts
        try:
            # Fetch citations for all initial candidates
            all_candidate_pmids = list(paper_details.keys())
            citation_records = pubmed_data_collector.fetch_citation_counts_with_fallback(
                all_candidate_pmids
            )
            citations_dict = {pmid: rec.get("count", 0) for pmid, rec in citation_records.items()}

            # Rank by citations desc and take top_n_cited
            ranked = sorted(
                all_candidate_pmids, key=lambda p: citations_dict.get(p, 0), reverse=True
            )
            selected = ranked[:top_n_cited] if top_n_cited else ranked

            minimal_rows_only = []
            for pmid in selected:
                base_info = paper_details.get(pmid, {})
                minimal_rows_only.append(build_minimal_row(pmid, base_info, citation_records))

            all_results_df = pd.DataFrame(minimal_rows_only)

            # Save immediately (no user columns beyond core ones yet)
            output_path = _create_unique_filepath("final_enriched_results", "csv")
            all_results_df.to_csv(output_path, index=False, encoding="utf-8")
            debug_path = write_drop_debug_artifact(
                status="metadata_only_no_full_text", output_csv_path=output_path
            )
            report_progress("Completed", 100)
            logging.info(
                f"--- PIPELINE FINISHED WITH MINIMAL ROWS IN {time.time() - start_time:.2f} SECONDS ---"
            )
            return {"local_path": output_path, "debug_path": debug_path}
        except Exception as e:
            logging.error(f"Fallback to minimal rows failed: {e}")
            return None

    # Citation selection: fetch citations only for scraped PMIDs and select top papers.
    report_progress("Fetching citation counts", 50)
    logging.info("Citation selection: fetching citations for scraped PMIDs and selecting top papers...")
    check_cancellation()
    cite_start = time.time()
    with pipeline_tracer.stage("citation_fetch"):
        citation_records = pubmed_data_collector.fetch_citation_counts_with_fallback(scraped_pmids)
    state.citation_records = citation_records
    citations_dict = {pmid: rec.get("count", 0) for pmid, rec in citation_records.items()}

    # ── Tracer: citation fetch for target PMID
    if pipeline_tracer.is_enabled():
        target = pipeline_tracer.target_pmid()
        rec = citation_records.get(target) if target else None
        pipeline_tracer.capture(
            "citation_fetch",
            pmid=target,
            inputs={"scraped_pmids_count": len(scraped_pmids)},
            outputs={
                "target_record": rec,
                "target_count": (rec or {}).get("count"),
                "source": (rec or {}).get("source"),
            },
            duration_ms=(time.time() - cite_start) * 1000.0,
        )

    scraped_details = {pmid: info for pmid, info in paper_details.items() if pmid in scraped_pmids}
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
    ranked_remaining = remaining_df.sort_values(by="citations", ascending=False).index.tolist()
    pmids_to_process = ordered_mandatory + ranked_remaining
    state.pmids_to_process = pmids_to_process
    logging.info(
        f"Prepared {len(pmids_to_process)} scraped PMIDs for AI analysis (mandatory first, then ranked by citations)."
    )

    # Abstract screening — forensic logging only (filtering moved to UI preview).
    # The UI now scores papers before the user selects them, so all user-selected
    # papers proceed to AI analysis without silent filtering.
    if getattr(config, "ENABLE_ABSTRACT_SCREENING", True):
        report_progress("Scoring abstracts", 65)
        logging.info(
            "Paper selection: scoring abstracts for forensic logging (no filtering — screening moved to UI)..."
        )
        check_cancellation()

        threshold = getattr(config, "ABSTRACT_SCREENING_THRESHOLD", 5)
        would_pass = 0
        would_reject = 0

        for pmid in pmids_to_process:
            base_info = paper_details.get(pmid, {})
            title = base_info.get("title", "")
            abstract = base_info.get("abstract", "")
            should_process, confidence, details = has_genetic_content(abstract, title, threshold)
            if should_process or pmid in mandatory_pmids:
                would_pass += 1
            else:
                would_reject += 1

        logging.info(
            f"Abstract scoring: {would_pass}/{len(pmids_to_process)} would pass threshold "
            f"(all {len(pmids_to_process)} papers proceeding — screening moved to UI)"
        )
        # All papers proceed — no filtering
        pipeline_stats["papers_screened_passed"] = len(pmids_to_process)
        report_progress("Scoring abstracts", 68, {"papers_screened": len(pmids_to_process)})

        # Forensic screening data collection (still useful for debug artifacts)
        if getattr(config, "FORENSIC_INCLUDE_SCREENING", True):
            try:
                from .abstract_screener import screen_papers_with_decisions, decisions_to_dicts

                screening_subset = {
                    pmid: paper_details.get(pmid, {}) for pmid in pmids_to_process
                }
                _, screening_decisions = screen_papers_with_decisions(
                    screening_subset,
                    threshold=threshold,
                    mandatory_pmids=mandatory_pmids,
                )
                forensic_screening.extend(decisions_to_dicts(screening_decisions))
            except Exception as e:
                logging.warning(f"Forensic screening data collection failed: {e}")

        if not pmids_to_process:
            logging.warning(
                "No papers to analyse. Falling back to minimal rows."
            )
            # Build minimal rows for all scraped PMIDs
            minimal_rows_only = []
            for pmid in scraped_pmids[:top_n_cited]:
                base_info = paper_details.get(pmid, {})
                minimal_rows_only.append({**build_minimal_row(pmid, base_info, citation_records)})
            all_results_df = pd.DataFrame(minimal_rows_only)
            output_path = _create_unique_filepath("final_enriched_results", "csv")
            all_results_df.to_csv(output_path, index=False, encoding="utf-8")
            debug_path = write_drop_debug_artifact(
                status="metadata_only_all_rejected_by_screening", output_csv_path=output_path
            )
            report_progress("Completed", 100)
            logging.info(
                f"--- PIPELINE FINISHED WITH MINIMAL ROWS IN {time.time() - start_time:.2f} SECONDS ---"
            )
            return {"local_path": output_path, "debug_path": debug_path}

    report_progress("Per-paper analysis", 70)
    emit_log("info", f"Analyzing {len(pmids_to_process)} papers with AI")
    logging.info("Per-paper analysis: analyzing papers with extraction pipeline...")
    column_descriptions = _sanitize_user_columns(user_columns)

    analysis_result = run_paper_analysis(
        pmids_to_process=pmids_to_process,
        content_dict=content_dict,
        paper_details=paper_details,
        pubtator_results=pubtator_results,
        citation_records=citation_records,
        column_descriptions=column_descriptions,
        pipeline_stats=pipeline_stats,
        report_progress=report_progress,
        emit_log=emit_log,
        check_cancellation=check_cancellation,
        build_minimal_row=build_minimal_row,
    )
    all_results_df = analysis_result.all_results_df
    paper_debug_artifacts.extend(analysis_result.paper_debug_artifacts)
    collected_rows = analysis_result.collected_rows
    full_rows_pmids = analysis_result.full_rows_pmids
    minimal_rows = analysis_result.minimal_rows
    analyzed_attempts = analysis_result.analyzed_attempts
    state.all_results_df = all_results_df
    state.collected_rows = collected_rows
    state.full_rows_pmids = full_rows_pmids
    state.minimal_rows = minimal_rows
    state.analyzed_attempts = analyzed_attempts

    if all_results_df.empty:
        if minimal_rows:
            logging.warning("AI produced no rows; falling back to minimal rows only.")
            all_results_df = pd.DataFrame(minimal_rows)
        else:
            logging.warning("No validated genes were extracted; saving metadata-only rows.")
            emit_log(
                "warn",
                "No validated genes were extracted",
                "The paper was analyzed, but no gene candidates passed validation and evidence gates.",
            )
            recorded_pmids = {
                str(artifact.get("pmid"))
                for artifact in paper_debug_artifacts
                if artifact.get("pmid")
            } or set(pmids_to_process)
            for pmid in pmids_to_process:
                if pmid not in recorded_pmids:
                    continue
                base_info = paper_details.get(pmid, {})
                minimal_rows.append(
                    {
                        **build_minimal_row(pmid, base_info, citation_records),
                        "extraction_mode": "no_validated_genes",
                        "detail_extraction_error": (
                            "No validated genes were extracted from this paper."
                        ),
                    }
                )
            all_results_df = pd.DataFrame(minimal_rows)

    # HYBRID PIPELINE: NCBI Gene enrichment
    if getattr(config, "ENABLE_NCBI_ENRICHMENT", True) and not all_results_df.empty:
        report_progress("Enriching gene metadata", 92)
        logging.info("Result enrichment: enriching genes with NCBI Gene metadata...")

        try:
            # Collect all unique genes that need enrichment
            genes_to_enrich = set()
            if "Gene/Group" in all_results_df.columns:
                genes_to_enrich = set(all_results_df["Gene/Group"].dropna().unique())
                genes_to_enrich = {g for g in genes_to_enrich if g}

            if genes_to_enrich:
                ncbi_tool = NCBIGeneTool()
                symbol_gene_ids = {}
                if "NCBI Gene ID" in all_results_df.columns and "Gene/Group" in all_results_df.columns:
                    for _, row in all_results_df[["Gene/Group", "NCBI Gene ID"]].dropna(how="all").iterrows():
                        symbol = str(row.get("Gene/Group") or "").strip()
                        gene_id = str(row.get("NCBI Gene ID") or "").strip()
                        if symbol and gene_id and ";" not in gene_id:
                            symbol_gene_ids[symbol] = gene_id
                with pipeline_tracer.stage("ncbi_enrichment"):
                    gene_metadata = ncbi_tool.enrich_gene_symbols(
                        list(genes_to_enrich),
                        symbol_gene_ids=symbol_gene_ids,
                    )
                all_results_df = _apply_ncbi_metadata_columns(all_results_df, gene_metadata)

                logging.info(
                    f"NCBI enrichment: Added metadata for {len(gene_metadata)}/{len(genes_to_enrich)} genes"
                )
        except Exception as e:
            logging.warning(f"NCBI enrichment failed, continuing without it: {e}")

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
        full_df = all_results_df[all_results_df["PMID"].isin(selected_full_set)].reset_index(
            drop=True
        )

        # Build minimal rows for PMIDs that had no full rows (in original processing order)
        minimal_append = []
        selected_full_or_minimal_pmids = set(selected_full_set)
        for mr in minimal_rows:
            if mr["PMID"] in selected_full_or_minimal_pmids:
                continue
            minimal_append.append(mr)
            selected_full_or_minimal_pmids.add(mr["PMID"])

        if minimal_append:
            all_results_df = pd.concat([full_df, pd.DataFrame(minimal_append)], ignore_index=True)
        else:
            all_results_df = full_df

    report_progress("Finalizing results", 95)

    # De-duplicate: If multiple rows within the same PMID and gene have identical user fields, aggregate variant names
    try:
        if not all_results_df.empty:
            core_cols = [
                "PMID",
                "DOI",
                "Gene/Group",
                "Variant Name",
                "Study Title",
                "Authors",
                "Publication Year",
                "Journal Name",
                "Author Affiliations",
                "Citations",
                "Citation Source",
                "Citation Retrieved At",
                "iCite Citations",
                "Semantic Scholar Citations",
                "Figure Count",
                "Figure Analysis Enabled",
                "Candidate Source",
                "Normalization Applied",
                "Validation Outcome",
                "Association Type",
                "Association Group",
                "Dropped By Gate",
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
                "context_truncation_applied",
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
                    c: "first" for c in df_full.columns if c not in group_keys + ["Variant Name"]
                }

                # Aggregate variant names: unique; sorted; semicolon-joined
                def _agg_variants(series):
                    vals = {str(v) for v in series if str(v).strip()}
                    return "; ".join(sorted(vals))

                agg_map["Variant Name"] = _agg_variants

                df_full = df_full.groupby(group_keys, dropna=False, as_index=False).agg(agg_map)

                # Recombine full and minimal, preserving original order later via sort key
                all_results_df = pd.concat([df_full, df_minimal], ignore_index=True)
    except Exception as e:
        logging.warning(f"Deduplication step skipped due to error: {e}")

    # Ensure unique columns before reordering to prevent reindex errors
    all_results_df = _ensure_unique_columns(all_results_df)
    state.all_results_df = all_results_df
    state.analyzed_attempts = analyzed_attempts

    # Reorder columns for better readability
    core_columns = [
        "Gene/Group",
        "Variant Name",
        "Gene Source",
        "NCBI Gene ID",
        "Gene Full Name",
        "Gene Aliases",
        "Gene Biotype",
        "Chromosome",
        "Candidate Source",
        "Normalization Applied",
        "Validation Outcome",
        "Association Type",
        "Association Group",
        "Dropped By Gate",
        "PMID",
        "DOI",
        "Study Title",
        "Authors",
        "Publication Year",
        "Journal Name",
        "Author Affiliations",
        "Citations",
        "Citation Source",
        "Citation Retrieved At",
        "iCite Citations",
        "Semantic Scholar Citations",
        "Figure Count",
        "Figure Analysis Enabled",
        "Metadata Completeness",
        "Metadata Warnings",
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
        "context_truncation_applied",
    ]

    user_columns_raw = [
        col
        for col in all_results_df.columns
        if col not in core_columns
        and not any(col.endswith(suffix) or col == suffix for suffix in metadata_suffixes)
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
        if any(col.endswith(suffix) or col == suffix for suffix in metadata_suffixes)
    ]

    # Build final column order
    final_column_order = []
    for col in core_columns:
        if col in all_results_df.columns:
            final_column_order.append(col)
    final_column_order.extend(user_columns_list)
    final_column_order.extend(metadata_columns)

    all_results_df = all_results_df[final_column_order]

    # Output writing: primary CSV + metadata CSV + Excel + JSON.
    output_path = _create_unique_filepath("final_enriched_results", "csv")
    with pipeline_tracer.stage("output_writer"):
        primary_path, metadata_path, excel_path, json_path = _write_split_output(
            df=all_results_df,
            output_path=output_path,
            user_cols=user_columns_raw,
        )
        state.primary_path = primary_path
        state.metadata_path = metadata_path
        state.excel_path = excel_path
        state.json_path = json_path
        candidate_audit_path = write_candidate_audit_artifact(output_csv_path=primary_path)
        debug_path = write_drop_debug_artifact(status="completed", output_csv_path=primary_path)
        state.candidate_audit_path = candidate_audit_path
        state.debug_path = debug_path
        if pipeline_tracer.is_enabled():
            pipeline_tracer.capture(
                "output_writer",
                inputs={"rows": int(len(all_results_df)), "columns": list(all_results_df.columns)},
                outputs={
                    "primary_path": primary_path,
                    "metadata_path": metadata_path,
                    "excel_path": excel_path,
                    "json_path": json_path,
                    "candidate_audit_path": candidate_audit_path,
                    "debug_path": debug_path,
                },
            )

    total_genes = pipeline_stats.get("genes_extracted", 0)
    total_analyzed = analyzed_attempts
    elapsed = time.time() - start_time
    emit_log(
        "info",
        f"Pipeline complete: {total_genes} genes from {total_analyzed} papers ({elapsed:.0f}s)",
    )
    quota_rows = int(pipeline_stats.get("quota_limited_rows", 0) or 0)
    if quota_rows:
        emit_log(
            "warn",
            f"Gemini quota/rate limit affected {quota_rows} output rows",
            "Treat this run as incomplete and rerun after quota resets or with a paid/higher-limit key.",
        )
    report_progress("Completed", 100)
    logging.info(f"--- PIPELINE FINISHED IN {elapsed:.2f} SECONDS ---")

    # ── Tracer: merge worker partials and write trace_<pmid>.json
    trace_path = None
    if pipeline_tracer.is_enabled():
        # Uninstall the function tracer before final I/O so the collector's own
        # work doesn't flood the trace with write-path noise.
        pipeline_tracer.uninstall_function_tracer()
        try:
            target = pipeline_tracer.target_pmid()
            out = os.path.join(config.OUTPUT_DIR, f"trace_{target}.json")
            written = pipeline_tracer.collect_and_write(target, out)
            if written:
                trace_path = str(written)
                state.trace_path = trace_path
                emit_log("info", f"Pipeline trace written to {trace_path}")
        except Exception as e:
            logging.warning(f"Trace collection failed: {e}")

    result = {
        "local_path": primary_path,
        "metadata_path": metadata_path,
        "excel_path": excel_path,
        "json_path": json_path,
        "candidate_audit_path": candidate_audit_path,
        "debug_path": debug_path,
        # F10b: explicit alias consumed by the Results banner. Mirrors debug_path
        # so the frontend doesn't have to know that "debug" and "drop_debug" refer
        # to the same artifact.
        "drop_debug_path": debug_path,
    }
    if quota_rows:
        result["warning"] = (
            f"Gemini quota/rate limit affected {quota_rows} output rows. "
            "Rows marked REVIEW/skeleton are fallback evidence, not full AI extraction."
        )
    if trace_path:
        result["trace_path"] = trace_path
    return result
