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


# ---------------------------------------------------------------------------
# Confidence flag tests
# ---------------------------------------------------------------------------

def test_confidence_high():
    """HIGH: gene in both NER+LLM sources with a verified citation."""
    from modules.pipeline_orchestrator import _compute_row_confidence

    row = {
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
        "validation_confidence": 1.0,
        "Gene Source": "both",
        "Candidate Source": "deterministic_lexicon,pubtator",
        "context_modifications": "No modifications needed",
        "Key Finding Citation": "BRCA1 mutations found.",
        "Key Finding_citation_valid": False,
    }
    level, note = _compute_row_confidence(row, ["Key Finding"])
    assert level == "REVIEW"
    assert note == "Citation mismatch"


def test_confidence_low_abstract_only():
    """LOW: no full text available (abstract-only paper)."""
    from modules.pipeline_orchestrator import _compute_row_confidence

    row = {
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
        "validation_confidence": 1.0,
        "Gene Source": "llm",
        "Candidate Source": "llm_figure",
        "context_modifications": "No modifications needed",
    }
    level, note = _compute_row_confidence(row, [])
    assert level == "REVIEW"
    assert note == "Figure-only"
