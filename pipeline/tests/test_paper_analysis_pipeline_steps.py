"""
Offline tests for the per-paper analysis step contract.

These tests inject local fixture behavior for Gemini-facing methods. They verify orchestration
behavior without calling Gemini, PubTator, NCBI, or any network service.
"""

import sys
from pathlib import Path

import pytest


_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))


class OfflineGeminiClient:
    pass


def _make_pipeline(
    paper_text: str = "IL6 and TP53 were measured in the full text.",
    *,
    abstract_text: str = "",
    pubtator_genes=None,
):
    from modules.paper_analysis.pipeline import PaperAnalysisPipeline

    return PaperAnalysisPipeline(
        paper_text=paper_text,
        abstract_text=abstract_text,
        pubtator_genes=pubtator_genes or [],
        figure_inputs=[],
        client=OfflineGeminiClient(),
    )


@pytest.fixture
def paper_analysis_config(monkeypatch):
    from modules import config

    monkeypatch.setattr(config, "GEMINI_MAX_CALLS_PER_PAPER", 3)
    monkeypatch.setattr(config, "ENABLE_ABSTRACT_GENE_DISCOVERY", False)
    monkeypatch.setattr(config, "ENABLE_LLM_GENE_DISCOVERY", False)
    monkeypatch.setattr(config, "ENABLE_SECOND_GENE_DISCOVERY_PASS", False)
    monkeypatch.setattr(config, "ENABLE_FIGURE_ANALYSIS", False)
    return config


def test_paper_analysis_step_table_order_and_required_flags():
    from modules.paper_analysis.pipeline import PAPER_ANALYSIS_STEPS

    keys = [step.key for step in PAPER_ANALYSIS_STEPS]
    assert keys == [
        "context_validation",
        "abstract_gemini_candidate_discovery",
        "fulltext_gemini_candidate_discovery",
        "deterministic_hgnc_scan",
        "figure_gemini_candidate_discovery",
        "pubtator_merge",
        "grounding_check",
        "hgnc_validation",
        "detail_extraction",
        "post_validation",
    ]

    required_by_key = {step.key: step.required for step in PAPER_ANALYSIS_STEPS}
    assert required_by_key["abstract_gemini_candidate_discovery"] is False
    assert required_by_key["fulltext_gemini_candidate_discovery"] is True
    assert required_by_key["deterministic_hgnc_scan"] is True
    assert required_by_key["figure_gemini_candidate_discovery"] is False
    assert required_by_key["detail_extraction"] is True

    fulltext_state = next(
        step.state for step in PAPER_ANALYSIS_STEPS
        if step.key == "fulltext_gemini_candidate_discovery"
    )
    assert "Mandatory full-text Gemini discovery" in fulltext_state
    assert "valid empty" in fulltext_state
    assert "fail" in fulltext_state


def test_mandatory_fulltext_discovery_runs_when_legacy_flag_disabled(
    monkeypatch,
    paper_analysis_config,
):
    pipeline = _make_pipeline()
    calls = []

    def recording_extract_gene_names(temperature=None, *, optional=True):
        calls.append({"temperature": temperature, "optional": optional})
        pipeline._ingest_associations([{"gene": "IL6", "variant": ""}], "llm_text")
        return pipeline.associations

    monkeypatch.setattr(pipeline, "extract_gene_names", recording_extract_gene_names)
    monkeypatch.setattr(pipeline, "extract_deterministic_candidates", lambda: [])

    pipeline._run_candidate_discovery()

    assert calls == [{"temperature": None, "optional": False}]
    key = pipeline._assoc_key("IL6", "")
    assert "llm_text" in pipeline.candidate_meta[key]["sources"]
    assert pipeline.candidate_discovery_status == "complete"


def test_call_budget_below_two_fails_before_analysis(monkeypatch, paper_analysis_config):
    paper_analysis_config.GEMINI_MAX_CALLS_PER_PAPER = 1
    pipeline = _make_pipeline()

    def fail_if_called():
        pytest.fail("context validation should not run when Gemini budget is invalid")

    monkeypatch.setattr(pipeline, "_validate_and_prepare_paper_text", fail_if_called)

    with pytest.raises(ValueError) as excinfo:
        pipeline.run_pipeline({"Key Finding": "primary finding"})

    message = str(excinfo.value)
    assert "GEMINI_MAX_CALLS_PER_PAPER=1" in message
    assert "at least 2 Gemini calls" in message
    assert "candidate discovery + detail extraction" in message


def test_empty_mandatory_discovery_continues_with_deterministic_and_pubtator(
    monkeypatch,
    paper_analysis_config,
):
    pipeline = _make_pipeline(pubtator_genes=["TP53"])
    calls = []

    def empty_extract_gene_names(temperature=None, *, optional=True):
        calls.append({"temperature": temperature, "optional": optional})
        return []

    monkeypatch.setattr(pipeline, "extract_gene_names", empty_extract_gene_names)
    monkeypatch.setattr(
        pipeline,
        "extract_deterministic_candidates",
        lambda: [{"gene": "IL6", "variant": ""}],
    )

    pipeline._run_candidate_discovery()

    assert calls == [{"temperature": None, "optional": False}]
    il6_key = pipeline._assoc_key("IL6", "")
    tp53_key = pipeline._assoc_key("TP53", "")
    assert pipeline.candidate_meta[il6_key]["sources"] == {"deterministic_lexicon"}
    assert pipeline.candidate_meta[tp53_key]["sources"] == {"pubtator"}
    assert {assoc["gene"] for assoc in pipeline.associations} == {"IL6", "TP53"}


def test_mandatory_discovery_failure_surfaces(monkeypatch, paper_analysis_config):
    pipeline = _make_pipeline()

    def failing_extract_gene_names(temperature=None, *, optional=True):
        assert optional is False
        raise RuntimeError("Gemini transport failed")

    monkeypatch.setattr(pipeline, "extract_gene_names", failing_extract_gene_names)
    monkeypatch.setattr(pipeline, "extract_deterministic_candidates", lambda: [])

    with pytest.raises(RuntimeError) as excinfo:
        pipeline._run_candidate_discovery()

    message = str(excinfo.value)
    assert "Mandatory full-text Gemini candidate discovery failed" in message
    assert "Gemini transport failed" in message
    assert pipeline.candidate_discovery_status == "failed_mandatory_fulltext_gemini"
    assert pipeline.candidate_discovery_error == "Gemini transport failed"
