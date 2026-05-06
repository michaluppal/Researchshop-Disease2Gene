#!/usr/bin/env python3
"""Compare an existing PIMS/MIS-C pipeline output directory to its gold standard.

This is an offline helper: it reads already-written ResearchShop artifacts and
does not call Gemini, PubMed, NCBI, or any other network service.

Usage:
    python pipeline/scripts/compare_pims_gold_standard.py \
      --output-dir /private/tmp/rs_pims_normalized_seed_validation
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).parent
PIPELINE_DIR = SCRIPT_DIR.parent
DEFAULT_GOLD_PATH = (
    PIPELINE_DIR / "data" / "gold_standard" / "pims_mis_c_35177862.json"
)
DEFAULT_PMID = "35177862"

PRIMARY_CSV_GLOB = "final_enriched_results_*.csv"
CANDIDATE_AUDIT_GLOB = "candidate_audit_*.json"

REQUIRED_TRACE_NODES = {
    "pubmed_metadata",
    "full_text_fetch",
    "pubtator_ner",
    "fulltext_pass_greedy",
    "deterministic_scan",
    "grounding_check",
    "hgnc_validation",
    "detail_extraction",
    "citation_validation",
    "output_writer",
}

ROW_TEXT_COLUMNS = [
    "Gene",
    "Gene/Group",
    "Variant",
    "Variant Name",
    "Key Finding",
    "Key Finding Citation",
    "Statistical Evidence",
    "Statistical Evidence Citation",
    "Conclusion",
    "Conclusion Citation",
    "Original Paper Mention",
    "Grounding Match",
    "Grounding Source",
    "Normalization Rule",
    "Evidence Sentence",
    "Association Group",
    "Association Type",
]

PIMS_CONTEXT_TOKENS = {
    "TRBV11-2": ["TRBV11-2", "TRBV11 2"],
    "HLA-A": ["A*02", "HLA-A*02", "HLA A*02"],
    "HLA-B": ["B*35", "HLA-B*35", "HLA B*35"],
    "HLA-C": ["C*04", "HLA-C*04", "HLA C*04"],
    "IFNG": ["IFN-gamma", "cytokine_alias_ifng"],
    "MMP9": ["MMP-9", "protein_alias_mmp9"],
}


class ComparisonError(RuntimeError):
    """Raised when required comparison artifacts are missing or unreadable."""


def normalize_symbol(value: Any) -> str:
    """Normalize gene symbols for set comparison without changing HGNC spelling."""
    return str(value or "").strip().upper()


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ComparisonError(f"Could not read JSON: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ComparisonError(f"Invalid JSON: {path}") from exc


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError as exc:
        raise ComparisonError(f"Could not read CSV: {path}") from exc
    except csv.Error as exc:
        raise ComparisonError(f"Invalid CSV: {path}") from exc


def _latest_path(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    return sorted(paths, key=lambda p: (p.stat().st_mtime, p.name))[-1]


def find_primary_csv(output_dir: Path, explicit_csv: Path | None = None) -> Path:
    if explicit_csv:
        if not explicit_csv.exists():
            raise ComparisonError(f"Primary CSV does not exist: {explicit_csv}")
        return explicit_csv

    if not output_dir.exists():
        raise ComparisonError(f"Output directory does not exist: {output_dir}")

    candidates = [
        path
        for path in output_dir.glob(PRIMARY_CSV_GLOB)
        if not path.name.endswith("_metadata.csv")
    ]
    latest = _latest_path(candidates)
    if latest is None:
        raise ComparisonError(
            f"No primary CSV matching {PRIMARY_CSV_GLOB} found in {output_dir}"
        )
    return latest


def companion_metadata_csv(primary_csv: Path) -> Path | None:
    metadata = primary_csv.with_name(f"{primary_csv.stem}_metadata.csv")
    return metadata if metadata.exists() else None


def find_candidate_audit(output_dir: Path) -> Path | None:
    return _latest_path(list(output_dir.glob(CANDIDATE_AUDIT_GLOB)))


def find_trace_json(output_dir: Path, pmid: str) -> Path | None:
    trace = output_dir / f"trace_{pmid}.json"
    return trace if trace.exists() else None


def find_live_events(output_dir: Path) -> Path | None:
    live_events = output_dir / "live_events.jsonl"
    return live_events if live_events.exists() else None


def expected_gene_symbols(gold: dict[str, Any]) -> list[str]:
    symbols = []
    for item in gold.get("expected_genes", []):
        if isinstance(item, str):
            symbol = item
            expected = True
        else:
            symbol = item.get("symbol", "")
            expected = item.get("expected", True)
        normalized = normalize_symbol(symbol)
        if expected and normalized:
            symbols.append(normalized)
    return _unique_preserve_order(symbols)


def mapped_excluded_symbols(gold: dict[str, Any]) -> set[str]:
    symbols: set[str] = set()
    for item in gold.get("excluded_markers", []):
        mapped = item.get("mapped_symbol") if isinstance(item, dict) else None
        if not mapped:
            continue
        for part in re.split(r"\s*/\s*|\s*,\s*|\s*;\s*", str(mapped)):
            symbol = normalize_symbol(part)
            if symbol:
                symbols.add(symbol)
    return symbols


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if not value or value in seen:
            continue
        unique.append(value)
        seen.add(value)
    return unique


def _row_gene(row: dict[str, str]) -> str:
    return normalize_symbol(row.get("Gene") or row.get("Gene/Group"))


def _row_pmid(row: dict[str, str]) -> str:
    return str(row.get("PMID") or "").strip()


def rows_for_pmid(
    rows: list[dict[str, str]],
    pmid: str,
    warnings: list[str],
    *,
    artifact_name: str,
) -> list[dict[str, str]]:
    if not rows:
        return []
    has_pmid_column = "PMID" in rows[0]
    if not has_pmid_column:
        warnings.append(f"{artifact_name} has no PMID column; comparing all rows.")
        return rows
    return [row for row in rows if _row_pmid(row) == pmid]


def _rows_text(rows: list[dict[str, str]]) -> str:
    parts = []
    for row in rows:
        for column in ROW_TEXT_COLUMNS:
            value = str(row.get(column) or "").strip()
            if value:
                parts.append(value)
    return "\n".join(parts)


def _context_check(symbol: str, rows: list[dict[str, str]]) -> dict[str, Any] | None:
    tokens = PIMS_CONTEXT_TOKENS.get(symbol)
    if not tokens:
        return None
    text = _rows_text(rows).lower()
    found = [token for token in tokens if token.lower() in text]
    return {
        "tokens": tokens,
        "found": found,
        "passed": bool(found),
    }


def _nonempty_values(rows: list[dict[str, str]], *columns: str) -> list[str]:
    values = []
    for row in rows:
        for column in columns:
            value = str(row.get(column) or "").strip()
            if value:
                values.append(value)
    return _unique_preserve_order(values)


def _float_values(rows: list[dict[str, str]], column: str) -> list[float]:
    values = []
    for row in rows:
        try:
            values.append(float(str(row.get(column) or "").strip()))
        except ValueError:
            continue
    return values


def summarize_expected_rows(
    expected_symbols: list[str],
    rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[dict[str, str]]] = {
        symbol: [] for symbol in expected_symbols
    }
    for row in rows:
        symbol = _row_gene(row)
        if symbol in by_symbol:
            by_symbol[symbol].append(row)

    details = []
    for symbol in expected_symbols:
        symbol_rows = by_symbol[symbol]
        validation_confidence_values = _float_values(symbol_rows, "validation_confidence")
        details.append(
            {
                "symbol": symbol,
                "row_count": len(symbol_rows),
                "variants": _nonempty_values(symbol_rows, "Variant", "Variant Name"),
                "association_groups": _nonempty_values(symbol_rows, "Association Group"),
                "association_types": _nonempty_values(symbol_rows, "Association Type"),
                "grounding_matches": _nonempty_values(symbol_rows, "Grounding Match"),
                "grounding_sources": _nonempty_values(symbol_rows, "Grounding Source"),
                "normalization_rules": _nonempty_values(symbol_rows, "Normalization Rule"),
                "confidence_values": _nonempty_values(symbol_rows, "Confidence"),
                "validation_confidence_max": max(validation_confidence_values)
                if validation_confidence_values
                else None,
                "extraction_modes": _nonempty_values(symbol_rows, "extraction_mode"),
                "context_check": _context_check(symbol, symbol_rows),
            }
        )
    return details


def summarize_candidate_audit(path: Path | None, pmid: str) -> dict[str, Any] | None:
    if not path:
        return None
    payload = load_json(path)
    paper = None
    for item in payload.get("papers", []):
        if str(item.get("pmid") or "").strip() == pmid:
            paper = item
            break

    return {
        "path": str(path),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "summary": payload.get("summary", {}),
        "paper": {
            "pmid": paper.get("pmid"),
            "status": paper.get("status"),
            "candidate_count": paper.get("candidate_count"),
            "emitted_rows": paper.get("emitted_rows"),
            "final_association_group_counts": paper.get(
                "final_association_group_counts", {}
            ),
        }
        if paper
        else None,
    }


def summarize_trace(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    payload = load_json(path)
    nodes = payload.get("nodes", {})
    stage_labels = sorted(nodes.keys())
    function_trace_path = payload.get("function_trace_path")
    function_trace_exists = (
        Path(function_trace_path).exists() if function_trace_path else False
    )
    return {
        "path": str(path),
        "pmid": payload.get("pmid"),
        "node_count": payload.get("node_count"),
        "stage_labels": stage_labels,
        "missing_required_nodes": sorted(REQUIRED_TRACE_NODES - set(stage_labels)),
        "function_event_count": payload.get("function_event_count"),
        "function_trace_path": function_trace_path,
        "function_trace_exists": function_trace_exists,
    }


def compare_output_directory(
    output_dir: Path | str,
    *,
    gold_path: Path | str = DEFAULT_GOLD_PATH,
    primary_csv: Path | str | None = None,
    pmid: str | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    gold_path = Path(gold_path)
    gold = load_json(gold_path)
    target_pmid = str(pmid or gold.get("pmid") or DEFAULT_PMID)
    warnings: list[str] = []

    primary_path = find_primary_csv(
        output_dir, Path(primary_csv) if primary_csv else None
    )
    metadata_path = companion_metadata_csv(primary_path)
    candidate_audit_path = find_candidate_audit(output_dir)
    trace_path = find_trace_json(output_dir, target_pmid)
    live_events_path = find_live_events(output_dir)

    primary_rows_all = load_csv_rows(primary_path)
    primary_rows = rows_for_pmid(
        primary_rows_all, target_pmid, warnings, artifact_name="primary CSV"
    )

    metadata_row_count = None
    metadata_rows = None
    if metadata_path:
        metadata_rows_all = load_csv_rows(metadata_path)
        metadata_rows = rows_for_pmid(
            metadata_rows_all, target_pmid, warnings, artifact_name="metadata CSV"
        )
        metadata_row_count = len(metadata_rows)
    else:
        warnings.append(
            "Metadata CSV not found; validation confidence checks use primary CSV only."
        )

    expected_symbols = expected_gene_symbols(gold)
    expected_set = set(expected_symbols)
    extracted_symbols = {
        symbol for symbol in (_row_gene(row) for row in primary_rows) if symbol
    }
    matched = [symbol for symbol in expected_symbols if symbol in extracted_symbols]
    missing = [symbol for symbol in expected_symbols if symbol not in extracted_symbols]
    additional = sorted(extracted_symbols - expected_set)
    excluded_detected = sorted(extracted_symbols & mapped_excluded_symbols(gold))

    detail_rows = metadata_rows if metadata_rows is not None else primary_rows
    expected_details = summarize_expected_rows(expected_symbols, detail_rows)
    context_failures = [
        detail["symbol"]
        for detail in expected_details
        if detail["row_count"] > 0
        and detail.get("context_check")
        and not detail["context_check"]["passed"]
    ]
    low_confidence = [
        {
            "symbol": detail["symbol"],
            "validation_confidence_max": detail["validation_confidence_max"],
        }
        for detail in expected_details
        if detail["row_count"] > 0
        and (
            detail["validation_confidence_max"] is None
            or detail["validation_confidence_max"] < 0.7
        )
    ]
    fallback_detail_genes = [
        detail["symbol"]
        for detail in expected_details
        if detail["row_count"] > 0
        and (
            "skeleton" in {mode.lower() for mode in detail["extraction_modes"]}
            or (
                detail["extraction_modes"]
                and "llm" not in {mode.lower() for mode in detail["extraction_modes"]}
            )
        )
    ]
    trace_summary = summarize_trace(trace_path)
    trace_missing_nodes = (
        trace_summary.get("missing_required_nodes", list(sorted(REQUIRED_TRACE_NODES)))
        if trace_summary
        else list(sorted(REQUIRED_TRACE_NODES))
    )
    function_event_count = (
        trace_summary.get("function_event_count") if trace_summary else None
    )
    missing_function_trace = not function_event_count or int(function_event_count or 0) <= 0
    missing_function_jsonl = (
        not trace_summary or not trace_summary.get("function_trace_exists")
    )
    missing_live_events = live_events_path is None
    candidate_audit_summary = summarize_candidate_audit(candidate_audit_path, target_pmid)
    candidate_audit_incomplete = (
        not candidate_audit_summary
        or candidate_audit_summary.get("status") != "completed"
        or not candidate_audit_summary.get("paper")
    )
    failed_checks = {
        "missing_expected_genes": missing,
        "low_confidence_expected_genes": low_confidence,
        "context_check_failures": context_failures,
        "fallback_detail_genes": fallback_detail_genes,
        "candidate_audit_incomplete": candidate_audit_incomplete,
        "trace_missing_nodes": trace_missing_nodes,
        "missing_function_trace": missing_function_trace,
        "missing_function_jsonl": missing_function_jsonl,
        "missing_live_events": missing_live_events,
    }
    review_notes = {
        "additional_non_fixture_genes": additional,
        "excluded_marker_genes_detected": excluded_detected,
    }
    status = "pass" if not any(failed_checks.values()) else "failed_acceptance_checks"

    return {
        "pmid": target_pmid,
        "gold_standard_path": str(gold_path),
        "output_dir": str(output_dir),
        "artifacts": {
            "primary_csv": str(primary_path),
            "metadata_csv": str(metadata_path) if metadata_path else None,
            "candidate_audit_json": str(candidate_audit_path)
            if candidate_audit_path
            else None,
            "trace_json": str(trace_path) if trace_path else None,
            "live_events_jsonl": str(live_events_path) if live_events_path else None,
        },
        "row_counts": {
            "primary_rows_for_pmid": len(primary_rows),
            "primary_rows_total": len(primary_rows_all),
            "metadata_rows_for_pmid": metadata_row_count,
        },
        "metrics": {
            "expected_gene_count": len(expected_symbols),
            "extracted_unique_gene_count": len(extracted_symbols),
            "matched_expected_count": len(matched),
            "focused_recall": round(len(matched) / len(expected_symbols), 4)
            if expected_symbols
            else None,
            "matched_expected_genes": matched,
            "missing_expected_genes": missing,
            "additional_non_fixture_genes": additional,
            "excluded_marker_genes_detected": excluded_detected,
            "context_check_failures": context_failures,
            "low_confidence_expected_genes": low_confidence,
            "fallback_detail_genes": fallback_detail_genes,
        },
        "failed_checks": failed_checks,
        "expected_gene_rows": expected_details,
        "candidate_audit": candidate_audit_summary,
        "trace": trace_summary,
        "review_notes": review_notes,
        "warnings": warnings,
        "status": status,
    }


def _format_list(values: list[str], *, max_items: int | None = None) -> str:
    if not values:
        return "None"
    shown = values if max_items is None else values[:max_items]
    rendered = ", ".join(shown)
    if max_items is not None and len(values) > max_items:
        rendered += f", ... (+{len(values) - max_items} more)"
    return rendered


def _md(value: Any) -> str:
    text = str(value or "")
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown_report(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    row_counts = result["row_counts"]
    artifacts = result["artifacts"]

    lines = [
        "# PIMS/MIS-C Gold Standard Comparison",
        "",
        f"- PMID: {result['pmid']}",
        f"- Status: {result['status']}",
        f"- Gold standard: `{result['gold_standard_path']}`",
        f"- Output directory: `{result['output_dir']}`",
        f"- Primary CSV: `{artifacts['primary_csv']}`",
        f"- Metadata CSV: `{artifacts['metadata_csv'] or 'not found'}`",
        f"- Candidate audit: `{artifacts['candidate_audit_json'] or 'not found'}`",
        f"- Trace JSON: `{artifacts['trace_json'] or 'not found'}`",
        f"- Live events JSONL: `{artifacts['live_events_jsonl'] or 'not found'}`",
        "",
        "## Focused Recovery",
        "",
        (
            f"- Expected genes recovered: {metrics['matched_expected_count']}/"
            f"{metrics['expected_gene_count']} "
            f"(focused recall {metrics['focused_recall']:.4f})"
        ),
        f"- Final rows for PMID: {row_counts['primary_rows_for_pmid']}",
        f"- Unique output genes: {metrics['extracted_unique_gene_count']}",
        f"- Matched expected genes: {_format_list(metrics['matched_expected_genes'])}",
        f"- Missing expected genes: {_format_list(metrics['missing_expected_genes'])}",
        (
            "- Additional non-fixture output genes: "
            f"{_format_list(metrics['additional_non_fixture_genes'], max_items=30)}"
        ),
        (
            "- Excluded mapped markers detected in output "
            "(review note, not acceptance failure): "
            f"{_format_list(metrics['excluded_marker_genes_detected'])}"
        ),
        (
            "- Context check failures: "
            f"{_format_list(metrics['context_check_failures'])}"
        ),
        (
            "- Low-confidence expected genes: "
            f"{_format_list([item['symbol'] for item in metrics['low_confidence_expected_genes']])}"
        ),
        (
            "- Fallback/skeleton detail genes: "
            f"{_format_list(metrics['fallback_detail_genes'])}"
        ),
    ]

    candidate_audit = result.get("candidate_audit")
    if candidate_audit:
        paper = candidate_audit.get("paper") or {}
        summary = candidate_audit.get("summary") or {}
        lines.extend(
            [
                "",
                "## Candidate Audit",
                "",
                f"- Run status: {candidate_audit.get('status')}",
                f"- Total candidates: {summary.get('total_candidates', 'n/a')}",
                f"- Total emitted rows: {summary.get('total_emitted_rows', 'n/a')}",
                f"- Paper candidate count: {paper.get('candidate_count', 'n/a')}",
                f"- Paper emitted rows: {paper.get('emitted_rows', 'n/a')}",
            ]
        )

    trace = result.get("trace")
    if trace:
        lines.extend(
            [
                "",
                "## Trace",
                "",
                f"- Node count: {trace.get('node_count', 'n/a')}",
                f"- Function events: {trace.get('function_event_count', 'n/a')}",
                f"- Function trace JSONL exists: {trace.get('function_trace_exists', False)}",
                f"- Missing required nodes: {_format_list(trace.get('missing_required_nodes') or [])}",
                f"- Stages: {_format_list(trace.get('stage_labels') or [], max_items=40)}",
            ]
        )

    lines.extend(
        [
            "",
            "## Expected Gene Details",
            "",
            (
                "| Symbol | Rows | Variants | Association groups | "
                "Grounding matches | Normalization rules | Context check |"
            ),
            "|---|---:|---|---|---|---|---|",
        ]
    )

    for detail in result["expected_gene_rows"]:
        context = detail.get("context_check")
        if context is None:
            context_text = "n/a"
        elif context["passed"]:
            context_text = "found " + _format_list(context["found"])
        else:
            context_text = "missing " + _format_list(context["tokens"])
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(detail["symbol"]),
                    str(detail["row_count"]),
                    _md(_format_list(detail["variants"], max_items=5)),
                    _md(_format_list(detail["association_groups"], max_items=5)),
                    _md(_format_list(detail["grounding_matches"], max_items=5)),
                    _md(_format_list(detail["normalization_rules"], max_items=5)),
                    _md(
                        f"{context_text}; max validation_confidence="
                        f"{detail['validation_confidence_max']}"
                    ),
                ]
            )
            + " |"
        )

    if result.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in result["warnings"])

    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare an existing ResearchShop output directory against the "
            "PIMS/MIS-C PMID 35177862 gold standard."
        )
    )
    parser.add_argument("output_dir_pos", nargs="?", help="Output directory to inspect")
    parser.add_argument(
        "--output-dir", dest="output_dir_opt", help="Output directory to inspect"
    )
    parser.add_argument(
        "--gold-standard",
        default=str(DEFAULT_GOLD_PATH),
        help=f"Gold-standard JSON path (default: {DEFAULT_GOLD_PATH})",
    )
    parser.add_argument(
        "--primary-csv",
        help="Specific primary final_enriched_results CSV to compare",
    )
    parser.add_argument(
        "--pmid",
        default=None,
        help=f"PMID to compare (default: value from gold JSON, usually {DEFAULT_PMID})",
    )
    parser.add_argument("--report", help="Optional Markdown report output path")
    parser.add_argument("--json", dest="json_out", help="Optional JSON summary output path")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help=(
            "Exit 0 when the only failed check is missing expected genes. "
            "Other acceptance failures still return nonzero."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output_dir = args.output_dir_opt or args.output_dir_pos
    if not output_dir:
        print("ERROR: provide an output directory", file=sys.stderr)
        return 2

    try:
        result = compare_output_directory(
            output_dir,
            gold_path=args.gold_standard,
            primary_csv=args.primary_csv,
            pmid=args.pmid,
        )
    except ComparisonError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    report = render_markdown_report(result)
    print(report, end="")

    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
        )

    failed_checks = dict(result.get("failed_checks") or {})
    if args.allow_missing:
        failed_checks["missing_expected_genes"] = []
    if any(failed_checks.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
