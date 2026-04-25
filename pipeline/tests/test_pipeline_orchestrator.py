"""
Tests for pipeline_orchestrator

Smoke test: imports succeed without errors.
Unit test: _run_pipeline_worker returns expected structure when GeneInfoPipeline is mocked.

These tests do NOT call the Gemini API or any external service.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def test_orchestrator_module_imports():
    """Pipeline orchestrator imports without errors (no API keys or env required)."""
    from modules.pipeline_orchestrator import _run_pipeline_worker, run_complete_pipeline  # noqa: F401


def test_sanitize_user_columns_removes_reserved_names():
    """_sanitize_user_columns should rename columns that collide with core fields."""
    from modules.pipeline_orchestrator import _sanitize_user_columns

    cols = {
        "Gene/Group": "This collides with a core column",
        "Mechanism": "Novel mechanism description",
        "PMID": "Also reserved",
    }
    result = _sanitize_user_columns(cols)

    # Reserved names should be renamed
    assert "Gene/Group" not in result
    assert "PMID" not in result
    # Non-reserved should pass through unchanged
    assert "Mechanism" in result


def test_sanitize_user_columns_empty_input():
    from modules.pipeline_orchestrator import _sanitize_user_columns

    assert _sanitize_user_columns({}) == {}
    assert _sanitize_user_columns(None) == {}


def test_run_pipeline_worker_returns_records_on_success(sample_paper_text):
    """
    _run_pipeline_worker should return {"records": [...], "debug": ...} when
    GeneInfoPipeline succeeds. The real Gemini extractor is mocked.
    """
    mock_df = pd.DataFrame([
        {"Gene/Group": "BRCA1", "Variant Name": "p.Glu1915Ter", "PMID": "34876594"},
    ])

    mock_pipeline = MagicMock()
    mock_pipeline.return_value.run_pipeline.return_value = mock_df
    mock_pipeline.return_value._collect_debug_artifact.return_value = {}

    with patch("modules.pipeline_orchestrator.GeneInfoPipeline", mock_pipeline):
        from modules.pipeline_orchestrator import _run_pipeline_worker
        result = _run_pipeline_worker(
            text=sample_paper_text,
            cols={"Mechanism": "Describe the molecular mechanism"},
        )

    assert "records" in result, f"Expected 'records' key, got: {list(result.keys())}"
    assert isinstance(result["records"], list)
    assert len(result["records"]) == 1
    assert result["records"][0]["Gene/Group"] == "BRCA1"


def test_run_pipeline_worker_deduplicates_columns_before_records(sample_paper_text):
    """
    Pandas raises when to_dict(orient="records") is called with duplicate
    columns. The worker should normalize columns before returning records.
    """
    mock_df = pd.DataFrame(
        [["BRCA1", "duplicate", "34876594"]],
        columns=["Gene/Group", "Gene/Group", "PMID"],
    )

    mock_pipeline = MagicMock()
    mock_pipeline.return_value.run_pipeline.return_value = mock_df
    mock_pipeline.return_value._collect_debug_artifact.return_value = {}

    with patch("modules.pipeline_orchestrator.GeneInfoPipeline", mock_pipeline):
        from modules.pipeline_orchestrator import _run_pipeline_worker
        result = _run_pipeline_worker(
            text=sample_paper_text,
            cols={"Mechanism": "Describe the molecular mechanism"},
        )

    assert "records" in result
    assert result["records"][0]["Gene/Group"] == "BRCA1"
    assert result["records"][0]["Gene/Group (2)"] == "duplicate"


def test_run_pipeline_worker_returns_error_on_exception(sample_paper_text):
    """
    _run_pipeline_worker should return {"error": "..."} rather than raising
    when GeneInfoPipeline raises an exception.
    """
    mock_pipeline = MagicMock()
    mock_pipeline.side_effect = RuntimeError("Simulated Gemini failure")

    with patch("modules.pipeline_orchestrator.GeneInfoPipeline", mock_pipeline):
        from modules.pipeline_orchestrator import _run_pipeline_worker
        result = _run_pipeline_worker(
            text=sample_paper_text,
            cols={"Mechanism": "Describe the molecular mechanism"},
        )

    assert "error" in result, f"Expected 'error' key on failure, got: {list(result.keys())}"
    assert "Simulated Gemini failure" in result["error"]


def test_write_split_output_deduplicates_columns_before_json(tmp_path):
    """Final CSV/JSON export should not crash when upstream columns collide."""
    from modules.pipeline_orchestrator import _write_split_output

    df = pd.DataFrame(
        [[
            "BRCA1",
            "",
            "34876594",
            "BRCA1 is associated with risk.",
            "duplicate detail",
            "BRCA1 is associated with risk.",
            True,
            1.0,
            "both",
            "pubtator,llm_text",
            "",
        ]],
        columns=[
            "Gene/Group",
            "Variant Name",
            "PMID",
            "Key Finding",
            "Key Finding",
            "Key Finding Citation",
            "Key Finding_citation_valid",
            "validation_confidence",
            "Gene Source",
            "Candidate Source",
            "context_modifications",
        ],
    )

    primary_path, metadata_path, excel_path, json_path = _write_split_output(
        df=df,
        output_path=tmp_path / "results.csv",
        user_cols=["Key Finding"],
    )

    assert pd.read_csv(primary_path).columns.is_unique
    assert pd.read_csv(metadata_path).columns.is_unique
    assert (tmp_path / "results.json").exists()
    assert json_path.endswith("results.json")
    assert excel_path.endswith("results.xlsx")


def test_finalize_result_marks_quota_limited_rows():
    """Quota-limited skeleton rows should be counted and logged as incomplete."""
    from modules.pipeline_orchestrator import _finalize_paper_result

    logs = []
    stats = {
        "gemini_api_calls": 0,
        "strict_gate_drops": [],
        "strict_gate_drops_count": 0,
        "quota_limited_papers": 0,
        "quota_limited_rows": 0,
    }
    payload = {
        "records": [
            {
                "gene_name": "BRCA1",
                "variant_name": "",
                "extraction_mode": "skeleton",
                "detail_extraction_error": "429 RESOURCE_EXHAUSTED. quota exceeded",
            }
        ],
        "debug": {
            "status": "ok",
            "detail_extraction_status": "quota_limited_fallback",
            "detail_extraction_error": "429 RESOURCE_EXHAUSTED. quota exceeded",
            "quota_limited": True,
        },
        "gemini_api_calls": 1,
    }

    paper_df, debug = _finalize_paper_result(
        payload=payload,
        pmid="34876594",
        base_info={"title": "Example", "authors": [], "year": "2024", "journal": "Journal"},
        citation_records={},
        figure_inputs=[],
        pubtator_results={},
        pipeline_stats=stats,
        emit_log=lambda level, msg, detail=None: logs.append((level, msg, detail)),
    )

    assert len(paper_df) == 1
    assert debug["quota_limited"] is True
    assert stats["quota_limited_papers"] == 1
    assert stats["quota_limited_rows"] == 1
    assert any(level == "warn" and "quota" in msg for level, msg, _ in logs)


# ---------------------------------------------------------------------------
# Confidence flag tests
# ---------------------------------------------------------------------------

def test_confidence_high():
    """HIGH: gene in both NER+LLM sources with a verified citation."""
    from modules.pipeline_orchestrator import _compute_row_confidence

    row = {
        "Gene/Group": "BRCA1",
        "validation_confidence": 1.0,
        "Gene Source": "both",
        "Candidate Source": "deterministic_lexicon,pubtator",
        "context_modifications": "No modifications needed",
        "Key Finding Citation": "BRCA1 mutations were found in 40% of samples.",
        "Key Finding_citation_valid": True,
    }
    level, note = _compute_row_confidence(row, ["Key Finding"])
    assert level == "HIGH"
    assert note == ""


def test_confidence_review_citation_mismatch():
    """REVIEW: citation marked invalid with no valid counterpart."""
    from modules.pipeline_orchestrator import _compute_row_confidence

    row = {
        "Gene/Group": "BRCA1",
        "validation_confidence": 1.0,
        "Gene Source": "both",
        "Candidate Source": "deterministic_lexicon,pubtator",
        "context_modifications": "No modifications needed",
        "Key Finding Citation": "BRCA1 mutations found.",
        "Key Finding_citation_valid": False,
    }
    level, note = _compute_row_confidence(row, ["Key Finding"])
    assert level == "REVIEW"
    assert note == "Citation text not found in paper"


def test_confidence_low_abstract_only():
    """LOW: no full text available (abstract-only paper)."""
    from modules.pipeline_orchestrator import _compute_row_confidence

    row = {
        "Gene/Group": "BRCA1",
        "validation_confidence": 1.0,
        "Gene Source": "both",
        "Candidate Source": "pubtator",
        "context_modifications": "method=no_oa_full_text",
    }
    level, note = _compute_row_confidence(row, [])
    assert level == "LOW"
    assert note == "Abstract only"


def test_confidence_review_figure_only():
    """REVIEW: gene sourced exclusively from figure analysis (no prose corroboration)."""
    from modules.pipeline_orchestrator import _compute_row_confidence

    row = {
        "Gene/Group": "BRCA1",
        "validation_confidence": 1.0,
        "Gene Source": "llm",
        "Candidate Source": "llm_figure",
        "context_modifications": "No modifications needed",
    }
    level, note = _compute_row_confidence(row, [])
    assert level == "REVIEW"
    assert note == "Figure-only gene — no prose citation available"
