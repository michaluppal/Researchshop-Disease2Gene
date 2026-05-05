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


def test_normalized_content_records_seed_candidates(monkeypatch, paper_analysis_config):
    paper_text = "MMP-9 was elevated as a matrisome-related inflammatory marker in MIS-C."
    pipeline = _make_pipeline(paper_text=paper_text)

    monkeypatch.setattr(pipeline, "extract_gene_names", lambda temperature=None, *, optional=True: [])
    monkeypatch.setattr(pipeline, "extract_deterministic_candidates", lambda: [])

    pipeline._run_candidate_discovery()

    key = pipeline._assoc_key("MMP9", "")
    meta = pipeline.candidate_meta[key]
    assert "normalized_text_index" in meta["sources"]
    assert meta["original_mentions"] == ["MMP-9"]
    assert meta["evidence_sentence"] == paper_text


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


def test_hla_detail_rows_reconcile_to_single_validated_allele_variant():
    pipeline = _make_pipeline()
    key = pipeline._assoc_key("HLA-B", "HLA-B*35")
    pipeline.candidate_meta[key] = {
        "gene": "HLA-B",
        "variant": "HLA-B*35",
        "sources": {"llm_text"},
        "validation_outcome": "passed",
        "raw_gene_labels": {"HLA-B", "B*35"},
    }
    rows = [{"gene_name": "HLA-B", "variant_name": "", "Key Finding": "HLA-B signal"}]

    pipeline._reconcile_hla_detail_rows_to_candidates(rows)

    assert rows[0]["variant_name"] == "HLA-B*35"
    assert rows[0]["Candidate Reconciliation"] == "single_validated_hla_allele_variant"


def test_hla_shorthand_and_gene_scoped_detail_rows_merge():
    pipeline = _make_pipeline()
    rows = [
        {"gene_name": "HLA-C", "variant_name": "C*04", "Key Finding": "first"},
        {"gene_name": "HLA-C", "variant_name": "HLA-C*04", "Statistical Evidence": "second"},
    ]

    merged = pipeline._merge_duplicate_gene_rows(
        rows,
        {
            "Key Finding": "finding",
            "Statistical Evidence": "stats",
        },
    )

    assert len(merged) == 1
    assert merged[0]["variant_name"] == "HLA-C*04"
    assert merged[0]["Key Finding"] == "first"
    assert merged[0]["Statistical Evidence"] == "second"


def test_duplicate_merge_preserves_hla_reconciliation_marker():
    pipeline = _make_pipeline()
    rows = [
        {"gene_name": "HLA-B", "variant_name": "HLA-B*35", "Key Finding": "first"},
        {
            "gene_name": "HLA-B",
            "variant_name": "B*35",
            "Candidate Reconciliation": "single_validated_hla_allele_variant",
        },
    ]

    merged = pipeline._merge_duplicate_gene_rows(rows, {"Key Finding": "finding"})

    assert len(merged) == 1
    assert merged[0]["Candidate Reconciliation"] == "single_validated_hla_allele_variant"


def test_gemini_json_parser_accepts_fenced_json():
    pipeline = _make_pipeline()

    parsed = pipeline._parse_json_response('```json\n{"associations": []}\n```')

    assert parsed == {"associations": []}


def test_gemini_json_parser_accepts_json_with_wrapper_text():
    pipeline = _make_pipeline()

    parsed = pipeline._parse_json_response('Result:\n[{"gene_name":"IFNG"}]\nDone.')

    assert parsed == [{"gene_name": "IFNG"}]


def test_transient_gemini_503_gets_bounded_retry(paper_analysis_config):
    pipeline = _make_pipeline()
    paper_analysis_config.GEMINI_TRANSIENT_RETRY_WAIT_SECONDS = 10

    should_retry, wait = pipeline._should_retry_gemini_error(
        RuntimeError("503 UNAVAILABLE: high demand"),
        attempt=0,
        max_retries=2,
    )

    assert should_retry is True
    assert wait == 10


def test_gemini_parsed_pydantic_response_coerces_to_plain_dict():
    from modules.paper_analysis.gemini_client import CandidateDiscoveryResponse

    parsed = CandidateDiscoveryResponse(
        associations=[
            {
                "reported_gene": "IFNG",
                "reported_variant": "",
                "original_mention": "IFN-gamma",
                "evidence_sentence": "IFN-gamma was elevated.",
            }
        ]
    )

    coerced = _make_pipeline()._coerce_parsed_value(parsed)

    assert coerced == {
        "associations": [
            {
                "reported_gene": "IFNG",
                "reported_variant": "",
                "original_mention": "IFN-gamma",
                "evidence_sentence": "IFN-gamma was elevated.",
            }
        ]
    }


def test_detail_extraction_rejects_non_array_json_response(monkeypatch, paper_analysis_config):
    pipeline = _make_pipeline()
    pipeline.associations = [{"gene": "IFNG", "variant": ""}]

    monkeypatch.setattr(
        pipeline,
        "_generate_content_json",
        lambda **_kwargs: {"gene_name": "IFNG"},
    )

    rows = pipeline.extract_gene_info({"Key Finding": "finding"})

    assert rows[0]["extraction_mode"] == "skeleton"
    assert "missing required 'rows'" in rows[0]["detail_extraction_error"]


def test_candidate_response_shape_validator_rejects_missing_associations():
    pipeline = _make_pipeline()

    with pytest.raises(ValueError, match="failed schema validation"):
        pipeline._associations_from_structured_response({}, "candidate discovery")


def test_candidate_response_schema_does_not_silently_cap_large_gene_lists():
    pipeline = _make_pipeline()
    payload = {
        "associations": [
            {
                "reported_gene": f"GENE{i}",
                "reported_variant": "",
                "original_mention": f"GENE{i}",
                "evidence_sentence": f"GENE{i} was reported.",
            }
            for i in range(30)
        ]
    }

    associations = pipeline._associations_from_structured_response(
        payload,
        "candidate discovery",
    )

    assert len(associations) == 30


def test_dynamic_detail_response_model_preserves_user_column_aliases():
    from modules.paper_analysis.gemini_client import build_detail_extraction_response_model

    response_model = build_detail_extraction_response_model(
        {"Key Finding": "primary finding"}
    )
    payload = {
        "rows": [
            {
                "gene_name": "IFNG",
                "variant_name": "",
                "Key Finding": "IFN-gamma was elevated.",
                "Key Finding Citation": "IFN-gamma was elevated.",
            }
        ]
    }

    parsed = response_model.model_validate(payload).model_dump(by_alias=True)

    assert parsed["rows"][0]["Key Finding"] == "IFN-gamma was elevated."
    assert parsed["rows"][0]["Key Finding Citation"] == "IFN-gamma was elevated."
