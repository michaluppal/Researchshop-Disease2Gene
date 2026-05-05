"""Run-level artifact helpers for pipeline debug and candidate audit JSON.

The orchestrator owns the run state; this module owns the stable JSON payload
shapes and file writing details so the main pipeline flow can stay readable.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from .association_policy import association_group_for_type, count_association_groups


def _ensure_unique_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DataFrame columns are uniquely named by suffixing duplicates."""
    if not isinstance(df, pd.DataFrame):
        return df
    cols = list(df.columns)
    seen_counts: dict[str, int] = {}
    new_cols: list[str] = []
    for col in cols:
        count = seen_counts.get(col, 0)
        if count == 0:
            new_cols.append(col)
        else:
            new_cols.append(f"{col} ({count + 1})")
        seen_counts[col] = count + 1
    df.columns = new_cols
    return df


def candidate_audit_rows_by_pmid(df: pd.DataFrame) -> dict:
    """Summarize emitted final rows for candidate-audit final counts."""
    if df is None or df.empty:
        return {}

    work = _ensure_unique_columns(df.copy())
    if "Association Type" in work.columns and "Association Group" not in work.columns:
        work["Association Group"] = work["Association Type"].apply(association_group_for_type)

    pmid_col = "PMID" if "PMID" in work.columns else None
    gene_col = "Gene/Group" if "Gene/Group" in work.columns else ("Gene" if "Gene" in work.columns else None)
    variant_col = (
        "Variant Name"
        if "Variant Name" in work.columns
        else ("Variant" if "Variant" in work.columns else None)
    )
    if not pmid_col or not gene_col:
        return {}

    rows_by_pmid = {}
    for pmid, group_df in work.groupby(pmid_col, dropna=False, sort=False):
        associations = []
        for _, row in group_df.iterrows():
            gene = str(row.get(gene_col) or "")
            if not gene.strip():
                continue
            association_type = str(row.get("Association Type") or "")
            association_group = str(row.get("Association Group") or "")
            if not association_group:
                association_group = association_group_for_type(association_type)
            associations.append(
                {
                    "gene": gene,
                    "variant": str(row.get(variant_col) or "") if variant_col else "",
                    "association_type": association_type,
                    "association_group": association_group,
                }
            )
        rows_by_pmid[str(pmid)] = {
            "final_associations": associations,
            "emitted_rows": int(len(group_df)),
            "final_association_group_counts": count_association_groups(associations),
        }
    return rows_by_pmid


def candidate_audit_summary(papers: list[dict]) -> dict:
    """Build run-level audit counts from emitted final rows."""
    final_group_counts = count_association_groups(
        association
        for paper in papers
        for association in (paper.get("final_associations") or [])
    )
    candidate_group_counts = count_association_groups(
        candidate for paper in papers for candidate in (paper.get("candidates") or [])
    )
    return {
        "papers": len(papers),
        "total_candidates": sum(int(p.get("candidate_count") or 0) for p in papers),
        "total_emitted_rows": sum(int(p.get("emitted_rows") or 0) for p in papers),
        "association_group_counts": final_group_counts,
        "final_association_group_counts": final_group_counts,
        "candidate_association_group_counts": candidate_group_counts,
    }


def build_drop_debug_payload(
    *,
    status: str,
    query: str,
    specific_pmids: list | None,
    specific_authors: list | None,
    top_n_cited: int,
    output_csv_path: str = "",
    paper_debug_artifacts: list[dict],
    pipeline_stats: dict,
    forensic_screening: list[dict],
    fetch_report: list[dict],
    generated_at_epoch: float | None = None,
) -> dict:
    """Build the stable drop-debug JSON payload."""
    return {
        "status": status,
        "generated_at_epoch": time.time() if generated_at_epoch is None else generated_at_epoch,
        "query": query,
        "specific_pmids": list(specific_pmids or []),
        "specific_authors": list(specific_authors or []),
        "top_n_cited": top_n_cited,
        "output_csv_path": output_csv_path or "",
        "paper_debug": paper_debug_artifacts,
        "pipeline_stats": pipeline_stats.copy(),
        "screening_decisions": forensic_screening,
        "fetch_outcomes": fetch_report,
    }


def build_candidate_audit_payload(
    *,
    all_results_df: pd.DataFrame,
    paper_debug_artifacts: list[dict],
    output_csv_path: str = "",
    generated_at_epoch: float | None = None,
) -> dict:
    """Build the stable candidate audit JSON payload."""
    emitted_by_pmid = candidate_audit_rows_by_pmid(all_results_df)
    papers = []
    for paper in paper_debug_artifacts:
        emitted_summary = emitted_by_pmid.get(str(paper.get("pmid", "")), {})
        candidates = paper.get("candidates", []) or []
        final_associations = (
            emitted_summary.get("final_associations")
            if emitted_summary
            else paper.get("final_associations", []) or []
        )
        papers.append(
            {
                "pmid": paper.get("pmid", ""),
                "status": paper.get("status", ""),
                "reason": paper.get("reason", ""),
                "candidate_count": paper.get("candidate_count"),
                "candidates": candidates,
                "validation_drops": paper.get("validation_drops", []),
                "strict_gate_drops": paper.get("strict_gate_drops", []),
                "evidence_gate_drops": paper.get("evidence_gate_drops", []),
                "final_associations": final_associations,
                "emitted_rows": emitted_summary.get(
                    "emitted_rows", paper.get("emitted_rows", 0)
                ),
                "association_group_counts": count_association_groups(candidates),
                "final_association_group_counts": emitted_summary.get(
                    "final_association_group_counts",
                    count_association_groups(final_associations),
                ),
            }
        )
    return {
        "schema_version": "candidate_audit_v1",
        "status": "completed",
        "generated_at_epoch": time.time() if generated_at_epoch is None else generated_at_epoch,
        "output_csv_path": output_csv_path or "",
        "summary": candidate_audit_summary(papers),
        "papers": papers,
    }


@dataclass
class RunArtifactWriter:
    """Write pipeline artifact JSON files through a narrow orchestrator API."""

    create_filepath: Callable[[str, str], str]
    emit_log: Callable[[str, str, Any], None]
    logger: Any = field(default_factory=lambda: logging.getLogger(__name__))
    clock: Callable[[], float] = time.time

    def write_drop_debug_artifact(
        self,
        *,
        status: str,
        query: str,
        specific_pmids: list | None,
        specific_authors: list | None,
        top_n_cited: int,
        output_csv_path: str = "",
        paper_debug_artifacts: list[dict],
        pipeline_stats: dict,
        forensic_screening: list[dict],
        fetch_report: list[dict],
    ) -> str:
        """Persist per-run candidate/drop diagnostics to JSON."""
        payload = build_drop_debug_payload(
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
            generated_at_epoch=self.clock(),
        )
        return self._write_json_artifact(
            "drop_debug",
            payload,
            success_message="Saved drop-debug artifact",
            failure_message="Failed to write drop-debug artifact",
        )

    def write_candidate_audit_artifact(
        self,
        *,
        all_results_df: pd.DataFrame,
        paper_debug_artifacts: list[dict],
        output_csv_path: str = "",
    ) -> str:
        """Persist candidate lifecycle as a stable first-class artifact."""
        payload = build_candidate_audit_payload(
            all_results_df=all_results_df,
            paper_debug_artifacts=paper_debug_artifacts,
            output_csv_path=output_csv_path,
            generated_at_epoch=self.clock(),
        )
        return self._write_json_artifact(
            "candidate_audit",
            payload,
            success_message="Saved candidate audit artifact",
            failure_message="Failed to write candidate audit artifact",
        )

    def _write_json_artifact(
        self,
        prefix: str,
        payload: dict,
        *,
        success_message: str,
        failure_message: str,
    ) -> str:
        path = self.create_filepath(prefix, "json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
            self.emit_log("info", success_message, path)
            return path
        except Exception as exc:
            self.logger.warning(f"{failure_message}: {exc}")
            return ""
