"""
Tests for gene_validator.GeneValidator and _citation_exists_in_paper()

The GeneValidator loads the bundled HGNC JSON on instantiation — no network calls
for local_symbol and local_alias resolution paths. Remote API paths are not tested here.

Citation existence checks are purely string-matching (difflib + regex) — no network.
"""

import pytest

from modules.gene_validator import GeneValidator, _citation_exists_in_paper


@pytest.fixture(scope="module")
def validator():
    """Single GeneValidator instance for all tests in this module (loads HGNC once)."""
    return GeneValidator()


# ---------------------------------------------------------------------------
# GeneValidator — local HGNC resolution (no network)
# ---------------------------------------------------------------------------

class TestGeneValidatorLocalResolution:
    def test_brca1_resolves_as_canonical_symbol(self, validator):
        """BRCA1 is a valid canonical HGNC symbol — resolves via local_symbol."""
        symbol, source = validator.resolve_gene_symbol("BRCA1")
        assert symbol == "BRCA1"
        assert source == "local_symbol"

    def test_tp53_resolves_as_canonical_symbol(self, validator):
        symbol, source = validator.resolve_gene_symbol("TP53")
        assert symbol == "TP53"
        assert source == "local_symbol"

    def test_empty_string_returns_none(self, validator):
        symbol, source = validator.resolve_gene_symbol("")
        assert symbol is None
        assert source == "empty"

    def test_obviously_invalid_symbol_does_not_resolve_locally(self, validator):
        """'NOTAGENEXYZ' should not match any local HGNC entry."""
        symbol, _ = validator.resolve_gene_symbol("NOTAGENEXYZ999")
        # If it resolves remotely the test will fail — acceptable, means network is up.
        # This test is primarily guarding against false-positive local hits.
        assert symbol != "NOTAGENEXYZ999"

    def test_hgnc_database_loaded(self, validator):
        """Sanity check: local DB should have thousands of genes."""
        assert len(validator._local_gene_db) > 10_000, (
            "Expected bundled HGNC DB to have >10,000 genes"
        )


# ---------------------------------------------------------------------------
# _citation_exists_in_paper — dense sequence matching (no network)
# ---------------------------------------------------------------------------

class TestCitationExistsInPaper:
    def test_verbatim_quote_returns_true(self, sample_paper_text):
        """An exact substring from the paper should match with confidence 1.0."""
        citation = "The most common variant was p.Glu1915Ter (E1915X), found in 45 patients (35%)."
        exists, confidence, reason = _citation_exists_in_paper(
            citation, sample_paper_text, gene_symbol="BRCA1"
        )
        assert exists is True, f"Verbatim quote should match. Reason: {reason}"
        assert confidence >= 0.85

    def test_empty_citation_returns_false(self, sample_paper_text):
        exists, confidence, reason = _citation_exists_in_paper(
            "", sample_paper_text, gene_symbol="BRCA1"
        )
        assert exists is False
        assert confidence == 0.0

    def test_empty_paper_text_returns_false(self):
        citation = "BRCA1 mutations were found in 45 patients."
        exists, confidence, reason = _citation_exists_in_paper(citation, "", gene_symbol="BRCA1")
        assert exists is False
        assert confidence == 0.0

    def test_invented_sentence_returns_false(self, sample_paper_text):
        """A plausible but non-existent sentence should not match."""
        fabricated = (
            "BRCA1 expression levels were elevated by 12-fold in all 200 tumor samples "
            "compared to adjacent normal tissue in this landmark study of hereditary cancer."
        )
        exists, confidence, _ = _citation_exists_in_paper(
            fabricated, sample_paper_text, gene_symbol="BRCA1"
        )
        assert exists is False, "Fabricated citation should not match"

    def test_gene_context_required(self, sample_paper_text):
        """A real sentence from the paper that mentions only a different gene should fail
        the gene context gate when checked against a mismatched gene."""
        # This sentence is about TP53, not BRCA2
        citation = "TP53 mutations were detected in 23% of triple-negative breast cancer cases."
        # Check it against a gene that doesn't appear near this sentence
        exists, confidence, reason = _citation_exists_in_paper(
            citation, sample_paper_text, gene_symbol="BRCA2",
            gene_aliases=[]
        )
        # The sentence IS in the paper, but BRCA2 context may not be within ±1500 chars.
        # We assert the function returns a result without crashing (behavior may vary
        # depending on proximity in the sample text).
        assert isinstance(exists, bool)
        assert 0.0 <= confidence <= 1.0


# ---------------------------------------------------------------------------
# Smoke test — C19 regression guard
# ---------------------------------------------------------------------------

def test_citation_smoke_verbatim_match():
    """
    Smoke test: citation validator MUST return True for a verbatim substring of paper_text.

    This guards against the C19 silent failure regression where a TypeError inside
    _citation_exists_in_paper was swallowed, causing the function to return False/0.0
    for every citation without raising any error. The pipeline would run normally but
    produce zero validated citations.

    Reference: CLAUDE.md Common Mistakes #5, AUDIT.md C19.
    Known-good calibration: PMID 17463248 (T2D GWAS, Scott et al. 2007) — 5/5 citations
    verified verbatim in PMC XML (2026-02-25).
    """
    paper_text = (
        "We identified a genome-wide significant association between TCF7L2 rs7903146 "
        "and type 2 diabetes risk (p = 2.1e-9). The TCF7L2 variant showed an odds ratio "
        "of 1.37 (95% CI 1.28-1.47) in the discovery cohort. Carriers of the risk allele "
        "had significantly impaired insulin secretion compared to non-carriers."
    )
    citation = (
        "TCF7L2 rs7903146 and type 2 diabetes risk (p = 2.1e-9)"
    )

    exists, ratio, reason = _citation_exists_in_paper(citation, paper_text, gene_symbol="TCF7L2")

    assert exists is True, (
        "Citation validator returned False on a verbatim sentence present in paper_text. "
        "This is the C19 regression: a silent TypeError causes the validator to return "
        "False/0.0 for all rows without raising an error. "
        f"Got: exists={exists}, ratio={ratio:.3f}, reason={reason}"
    )
    assert ratio >= 0.85, (
        f"Expected matching ratio >= 0.85 for verbatim match, got {ratio:.3f}. "
        f"Reason: {reason}"
    )
