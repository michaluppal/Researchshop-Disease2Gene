#!/usr/bin/env python3
"""Aggregate Gemini time-of-day study run manifests."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


STUDY_DIR = Path(__file__).resolve().parent
DEFAULT_RUN_ROOT = STUDY_DIR / "runs"
DEFAULT_REPORT_DIR = STUDY_DIR / "reports"
DEFAULT_CORPUS = STUDY_DIR / "corpus.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def pmid_fingerprint(pmids: list[str]) -> str:
    normalized = "\n".join(str(pmid).strip() for pmid in pmids)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def corpus_fingerprint(corpus_path: Path) -> str:
    corpus = load_json(corpus_path)
    pmids = [
        str(entry.get("pmid", "")).strip()
        for entry in corpus.get("pmids", [])
        if str(entry.get("pmid", "")).strip()
    ]
    return pmid_fingerprint(pmids)


def collect_manifests(
    run_root: Path,
    *,
    include_pilots: bool = False,
    expected_corpus_fingerprint: str | None = None,
    include_unlocked_corpus_runs: bool = False,
) -> list[dict[str, Any]]:
    manifests = []
    for path in sorted(run_root.glob("*/study_run.json")):
        payload = load_json(path)
        run_id = str(payload.get("run_id", path.parent.name)).lower()
        time_block = str(payload.get("time_block", "")).lower()
        if not include_pilots and (run_id.startswith("pilot") or time_block == "pilot"):
            continue
        manifest_fingerprint = str(payload.get("corpus_fingerprint", "")).strip()
        if (
            expected_corpus_fingerprint
            and not include_unlocked_corpus_runs
            and manifest_fingerprint != expected_corpus_fingerprint
        ):
            continue
        payload["_manifest_path"] = str(path)
        manifests.append(payload)
    return manifests


def median(values: list[float]) -> float:
    clean = [float(v) for v in values if v is not None]
    return statistics.median(clean) if clean else 0.0


def summarize(manifests: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    batch_rows: list[dict[str, Any]] = []
    paper_rows: list[dict[str, Any]] = []
    by_block: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for manifest in manifests:
        batch = manifest.get("batch", {})
        per_paper = manifest.get("per_paper", [])
        if per_paper:
            completed_papers = sum(1 for paper in per_paper if paper.get("status") == "ok")
            failed_papers = sum(
                1
                for paper in per_paper
                if paper.get("status") and paper.get("status") not in {"ok", "timeout", "no_full_text"}
            )
            total_papers = len(per_paper)
        else:
            completed_papers = int(batch.get("completed_papers", 0) or 0)
            failed_papers = int(batch.get("failed_papers", 0) or 0)
            total_papers = int(batch.get("total_papers", 0) or 0)
        batch_row = {
            "run_id": manifest.get("run_id", ""),
            "time_block": manifest.get("time_block", ""),
            "repeat": manifest.get("repeat", ""),
            "planned_date": manifest.get("planned_date", ""),
            "planned_local_time": manifest.get("planned_local_time", ""),
            "quota_window_start_date": manifest.get("quota_window_start_date", ""),
            "started_at": manifest.get("started_at", ""),
            "runtime_seconds": manifest.get("runtime_seconds", 0),
            "return_code": manifest.get("return_code", 0),
            "completed_papers": completed_papers,
            "total_papers": total_papers,
            "completion_rate": (
                float(completed_papers) / float(total_papers or 1)
            ),
            "failed_papers": failed_papers,
            "quota_limited_papers": batch.get("quota_limited_papers", 0),
            "quota_limited_rows": batch.get("quota_limited_rows", 0),
            "quota_warning_count": batch.get("quota_warning_count", 0),
            "timeout_count": batch.get("timeout_count", 0),
            "gemini_api_calls": batch.get("gemini_api_calls", 0),
            "gemini_error_count": batch.get("gemini_error_count", 0),
            "model_unavailable_count": batch.get("model_unavailable_count", 0),
            "permission_denied_count": batch.get("permission_denied_count", 0),
            "output_rows": batch.get("output_rows", 0),
            "manifest_path": manifest.get("_manifest_path", ""),
        }
        batch_rows.append(batch_row)
        by_block[str(batch_row["time_block"])].append(batch_row)

        for paper in manifest.get("per_paper", []):
            paper_rows.append(
                {
                    "run_id": manifest.get("run_id", ""),
                    "time_block": manifest.get("time_block", ""),
                    "repeat": manifest.get("repeat", ""),
                    "planned_date": manifest.get("planned_date", ""),
                    "planned_local_time": manifest.get("planned_local_time", ""),
                    "quota_window_start_date": manifest.get("quota_window_start_date", ""),
                    "pmid": paper.get("pmid", ""),
                    "runtime_seconds": paper.get("runtime_seconds", 0),
                    "status": paper.get("status", ""),
                    "fetch_source": paper.get("fetch_source", ""),
                    "text_chars": paper.get("text_chars", ""),
                    "candidate_count": paper.get("candidate_count", ""),
                    "emitted_rows": paper.get("emitted_rows", 0),
                    "strict_gate_drops": paper.get("strict_gate_drops", 0),
                    "citation_gate_drops": paper.get("citation_gate_drops", 0),
                    "quota_limited": paper.get("quota_limited", False),
                    "detail_extraction_status": paper.get("detail_extraction_status", ""),
                    "detail_extraction_error": paper.get("detail_extraction_error", ""),
                }
            )

    block_rows = []
    for block, rows in sorted(by_block.items()):
        runtimes = [float(row["runtime_seconds"]) for row in rows]
        completion_rates = [float(row["completion_rate"]) for row in rows]
        block_rows.append(
            {
                "time_block": block,
                "runs": len(rows),
                "median_batch_runtime_seconds": median(runtimes),
                "median_completion_rate": median(completion_rates),
                "quota_limited_runs": sum(1 for row in rows if int(row["quota_limited_rows"] or 0) > 0),
                "model_unavailable_runs": sum(
                    1 for row in rows if int(row["model_unavailable_count"] or 0) > 0
                ),
                "timeout_runs": sum(1 for row in rows if int(row["timeout_count"] or 0) > 0),
                "median_output_rows": median([float(row["output_rows"] or 0) for row in rows]),
            }
        )
    return batch_rows, paper_rows, block_rows


def classify(batch_rows: list[dict[str, Any]], block_rows: list[dict[str, Any]]) -> str:
    if not batch_rows:
        return "no_data"
    completion = median([float(row["completion_rate"]) for row in batch_rows])
    median_runtime = median([float(row["runtime_seconds"]) for row in batch_rows])
    quota_runs = sum(1 for row in batch_rows if int(row["quota_limited_rows"] or 0) > 0)
    timeout_runs = sum(1 for row in batch_rows if int(row["timeout_count"] or 0) > 0)
    failed_runs = sum(1 for row in batch_rows if int(row.get("failed_papers") or 0) > 0)
    permission_denied_runs = sum(
        1 for row in batch_rows if int(row.get("permission_denied_count") or 0) > 0
    )
    block_runtimes = [
        float(row["median_batch_runtime_seconds"])
        for row in block_rows
        if float(row["median_batch_runtime_seconds"] or 0) > 0
    ]
    runtime_ratio = (max(block_runtimes) / min(block_runtimes)) if len(block_runtimes) >= 2 else 1.0

    if completion < 0.7:
        return "not_usable"
    if quota_runs or timeout_runs or permission_denied_runs:
        return "not_usable" if completion < 0.9 else "marginal"
    if len(block_rows) < 4:
        return "insufficient_data"
    if (
        completion >= 0.9
        and median_runtime <= 90 * 60
        and runtime_ratio <= 2.0
        and failed_runs == 0
    ):
        return "usable"
    if completion >= 0.7:
        return "marginal"
    return "not_usable"


def write_markdown(
    path: Path,
    batch_rows: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
    verdict: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Gemini Free-Tier Time-of-Day Study Report",
        "",
        f"Verdict: **{verdict}**",
        "",
        f"Formal runs analyzed: {len(batch_rows)}",
        "",
        "## Time Blocks",
        "",
        "| Time block | Runs | Median runtime (min) | Median completion | Quota-limited runs | 503/high-demand runs | Timeout runs | Median output rows |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in block_rows:
        lines.append(
            "| {time_block} | {runs} | {runtime:.1f} | {completion:.0%} | {quota} | {unavailable} | {timeouts} | {rows:.0f} |".format(
                time_block=row["time_block"],
                runs=row["runs"],
                runtime=float(row["median_batch_runtime_seconds"] or 0) / 60.0,
                completion=float(row["median_completion_rate"] or 0),
                quota=row["quota_limited_runs"],
                unavailable=row["model_unavailable_runs"],
                timeouts=row["timeout_runs"],
                rows=float(row["median_output_rows"] or 0),
            )
        )
    lines.extend(
        [
            "",
            "## Decision Rules",
            "",
            "- Usable: >=90% batch completion, median runtime <=90 minutes, no time block >2x another, no quota-limited or timeout runs.",
            "- Marginal: >=70% completion but one or more usability criteria missed.",
            "- Not usable: <70% completion.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--include-pilots",
        action="store_true",
        help="Include pilot manifests in aggregate reports. Formal reports exclude them.",
    )
    parser.add_argument(
        "--include-unlocked-corpus-runs",
        action="store_true",
        help="Include older manifests missing or mismatching the current corpus fingerprint.",
    )
    args = parser.parse_args()

    expected_fingerprint = corpus_fingerprint(args.corpus)
    manifests = collect_manifests(
        args.run_root,
        include_pilots=args.include_pilots,
        expected_corpus_fingerprint=expected_fingerprint,
        include_unlocked_corpus_runs=args.include_unlocked_corpus_runs,
    )
    batch_rows, paper_rows, block_rows = summarize(manifests)
    verdict = classify(batch_rows, block_rows)

    write_csv(args.report_dir / "batch_metrics.csv", batch_rows)
    write_csv(args.report_dir / "paper_metrics.csv", paper_rows)
    write_csv(args.report_dir / "time_block_summary.csv", block_rows)
    write_markdown(args.report_dir / "report.md", batch_rows, block_rows, verdict)

    print(f"Analyzed {len(batch_rows)} run(s). Verdict: {verdict}")
    print(f"Report written: {args.report_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
