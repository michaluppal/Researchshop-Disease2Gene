#!/usr/bin/env python3
"""Aggregate Gemini time-of-day study run manifests."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import json
import statistics
from collections import defaultdict
from itertools import combinations
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


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


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
    return [
        describe_metric(name, [safe_float(row.get(key)) for row in rows])
        for name, rows, key in metrics
    ]


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


def load_output_observations(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = manifest.get("outputs") or {}
    observations: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"rows": 0, "genes": set(), "gene_variants": set()}
    )
    csv_raw = str(outputs.get("csv") or "").strip()
    if not csv_raw:
        return observations
    csv_path = Path(csv_raw)
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
                "median_gemini_api_calls": median(
                    [float(row["gemini_api_calls"] or 0) for row in rows]
                ),
                "median_gemini_total_tokens": median(
                    [float(row["gemini_total_tokens"] or 0) for row in rows]
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


def write_markdown(
    path: Path,
    batch_rows: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
    descriptive: list[dict[str, Any]],
    stability: list[dict[str, Any]],
    verdict: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        f"Formal runs analyzed: {len(batch_rows)}",
        "",
        "## Overall Metrics",
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
        "| Time block | Runs | Median runtime (min) | Median completion | Quota-limited runs | 503/high-demand runs | Timeout runs | Median calls | Median total tokens | Median output rows |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in block_rows:
        lines.append(
            "| {time_block} | {runs} | {runtime:.1f} | {completion:.0%} | {quota} | {unavailable} | {timeouts} | {calls:.0f} | {tokens:.0f} | {rows:.0f} |".format(
                time_block=row["time_block"],
                runs=row["runs"],
                runtime=float(row["median_batch_runtime_seconds"] or 0) / 60.0,
                completion=float(row["median_completion_rate"] or 0),
                quota=row["quota_limited_runs"],
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
    descriptive = descriptive_rows(batch_rows, paper_rows)
    stability = output_stability_rows(manifests)
    verdict = classify(batch_rows, block_rows)

    write_csv(args.report_dir / "batch_metrics.csv", batch_rows)
    write_csv(args.report_dir / "paper_metrics.csv", paper_rows)
    write_csv(args.report_dir / "time_block_summary.csv", block_rows)
    write_csv(args.report_dir / "descriptive_summary.csv", descriptive)
    write_csv(args.report_dir / "stability_metrics.csv", stability)
    write_markdown(
        args.report_dir / "report.md",
        batch_rows,
        block_rows,
        descriptive,
        stability,
        verdict,
    )

    print(f"Analyzed {len(batch_rows)} run(s). Verdict: {verdict}")
    print(f"Report written: {args.report_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
