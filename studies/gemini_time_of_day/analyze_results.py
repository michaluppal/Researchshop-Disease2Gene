#!/usr/bin/env python3
"""Aggregate Gemini time-of-day study run manifests."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import math
import json
import statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any


STUDY_DIR = Path(__file__).resolve().parent
REPO_ROOT = STUDY_DIR.parents[1]
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


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def stdev(values: list[float]) -> float:
    clean = [float(v) for v in values if v is not None]
    return statistics.stdev(clean) if len(clean) >= 2 else 0.0


def p95(values: list[float]) -> float:
    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return 0.0
    index = max(0, math.ceil(0.95 * len(clean)) - 1)
    return clean[index]


def describe_metric(name: str, values: list[float]) -> dict[str, Any]:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return {
            "metric": name,
            "count": 0,
            "mean": 0,
            "median": 0,
            "sd": 0,
            "min": 0,
            "max": 0,
            "p95": 0,
        }
    return {
        "metric": name,
        "count": len(clean),
        "mean": statistics.mean(clean),
        "median": statistics.median(clean),
        "sd": stdev(clean),
        "min": min(clean),
        "max": max(clean),
        "p95": p95(clean),
    }


def descriptive_rows(
    batch_rows: list[dict[str, Any]],
    paper_rows: list[dict[str, Any]],
    *,
    scope: str = "all_attempted_runs",
) -> list[dict[str, Any]]:
    metrics = [
        ("batch_runtime_seconds", batch_rows, "runtime_seconds"),
        ("batch_gemini_api_calls", batch_rows, "gemini_api_calls"),
        ("batch_gemini_prompt_tokens", batch_rows, "gemini_prompt_tokens"),
        ("batch_gemini_response_tokens", batch_rows, "gemini_response_tokens"),
        ("batch_gemini_total_tokens", batch_rows, "gemini_total_tokens"),
        ("batch_output_rows", batch_rows, "output_rows"),
        ("paper_runtime_seconds", paper_rows, "runtime_seconds"),
        ("paper_gemini_api_calls", paper_rows, "gemini_api_calls"),
        ("paper_gemini_prompt_tokens", paper_rows, "gemini_prompt_tokens"),
        ("paper_gemini_response_tokens", paper_rows, "gemini_response_tokens"),
        ("paper_gemini_total_tokens", paper_rows, "gemini_total_tokens"),
        ("paper_emitted_rows", paper_rows, "emitted_rows"),
        ("paper_strict_gate_drops", paper_rows, "strict_gate_drops"),
        ("paper_citation_gate_drops", paper_rows, "citation_gate_drops"),
    ]
    rows_out = [
        describe_metric(name, [safe_float(row.get(key)) for row in rows])
        for name, rows, key in metrics
    ]
    for row in rows_out:
        row["scope"] = scope
    return rows_out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def mean_pairwise_jaccard(sets: list[set[str]]) -> float | None:
    if len(sets) < 2:
        return None
    scores = [jaccard(left, right) for left, right in combinations(sets, 2)]
    return statistics.mean(scores) if scores else None


def first_present(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {name.lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return None


def normalize_output_value(value: Any) -> str:
    return str(value or "").strip()


def manifest_artifact_path(manifest: dict[str, Any], raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    candidates = [REPO_ROOT / path]
    manifest_path = str(manifest.get("_manifest_path") or "").strip()
    if manifest_path:
        candidates.append(Path(manifest_path).parent / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def batch_success(row: dict[str, Any]) -> bool:
    return (
        safe_int(row.get("total_papers")) > 0
        and safe_int(row.get("completed_papers")) == safe_int(row.get("total_papers"))
        and safe_float(row.get("completion_rate")) >= 1.0
    )


def failure_class(row: dict[str, Any]) -> str:
    if batch_success(row):
        if safe_int(row.get("quota_limited_rows")) or safe_int(row.get("quota_limited_papers")):
            return "complete_with_quota_limit"
        if safe_int(row.get("timeout_count")):
            return "complete_with_timeout"
        if safe_int(row.get("gemini_error_count")) or safe_int(row.get("model_unavailable_count")):
            return "complete_recovered_gemini_errors"
        return "complete_clean"
    if safe_int(row.get("quota_limited_rows")) or safe_int(row.get("quota_limited_papers")):
        return "quota_limited"
    if safe_int(row.get("timeout_count")):
        return "timeout"
    if safe_int(row.get("gemini_error_count")) or safe_int(row.get("model_unavailable_count")):
        return "gemini_api_failure"
    if safe_int(row.get("gemini_api_calls")) == 0 and safe_int(row.get("output_rows")) == 0:
        return "upstream_metadata_or_fulltext_failure"
    if safe_int(row.get("return_code")) != 0:
        return "runner_error"
    return "partial_or_unclassified_failure"


def load_output_observations(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = manifest.get("outputs") or {}
    observations: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"rows": 0, "genes": set(), "gene_variants": set()}
    )
    csv_raw = str(outputs.get("csv") or "").strip()
    if not csv_raw:
        return observations
    csv_path = manifest_artifact_path(manifest, csv_raw)
    if not csv_path.exists() or not csv_path.is_file():
        return observations
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        pmid_col = first_present(fieldnames, ("PMID", "pmid"))
        gene_col = first_present(fieldnames, ("Gene", "Gene/Group", "gene_name"))
        variant_col = first_present(fieldnames, ("Variant", "Variant Name", "variant_name"))
        if not pmid_col:
            return observations
        for row in reader:
            pmid = normalize_output_value(row.get(pmid_col))
            if not pmid:
                continue
            obs = observations[pmid]
            obs["rows"] += 1
            gene = normalize_output_value(row.get(gene_col)) if gene_col else ""
            variant = normalize_output_value(row.get(variant_col)) if variant_col else ""
            if gene:
                gene_key = gene.upper()
                obs["genes"].add(gene_key)
                if variant:
                    obs["gene_variants"].add(f"{gene_key}|{variant.upper()}")
    return observations


def output_stability_rows(manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output_by_run = {
        str(manifest.get("run_id", "")): load_output_observations(manifest)
        for manifest in manifests
    }
    paper_metrics: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for manifest in manifests:
        run_id = str(manifest.get("run_id", ""))
        observed = output_by_run.get(run_id, {})
        per_paper = {
            str(paper.get("pmid", "")): paper
            for paper in manifest.get("per_paper", [])
            if str(paper.get("pmid", "")).strip()
        }
        pmids = set(observed.keys()) | set(per_paper.keys())
        for pmid in pmids:
            obs = observed.get(pmid, {"rows": 0, "genes": set(), "gene_variants": set()})
            paper = per_paper.get(pmid, {})
            emitted_rows = safe_float(paper.get("emitted_rows"))
            if emitted_rows == 0 and obs.get("rows"):
                emitted_rows = safe_float(obs.get("rows"))
            strict_drops = safe_float(paper.get("strict_gate_drops"))
            citation_drops = safe_float(paper.get("citation_gate_drops"))
            denominator = emitted_rows + strict_drops + citation_drops
            paper_metrics[pmid].append(
                {
                    "run_id": run_id,
                    "emitted_rows": emitted_rows,
                    "strict_gate_drops": strict_drops,
                    "citation_gate_drops": citation_drops,
                    "gate_drop_rate": (
                        (strict_drops + citation_drops) / denominator
                        if denominator > 0
                        else 0.0
                    ),
                    "genes": set(obs.get("genes") or set()),
                    "gene_variants": set(obs.get("gene_variants") or set()),
                }
            )

    rows: list[dict[str, Any]] = []
    for pmid, observations in sorted(paper_metrics.items()):
        emitted = [float(item["emitted_rows"]) for item in observations]
        mean_rows = statistics.mean(emitted) if emitted else 0.0
        row_sd = stdev(emitted)
        gene_sets = [set(item["genes"]) for item in observations]
        gene_variant_sets = [set(item["gene_variants"]) for item in observations]
        gene_jaccard = mean_pairwise_jaccard(gene_sets)
        gene_variant_jaccard = mean_pairwise_jaccard(gene_variant_sets)
        rows.append(
            {
                "pmid": pmid,
                "runs": len(observations),
                "mean_emitted_rows": mean_rows,
                "sd_emitted_rows": row_sd,
                "cv_emitted_rows": row_sd / mean_rows if mean_rows else 0.0,
                "min_emitted_rows": min(emitted) if emitted else 0,
                "max_emitted_rows": max(emitted) if emitted else 0,
                "mean_strict_gate_drops": statistics.mean(
                    [float(item["strict_gate_drops"]) for item in observations]
                )
                if observations
                else 0,
                "mean_citation_gate_drops": statistics.mean(
                    [float(item["citation_gate_drops"]) for item in observations]
                )
                if observations
                else 0,
                "mean_validation_gate_drop_rate": statistics.mean(
                    [float(item["gate_drop_rate"]) for item in observations]
                )
                if observations
                else 0,
                "mean_gene_jaccard": "" if gene_jaccard is None else gene_jaccard,
                "mean_gene_variant_jaccard": (
                    "" if gene_variant_jaccard is None else gene_variant_jaccard
                ),
            }
        )
    return rows


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
            "gemini_usage_metadata_calls": batch.get("gemini_usage_metadata_calls", 0),
            "gemini_prompt_tokens": batch.get("gemini_prompt_tokens", 0),
            "gemini_response_tokens": batch.get("gemini_response_tokens", 0),
            "gemini_total_tokens": batch.get("gemini_total_tokens", 0),
            "gemini_cached_tokens": batch.get("gemini_cached_tokens", 0),
            "gemini_thought_tokens": batch.get("gemini_thought_tokens", 0),
            "gemini_error_count": batch.get("gemini_error_count", 0),
            "model_unavailable_count": batch.get("model_unavailable_count", 0),
            "permission_denied_count": batch.get("permission_denied_count", 0),
            "output_rows": batch.get("output_rows", 0),
            "manifest_path": manifest.get("_manifest_path", ""),
        }
        batch_row["successful_batch"] = batch_success(batch_row)
        batch_row["failure_class"] = failure_class(batch_row)
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
                    "gemini_api_calls": paper.get("gemini_api_calls", 0),
                    "gemini_usage_metadata_calls": paper.get("gemini_usage_metadata_calls", 0),
                    "gemini_prompt_tokens": paper.get("gemini_prompt_tokens", 0),
                    "gemini_response_tokens": paper.get("gemini_response_tokens", 0),
                    "gemini_total_tokens": paper.get("gemini_total_tokens", 0),
                    "gemini_cached_tokens": paper.get("gemini_cached_tokens", 0),
                    "gemini_thought_tokens": paper.get("gemini_thought_tokens", 0),
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
        successful_rows = [row for row in rows if batch_success(row)]
        runtime_source = successful_rows or rows
        runtimes = [float(row["runtime_seconds"]) for row in runtime_source]
        completion_rates = [float(row["completion_rate"]) for row in rows]
        block_rows.append(
            {
                "time_block": block,
                "runs": len(rows),
                "successful_runs": len(successful_rows),
                "median_batch_runtime_seconds": median(runtimes),
                "median_completion_rate": median(completion_rates),
                "quota_limited_runs": sum(1 for row in rows if int(row["quota_limited_rows"] or 0) > 0),
                "model_unavailable_runs": sum(
                    1 for row in rows if int(row["model_unavailable_count"] or 0) > 0
                ),
                "timeout_runs": sum(1 for row in rows if int(row["timeout_count"] or 0) > 0),
                "upstream_failure_runs": sum(
                    1
                    for row in rows
                    if row.get("failure_class") == "upstream_metadata_or_fulltext_failure"
                ),
                "median_output_rows": median(
                    [float(row["output_rows"] or 0) for row in runtime_source]
                ),
                "median_gemini_api_calls": median(
                    [float(row["gemini_api_calls"] or 0) for row in runtime_source]
                ),
                "median_gemini_total_tokens": median(
                    [float(row["gemini_total_tokens"] or 0) for row in runtime_source]
                ),
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


def planned_label(row: dict[str, Any]) -> str:
    planned = str(row.get("planned_local_time") or "").strip()
    return planned or str(row.get("run_id") or "").strip()


def quantile(values: list[float], q: float) -> float:
    clean = sorted(float(v) for v in values)
    if not clean:
        return 0.0
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[lower]
    return clean[lower] * (upper - position) + clean[upper] * (position - lower)


def svg_text(
    x: float,
    y: float,
    text: Any,
    *,
    size: int = 12,
    anchor: str = "start",
    weight: str = "400",
    fill: str = "#111827",
    rotate: int | None = None,
) -> str:
    transform = f' transform="rotate({rotate} {x:.1f} {y:.1f})"' if rotate is not None else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'fill="{fill}"{transform}>{html.escape(str(text))}</text>'
    )


def svg_line(x1: float, y1: float, x2: float, y2: float, *, stroke: str = "#111827", width: float = 1.0) -> str:
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="{width:.1f}" />'
    )


def svg_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    fill: str,
    stroke: str = "none",
    rx: float = 0.0,
) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
        f'rx="{rx:.1f}" fill="{fill}" stroke="{stroke}" />'
    )


def write_svg(path: Path, width: int, height: int, elements: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                '<rect width="100%" height="100%" fill="white" />',
                *elements,
                "</svg>",
            ]
        ),
        encoding="utf-8",
    )


def nice_ticks(max_value: float, count: int = 5) -> list[float]:
    if max_value <= 0:
        return [0.0]
    raw_step = max_value / max(count - 1, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    normalized = raw_step / magnitude
    if normalized <= 1:
        step = magnitude
    elif normalized <= 2:
        step = 2 * magnitude
    elif normalized <= 5:
        step = 5 * magnitude
    else:
        step = 10 * magnitude
    top = math.ceil(max_value / step) * step
    ticks = []
    value = 0.0
    while value <= top + step * 0.1:
        ticks.append(value)
        value += step
    return ticks


def format_tick(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value / 1000:.0f}k"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def write_hour_line_plot(
    path: Path,
    batch_rows: list[dict[str, Any]],
    *,
    title: str,
    y_key: str,
    y_label: str,
    transform=lambda x: x,
    color: str = "#2563eb",
) -> None:
    rows = sorted(batch_rows, key=lambda row: str(row.get("planned_local_time") or row.get("run_id") or ""))
    width, height = 1120, 520
    left, right, top, bottom = 78, 32, 58, 96
    plot_w = width - left - right
    plot_h = height - top - bottom
    success_rows = [row for row in rows if batch_success(row)]
    values = [transform(safe_float(row.get(y_key))) for row in success_rows]
    y_max = max(values) if values else 1.0
    ticks = nice_ticks(y_max)
    y_top = max(ticks) if ticks else y_max

    def x_pos(index: int) -> float:
        if len(rows) <= 1:
            return left + plot_w / 2
        return left + index * (plot_w / (len(rows) - 1))

    def y_pos(value: float) -> float:
        return top + plot_h - (value / (y_top or 1)) * plot_h

    elements = [
        svg_text(left, 28, title, size=20, weight="700"),
        svg_text(left, 48, y_label, size=12, fill="#4b5563"),
    ]
    for tick in ticks:
        y = y_pos(tick)
        elements.append(svg_line(left, y, width - right, y, stroke="#e5e7eb", width=1))
        elements.append(svg_text(left - 8, y + 4, format_tick(tick), size=11, anchor="end", fill="#6b7280"))
    elements.append(svg_line(left, top, left, top + plot_h, stroke="#9ca3af", width=1))
    elements.append(svg_line(left, top + plot_h, width - right, top + plot_h, stroke="#9ca3af", width=1))

    points = []
    row_index = {id(row): idx for idx, row in enumerate(rows)}
    for row in success_rows:
        idx = row_index[id(row)]
        value = transform(safe_float(row.get(y_key)))
        points.append((x_pos(idx), y_pos(value), row))
    if len(points) >= 2:
        path_data = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
        elements.append(
            f'<polyline points="{path_data}" fill="none" stroke="{color}" stroke-width="2.5" />'
        )
    for x, y, row in points:
        elements.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" />')
        elements.append(
            f'<title>{html.escape(str(row.get("run_id")))}: {transform(safe_float(row.get(y_key))):.2f}</title>'
        )
    for idx, row in enumerate(rows):
        x = x_pos(idx)
        elements.append(svg_text(x, top + plot_h + 24, planned_label(row), size=10, anchor="end", rotate=-45, fill="#374151"))
        if not batch_success(row):
            y = top + plot_h - 7
            elements.append(svg_line(x - 6, y - 6, x + 6, y + 6, stroke="#dc2626", width=2))
            elements.append(svg_line(x - 6, y + 6, x + 6, y - 6, stroke="#dc2626", width=2))
            elements.append(svg_text(x, y - 14, "failed", size=10, anchor="middle", fill="#dc2626"))
    write_svg(path, width, height, elements)


def write_failure_matrix(path: Path, batch_rows: list[dict[str, Any]]) -> None:
    rows = sorted(batch_rows, key=lambda row: str(row.get("planned_local_time") or row.get("run_id") or ""))
    categories = [
        ("complete", lambda row: batch_success(row), "#16a34a"),
        ("upstream fetch failure", lambda row: row.get("failure_class") == "upstream_metadata_or_fulltext_failure", "#dc2626"),
        ("quota limited", lambda row: safe_int(row.get("quota_limited_rows")) > 0 or safe_int(row.get("quota_limited_papers")) > 0, "#7c3aed"),
        ("timeout", lambda row: safe_int(row.get("timeout_count")) > 0, "#ea580c"),
        ("recovered Gemini/API error", lambda row: safe_int(row.get("gemini_error_count")) > 0 or safe_int(row.get("model_unavailable_count")) > 0, "#f59e0b"),
    ]
    cell = 28
    left = 190
    top = 74
    width = max(620, left + len(rows) * cell + 40)
    height = top + len(categories) * cell + 88
    elements = [
        svg_text(28, 30, "Failure and Recovery Matrix", size=20, weight="700"),
        svg_text(28, 50, "Each column is one scheduled hourly batch.", size=12, fill="#4b5563"),
    ]
    for idx, row in enumerate(rows):
        x = left + idx * cell + cell / 2
        elements.append(svg_text(x, top - 12, planned_label(row), size=10, anchor="end", rotate=-45, fill="#374151"))
    for y_idx, (label, predicate, color) in enumerate(categories):
        y = top + y_idx * cell
        elements.append(svg_text(left - 12, y + 19, label, size=12, anchor="end"))
        for x_idx, row in enumerate(rows):
            x = left + x_idx * cell
            active = predicate(row)
            fill = color if active else "#f3f4f6"
            stroke = "#ffffff" if active else "#d1d5db"
            elements.append(svg_rect(x, y, cell - 3, cell - 3, fill=fill, stroke=stroke, rx=2))
    write_svg(path, width, height, elements)


def write_runtime_boxplot(path: Path, batch_rows: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in batch_rows:
        if batch_success(row):
            grouped[str(row.get("time_block") or "unknown")].append(safe_float(row.get("runtime_seconds")) / 60.0)
    blocks = [block for block in ("night", "morning", "afternoon", "evening") if grouped.get(block)]
    width, height = 760, 460
    left, right, top, bottom = 76, 40, 58, 76
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [value for block in blocks for value in grouped[block]]
    ticks = nice_ticks(max(values) if values else 1.0)
    y_top = max(ticks)

    def y_pos(value: float) -> float:
        return top + plot_h - (value / (y_top or 1)) * plot_h

    elements = [
        svg_text(left, 30, "Batch Runtime by Time Block", size=20, weight="700"),
        svg_text(left, 50, "Successful 10-paper batches only.", size=12, fill="#4b5563"),
    ]
    for tick in ticks:
        y = y_pos(tick)
        elements.append(svg_line(left, y, width - right, y, stroke="#e5e7eb"))
        elements.append(svg_text(left - 8, y + 4, format_tick(tick), size=11, anchor="end", fill="#6b7280"))
    elements.append(svg_line(left, top, left, top + plot_h, stroke="#9ca3af"))
    elements.append(svg_line(left, top + plot_h, width - right, top + plot_h, stroke="#9ca3af"))
    for idx, block in enumerate(blocks):
        vals = sorted(grouped[block])
        x = left + (idx + 0.5) * (plot_w / max(len(blocks), 1))
        q1, med, q3 = quantile(vals, 0.25), quantile(vals, 0.5), quantile(vals, 0.75)
        vmin, vmax = min(vals), max(vals)
        box_w = 58
        elements.append(svg_line(x, y_pos(vmin), x, y_pos(vmax), stroke="#374151", width=1.5))
        elements.append(svg_line(x - 18, y_pos(vmin), x + 18, y_pos(vmin), stroke="#374151", width=1.5))
        elements.append(svg_line(x - 18, y_pos(vmax), x + 18, y_pos(vmax), stroke="#374151", width=1.5))
        elements.append(svg_rect(x - box_w / 2, y_pos(q3), box_w, max(1, y_pos(q1) - y_pos(q3)), fill="#dbeafe", stroke="#2563eb", rx=3))
        elements.append(svg_line(x - box_w / 2, y_pos(med), x + box_w / 2, y_pos(med), stroke="#1d4ed8", width=2.5))
        for value in vals:
            elements.append(f'<circle cx="{x + 42:.1f}" cy="{y_pos(value):.1f}" r="3" fill="#64748b" opacity="0.75" />')
        elements.append(svg_text(x, top + plot_h + 28, f"{block} (n={len(vals)})", size=12, anchor="middle"))
    write_svg(path, width, height, elements)


def write_pmid_heatmap(path: Path, paper_rows: list[dict[str, Any]], batch_rows: list[dict[str, Any]]) -> None:
    successful_run_ids = {str(row.get("run_id")) for row in batch_rows if batch_success(row)}
    rows = [row for row in paper_rows if str(row.get("run_id")) in successful_run_ids]
    run_ids = sorted({str(row.get("run_id")) for row in rows})
    pmids = sorted({str(row.get("pmid")) for row in rows})
    values: dict[tuple[str, str], float] = {
        (str(row.get("pmid")), str(row.get("run_id"))): safe_float(row.get("emitted_rows"))
        for row in rows
    }
    max_value = max(values.values()) if values else 1.0
    cell_w, cell_h = 44, 24
    left, top = 92, 82
    width = max(760, left + len(run_ids) * cell_w + 40)
    height = max(360, top + len(pmids) * cell_h + 78)

    def color(value: float) -> str:
        if max_value <= 0:
            intensity = 0
        else:
            intensity = value / max_value
        r = int(239 - 202 * intensity)
        g = int(246 - 117 * intensity)
        b = int(255 - 57 * intensity)
        return f"#{r:02x}{g:02x}{b:02x}"

    elements = [
        svg_text(28, 30, "Per-PMID Output Row Stability", size=20, weight="700"),
        svg_text(28, 50, "Cell color encodes emitted rows for a paper in a successful run.", size=12, fill="#4b5563"),
    ]
    for idx, run_id in enumerate(run_ids):
        x = left + idx * cell_w + cell_w / 2
        label = run_id.replace("hour", "")
        elements.append(svg_text(x, top - 12, label, size=10, anchor="end", rotate=-45, fill="#374151"))
    for y_idx, pmid in enumerate(pmids):
        y = top + y_idx * cell_h
        elements.append(svg_text(left - 8, y + 16, pmid, size=11, anchor="end"))
        for x_idx, run_id in enumerate(run_ids):
            value = values.get((pmid, run_id), 0.0)
            x = left + x_idx * cell_w
            elements.append(svg_rect(x, y, cell_w - 2, cell_h - 2, fill=color(value), stroke="#ffffff"))
            if cell_w >= 34:
                elements.append(svg_text(x + cell_w / 2 - 1, y + 16, int(value), size=9, anchor="middle", fill="#111827"))
    write_svg(path, width, height, elements)


def write_plots(report_dir: Path, batch_rows: list[dict[str, Any]], paper_rows: list[dict[str, Any]]) -> list[Path]:
    plot_dir = report_dir / "plots"
    plots = [
        plot_dir / "batch_runtime_by_hour.svg",
        plot_dir / "gemini_calls_by_hour.svg",
        plot_dir / "gemini_tokens_by_hour.svg",
        plot_dir / "output_rows_by_hour.svg",
        plot_dir / "failure_matrix.svg",
        plot_dir / "runtime_by_time_block.svg",
        plot_dir / "per_pmid_output_rows_heatmap.svg",
    ]
    write_hour_line_plot(
        plots[0],
        batch_rows,
        title="10-Paper Batch Runtime by Scheduled Hour",
        y_key="runtime_seconds",
        y_label="Runtime (minutes); failed upstream slots marked in red",
        transform=lambda value: value / 60.0,
        color="#2563eb",
    )
    write_hour_line_plot(
        plots[1],
        batch_rows,
        title="Gemini API Calls by Scheduled Hour",
        y_key="gemini_api_calls",
        y_label="Gemini API calls per batch",
        color="#7c3aed",
    )
    write_hour_line_plot(
        plots[2],
        batch_rows,
        title="Gemini Total Tokens by Scheduled Hour",
        y_key="gemini_total_tokens",
        y_label="Total Gemini tokens per batch (thousands)",
        transform=lambda value: value / 1000.0,
        color="#0891b2",
    )
    write_hour_line_plot(
        plots[3],
        batch_rows,
        title="Final Output Rows by Scheduled Hour",
        y_key="output_rows",
        y_label="Final emitted rows per batch",
        color="#16a34a",
    )
    write_failure_matrix(plots[4], batch_rows)
    write_runtime_boxplot(plots[5], batch_rows)
    write_pmid_heatmap(plots[6], paper_rows, batch_rows)
    return plots


def write_markdown(
    path: Path,
    batch_rows: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
    descriptive: list[dict[str, Any]],
    stability: list[dict[str, Any]],
    verdict: str,
    plots: list[Path] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plots = plots or []
    successful_rows = [row for row in batch_rows if batch_success(row)]
    failure_counts: dict[str, int] = defaultdict(int)
    for row in batch_rows:
        failure_counts[str(row.get("failure_class") or "unknown")] += 1
    descriptive_by_metric = {row["metric"]: row for row in descriptive}
    batch_runtime = descriptive_by_metric.get("batch_runtime_seconds", {})
    paper_runtime = descriptive_by_metric.get("paper_runtime_seconds", {})
    batch_tokens = descriptive_by_metric.get("batch_gemini_total_tokens", {})
    paper_tokens = descriptive_by_metric.get("paper_gemini_total_tokens", {})
    row_cv_values = [
        safe_float(row.get("cv_emitted_rows"))
        for row in stability
        if str(row.get("cv_emitted_rows", "")).strip() != ""
    ]
    gene_jaccards = [
        safe_float(row.get("mean_gene_jaccard"))
        for row in stability
        if str(row.get("mean_gene_jaccard", "")).strip() != ""
    ]
    pair_jaccards = [
        safe_float(row.get("mean_gene_variant_jaccard"))
        for row in stability
        if str(row.get("mean_gene_variant_jaccard", "")).strip() != ""
    ]
    lines = [
        "# Gemini Free-Tier Time-of-Day Study Report",
        "",
        f"Verdict: **{verdict}**",
        "",
        f"Formal runs analyzed: {len(batch_rows)} attempted slots; {len(successful_rows)} complete 10-paper batches.",
        "",
        "Failure / recovery classes:",
        "",
        "| Class | Runs |",
        "|---|---:|",
    ]
    for label, count in sorted(failure_counts.items()):
        lines.append(f"| {label} | {count} |")
    lines.extend(
        [
            "",
            "## Plots",
            "",
        ]
    )
    for plot in plots:
        rel = plot.relative_to(path.parent)
        lines.append(f"- [{plot.stem}]({rel.as_posix()})")
    lines.extend(
        [
        "",
        "## Overall Metrics",
        "",
        "Runtime, token, and row-count summaries below use successful 10-paper batches only.",
        "",
        "| Metric | Mean | Median | SD | Min | Max | P95 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        "| Batch runtime (min) | {mean:.1f} | {median:.1f} | {sd:.1f} | {min:.1f} | {max:.1f} | {p95:.1f} |".format(
            mean=safe_float(batch_runtime.get("mean")) / 60.0,
            median=safe_float(batch_runtime.get("median")) / 60.0,
            sd=safe_float(batch_runtime.get("sd")) / 60.0,
            min=safe_float(batch_runtime.get("min")) / 60.0,
            max=safe_float(batch_runtime.get("max")) / 60.0,
            p95=safe_float(batch_runtime.get("p95")) / 60.0,
        ),
        "| Paper runtime (min) | {mean:.1f} | {median:.1f} | {sd:.1f} | {min:.1f} | {max:.1f} | {p95:.1f} |".format(
            mean=safe_float(paper_runtime.get("mean")) / 60.0,
            median=safe_float(paper_runtime.get("median")) / 60.0,
            sd=safe_float(paper_runtime.get("sd")) / 60.0,
            min=safe_float(paper_runtime.get("min")) / 60.0,
            max=safe_float(paper_runtime.get("max")) / 60.0,
            p95=safe_float(paper_runtime.get("p95")) / 60.0,
        ),
        "| Batch Gemini total tokens | {mean:.0f} | {median:.0f} | {sd:.0f} | {min:.0f} | {max:.0f} | {p95:.0f} |".format(
            mean=safe_float(batch_tokens.get("mean")),
            median=safe_float(batch_tokens.get("median")),
            sd=safe_float(batch_tokens.get("sd")),
            min=safe_float(batch_tokens.get("min")),
            max=safe_float(batch_tokens.get("max")),
            p95=safe_float(batch_tokens.get("p95")),
        ),
        "| Paper Gemini total tokens | {mean:.0f} | {median:.0f} | {sd:.0f} | {min:.0f} | {max:.0f} | {p95:.0f} |".format(
            mean=safe_float(paper_tokens.get("mean")),
            median=safe_float(paper_tokens.get("median")),
            sd=safe_float(paper_tokens.get("sd")),
            min=safe_float(paper_tokens.get("min")),
            max=safe_float(paper_tokens.get("max")),
            p95=safe_float(paper_tokens.get("p95")),
        ),
        "",
        "## Output Stability",
        "",
        f"- Median per-PMID emitted-row CV: {median(row_cv_values):.3f}",
        f"- Median per-PMID gene-set Jaccard: {median(gene_jaccards):.3f}",
        f"- Median per-PMID gene-variant Jaccard: {median(pair_jaccards):.3f}",
        "",
        "## Time Blocks",
        "",
        "| Time block | Runs | Successful | Median runtime (min) | Median completion | Quota-limited runs | Upstream failures | 503/high-demand runs | Timeout runs | Median calls | Median total tokens | Median output rows |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in block_rows:
        lines.append(
            "| {time_block} | {runs} | {successful} | {runtime:.1f} | {completion:.0%} | {quota} | {upstream} | {unavailable} | {timeouts} | {calls:.0f} | {tokens:.0f} | {rows:.0f} |".format(
                time_block=row["time_block"],
                runs=row["runs"],
                successful=row.get("successful_runs", ""),
                runtime=float(row["median_batch_runtime_seconds"] or 0) / 60.0,
                completion=float(row["median_completion_rate"] or 0),
                quota=row["quota_limited_runs"],
                upstream=row.get("upstream_failure_runs", 0),
                unavailable=row["model_unavailable_runs"],
                timeouts=row["timeout_runs"],
                calls=safe_float(row.get("median_gemini_api_calls")),
                tokens=safe_float(row.get("median_gemini_total_tokens")),
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
            "## Interim Interpretation",
            "",
            "Treat this report as a snapshot until the 24-hour schedule has finished. A failed upstream metadata/full-text slot should be described separately from Gemini quota or model failures because it does not consume Gemini requests and does not test free-tier capacity.",
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
    successful_run_ids = {
        str(row.get("run_id"))
        for row in batch_rows
        if batch_success(row)
    }
    successful_batch_rows = [
        row for row in batch_rows if str(row.get("run_id")) in successful_run_ids
    ]
    successful_paper_rows = [
        row for row in paper_rows if str(row.get("run_id")) in successful_run_ids
    ]
    successful_manifests = [
        manifest for manifest in manifests if str(manifest.get("run_id")) in successful_run_ids
    ]
    descriptive_all = descriptive_rows(batch_rows, paper_rows, scope="all_attempted_runs")
    descriptive_success = descriptive_rows(
        successful_batch_rows,
        successful_paper_rows,
        scope="successful_10_paper_batches",
    )
    descriptive = descriptive_all + descriptive_success
    stability = output_stability_rows(successful_manifests)
    verdict = classify(batch_rows, block_rows)
    plots = write_plots(args.report_dir, batch_rows, paper_rows)

    write_csv(args.report_dir / "batch_metrics.csv", batch_rows)
    write_csv(args.report_dir / "paper_metrics.csv", paper_rows)
    write_csv(args.report_dir / "time_block_summary.csv", block_rows)
    write_csv(args.report_dir / "descriptive_summary.csv", descriptive)
    write_csv(
        args.report_dir / "failure_events.csv",
        [
            {
                "run_id": row.get("run_id"),
                "planned_local_time": row.get("planned_local_time"),
                "time_block": row.get("time_block"),
                "failure_class": row.get("failure_class"),
                "successful_batch": row.get("successful_batch"),
                "completed_papers": row.get("completed_papers"),
                "total_papers": row.get("total_papers"),
                "runtime_seconds": row.get("runtime_seconds"),
                "gemini_api_calls": row.get("gemini_api_calls"),
                "gemini_error_count": row.get("gemini_error_count"),
                "model_unavailable_count": row.get("model_unavailable_count"),
                "quota_limited_rows": row.get("quota_limited_rows"),
                "quota_limited_papers": row.get("quota_limited_papers"),
                "timeout_count": row.get("timeout_count"),
                "output_rows": row.get("output_rows"),
                "manifest_path": row.get("manifest_path"),
            }
            for row in batch_rows
        ],
    )
    write_csv(args.report_dir / "stability_metrics.csv", stability)
    write_markdown(
        args.report_dir / "report.md",
        batch_rows,
        block_rows,
        descriptive_success or descriptive_all,
        stability,
        verdict,
        plots,
    )

    print(f"Analyzed {len(batch_rows)} run(s). Verdict: {verdict}")
    print(f"Report written: {args.report_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
