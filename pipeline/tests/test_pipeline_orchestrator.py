"""
Tests for pipeline_orchestrator

Smoke test: imports succeed without errors.
Unit tests use explicit local pipeline fixtures instead of runtime patching.

These tests do NOT call the Gemini API or any external service.
"""

from types import SimpleNamespace

import pandas as pd
import pytest


class DataFramePipelineFixture:
    _paper_api_calls = 0

    def __init__(self, *_args, dataframe=None, **_kwargs):
        self.dataframe = dataframe if dataframe is not None else pd.DataFrame()

    def run_pipeline(self, _cols):
        return self.dataframe

    def _collect_debug_artifact(self):
        return {}


class FailingPipelineFixture:
    def __init__(self, *_args, **_kwargs):
        raise RuntimeError("Fixture pipeline failure")


def test_orchestrator_module_imports():
    """Pipeline orchestrator imports without errors (no API keys or env required)."""
    from modules.pipeline_orchestrator import _run_pipeline_worker, run_complete_pipeline  # noqa: F401


def test_pipeline_run_state_exposes_run_data_carrier():
    from modules.pipeline_state import PipelineRunState

    state = PipelineRunState(
        query="BRCA1",
        specific_pmids=["34876594"],
        specific_authors=[],
        user_columns={"Key Finding": "main finding"},
        top_n_cited=1,
    )

    assert state.query == "BRCA1"
    assert state.specific_pmids == ["34876594"]
    assert state.pipeline_stats["papers_found"] == 0
    assert state.paper_debug_artifacts == []
    assert state.all_results_df.empty


def test_run_complete_pipeline_rejects_too_small_gemini_budget(monkeypatch):
    from modules import config
    from modules.pipeline_orchestrator import run_complete_pipeline

    monkeypatch.setattr(config, "GEMINI_MAX_CALLS_PER_PAPER", 1)

    with pytest.raises(ValueError) as excinfo:
        run_complete_pipeline(
            query="",
            specific_pmids=["34876594"],
            specific_authors=[],
            user_columns={"Key Finding": "main finding"},
            top_n_cited=1,
        )

    message = str(excinfo.value)
    assert "GEMINI_MAX_CALLS_PER_PAPER=1" in message
    assert "at least 2 Gemini calls" in message


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
    per-paper extraction succeeds.
    """
    fixture_df = pd.DataFrame([
        {"Gene/Group": "BRCA1", "Variant Name": "p.Glu1915Ter", "PMID": "34876594"},
    ])

    def pipeline_factory(*args, **kwargs):
        return DataFramePipelineFixture(*args, dataframe=fixture_df, **kwargs)

    from modules.pipeline_orchestrator import _run_pipeline_worker
    result = _run_pipeline_worker(
        text=sample_paper_text,
        cols={"Mechanism": "Describe the molecular mechanism"},
        pipeline_factory=pipeline_factory,
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
    fixture_df = pd.DataFrame(
        [["BRCA1", "duplicate", "34876594"]],
        columns=["Gene/Group", "Gene/Group", "PMID"],
    )

    def pipeline_factory(*args, **kwargs):
        return DataFramePipelineFixture(*args, dataframe=fixture_df, **kwargs)

    from modules.pipeline_orchestrator import _run_pipeline_worker
    result = _run_pipeline_worker(
        text=sample_paper_text,
        cols={"Mechanism": "Describe the molecular mechanism"},
        pipeline_factory=pipeline_factory,
    )

    assert "records" in result
    assert result["records"][0]["Gene/Group"] == "BRCA1"
    assert result["records"][0]["Gene/Group (2)"] == "duplicate"


def test_run_pipeline_worker_returns_error_on_exception(sample_paper_text):
    """
    _run_pipeline_worker should return {"error": "..."} rather than raising
    when the per-paper extraction coordinator raises an exception.
    """
    from modules.pipeline_orchestrator import _run_pipeline_worker
    result = _run_pipeline_worker(
        text=sample_paper_text,
        cols={"Mechanism": "Describe the molecular mechanism"},
        pipeline_factory=FailingPipelineFixture,
    )

    assert "error" in result, f"Expected 'error' key on failure, got: {list(result.keys())}"
    assert "Fixture pipeline failure" in result["error"]


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


def test_write_split_output_adds_and_sorts_association_groups(tmp_path):
    from modules.pipeline_orchestrator import _write_split_output

    df = pd.DataFrame(
        [
            {
                "Gene/Group": "MAPK1",
                "Variant Name": "",
                "PMID": "2",
                "Association Type": "mechanistic_pathway_gene",
                "Key Finding": "MAPK1 pathway signal.",
                "validation_confidence": 0.9,
            },
            {
                "Gene/Group": "CASP3",
                "Variant Name": "",
                "PMID": "3",
                "Association Type": "animal_model_gene",
                "Key Finding": "CASP3 knockout mouse model signal.",
                "validation_confidence": 0.9,
            },
            {
                "Gene/Group": "BRCA1",
                "Variant Name": "p.Glu1915Ter",
                "PMID": "1",
                "Association Type": "variant_association",
                "Key Finding": "BRCA1 susceptibility variant.",
                "validation_confidence": 0.9,
            },
        ]
    )

    primary_path, _, _, _ = _write_split_output(
        df=df,
        output_path=tmp_path / "grouped.csv",
        user_cols=["Key Finding"],
    )

    out = pd.read_csv(primary_path)
    assert "Association Group" in out.columns
    assert out.loc[0, "Gene"] == "BRCA1"
    assert out.loc[0, "Association Group"] == "Primary Genetic Association"
    assert out.loc[1, "Association Group"] == "Mechanistic/Pathway Signal"
    assert out.loc[2, "Association Group"] == "Animal Model Signal"


def test_candidate_audit_rows_by_pmid_uses_emitted_row_groups():
    from modules.pipeline_orchestrator import _candidate_audit_rows_by_pmid

    df = pd.DataFrame(
        [
            {
                "PMID": "1",
                "Gene/Group": "",
                "Variant Name": "",
                "Association Type": "",
                "Association Group": "Review Needed",
            },
            {
                "PMID": "1",
                "Gene/Group": "CASP3",
                "Variant Name": "",
                "Association Type": "animal_model_gene",
                "Association Group": "Animal Model Signal",
            },
            {
                "PMID": "1",
                "Gene/Group": "ITPKC",
                "Variant Name": "",
                "Association Type": "susceptibility_gene",
                "Association Group": "Primary Genetic Association",
            },
        ]
    )

    summary = _candidate_audit_rows_by_pmid(df)

    assert summary["1"]["emitted_rows"] == 3
    assert len(summary["1"]["final_associations"]) == 2
    assert summary["1"]["final_association_group_counts"] == {
        "Animal Model Signal": 1,
        "Primary Genetic Association": 1,
    }


def test_candidate_audit_summary_uses_final_row_groups():
    from modules.pipeline_orchestrator import _candidate_audit_summary

    summary = _candidate_audit_summary(
        [
            {
                "candidate_count": 4,
                "emitted_rows": 2,
                "candidates": [
                    {"association_group": "Other Candidate Signal"},
                    {"association_group": "Review Needed"},
                ],
                "final_associations": [
                    {"association_group": "Primary Genetic Association"},
                    {"association_group": "Animal Model Signal"},
                ],
            }
        ]
    )

    assert summary["total_candidates"] == 4
    assert summary["total_emitted_rows"] == 2
    assert summary["association_group_counts"] == {
        "Primary Genetic Association": 1,
        "Animal Model Signal": 1,
    }
    assert summary["final_association_group_counts"] == summary["association_group_counts"]
    assert summary["candidate_association_group_counts"] == {
        "Other Candidate Signal": 1,
        "Review Needed": 1,
    }


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


def test_pubtator_row_enrichment_uses_per_paper_symbol_lookup():
    from modules.pipeline_orchestrator import _apply_pubtator_row_enrichment

    df = pd.DataFrame({"Gene/Group": ["BRCA1", "TP53", "brca1"]})
    hybrid = SimpleNamespace(
        pubtator_genes=[
            SimpleNamespace(symbol="BRCA1", ncbi_gene_id="672"),
            SimpleNamespace(symbol="TP53", ncbi_gene_id="7157"),
        ],
        llm_genes=[],
    )

    enriched = _apply_pubtator_row_enrichment(df, "123", {"123": hybrid})

    assert enriched["Gene Source"].tolist() == ["both", "both", "both"]
    assert enriched["NCBI Gene ID"].tolist() == ["672", "7157", "672"]
    assert hybrid.llm_genes == ["BRCA1", "TP53"]


def test_ncbi_metadata_columns_fill_missing_ids_once():
    from modules.pipeline_orchestrator import _apply_ncbi_metadata_columns

    df = pd.DataFrame({
        "Gene/Group": ["BRCA1", "TP53"],
        "NCBI Gene ID": ["", "existing"],
    })
    metadata = {
        "brca1": SimpleNamespace(
            full_name="BRCA1 DNA repair associated",
            aliases=["RNF53", "FANCS", "BRCC1", "extra"],
            chromosome="17",
            gene_id="672",
        ),
        "TP53": SimpleNamespace(
            full_name="tumor protein p53",
            aliases=[],
            chromosome="17",
            gene_id="7157",
        ),
    }

    enriched = _apply_ncbi_metadata_columns(df, metadata)

    assert enriched.loc[0, "Gene Full Name"] == "BRCA1 DNA repair associated"
    assert enriched.loc[0, "Gene Aliases"] == "RNF53, FANCS, BRCC1"
    assert enriched.loc[0, "NCBI Gene ID"] == "672"
    assert enriched.loc[1, "NCBI Gene ID"] == "existing"


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
