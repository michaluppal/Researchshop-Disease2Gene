"""Helpers for turning fetched paper content into analysis inputs."""

from __future__ import annotations

import gzip
import logging
import os
import pickle
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict

from . import config, full_text_fetcher, pipeline_tracer
from .content_preparation import PreparedPaperContent
from .pubtator_tool import HybridExtractionResult, PubTatorTool


@dataclass
class PaperReadingResult:
    content_dict: Dict[str, Any]
    scraped_pmids: list[str]
    pubtator_results: Dict[str, HybridExtractionResult]
    fetch_report: list[dict[str, Any]]


def _create_unique_filepath(filename_base: str, extension: str) -> str:
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{filename_base}_{unique_id}.{extension}"
    return os.path.join(config.OUTPUT_DIR, filename)


def fetch_oa_full_text_and_pubtator(
    *,
    paper_details: Dict[str, Dict[str, Any]],
    report_progress,
    emit_log,
    check_cancellation,
    pipeline_stats: dict,
) -> PaperReadingResult | None:
    """Fetch OA full text and optional PubTator NER for selected PubMed metadata."""
    report_progress("Fetching full text", 30)
    emit_log("info", f"Fetching full text for {len(paper_details)} papers")
    logging.info("Paper reading: fetching full text for relevance-selected PMIDs...")
    check_cancellation()
    pmids_to_fetch = list(paper_details.keys())
    content_dict_path = _create_unique_filepath("content_dict", "pkl.gz")
    fetch_start = time.time()
    with pipeline_tracer.stage("full_text_fetch"):
        full_text_fetcher.run_fetching(pmids_to_fetch, content_dict_path)
    fetch_duration_ms = (time.time() - fetch_start) * 1000.0

    report_progress("Processing fetched content", 45)
    try:
        with gzip.open(content_dict_path, "rb") as f:
            content_dict = pickle.load(f)
    except Exception:
        logging.warning("Content dictionary is empty. No papers could be fetched.")
        return None

    scraped_pmids = list(content_dict.keys())
    emit_log(
        "info", f"Retrieved full text for {len(scraped_pmids)} of {len(pmids_to_fetch)} papers"
    )

    if pipeline_tracer.is_enabled():
        target = pipeline_tracer.target_pmid()
        entry = content_dict.get(target) if target else None
        pipeline_tracer.capture(
            "full_text_fetch",
            pmid=target,
            inputs={"pmids_requested": len(pmids_to_fetch)},
            outputs={
                "scraped_count": len(scraped_pmids),
                "target_present": entry is not None,
                "extraction_method": (entry or {}).get("extraction_method"),
                "content_length": (entry or {}).get("content_length"),
                "quality_score": (entry or {}).get("quality_score"),
                "figures_count": len((entry or {}).get("figures") or []),
                "tables_count": len((entry or {}).get("tables") or []),
                "content_preview": pipeline_tracer.summarise((entry or {}).get("content", "")),
            },
            duration_ms=fetch_duration_ms,
        )
        pipeline_tracer.capture(
            "text_cleaning",
            pmid=target,
            inputs={"note": "Greek transliteration + non-ASCII strip already applied"},
            outputs={
                "final_content_length": (entry or {}).get("content_length"),
                "ascii_only": True,
            },
        )

    if getattr(config, "ENABLE_FIGURE_ANALYSIS", True):
        papers_with_figures = 0
        total_figures = 0
        for payload in content_dict.values():
            figs = payload.get("figures", []) if isinstance(payload, dict) else []
            if figs:
                papers_with_figures += 1
                total_figures += len(figs)
        if total_figures:
            emit_log("info", f"Discovered {total_figures} figures in {papers_with_figures} papers")

    total_tables = sum(
        len(v.get("tables", []))
        for v in content_dict.values()
        if isinstance(v, dict)
    )
    pipeline_stats["tables_extracted"] = total_tables
    if total_tables:
        papers_with_tables = sum(
            1
            for v in content_dict.values()
            if isinstance(v, dict) and v.get("tables")
        )
        emit_log("info", f"Extracted {total_tables} tables from {papers_with_tables} papers")

    pipeline_stats["papers_fetch_failed"] = len(pmids_to_fetch) - len(scraped_pmids)

    fetch_report: list[dict[str, Any]] = []
    if getattr(config, "FORENSIC_INCLUDE_FETCH_OUTCOMES", True) and content_dict:
        try:
            from .full_text_fetcher import generate_fetch_report

            fetch_report.extend(generate_fetch_report(content_dict))
        except Exception as e:
            logging.warning(f"Forensic fetch report generation failed: {e}")

    pubtator_results: Dict[str, HybridExtractionResult] = {}
    if getattr(config, "ENABLE_PUBTATOR_EXTRACTION", True) and scraped_pmids:
        report_progress("Running PubTator extraction", 47)
        emit_log("info", "Running PubTator gene extraction")
        logging.info(
            "Candidate discovery: running PubTator extraction for high-precision gene discovery..."
        )
        check_cancellation()

        try:
            pubtator_tool = PubTatorTool()
            pt_start = time.time()
            with pipeline_tracer.stage("pubtator_ner"):
                batch_results = pubtator_tool.extract_from_pmids(scraped_pmids)
            pt_duration_ms = (time.time() - pt_start) * 1000.0

            for pmid, (genes, variants) in batch_results.items():
                result = HybridExtractionResult(pmid)
                result.pubtator_genes = genes
                result.pubtator_variants = variants
                pubtator_results[pmid] = result

            if pipeline_tracer.is_enabled():
                target = pipeline_tracer.target_pmid()
                target_result = pubtator_results.get(target) if target else None
                pipeline_tracer.capture(
                    "pubtator_ner",
                    pmid=target,
                    inputs={"scraped_pmids_count": len(scraped_pmids)},
                    outputs={
                        "target_present": target_result is not None,
                        "genes": [
                            g.symbol
                            for g in (
                                target_result.pubtator_genes if target_result else []
                            )
                        ],
                        "variants": pipeline_tracer.summarise(
                            [
                                {
                                    "text": v.text,
                                    "type": v.variant_type,
                                    "rsid": v.rsid,
                                    "hgvs": v.hgvs,
                                }
                                for v in (
                                    target_result.pubtator_variants if target_result else []
                                )
                            ]
                        ),
                    },
                    meta={"papers_returned": len(pubtator_results)},
                    duration_ms=pt_duration_ms,
                )

            total_pt_genes = sum(len(r.pubtator_genes) for r in pubtator_results.values())
            pt_skipped = len(scraped_pmids) - len(pubtator_results)
            pipeline_stats["pubtator_pmids_skipped"] = pt_skipped
            emit_log(
                "info",
                f"PubTator found {total_pt_genes} genes across {len(pubtator_results)} papers",
                f"{pt_skipped} PMID(s) not returned by PubTator (not indexed or parse error)"
                if pt_skipped
                else None,
            )
            logging.info(
                f"PubTator: Found {total_pt_genes} genes across {len(pubtator_results)} papers"
            )
        except Exception as e:
            emit_log("warn", "PubTator extraction failed, continuing without it")
            logging.warning(f"PubTator extraction failed, continuing without it: {e}")

    return PaperReadingResult(
        content_dict=content_dict,
        scraped_pmids=scraped_pmids,
        pubtator_results=pubtator_results,
        fetch_report=fetch_report,
    )


def prepare_paper_inputs(
    pmid: str,
    content_dict: Dict[str, Any],
    paper_details: Dict[str, Dict[str, Any]],
    pubtator_results: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the per-paper evidence package consumed by the analysis worker."""
    content = content_dict.get(pmid, {})
    paper_text = content.get("content", "")
    figure_inputs = (
        content.get("figures", [])
        if getattr(config, "ENABLE_FIGURE_ANALYSIS", True)
        else []
    )
    table_inputs = (
        content.get("tables", [])
        if getattr(config, "ENABLE_TABLE_CITATIONS", True)
        else []
    )
    base_info = paper_details.get(pmid, {})
    abstract = base_info.get("abstract", "")
    title = base_info.get("title", "")

    pt_gene_symbols = []
    if pmid in pubtator_results:
        pt_gene_symbols = [g.symbol for g in pubtator_results[pmid].pubtator_genes]
        if pt_gene_symbols:
            logging.debug(
                "PMID %s: Passing %s PubTator genes to Gemini",
                pmid,
                len(pt_gene_symbols),
            )

    return {
        "pmid": pmid,
        "paper_text": paper_text,
        "figure_inputs": figure_inputs,
        "table_inputs": table_inputs,
        "prepared_content": PreparedPaperContent.from_raw(
            paper_text=paper_text,
            abstract_text=abstract,
            table_inputs=table_inputs,
        ),
        "base_info": base_info,
        "abstract": abstract,
        "title": title,
        "pt_gene_symbols": pt_gene_symbols,
    }
