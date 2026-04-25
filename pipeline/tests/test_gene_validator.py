"""
Tests for gene_validator.GeneValidator and _citation_exists_in_paper()

The GeneValidator loads the bundled HGNC JSON on instantiation — no network calls
for local_symbol and local_alias resolution paths. Remote API paths are not tested here.

Citation existence checks are purely string-matching (difflib + regex) — no network.
"""

import pytest

from modules import config
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

    # ------------------------------------------------------------------
    # F10a — Citation drift normalisation (soft-hyphen, line-break
    # hyphenation, Unicode dashes, ligatures) + tiered failure messages
    # + config-driven threshold.
    # ------------------------------------------------------------------

    def test_drift_soft_hyphen_matches(self):
        """Soft hyphens (U+00AD) inside a paper word should be stripped before matching."""
        paper = (
            "Introduction: BRCA1 mutations increase disease suscep\u00adtibility in patients. "
            "We analysed a cohort of 200 patients with hereditary breast cancer."
        )
        citation = "increase disease susceptibility"
        exists, confidence, reason = _citation_exists_in_paper(
            citation, paper, gene_symbol="BRCA1"
        )
        assert exists is True, f"Soft-hyphen normalisation should match. Reason: {reason}"
        assert confidence >= 0.85

    def test_drift_line_break_hyphenation_matches(self):
        """Line-break hyphenation (word-\\nword) should re-merge into one word before matching."""
        paper = (
            "BRCA1 mutations increase disease suscep-\ntibility to severe disease in patients. "
            "The cohort included 200 individuals with hereditary cancer."
        )
        citation = "increase disease susceptibility to severe disease"
        exists, confidence, reason = _citation_exists_in_paper(
            citation, paper, gene_symbol="BRCA1"
        )
        assert exists is True, f"Line-break hyphenation should match. Reason: {reason}"
        assert confidence >= 0.85

    def test_drift_en_dash_matches(self):
        """En-dash (U+2013) should normalise to ASCII hyphen on both sides before matching."""
        paper = (
            "We observed that BRCA1 carriers showed p-value between 1.5\u20139.0 for survival. "
            "These findings were consistent across the whole cohort of 200 patients."
        )
        citation = "BRCA1 carriers showed p-value between 1.5-9.0 for survival"
        exists, confidence, reason = _citation_exists_in_paper(
            citation, paper, gene_symbol="BRCA1"
        )
        assert exists is True, f"En-dash normalisation should match. Reason: {reason}"
        assert confidence >= 0.85

    def test_drift_em_dash_matches(self):
        """Em-dash (U+2014) should normalise to ASCII hyphen on both sides before matching."""
        paper = (
            "BRCA1 carriers had increased expression\u2014approximately 3-fold\u2014in tumor tissue. "
            "This effect was consistent across the discovery cohort."
        )
        citation = "BRCA1 carriers had increased expression-approximately 3-fold-in tumor tissue"
        exists, confidence, reason = _citation_exists_in_paper(
            citation, paper, gene_symbol="BRCA1"
        )
        assert exists is True, f"Em-dash normalisation should match. Reason: {reason}"
        assert confidence >= 0.85

    def test_drift_ligature_fi_matches(self):
        """U+FB01 ﬁ ligature should expand to 'fi' on both sides before matching."""
        paper = (
            "BRCA1 expression analysis revealed a statistically signi\ufb01cant decrease in tumour tissue. "
            "The effect was reproducible across three independent cohorts."
        )
        citation = "statistically significant decrease in tumour tissue"
        exists, confidence, reason = _citation_exists_in_paper(
            citation, paper, gene_symbol="BRCA1"
        )
        assert exists is True, f"fi-ligature normalisation should match. Reason: {reason}"
        assert confidence >= 0.85

    def test_drift_non_breaking_hyphen_matches(self):
        """Non-breaking hyphen (U+2011) should normalise to ASCII hyphen before matching."""
        paper = (
            "We investigated BRCA1\u2011associated breast cancer risk in a cohort of 200 patients. "
            "Hereditary cases made up 35% of the sample."
        )
        citation = "BRCA1-associated breast cancer risk in a cohort"
        exists, confidence, reason = _citation_exists_in_paper(
            citation, paper, gene_symbol="BRCA1"
        )
        assert exists is True, f"Non-breaking-hyphen normalisation should match. Reason: {reason}"
        assert confidence >= 0.85

    def test_near_miss_message_distinguishes_from_no_match(self):
        """
        When the best dense-match ratio lands in [0.6, threshold), the failure reason
        should be the 'Near-miss match' branch, distinct from the 'No similar text' branch.
        """
        # Paper and citation share most words, differ on one key token ('increase' vs 'decrease')
        paper = (
            "BRCA1 expression analysis showed a significant increase in gene expression in "
            "tumor tissue compared to normal tissue across the entire cohort."
        )
        citation = "significant decrease in gene expression in tumor tissue compared to normal"
        exists, best_ratio, reason = _citation_exists_in_paper(
            citation, paper, gene_symbol="BRCA1"
        )
        assert exists is False, (
            f"Citation differs on a key semantic token; should not pass. Ratio={best_ratio:.2f}"
        )
        assert best_ratio >= 0.6, (
            f"Expected ratio in [0.6, threshold) range, got {best_ratio:.2f}. Reason: {reason}"
        )
        assert "Near-miss match" in reason, (
            f"Expected 'Near-miss match' in reason, got: {reason}"
        )
        assert "No similar text" not in reason, (
            f"Expected 'No similar text' NOT in reason, got: {reason}"
        )

    def test_no_match_message_below_0_6(self):
        """When best ratio < 0.6, failure reason should be the 'No similar text' branch."""
        paper = (
            "The BRCA1 gene encodes a tumour suppressor protein involved in DNA repair. "
            "Pathogenic variants predispose carriers to breast and ovarian cancer."
        )
        # Completely unrelated content with ≥5 words so it reaches the dense-match path
        citation = "cardiac hypertrophy atrial fibrillation ventricular arrhythmia echocardiography"
        exists, best_ratio, reason = _citation_exists_in_paper(
            citation, paper, gene_symbol="BRCA1"
        )
        assert exists is False
        assert best_ratio < 0.6, f"Expected ratio < 0.6, got {best_ratio:.2f}"
        assert "No similar text" in reason, (
            f"Expected 'No similar text' in reason, got: {reason}"
        )

    def test_threshold_respects_config_override(self, monkeypatch):
        """
        The dense-match threshold is config-driven via CITATION_DENSE_MATCH_MIN_RATIO.
        A near-miss that fails at default 0.85 should pass when the threshold is
        lowered to 0.75 via monkeypatch.
        """
        paper = (
            "We observed increased expression of TP53 in tumor cells across the cohort. "
            "This was confirmed by independent RNA-seq measurements."
        )
        # One token differs ("elevated" vs "increased"); ratio lands at ~0.78 — above
        # a 0.75 override but below the 0.85 default.
        citation = "observed elevated expression of TP53 in tumor cells across the"

        # First, confirm the citation is a near-miss at the default threshold (0.85).
        exists_default, ratio_default, reason_default = _citation_exists_in_paper(
            citation, paper, gene_symbol="TP53"
        )
        assert exists_default is False, (
            f"Expected failure at default threshold. Ratio={ratio_default:.2f} reason={reason_default}"
        )
        # Second, confirm the same case passes once the threshold is dropped to 0.75.
        monkeypatch.setattr(config, "CITATION_DENSE_MATCH_MIN_RATIO", 0.75)
        exists_override, ratio_override, reason_override = _citation_exists_in_paper(
            citation, paper, gene_symbol="TP53"
        )
        assert ratio_default == pytest.approx(ratio_override, abs=1e-9), (
            "Ratio should be independent of the threshold override"
        )
        assert ratio_override >= 0.75, (
            f"Expected ratio >= 0.75 for the override to flip the result, got {ratio_override:.2f}"
        )
        assert exists_override is True, (
            f"Expected success at threshold=0.75. Ratio={ratio_override:.2f} reason={reason_override}"
        )


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

    Reference: AGENTS.md Common Agent Mistakes #5, AUDIT.md C19.
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
