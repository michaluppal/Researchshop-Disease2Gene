import csv
import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = (
    REPO_ROOT
    / "studies"
    / "gemini_time_of_day"
    / "analyze_numeric_preservation.py"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_metadata(path: Path):
    rows = [
        {
            "PMID": "111",
            "Gene/Group": "BRCA1",
            "Variant Name": "",
            "Key Finding Citation": "BRCA1 was observed in 45 patients.",
            "Key Finding Citation_citation_valid": "True",
            "Key Finding Citation_citation_details": "Match found and constraints verified",
            "Key Finding Citation_numeric_tokens_in_citation": "45",
            "Evidence Context Citation": "BRCA1 was observed in 1.3 patients.",
            "Evidence Context Citation_citation_valid": "False",
            "Evidence Context Citation_citation_details": "Numerical mismatch: '1.3' not found in matching paragraph",
            "Evidence Context Citation_numeric_tokens_in_citation": "1.3",
        },
        {
            "PMID": "222",
            "Gene/Group": "TP53",
            "Variant Name": "",
            "Key Finding Citation": "TP53 was observed in 23% of samples.",
            "Key Finding Citation_citation_valid": "True",
            "Key Finding Citation_citation_details": "Match found and constraints verified",
            "Key Finding Citation_numeric_tokens_in_citation": "23",
            "Evidence Context Citation": "",
            "Evidence Context Citation_citation_valid": "False",
            "Evidence Context Citation_citation_details": "No citation provided",
            "Evidence Context Citation_numeric_tokens_in_citation": "",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_numeric_preservation_analyzer_classifies_metadata_and_drop_events(tmp_path):
    analyzer = _load_module(ANALYZER_PATH, "numeric_preservation_analyzer")
    run_dir = tmp_path / "hour00"
    run_dir.mkdir()
    (run_dir / "study_run.json").write_text(
        json.dumps(
            {
                "run_id": "hour00",
                "time_block": "night",
                "batch": {"completed_papers": 1, "total_papers": 1, "output_rows": 2},
                "per_paper": [{"pmid": "111", "citation_gate_drops": 1}],
            }
        ),
        encoding="utf-8",
    )
    _write_metadata(run_dir / "final_enriched_results_test_metadata.csv")
    (run_dir / "drop_debug_test.json").write_text(
        json.dumps(
            {
                "paper_debug": [
                    {
                        "pmid": "111",
                        "evidence_gate_drops": [
                            {
                                "gene": "BRCA2",
                                "variant": "",
                                "reason": "ungrounded_citation",
                                "invalid_fields": [
                                    {
                                        "field": "Statistical Evidence Citation",
                                        "detail": "Numerical mismatch: '2.7' not found in matching paragraph",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    events, run_rows, totals = analyzer.collect(tmp_path)
    summary = {
        row["metric"]: row["value"]
        for row in analyzer.summary_rows(events, run_rows, totals)
    }

    assert len(events) == 2
    assert {event["row_outcome"] for event in events} == {
        "retained_with_another_valid_citation",
        "citation_gate_drop",
    }
    assert summary["Numeric mismatch events"] == 2
    assert summary["Rows excluded from primary export"] == 1
    assert summary["Rows removed only after numeric mismatch"] == 1
