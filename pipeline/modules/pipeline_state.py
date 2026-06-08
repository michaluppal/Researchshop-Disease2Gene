"""Explicit run state and callback helpers for the pipeline orchestrator."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import pandas as pd

from . import config


class JobCancelledException(Exception):
    """Raised when a job is cancelled by the user."""


def default_pipeline_stats() -> Dict[str, Any]:
    """Initial frontend-visible run statistics."""
    return {
        "papers_found": 0,
        "papers_screened": 0,
        "papers_screened_passed": 0,
        "papers_fetch_failed": 0,
        "papers_analyzed": 0,
        "genes_extracted": 0,
        "gemini_api_calls": 0,
        "gemini_usage_metadata_calls": 0,
        "gemini_prompt_tokens": 0,
        "gemini_response_tokens": 0,
        "gemini_total_tokens": 0,
        "gemini_cached_tokens": 0,
        "gemini_thought_tokens": 0,
        "tables_extracted": 0,
        "pubtator_pmids_skipped": 0,
        "papers_excluded_not_oa": 0,
        "strict_gate_drops": [],
        "strict_gate_drops_count": 0,
        "quota_limited_papers": 0,
        "quota_limited_rows": 0,
    }


@dataclass
class PipelineRunState:
    """Readable data carrier for one end-to-end ResearchShop pipeline run."""

    query: str
    specific_pmids: List[str]
    specific_authors: List[str]
    user_columns: Dict[str, str]
    top_n_cited: int
    start_time: float = field(default_factory=time.time)

    pipeline_stats: Dict[str, Any] = field(default_factory=default_pipeline_stats)
    paper_debug_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    forensic_screening: List[Dict[str, Any]] = field(default_factory=list)
    fetch_report: List[Dict[str, Any]] = field(default_factory=list)

    initial_pmids: Set[str] = field(default_factory=set)
    mandatory_pmids: Set[str] = field(default_factory=set)
    paper_details: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    content_dict: Dict[str, Any] = field(default_factory=dict)
    scraped_pmids: List[str] = field(default_factory=list)
    pubtator_results: Dict[str, Any] = field(default_factory=dict)
    citation_records: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    pmids_to_process: List[str] = field(default_factory=list)

    all_results_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    collected_rows: List[str] = field(default_factory=list)
    full_rows_pmids: Set[str] = field(default_factory=set)
    minimal_rows: List[Dict[str, Any]] = field(default_factory=list)
    analyzed_attempts: int = 0

    primary_path: str = ""
    metadata_path: str = ""
    excel_path: str = ""
    json_path: str = ""
    candidate_audit_path: str = ""
    debug_path: str = ""
    trace_path: str = ""


class PipelineEmitters:
    """Frontend callback, cancellation, and progress helper for a run."""

    def __init__(
        self,
        state: PipelineRunState,
        progress_callback: Optional[Callable[[str, int, Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str, str, Optional[str]], None]] = None,
    ):
        self.state = state
        self.progress_callback = progress_callback
        self.log_callback = log_callback

    def emit_log(self, level: str, msg: str, detail: Optional[str] = None) -> None:
        if self.log_callback:
            self.log_callback(level, msg, detail)
        log_level = {
            "info": logging.INFO,
            "debug": logging.DEBUG,
            "warn": logging.WARNING,
            "error": logging.ERROR,
        }.get(level, logging.INFO)
        logging.log(log_level, msg)

    def check_cancellation(self) -> None:
        cancel_path = os.path.join(config.OUTPUT_DIR, ".cancel")
        if os.path.exists(cancel_path):
            self.emit_log("warn", "Pipeline cancelled by user")
            raise JobCancelledException("Job was cancelled")

    def report_progress(
        self,
        stage: str,
        pct: int,
        extra_stats: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.check_cancellation()
        if extra_stats:
            self.state.pipeline_stats.update(extra_stats)
        if self.progress_callback:
            self.progress_callback(stage, pct, self.state.pipeline_stats.copy())
        logging.info(
            "Progress: %s (%s%%) - Stats: %s",
            stage,
            pct,
            self.state.pipeline_stats,
        )
