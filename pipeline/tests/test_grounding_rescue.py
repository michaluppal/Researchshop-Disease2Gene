"""
Tests for F8a truncation rescue branch in _run_grounding_check.

When per-paper extraction full-text truncation drops a section containing a candidate gene,
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

import pytest

# Ensure `pipeline/` is on sys.path so `import modules.*` works regardless of
# which directory pytest is invoked from.
_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------


class OfflineGeminiClient:
    pass


def _make_pipeline(paper_text: str = ""):
    """Return a PaperAnalysisPipeline instance with no live Gemini dependency."""
    from modules.paper_analysis.pipeline import PaperAnalysisPipeline

    return PaperAnalysisPipeline(
        paper_text=paper_text,
        abstract_text="",
        pubtator_genes=[],
        figure_inputs=[],
        client=OfflineGeminiClient(),
    )


# ---------------------------------------------------------------------------
# Helper: inject a candidate with a given source into an already-built pipeline
# ---------------------------------------------------------------------------


def _inject_candidate(pipeline, gene: str, variant: str, source: str) -> tuple:
    """Populate candidate_meta + associations for a single candidate.

    Returns the candidate_meta key so tests can introspect the entry.
    """
    variant = pipeline._normalize_variant_for_gene(gene, variant)
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


def test_llm_discovery_rescue_corroborates_deterministic_only_gene(monkeypatch):
    """Free-tier mode should spend one rescue discovery call before emitting zero genes.

    Deterministic-only gene-level hits are intentionally dropped unless another
    source corroborates them. When all candidates would otherwise be dropped,
    the rescue pass can add ``llm_text`` provenance and let real paper genes
    proceed to detail extraction.
    """
    from modules import config

    pipeline = _make_pipeline("IL6 expression increased after infection.")
    key = _inject_candidate(pipeline, "IL6", "", "deterministic_lexicon")

    monkeypatch.setattr(config, "ENABLE_LLM_GENE_DISCOVERY", False)
    monkeypatch.setattr(config, "ENABLE_LLM_GENE_DISCOVERY_RESCUE", True)
    monkeypatch.setattr(config, "ENABLE_DETERMINISTIC_CONTEXT_RESCUE", False)
    monkeypatch.setattr(config, "GEMINI_MAX_CALLS_PER_PAPER", 2)

    def fixture_extract_gene_names(*args, **kwargs):
        pipeline.candidate_meta[key]["sources"].add("llm_text")
        pipeline._refresh_associations_from_meta()
        return pipeline.associations

    monkeypatch.setattr(pipeline, "extract_gene_names", fixture_extract_gene_names)

    pipeline._run_validation_and_normalize()

    assert pipeline.associations == [{"gene": "IL6", "variant": ""}]
    assert "llm_text" in pipeline.candidate_meta[key]["sources"]
    assert pipeline.candidate_meta[key]["validation_outcome"] == "passed"


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
    # No truncation: both handles point at the same string.
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
        "test setup invariant: truncation branch requires distinct text handles"
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
    Even with distinct truncated/original text handles, the rescue counter must stay 0 and the
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


def test_deterministic_context_rescue_keeps_strong_result_gene(monkeypatch):
    """Deterministic-only HGNC hits can pass when the paper gives result evidence."""
    from modules import config

    paper_text = (
        "Results: Pathways including IFNA and IFNG responses were shown to be "
        "significantly upregulated in infected macrophages compared with controls."
    )
    pipeline = _make_pipeline(paper_text=paper_text)
    key = _inject_candidate(pipeline, "IFNG", "", "deterministic_lexicon")

    monkeypatch.setattr(config, "DETERMINISTIC_REQUIRE_CORROBORATION_FOR_GENE_ONLY", True)
    monkeypatch.setattr(config, "ENABLE_DETERMINISTIC_CONTEXT_RESCUE", True)

    pipeline._apply_gene_validation_heuristics()

    assert pipeline.associations == [{"gene": "IFNG", "variant": ""}]
    meta = pipeline.candidate_meta[key]
    assert meta["validation_outcome"] == "passed_deterministic_context"
    assert meta["deterministic_context_reason"] == "result_context"
    assert "significantly upregulated" in meta["deterministic_context_snippet"]


def test_deterministic_context_rescue_keeps_pathway_gene(monkeypatch):
    """Pathway/signaling context is enough even without PubTator or LLM provenance."""
    from modules import config

    paper_text = (
        "Discussion: The data support mitochondrial antiviral signaling pathways "
        "mediated by MAVS and downstream RIG-I-like receptor signaling."
    )
    pipeline = _make_pipeline(paper_text=paper_text)
    key = _inject_candidate(pipeline, "MAVS", "", "deterministic_lexicon")

    monkeypatch.setattr(config, "DETERMINISTIC_REQUIRE_CORROBORATION_FOR_GENE_ONLY", True)
    monkeypatch.setattr(config, "ENABLE_DETERMINISTIC_CONTEXT_RESCUE", True)

    pipeline._apply_gene_validation_heuristics()

    assert pipeline.associations == [{"gene": "MAVS", "variant": ""}]
    meta = pipeline.candidate_meta[key]
    assert meta["validation_outcome"] == "passed_deterministic_context"
    assert meta["deterministic_context_reason"] == "pathway_context"


@pytest.mark.parametrize(
    ("gene", "paper_text"),
    [
        (
            "RPS24",
            "Methods: RPS24 F and RPS24 R primers were used as a housekeeping "
            "reference gene for RT-qPCR normalization.",
        ),
        (
            "PAM",
            "Methods: Primary porcine alveolar macrophages (PAM) were isolated "
            "and infected with PRRSV before RNA extraction.",
        ),
        (
            "PAM",
            "Results: Differential pathway responses were analyzed separately for "
            "PAM and PIM samples after infection.",
        ),
        (
            "GP5",
            "Results: PRRSV strain GP5 sequences showed viral genome nucleotide "
            "identity across isolates.",
        ),
    ],
)
def test_deterministic_context_rescue_rejects_methods_and_abbreviation_noise(
    monkeypatch, gene, paper_text
):
    """Primer, macrophage-abbreviation, and viral strain/protein hits stay filtered."""
    from modules import config

    pipeline = _make_pipeline(paper_text=paper_text)
    key = _inject_candidate(pipeline, gene, "", "deterministic_lexicon")

    monkeypatch.setattr(config, "DETERMINISTIC_REQUIRE_CORROBORATION_FOR_GENE_ONLY", True)
    monkeypatch.setattr(config, "ENABLE_DETERMINISTIC_CONTEXT_RESCUE", True)

    pipeline._apply_gene_validation_heuristics()

    assert pipeline.associations == []
    assert pipeline.candidate_meta[key]["validation_outcome"] == (
        "rejected_uncorroborated_deterministic"
    )
    assert any(
        drop["gene"] == gene and drop["reason"] == "deterministic_uncorroborated"
        for drop in pipeline.dropped_candidates
    )


def test_grounding_uses_prepared_cytokine_normalization_records():
    pipeline = _make_pipeline(
        "Results: IFN-gamma, CXCL9, and CXCL10 were elevated in early MIS-C."
    )
    key = _inject_candidate(pipeline, "IFNG", "", "llm_text")

    pipeline._run_grounding_check()

    assert pipeline.associations == [{"gene": "IFNG", "variant": ""}]
    meta = pipeline.candidate_meta[key]
    assert meta["grounding_match"] == "IFN-gamma"
    assert meta["grounding_source"] == "normalized_evidence_index"
    assert meta["normalization_rule"] == "cytokine_alias_ifng"
    assert "IFN-gamma" in meta["original_mentions"]


def test_grounding_uses_hla_allele_shorthand_normalization_records():
    pipeline = _make_pipeline(
        "The association of MIS-C with HLA class I alleles A*02, B*35 and C*04 "
        "suggested genetic susceptibility."
    )
    key = _inject_candidate(pipeline, "HLA-C", "C*04", "llm_text")

    pipeline._run_grounding_check()

    assert pipeline.associations == [{"gene": "HLA-C", "variant": "HLA-C*04"}]
    meta = pipeline.candidate_meta[key]
    assert meta["grounding_match"] == "C*04"
    assert meta["grounding_source"] == "normalized_evidence_index"
    assert meta["normalization_rule"] == "hla_class_i_allele_shorthand"
    assert "C*04" in meta["original_mentions"]


def test_grounding_uses_direct_hla_allele_normalization_records():
    pipeline = _make_pipeline(
        "Results: HLA-C*04:01 was enriched in the MIS-C subgroup."
    )
    key = _inject_candidate(pipeline, "HLA-C", "C04:01", "llm_text")

    pipeline._run_grounding_check()

    assert pipeline.associations == [{"gene": "HLA-C", "variant": "HLA-C*04:01"}]
    meta = pipeline.candidate_meta[key]
    assert meta["grounding_match"] == "HLA-C*04:01"
    assert meta["grounding_source"] == "normalized_evidence_index"
    assert meta["normalization_rule"] == "hla_direct_allele"
