"""Offline tests for the PIMS/MIS-C gold-standard comparison helper."""

import csv
import json

from scripts.compare_pims_gold_standard import (
    DEFAULT_GOLD_PATH,
    REQUIRED_TRACE_NODES,
    compare_output_directory,
    expected_gene_symbols,
    load_json,
    main,
    render_markdown_report,
)


FIELDNAMES = [
    "PMID",
    "Gene",
    "Variant",
    "Key Finding",
    "Grounding Match",
    "Normalization Rule",
    "Association Group",
    "Association Type",
    "Confidence",
    "validation_confidence",
    "extraction_mode",
]


def _context_for_symbol(symbol):
    contexts = {
        "TRBV11-2": ("", "TRBV11-2"),
        "HLA-A": ("A*02", "HLA A*02"),
        "HLA-B": ("B*35", "HLA-B*35"),
        "HLA-C": ("C*04", "HLA-C*04"),
        "IFNG": ("", "IFN-gamma"),
        "MMP9": ("", "MMP-9"),
    }
    return contexts.get(symbol, ("", symbol))


def _row(symbol):
    variant, mention = _context_for_symbol(symbol)
    normalization = "cytokine_alias_ifng" if symbol == "IFNG" else ""
    if symbol == "MMP9":
        normalization = "protein_alias_mmp9"
    return {
        "PMID": "35177862",
        "Gene": symbol,
        "Variant": variant,
        "Key Finding": f"{mention} is reported in the MIS-C signature.",
        "Grounding Match": mention,
        "Normalization Rule": normalization,
        "Association Group": (
            "Primary Genetic Association"
            if symbol.startswith("HLA-")
            else "Biomarker/Response Signal"
        ),
        "Association Type": (
            "variant_association"
            if symbol.startswith("HLA-")
            else "biomarker_response_gene"
        ),
        "Confidence": "HIGH",
        "validation_confidence": "1.0",
        "extraction_mode": "llm",
    }


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _write_required_artifacts(tmp_path, row_count):
    (tmp_path / "candidate_audit_abc123.json").write_text(
        json.dumps(
            {
                "schema_version": "candidate_audit_v1",
                "status": "completed",
                "summary": {
                    "total_candidates": 20,
                    "total_emitted_rows": row_count,
                },
                "papers": [
                    {
                        "pmid": "35177862",
                        "status": "ok",
                        "candidate_count": 20,
                        "emitted_rows": row_count,
                        "final_association_group_counts": {
                            "Biomarker/Response Signal": 13,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "trace_35177862.json").write_text(
        json.dumps(
            {
                "pmid": "35177862",
                "node_count": len(REQUIRED_TRACE_NODES),
                "nodes": {node: {} for node in REQUIRED_TRACE_NODES},
                "function_event_count": 7,
                "function_trace_path": str(tmp_path / "trace_35177862_functions.jsonl"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "trace_35177862_functions.jsonl").write_text(
        '{"event":"fn_call"}\n', encoding="utf-8"
    )
    (tmp_path / "live_events.jsonl").write_text(
        '{"event":"stage"}\n', encoding="utf-8"
    )


def test_compare_pims_gold_standard_reports_focused_recovery_and_artifacts(tmp_path):
    gold = load_json(DEFAULT_GOLD_PATH)
    rows = [_row(symbol) for symbol in expected_gene_symbols(gold)]
    rows.append(_row("BCR"))

    primary = tmp_path / "final_enriched_results_abc123.csv"
    metadata = tmp_path / "final_enriched_results_abc123_metadata.csv"
    _write_csv(primary, rows)
    _write_csv(metadata, rows)

    (tmp_path / "candidate_audit_abc123.json").write_text(
        json.dumps(
            {
                "schema_version": "candidate_audit_v1",
                "status": "completed",
                "summary": {
                    "total_candidates": 20,
                    "total_emitted_rows": len(rows),
                },
                "papers": [
                    {
                        "pmid": "35177862",
                        "status": "ok",
                        "candidate_count": 20,
                        "emitted_rows": len(rows),
                        "final_association_group_counts": {
                            "Biomarker/Response Signal": 13,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "trace_35177862.json").write_text(
        json.dumps(
            {
                "pmid": "35177862",
                "node_count": len(REQUIRED_TRACE_NODES),
                "nodes": {node: {} for node in REQUIRED_TRACE_NODES},
                "function_event_count": 7,
                "function_trace_path": str(tmp_path / "trace_35177862_functions.jsonl"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "trace_35177862_functions.jsonl").write_text(
        '{"event":"fn_call"}\n', encoding="utf-8"
    )
    (tmp_path / "live_events.jsonl").write_text(
        '{"event":"stage"}\n', encoding="utf-8"
    )

    result = compare_output_directory(tmp_path)

    assert result["status"] == "pass"
    assert result["metrics"]["matched_expected_count"] == 16
    assert result["metrics"]["focused_recall"] == 1.0
    assert result["metrics"]["missing_expected_genes"] == []
    assert result["metrics"]["low_confidence_expected_genes"] == []
    assert result["metrics"]["fallback_detail_genes"] == []
    assert result["metrics"]["excluded_marker_genes_detected"] == []
    assert result["metrics"]["context_check_failures"] == []
    assert result["row_counts"]["primary_rows_for_pmid"] == len(rows)
    assert result["row_counts"]["metadata_rows_for_pmid"] == len(rows)
    assert result["candidate_audit"]["paper"]["emitted_rows"] == len(rows)
    assert result["trace"]["missing_required_nodes"] == []
    assert result["trace"]["function_trace_exists"] is True
    assert result["failed_checks"]["missing_live_events"] is False
    assert result["failed_checks"]["missing_function_jsonl"] is False

    report = render_markdown_report(result)
    assert "Expected genes recovered: 16/16" in report
    assert "Additional non-fixture output genes: BCR" in report


def test_compare_pims_gold_standard_fails_when_excluded_marker_is_detected(tmp_path):
    gold = load_json(DEFAULT_GOLD_PATH)
    rows = [_row(symbol) for symbol in expected_gene_symbols(gold)]
    rows.append(_row("CRP"))

    primary = tmp_path / "final_enriched_results_abc123.csv"
    metadata = tmp_path / "final_enriched_results_abc123_metadata.csv"
    _write_csv(primary, rows)
    _write_csv(metadata, rows)
    _write_required_artifacts(tmp_path, len(rows))

    result = compare_output_directory(tmp_path)

    assert result["status"] == "failed_acceptance_checks"
    assert result["metrics"]["excluded_marker_genes_detected"] == ["CRP"]
    assert result["failed_checks"]["excluded_marker_genes_detected"] == ["CRP"]


def test_compare_pims_gold_standard_cli_exits_nonzero_for_missing_expected(tmp_path):
    rows = [_row("TRBV11-2")]
    _write_csv(tmp_path / "final_enriched_results_missing.csv", rows)
    _write_csv(tmp_path / "final_enriched_results_missing_metadata.csv", rows)
    _write_required_artifacts(tmp_path, len(rows))

    assert main(["--output-dir", str(tmp_path), "--allow-missing"]) == 0
    assert main(["--output-dir", str(tmp_path)]) == 1
