"""Static checks for the public pipeline contract."""

from modules.paper_analysis.pipeline import PAPER_ANALYSIS_STEPS


def test_paper_analysis_steps_contract_keys_order_and_required_flags():
    expected = [
        ("context_validation", True),
        ("abstract_gemini_candidate_discovery", False),
        ("fulltext_gemini_candidate_discovery", True),
        ("deterministic_hgnc_scan", True),
        ("figure_gemini_candidate_discovery", False),
        ("pubtator_merge", True),
        ("grounding_check", True),
        ("hgnc_validation", True),
        ("detail_extraction", True),
        ("post_validation", True),
    ]

    assert [(step.key, step.required) for step in PAPER_ANALYSIS_STEPS] == expected
    assert [step.sequence for step in PAPER_ANALYSIS_STEPS] == list(range(10, 110, 10))
    assert all(step.label and step.state for step in PAPER_ANALYSIS_STEPS)
