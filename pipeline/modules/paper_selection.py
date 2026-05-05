"""Paper selection and PubMed metadata collection for pipeline runs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from . import config, pipeline_tracer, pubmed_data_collector


@dataclass
class PaperSelectionResult:
    initial_pmids: set[str]
    mandatory_pmids: set[str]
    paper_details: dict
    papers_excluded_not_oa: int = 0


def select_papers_and_fetch_metadata(
    *,
    query: str,
    specific_pmids: list[str] | None,
    specific_authors: list[str] | None,
    top_n_cited: int,
    report_progress: Callable,
    emit_log: Callable,
    check_cancellation: Callable,
) -> PaperSelectionResult:
    """Collect PMIDs from user inputs, enforce OA for mandatory papers, and fetch metadata."""
    report_progress("Searching PubMed", 10)
    if query:
        emit_log("info", f"Searching PubMed for: {query}")
    if specific_pmids:
        emit_log("info", f"Including {len(specific_pmids)} specific PMIDs")
    if specific_authors:
        emit_log("info", f"Searching papers by {len(specific_authors)} author(s)")
    logging.info("Paper selection: gathering PMIDs and fetching metadata...")

    initial_pmids = set(specific_pmids or [])
    mandatory_pmids = set(specific_pmids or [])
    author_pmids = set()

    if specific_authors:
        for author in specific_authors:
            check_cancellation()
            author_results = pubmed_data_collector.search_pubmed_by_author(author, max_results=200)
            initial_pmids.update(author_results)
            author_pmids.update(author_results)

    mandatory_pmids |= author_pmids

    papers_excluded_not_oa = 0
    if mandatory_pmids:
        check_cancellation()
        from .full_text_fetcher import _get_pmcid_for_pmid

        oa_mandatory = set()
        paywalled = []
        for pmid in sorted(mandatory_pmids):
            check_cancellation()
            pmcid = _get_pmcid_for_pmid(pmid)
            if pmcid:
                oa_mandatory.add(pmid)
            else:
                paywalled.append(pmid)
        if paywalled:
            papers_excluded_not_oa = len(paywalled)
            emit_log(
                "warn",
                f"OA gate: excluded {len(paywalled)} paywalled PMID(s) from the run",
                f"PMIDs: {', '.join(paywalled[:10])}"
                + ("..." if len(paywalled) > 10 else ""),
            )
        mandatory_pmids = oa_mandatory

    if mandatory_pmids:
        initial_pmids.update(mandatory_pmids)

    if query:
        check_cancellation()
        if getattr(config, "ENABLE_OA_FILTER", True):
            emit_log(
                "info",
                "Filtering to open-access papers only - paywalled papers will be excluded",
                "Filter: loattrfull text[sb]",
            )
        relevant_count = getattr(config, "PUBMED_RELEVANT_COUNT", 100)
        query_results = pubmed_data_collector.search_pubmed(query, relevant_count)
        initial_pmids.update(query_results)

    emit_log("info", f"Found {len(initial_pmids)} papers")
    report_progress("Fetching paper details", 20, {"papers_found": len(initial_pmids)})
    check_cancellation()
    emit_log("debug", f"Fetching details for {len(initial_pmids)} PMIDs from PubMed")

    if pipeline_tracer.is_enabled():
        pipeline_tracer.capture(
            "user_selection",
            inputs={
                "query": query or "",
                "specific_pmids": list(specific_pmids or []),
                "specific_authors": list(specific_authors or []),
                "top_n_cited": top_n_cited,
            },
            outputs={
                "deduplicated_pmids_count": len(initial_pmids),
                "mandatory_pmids_count": len(mandatory_pmids),
                "target_pmid_in_selection": pipeline_tracer.matches_any(initial_pmids),
            },
        )

    fetch_start = time.time()
    with pipeline_tracer.stage("pubmed_metadata"):
        paper_details = pubmed_data_collector.fetch_paper_details(list(initial_pmids))
    fetch_duration_ms = (time.time() - fetch_start) * 1000.0

    if pipeline_tracer.is_enabled():
        target = pipeline_tracer.target_pmid()
        entry = paper_details.get(target) if target else None
        pipeline_tracer.capture(
            "pubmed_metadata",
            pmid=target,
            inputs={"pmids_requested": len(initial_pmids)},
            outputs={
                "target_metadata": pipeline_tracer.summarise(entry) if entry else None,
                "retrieved_count": len(paper_details),
            },
            duration_ms=fetch_duration_ms,
        )

    incomplete_count = sum(
        1
        for v in paper_details.values()
        if (v.get("_metadata_completeness", 1) < 1 or v.get("_metadata_warnings"))
    )
    if incomplete_count:
        emit_log(
            "warn",
            f"Metadata quality warning: {incomplete_count}/{len(paper_details)} papers have incomplete metadata",
            "Check 'Metadata Completeness' and 'Metadata Warnings' columns in output",
        )

    return PaperSelectionResult(
        initial_pmids=initial_pmids,
        mandatory_pmids=mandatory_pmids,
        paper_details=paper_details,
        papers_excluded_not_oa=papers_excluded_not_oa,
    )
