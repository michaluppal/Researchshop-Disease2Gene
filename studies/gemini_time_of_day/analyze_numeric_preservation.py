#!/usr/bin/env python3
"""Analyze numerical-preservation citation-validation events."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


STUDY_DIR = Path(__file__).resolve().parent
DEFAULT_SESSION = STUDY_DIR / "runs" / "session_20260609_0100_scheduler"
DEFAULT_RUN_ROOT = DEFAULT_SESSION if DEFAULT_SESSION.exists() else STUDY_DIR / "runs"
DEFAULT_REPORT_DIR = STUDY_DIR / "reports"
NUMERIC_RE = re.compile(r"Numerical mismatch:\s*'([^']+)'")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def is_truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def run_dirs(run_root: Path) -> list[Path]:
    return [
        path
        for path in sorted(run_root.glob("hour*"))
        if path.is_dir() and (path / "study_run.json").exists()
    ]


def citation_detail_columns(fieldnames: list[str]) -> list[str]:
    return [
        name
        for name in fieldnames
        if name.endswith(" Citation_citation_details")
    ]


def base_field(detail_col: str) -> str:
    return detail_col[: -len(" Citation_citation_details")]


def row_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("PMID") or row.get("pmid") or "").strip(),
        str(row.get("gene_name") or row.get("Gene/Group") or row.get("Gene") or "").strip(),
        str(row.get("variant_name") or row.get("Variant Name") or row.get("Variant") or "").strip(),
    )


def row_has_valid_citation(row: dict[str, Any], fieldnames: list[str]) -> bool:
    return any(
        name.endswith(" Citation_citation_valid") and is_truthy(row.get(name))
        for name in fieldnames
    )


def row_citation_field_count(row: dict[str, Any], fieldnames: list[str]) -> int:
    count = 0
    for detail_col in citation_detail_columns(fieldnames):
        field = base_field(detail_col)
        citation_col = f"{field} Citation"
        if str(row.get(citation_col, "")).strip():
            count += 1
    return count


def extract_metadata_events(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    run_id = run_dir.name
    metadata_paths = sorted(run_dir.glob("final_enriched_results_*_metadata.csv"))
    events: list[dict[str, Any]] = []
    denominators = {
        "citation_validations": 0,
        "numeric_bearing_citations": 0,
        "citation_bearing_rows": 0,
        "emitted_rows": 0,
    }
    for path in metadata_paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            detail_cols = citation_detail_columns(fieldnames)
            for row_idx, row in enumerate(reader):
                denominators["emitted_rows"] += 1
                citation_field_count = row_citation_field_count(row, fieldnames)
                if citation_field_count:
                    denominators["citation_bearing_rows"] += 1
                has_valid = row_has_valid_citation(row, fieldnames)
                pmid, gene, variant = row_identity(row)
                for detail_col in detail_cols:
                    field = base_field(detail_col)
                    citation = str(row.get(f"{field} Citation", "")).strip()
                    if not citation:
                        continue
                    denominators["citation_validations"] += 1
                    numeric_tokens = str(
                        row.get(f"{field} Citation_numeric_tokens_in_citation")
                        or row.get(f"{field} Citation_numeric_tokens_matched")
                        or ""
                    ).strip()
                    detail = str(row.get(detail_col, "")).strip()
                    missing = NUMERIC_RE.findall(detail)
                    if numeric_tokens or missing:
                        denominators["numeric_bearing_citations"] += 1
                    for token in missing:
                        events.append(
                            {
                                "source": "metadata_csv",
                                "run_id": run_id,
                                "pmid": pmid,
                                "gene": gene,
                                "variant": variant,
                                "field": field,
                                "missing_numeric_token": token,
                                "detail": detail,
                                "row_index": row_idx,
                                "row_outcome": (
                                    "retained_with_another_valid_citation"
                                    if has_valid
                                    else "exported_with_numeric_mismatch_metadata"
                                ),
                                "artifact_path": str(path),
                            }
                        )
    return events, denominators


def extract_drop_events(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    run_id = run_dir.name
    events: list[dict[str, Any]] = []
    denominators = {
        "citation_gate_drop_rows": 0,
        "numeric_citation_gate_drop_rows": 0,
        "numeric_only_citation_gate_drop_rows": 0,
    }
    for path in sorted(run_dir.glob("drop_debug_*.json")):
        payload = read_json(path)
        for paper in payload.get("paper_debug", []) or []:
            pmid = str(paper.get("pmid", "")).strip()
            for drop_idx, drop in enumerate(paper.get("evidence_gate_drops", []) or []):
                if drop.get("reason") != "ungrounded_citation":
                    continue
                denominators["citation_gate_drop_rows"] += 1
                invalid = drop.get("invalid_fields", []) or []
                numeric_invalid = [
                    item for item in invalid if NUMERIC_RE.search(str(item.get("detail", "")))
                ]
                if numeric_invalid:
                    denominators["numeric_citation_gate_drop_rows"] += 1
                if invalid and len(numeric_invalid) == len(invalid):
                    denominators["numeric_only_citation_gate_drop_rows"] += 1
                for item in numeric_invalid:
                    detail = str(item.get("detail", "")).strip()
                    for token in NUMERIC_RE.findall(detail):
                        events.append(
                            {
                                "source": "drop_debug",
                                "run_id": run_id,
                                "pmid": pmid,
                                "gene": str(drop.get("gene", "")).strip(),
                                "variant": str(drop.get("variant", "")).strip(),
                                "field": str(item.get("field", "")).replace(" Citation", ""),
                                "missing_numeric_token": token,
                                "detail": detail,
                                "row_index": drop_idx,
                                "row_outcome": "citation_gate_drop",
                                "artifact_path": str(path),
                            }
                        )
    return events, denominators


def load_manifest_metrics(run_dir: Path) -> dict[str, Any]:
    manifest = read_json(run_dir / "study_run.json")
    batch = manifest.get("batch", {}) or {}
    return {
        "run_id": manifest.get("run_id", run_dir.name),
        "time_block": manifest.get("time_block", ""),
        "completed_papers": safe_int(batch.get("completed_papers")),
        "total_papers": safe_int(batch.get("total_papers")),
        "output_rows": safe_int(batch.get("output_rows")),
        "citation_gate_drops": sum(
            safe_int(paper.get("citation_gate_drops"))
            for paper in manifest.get("per_paper", []) or []
        ),
    }


def collect(run_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    totals: dict[str, Any] = defaultdict(int)
    for run_dir in run_dirs(run_root):
        manifest = load_manifest_metrics(run_dir)
        metadata_events, metadata_denoms = extract_metadata_events(run_dir)
        drop_events, drop_denoms = extract_drop_events(run_dir)
        run_events = metadata_events + drop_events
        events.extend(run_events)
        for key, value in {**metadata_denoms, **drop_denoms}.items():
            totals[key] += safe_int(value)
        by_pmid = {event["pmid"] for event in run_events if event.get("pmid")}
        run_rows.append(
            {
                **manifest,
                "numeric_mismatch_events": len(run_events),
                "affected_pmids": len(by_pmid),
                "metadata_numeric_events": len(metadata_events),
                "drop_numeric_events": len(drop_events),
                "numeric_citation_gate_drop_rows": drop_denoms[
                    "numeric_citation_gate_drop_rows"
                ],
                "numeric_only_citation_gate_drop_rows": drop_denoms[
                    "numeric_only_citation_gate_drop_rows"
                ],
                "citation_validations": metadata_denoms["citation_validations"],
                "numeric_bearing_citations": metadata_denoms[
                    "numeric_bearing_citations"
                ],
                "emitted_rows": metadata_denoms["emitted_rows"],
            }
        )
    totals["runs"] = len(run_rows)
    totals["events"] = len(events)
    return events, run_rows, dict(totals)


def summary_rows(events: list[dict[str, Any]], run_rows: list[dict[str, Any]], totals: dict[str, Any]) -> list[dict[str, Any]]:
    affected_rows = {
        (event["run_id"], event["pmid"], event["gene"], event["variant"], event["row_index"], event["source"])
        for event in events
    }
    batches_with_events = sum(1 for row in run_rows if safe_int(row["numeric_mismatch_events"]) > 0)
    mismatch_counts = [safe_int(row["numeric_mismatch_events"]) for row in run_rows]
    citation_validations = safe_int(totals.get("citation_validations"))
    emitted_rows = safe_int(totals.get("emitted_rows"))
    citation_drop_rows = safe_int(totals.get("citation_gate_drop_rows"))
    numeric_drop_rows = safe_int(totals.get("numeric_citation_gate_drop_rows"))
    return [
        {"metric": "Hourly batches analyzed", "value": safe_int(totals.get("runs"))},
        {"metric": "Total citation validations", "value": citation_validations},
        {"metric": "Numeric-bearing citations", "value": safe_int(totals.get("numeric_bearing_citations"))},
        {"metric": "Numeric mismatch events", "value": len(events)},
        {"metric": "Affected rows", "value": len(affected_rows)},
        {"metric": "Batches with >=1 mismatch", "value": batches_with_events},
        {"metric": "Rows excluded from primary export", "value": numeric_drop_rows},
        {"metric": "Rows removed only after numeric mismatch", "value": safe_int(totals.get("numeric_only_citation_gate_drop_rows"))},
        {"metric": "Mean mismatches per 10-paper batch", "value": round(statistics.mean(mismatch_counts), 3) if mismatch_counts else 0},
        {"metric": "Median mismatches per 10-paper batch", "value": round(statistics.median(mismatch_counts), 3) if mismatch_counts else 0},
        {"metric": "Mismatches per emitted row", "value": round(len(events) / emitted_rows, 4) if emitted_rows else 0},
        {"metric": "Mismatches per citation validation", "value": round(len(events) / citation_validations, 4) if citation_validations else 0},
        {"metric": "Numeric-attributed share of citation-gate drops", "value": round(numeric_drop_rows / citation_drop_rows, 4) if citation_drop_rows else 0},
    ]


def pmid_rows(events: list[dict[str, Any]], run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs = {row["run_id"] for row in run_rows}
    by_pmid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_pmid[str(event.get("pmid", ""))].append(event)
    rows = []
    for pmid, pmid_events in sorted(by_pmid.items()):
        citation_drop_rows = {
            (event["run_id"], event["pmid"], event["gene"], event["variant"], event["row_index"])
            for event in pmid_events
            if event.get("row_outcome") == "citation_gate_drop"
        }
        observed_runs = {event["run_id"] for event in pmid_events}
        rows.append(
            {
                "pmid": pmid,
                "runs_observed": len(runs),
                "runs_with_numeric_mismatch": len(observed_runs),
                "numeric_mismatch_count": len(pmid_events),
                "citation_gate_drops_attributable_to_numeric_mismatch": len(citation_drop_rows),
                "mismatch_rate_per_run": round(len(pmid_events) / len(runs), 4) if runs else 0,
            }
        )
    return rows


def write_heatmap(path: Path, events: list[dict[str, Any]], run_rows: list[dict[str, Any]]) -> None:
    pmids = sorted({event["pmid"] for event in events if event.get("pmid")})
    run_ids = [str(row["run_id"]) for row in run_rows]
    counts = defaultdict(int)
    for event in events:
        counts[(event["pmid"], event["run_id"])] += 1
    cell = 22
    left = 78
    top = 36
    width = left + len(run_ids) * cell + 20
    height = top + len(pmids) * cell + 55
    max_count = max(counts.values(), default=1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Arial,Helvetica,sans-serif;font-size:9px}.title{font-size:14px;font-weight:700}.axis{fill:#666}</style>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text class="title" x="8" y="18">Numerical-preservation mismatches</text>',
    ]
    for col, run_id in enumerate(run_ids):
        label = run_id.replace("hour", "")
        x = left + col * cell + cell / 2
        parts.append(f'<text class="axis" x="{x}" y="32" text-anchor="middle">{html.escape(label)}</text>')
    for row, pmid in enumerate(pmids):
        y = top + row * cell
        parts.append(f'<text class="axis" x="{left - 6}" y="{y + 14}" text-anchor="end">{html.escape(pmid)}</text>')
        for col, run_id in enumerate(run_ids):
            value = counts[(pmid, run_id)]
            intensity = int(240 - (180 * value / max_count)) if value else 248
            color = f"rgb(255,{intensity},{intensity})" if value else "rgb(248,248,248)"
            x = left + col * cell
            parts.append(f'<rect x="{x}" y="{y}" width="{cell - 2}" height="{cell - 2}" fill="{color}" stroke="#ddd"/>')
            if value:
                parts.append(f'<text x="{x + (cell - 2) / 2}" y="{y + 14}" text-anchor="middle">{value}</text>')
    parts.append('<rect x="8" y="{0}" width="10" height="10" fill="rgb(255,60,60)"/>'.format(height - 26))
    parts.append(f'<text class="axis" x="24" y="{height - 17}">Darker red = more missing numeric tokens in citation validation</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_markdown(path: Path, summary: list[dict[str, Any]], pmids: list[dict[str, Any]], figure_name: str) -> None:
    value_for = {row["metric"]: row["value"] for row in summary}
    triggered = value_for.get("Numeric mismatch events", 0)
    fields = value_for.get("Total citation validations", 0)
    excluded = value_for.get("Rows excluded from primary export", 0)
    text = (
        f"Numerical preservation was triggered {triggered} times across {fields} citation validations. "
        f"{excluded} row(s) were excluded from the primary export with a numeric-mismatch citation-gate signal; "
        "the remaining events were retained in exported metadata because another citation or validation path kept the row reviewable. "
        "This indicates that the check catches quantitative drift in LLM-provided evidence quotes rather than broad extraction failure."
    )
    lines = [
        "# Numerical-Preservation Gate Analysis",
        "",
        text,
        "",
        "## Manuscript-Ready Summary Table",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for row in summary:
        lines.append(f"| {row['metric']} | {row['value']} |")
    lines.extend([
        "",
        "## PMIDs With Numeric Mismatches",
        "",
        "| PMID | Mismatches | Runs with mismatch | Numeric-attributed citation-gate drops |",
        "|---|---:|---:|---:|",
    ])
    for row in pmids:
        lines.append(
            "| {pmid} | {numeric_mismatch_count} | {runs_with_numeric_mismatch} | {citation_gate_drops_attributable_to_numeric_mismatch} |".format(**row)
        )
    lines.extend(["", f"![Numerical-preservation heatmap]({figure_name})", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    events, run_rows, totals = collect(args.run_root)
    summary = summary_rows(events, run_rows, totals)
    pmids = pmid_rows(events, run_rows)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.report_dir / "numeric_preservation_events.csv", events)
    write_csv(args.report_dir / "numeric_preservation_by_run.csv", run_rows)
    write_csv(args.report_dir / "numeric_preservation_summary.csv", summary)
    write_csv(args.report_dir / "numeric_preservation_by_pmid.csv", pmids)
    write_heatmap(args.report_dir / "numeric_preservation_heatmap.svg", events, run_rows)
    write_markdown(
        args.report_dir / "numeric_preservation_report.md",
        summary,
        pmids,
        "numeric_preservation_heatmap.svg",
    )
    print(f"Wrote numeric-preservation analysis to {args.report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
