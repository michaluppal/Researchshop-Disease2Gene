"""Result finalization and enrichment helpers for pipeline orchestration."""

from __future__ import annotations

import logging
from typing import Any, Callable

import pandas as pd

from . import config
from .pipeline_artifacts import _ensure_unique_columns


def get_citation_record(pmid: str, citation_records: dict) -> dict:
    """Return a stable citation payload for a PMID."""
    rec = citation_records.get(pmid, {}) if citation_records else {}
    return {
        "count": int(rec.get("count", 0) or 0),
        "source": rec.get("source", "none") or "none",
        "retrieved_at": rec.get("retrieved_at", "") or "",
        "icite_count": rec.get("icite_count"),
        "semantic_scholar_count": rec.get("semantic_scholar_count"),
    }


def is_gemini_quota_error(text: object) -> bool:
    """Detect Gemini quota/rate-limit errors from stored worker text."""
    err = str(text or "")
    return "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower()


def aggregate_strict_gate_drops(
    pipeline_stats: dict,
    worker_debug: dict,
    pmid: str,
) -> list[dict]:
    """Copy per-paper strict gate drops into run-level stats for UI banners."""
    paper_drops = worker_debug.get("strict_gate_drops", []) or []
    for drop in paper_drops:
        drop_entry = dict(drop)
        drop_entry["pmid"] = pmid
        pipeline_stats.setdefault("strict_gate_drops", []).append(drop_entry)
    pipeline_stats["strict_gate_drops_count"] = len(
        pipeline_stats.get("strict_gate_drops", [])
    )
    return paper_drops


def _gene_key(gene: str) -> str:
    return str(gene or "").strip().upper()


def apply_pubtator_row_enrichment(
    paper_df: pd.DataFrame,
    pmid: str,
    pubtator_results: dict,
) -> pd.DataFrame:
    """Attach PubTator source and NCBI IDs with per-paper lookup caches."""
    if paper_df.empty or pmid not in pubtator_results or "Gene/Group" not in paper_df.columns:
        return paper_df

    hybrid_result = pubtator_results[pmid]
    pt_by_symbol = {
        _gene_key(g.symbol): g
        for g in hybrid_result.pubtator_genes
        if _gene_key(g.symbol)
    }
    llm_symbols = {
        _gene_key(g)
        for g in paper_df["Gene/Group"].dropna().unique().tolist()
        if _gene_key(g)
    }
    hybrid_result.llm_genes = sorted(llm_symbols)

    source_by_symbol = {}
    ncbi_id_by_symbol = {}
    for symbol in llm_symbols:
        source_by_symbol[symbol] = "both" if symbol in pt_by_symbol else "llm"
        ncbi_id_by_symbol[symbol] = getattr(pt_by_symbol.get(symbol), "ncbi_gene_id", "") or ""

    paper_df["Gene Source"] = paper_df["Gene/Group"].map(
        lambda gene: source_by_symbol.get(_gene_key(gene), "")
    )
    paper_df["NCBI Gene ID"] = paper_df["Gene/Group"].map(
        lambda gene: ncbi_id_by_symbol.get(_gene_key(gene), "")
    )
    return paper_df


def apply_ncbi_metadata_columns(all_results_df: pd.DataFrame, gene_metadata: dict) -> pd.DataFrame:
    """Attach NCBI enrichment columns using a single uppercase-keyed lookup."""
    if all_results_df.empty or "Gene/Group" not in all_results_df.columns:
        return all_results_df

    metadata_by_symbol = {
        _gene_key(symbol): value
        for symbol, value in (gene_metadata or {}).items()
        if _gene_key(symbol)
    }

    all_results_df["Gene Full Name"] = all_results_df["Gene/Group"].map(
        lambda gene: getattr(metadata_by_symbol.get(_gene_key(gene)), "full_name", "") or ""
    )
    all_results_df["Gene Aliases"] = all_results_df["Gene/Group"].map(
        lambda gene: ", ".join(
            (getattr(metadata_by_symbol.get(_gene_key(gene)), "aliases", None) or [])[:3]
        )
    )
    all_results_df["Chromosome"] = all_results_df["Gene/Group"].map(
        lambda gene: getattr(metadata_by_symbol.get(_gene_key(gene)), "chromosome", "") or ""
    )

    if "NCBI Gene ID" not in all_results_df.columns:
        all_results_df["NCBI Gene ID"] = ""
    missing_mask = (
        all_results_df["NCBI Gene ID"].fillna("").astype(str).str.strip() == ""
    )
    all_results_df.loc[missing_mask, "NCBI Gene ID"] = all_results_df.loc[
        missing_mask, "Gene/Group"
    ].map(lambda gene: getattr(metadata_by_symbol.get(_gene_key(gene)), "gene_id", "") or "")

    return all_results_df


def finalize_paper_result(
    payload: Any,
    pmid: str,
    base_info: dict,
    citation_records: dict,
    figure_inputs: list[dict],
    pubtator_results: dict,
    pipeline_stats: dict,
    emit_log: Callable[[str, str, str | None], None],
) -> tuple[pd.DataFrame, dict]:
    """Normalize worker output, attach metadata, and build the debug artifact."""
    paper_df = pd.DataFrame()
    worker_debug: dict[str, Any] = {}

    if isinstance(payload, dict) and payload.get("error"):
        logging.error(f"AI analysis error for PMID {pmid}: {payload['error']}")
        worker_debug = {
            "status": "worker_error",
            "reason": str(payload.get("error")),
        }
    elif isinstance(payload, dict) and payload.get("records") is not None:
        paper_df = pd.DataFrame(payload["records"])
        if isinstance(payload.get("debug"), dict):
            worker_debug = payload["debug"]
        else:
            worker_debug = {"status": "ok"}
        pipeline_stats["gemini_api_calls"] += int(payload.get("gemini_api_calls", 0))
        ctx_warn = (worker_debug or {}).get("context_warning")
        if ctx_warn:
            emit_log("warn", f"PMID {pmid}: {ctx_warn}")

    paper_df = paper_df.rename(
        columns={"gene_name": "Gene/Group", "variant_name": "Variant Name"}
    )

    paper_df["PMID"] = pmid
    paper_df["DOI"] = base_info.get("doi", "")
    paper_df["Study Title"] = base_info.get("title", "N/A")
    paper_df["Authors"] = ", ".join(base_info.get("authors", []))
    paper_df["Publication Year"] = base_info.get("year", "N/A")
    paper_df["Journal Name"] = base_info.get("journal", "N/A")
    paper_df["Author Affiliations"] = "; ".join(base_info.get("affiliations", []))
    citation = get_citation_record(pmid, citation_records)
    paper_df["Citations"] = citation["count"]
    paper_df["Citation Source"] = citation["source"]
    paper_df["Citation Retrieved At"] = citation["retrieved_at"]
    paper_df["iCite Citations"] = citation["icite_count"]
    paper_df["Semantic Scholar Citations"] = citation["semantic_scholar_count"]
    paper_df["Metadata Completeness"] = base_info.get("_metadata_completeness", 0)
    paper_df["Metadata Warnings"] = "; ".join(base_info.get("_metadata_warnings", []))
    paper_df["Figure Count"] = len(figure_inputs)
    paper_df["Figure Analysis Enabled"] = bool(
        getattr(config, "ENABLE_FIGURE_ANALYSIS", True)
    )

    paper_df = apply_pubtator_row_enrichment(paper_df, pmid, pubtator_results)

    if "Abstract" in paper_df.columns:
        paper_df["Abstract"] = base_info.get("abstract", "No abstract available")

    if paper_df.empty and not worker_debug:
        worker_debug = {"status": "empty_result"}

    detail_error = worker_debug.get("detail_extraction_error", "")
    detail_status = worker_debug.get("detail_extraction_status", "")
    quota_limited = (
        bool(worker_debug.get("quota_limited"))
        or is_gemini_quota_error(detail_error)
        or detail_status == "quota_limited_fallback"
    )
    if quota_limited:
        row_count = int(len(paper_df))
        pipeline_stats["quota_limited_papers"] = int(
            pipeline_stats.get("quota_limited_papers", 0)
        ) + 1
        pipeline_stats["quota_limited_rows"] = int(
            pipeline_stats.get("quota_limited_rows", 0)
        ) + row_count
        emit_log(
            "warn",
            f"PMID {pmid}: Gemini quota/rate limit reached; output rows require review",
            "Rows were saved as fallback skeletons with auto-snippets, not full AI extraction.",
        )

    paper_drops = aggregate_strict_gate_drops(pipeline_stats, worker_debug, pmid)

    debug_artifact = {
        "pmid": pmid,
        "status": worker_debug.get("status", "ok"),
        "reason": worker_debug.get("reason", ""),
        "candidate_count": worker_debug.get("candidate_count"),
        "candidates": worker_debug.get("candidates", []),
        "detail_extraction_status": worker_debug.get("detail_extraction_status", ""),
        "detail_extraction_error": worker_debug.get("detail_extraction_error", ""),
        "quota_limited": quota_limited,
        "detail_extraction_rows": worker_debug.get("detail_extraction_rows"),
        "validation_drops": worker_debug.get("validation_drops", []),
        "strict_gate_drops": paper_drops,
        "evidence_gate_drops": worker_debug.get("evidence_gate_drops", []),
        "final_associations": worker_debug.get("final_associations", []),
        "emitted_rows": int(len(paper_df)),
    }
    return paper_df, debug_artifact


def accumulate_result(
    all_results_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    pmid: str,
    collected_rows: list,
    full_rows_pmids: set,
    pipeline_stats: dict,
    emit_log: Callable[[str, str, str | None], None],
) -> pd.DataFrame:
    """Append one paper's rows and update run-level counters."""
    if paper_df.empty:
        return all_results_df

    paper_df = _ensure_unique_columns(paper_df)
    all_results_df = _ensure_unique_columns(all_results_df)
    all_results_df = pd.concat([all_results_df, paper_df], ignore_index=True)
    collected_rows.append(pmid)
    full_rows_pmids.add(pmid)

    if "Gene/Group" in paper_df.columns:
        unique_genes = paper_df["Gene/Group"].dropna().nunique()
        pipeline_stats["genes_extracted"] = (
            pipeline_stats.get("genes_extracted", 0) + unique_genes
        )
        if unique_genes > 0:
            emit_log("info", f"Extracted {unique_genes} genes from PMID {pmid}")

    return all_results_df
