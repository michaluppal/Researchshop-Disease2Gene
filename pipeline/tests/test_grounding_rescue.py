"""
Tests for F8a truncation rescue branch in _run_grounding_check.

When Stage 5 full-text truncation drops a section containing a candidate gene,
the grounding check would previously reject that gene as "ungrounded". F8a adds
a rescue step: if primary search in self.paper_text (truncated) fails AND
self.paper_text != self.original_paper_text (truncation fired), retry the
grounding search against self.original_paper_text. On success, tag the meta
with truncation_rescued=True, validation_outcome="passed_untruncated_rescue",
and increment self._truncation_rescue_count.

All tests are offline — no Gemini API, no network access. They exercise
_run_grounding_check by wiring self.paper_text, self.original_paper_text,
self.associations, and self.candidate_meta directly.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure `pipeline/` is on sys.path so `import modules.*` works regardless of
# which directory pytest is invoked from.
_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))


# ---------------------------------------------------------------------------
# Pipeline factory (mirrors test_figure_extraction._make_pipeline)
# ---------------------------------------------------------------------------


def _make_pipeline(paper_text: str = ""):
    """Return a GeneInfoPipeline instance with the Gemini client mocked out."""
    from modules import config as _config

    original_key = _config.GEMINI_API_KEY
    _config.GEMINI_API_KEY = "fake-api-key-for-testing"

    try:
        with patch(
            "modules.gemini_extractor.config.GEMINI_API_KEY",
            "fake-api-key-for-testing",
        ):
            with patch("google.genai.Client") as mock_client_cls:
                mock_client_cls.return_value = MagicMock()
                from modules.gemini_extractor import GeneInfoPipeline

                pipeline = GeneInfoPipeline(
                    paper_text=paper_text,
                    abstract_text="",
                    pubtator_genes=[],
                    figure_inputs=[],
                )
    finally:
        _config.GEMINI_API_KEY = original_key

    return pipeline


# ---------------------------------------------------------------------------
# Helper: inject a candidate with a given source into an already-built pipeline
# ---------------------------------------------------------------------------


def _inject_candidate(pipeline, gene: str, variant: str, source: str) -> tuple:
    """Populate candidate_meta + associations for a single candidate.

    Returns the candidate_meta key so tests can introspect the entry.
    """
    key = pipeline._assoc_key(gene, variant)
    entry = pipeline.candidate_meta.get(key)
    if entry is None:
        entry = {
            "gene": gene,
            "variant": variant,
            "sources": set(),
            "normalization_applied": "",
            "raw_gene_labels": {gene},
        }
        pipeline.candidate_meta[key] = entry
    entry["sources"].add(source)
    pipeline._refresh_associations_from_meta()
    return key


# ---------------------------------------------------------------------------
# Guard: these tests assume ENABLE_GROUNDING_CHECK=True
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ensure_grounding_enabled():
    """All tests in this module require the grounding check to run."""
    from modules import config as _config

    original = getattr(_config, "ENABLE_GROUNDING_CHECK", True)
    _config.ENABLE_GROUNDING_CHECK = True
    try:
        yield
    finally:
        _config.ENABLE_GROUNDING_CHECK = original


# ---------------------------------------------------------------------------
# Test 1 — no truncation, no rescue
# ---------------------------------------------------------------------------


def test_no_truncation_no_rescue():
    """When paper_text == original_paper_text and the gene is absent from both,
    the candidate is dropped as rejected_ungrounded; no rescue counter bump;
    no truncation_rescued flag added.
    """
    paper_text = (
        "Introduction: We studied KRAS mutations in lung cancer cohort. "
        "Results: High mutation frequency was observed in codon 12."
    )
    pipeline = _make_pipeline(paper_text=paper_text)
    # Simulate "no truncation happened" — both handles point at the same string.
    pipeline.original_paper_text = paper_text
    pipeline.paper_text = paper_text

    key = _inject_candidate(pipeline, "ZNF123", "", "llm_text")

    pipeline._run_grounding_check()

    final_genes = {(a.get("gene") or "").upper() for a in pipeline.associations}
    assert "ZNF123" not in final_genes, (
        "ZNF123 should be dropped — gene is absent from paper_text and rescue must not fire"
    )
    meta = pipeline.candidate_meta[key]
    assert meta.get("validation_outcome") == "rejected_ungrounded"
    assert "truncation_rescued" not in meta, (
        "truncation_rescued flag must not be set when rescue did not run"
    )
    assert pipeline._truncation_rescue_count == 0


# ---------------------------------------------------------------------------
# Test 2 — rescue when gene appears only in truncated (original) section
# ---------------------------------------------------------------------------


def test_rescue_when_gene_in_truncated_section():
    """Gene X absent from truncated paper_text but present in original_paper_text:
    rescue must kick in, association kept, meta flagged, counter == 1.
    """
    truncated = (
        "We studied KRAS mutations in lung cancer. Results showed high frequency."
    )
    original = (
        truncated
        + " Methods: We measured ZNF123 expression using qPCR across all samples."
    )

    pipeline = _make_pipeline(paper_text=truncated)
    pipeline.original_paper_text = original
    pipeline.paper_text = truncated

    key = _inject_candidate(pipeline, "ZNF123", "", "llm_text")

    pipeline._run_grounding_check()

    final_genes = {(a.get("gene") or "").upper() for a in pipeline.associations}
    assert "ZNF123" in final_genes, (
        "ZNF123 should have been rescued — appears in original_paper_text's Methods section"
    )
    meta = pipeline.candidate_meta[key]
    assert meta.get("truncation_rescued") is True
    assert meta.get("validation_outcome") == "passed_untruncated_rescue"
    assert pipeline._truncation_rescue_count == 1


# ---------------------------------------------------------------------------
# Test 3 — no rescue when gene absent from both texts
# ---------------------------------------------------------------------------


def test_no_rescue_when_gene_absent_from_both():
    """Truncation applied (paper_text != original_paper_text) BUT gene is in
    neither version. Candidate dropped; rescue counter stays 0.
    """
    truncated = "We studied KRAS mutations in lung cancer. Results were positive."
    original = (
        truncated
        + " Methods: RNA was extracted using Trizol reagent per manufacturer instructions."
    )

    pipeline = _make_pipeline(paper_text=truncated)
    pipeline.original_paper_text = original
    pipeline.paper_text = truncated
    assert pipeline.paper_text != pipeline.original_paper_text, (
        "test setup invariant: truncation must be simulated"
    )

    key = _inject_candidate(pipeline, "ZNF123", "", "llm_text")

    pipeline._run_grounding_check()

    final_genes = {(a.get("gene") or "").upper() for a in pipeline.associations}
    assert "ZNF123" not in final_genes
    meta = pipeline.candidate_meta[key]
    assert meta.get("validation_outcome") == "rejected_ungrounded"
    assert "truncation_rescued" not in meta
    assert pipeline._truncation_rescue_count == 0


# ---------------------------------------------------------------------------
# Test 4 — primary search succeeds, rescue branch not reached
# ---------------------------------------------------------------------------


def test_no_rescue_when_gene_in_retained_section():
    """Truncation applied, but gene is in the RETAINED paper_text so primary
    search succeeds. Rescue branch must not run; meta must not get the rescue
    flag; outcome must not be the rescue outcome; counter stays 0.
    """
    truncated = (
        "We studied ZNF123 expression patterns in lung cancer samples. "
        "Results showed high frequency of upregulation."
    )
    original = (
        truncated
        + " Methods: RNA extraction and qPCR were performed as previously described."
    )

    pipeline = _make_pipeline(paper_text=truncated)
    pipeline.original_paper_text = original
    pipeline.paper_text = truncated
    assert pipeline.paper_text != pipeline.original_paper_text

    key = _inject_candidate(pipeline, "ZNF123", "", "llm_text")

    pipeline._run_grounding_check()

    final_genes = {(a.get("gene") or "").upper() for a in pipeline.associations}
    assert "ZNF123" in final_genes, "Gene should survive primary (truncated) grounding"
    meta = pipeline.candidate_meta[key]
    assert not meta.get("truncation_rescued"), (
        "truncation_rescued must be falsy/missing when primary grounding succeeds"
    )
    assert meta.get("validation_outcome") != "passed_untruncated_rescue"
    assert pipeline._truncation_rescue_count == 0


# ---------------------------------------------------------------------------
# Test 5 — figure branch is unaffected by rescue logic
# ---------------------------------------------------------------------------


def test_figure_branch_unaffected_by_rescue():
    """A candidate sourced exclusively from llm_figure takes the figure branch
    (caption/label check) and early-continues before the rescue code path.
    Even with truncation simulated, the rescue counter must stay 0 and the
    meta must not carry the truncation_rescued flag.
    """
    truncated = "No mention of the gene in this short prose snippet."
    original = (
        truncated
        + " Methods: Standard cell culture protocols were used throughout."
    )

    pipeline = _make_pipeline(paper_text=truncated)
    pipeline.original_paper_text = original
    pipeline.paper_text = truncated
    assert pipeline.paper_text != pipeline.original_paper_text

    # A figure whose caption mentions ZNF123, so the figure branch passes.
    pipeline.figure_inputs = [
        {
            "label": "Figure 1",
            "caption": "ZNF123 expression heatmap across tumour subtypes.",
            "url": "https://example.com/fig1.jpg",
        }
    ]

    key = _inject_candidate(pipeline, "ZNF123", "", "llm_figure")

    pipeline._run_grounding_check()

    final_genes = {(a.get("gene") or "").upper() for a in pipeline.associations}
    assert "ZNF123" in final_genes, (
        "ZNF123 should pass via the figure branch (caption mentions it)"
    )
    meta = pipeline.candidate_meta[key]
    assert "truncation_rescued" not in meta, (
        "Figure-only candidates early-continue — rescue flag must not appear"
    )
    assert meta.get("validation_outcome") != "passed_untruncated_rescue"
    assert pipeline._truncation_rescue_count == 0


# ---------------------------------------------------------------------------
# Test 6 — counter increments correctly across multiple rescues
# ---------------------------------------------------------------------------


def test_rescue_increments_counter():
    """Two candidates both present only in original_paper_text: both get
    rescued; counter reaches 2; both have truncation_rescued=True.
    """
    truncated = "We studied cancer biology in a 200-sample cohort. Results were varied."
    original = (
        truncated
        + " Methods: We measured ZNF123 and ABCA7 expression using qPCR on all samples."
    )

    pipeline = _make_pipeline(paper_text=truncated)
    pipeline.original_paper_text = original
    pipeline.paper_text = truncated

    key_a = _inject_candidate(pipeline, "ZNF123", "", "llm_text")
    key_b = _inject_candidate(pipeline, "ABCA7", "", "llm_text")

    pipeline._run_grounding_check()

    final_genes = {(a.get("gene") or "").upper() for a in pipeline.associations}
    assert "ZNF123" in final_genes and "ABCA7" in final_genes, (
        f"Both genes should be rescued; got final_genes={final_genes}"
    )
    assert pipeline.candidate_meta[key_a].get("truncation_rescued") is True
    assert pipeline.candidate_meta[key_b].get("truncation_rescued") is True
    assert (
        pipeline.candidate_meta[key_a].get("validation_outcome")
        == "passed_untruncated_rescue"
    )
    assert (
        pipeline.candidate_meta[key_b].get("validation_outcome")
        == "passed_untruncated_rescue"
    )
    assert pipeline._truncation_rescue_count == 2


# ---------------------------------------------------------------------------
# Test 7 — regression guard for _find_evidence_snippet signature change
# ---------------------------------------------------------------------------


def test_find_evidence_snippet_param_default_unchanged():
    """The new optional `text` kwarg must be strictly additive:
    calling with no kwarg, text=None, or text=self.paper_text must produce
    identical output. Regression guard for existing callers.
    """
    paper_text = (
        "Introduction: BRCA1 mutations increase breast cancer risk. "
        "Several studies have characterised BRCA1 loss-of-function variants."
    )
    pipeline = _make_pipeline(paper_text=paper_text)
    pipeline.original_paper_text = paper_text
    pipeline.paper_text = paper_text

    snippet_default = pipeline._find_evidence_snippet(["BRCA1"])
    snippet_none = pipeline._find_evidence_snippet(["BRCA1"], text=None)
    snippet_self = pipeline._find_evidence_snippet(["BRCA1"], text=pipeline.paper_text)

    assert snippet_default, "Expected a non-empty snippet for BRCA1 in paper_text"
    assert snippet_default == snippet_none == snippet_self, (
        "All three call forms must yield identical output:\n"
        f"  default: {snippet_default!r}\n"
        f"  None   : {snippet_none!r}\n"
        f"  self.paper_text: {snippet_self!r}"
    )
