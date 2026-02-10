"""Unit tests for modules/abstract_screener.py"""

import pytest
from modules.abstract_screener import has_genetic_content, screen_papers, get_passed_pmids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_abstract(text: str) -> str:
    """Pad short text to exceed the 100-char minimum length requirement."""
    padding = " " * max(0, 101 - len(text))
    return text + padding


# ---------------------------------------------------------------------------
# has_genetic_content — basic acceptance / rejection
# ---------------------------------------------------------------------------

class TestHasGeneticContentBasic:

    def test_empty_abstract_rejected(self):
        ok, conf, det = has_genetic_content("", "Some title")
        assert ok is False
        assert conf == 0.0
        assert det["reason"] == "abstract_too_short"

    def test_none_abstract_rejected(self):
        ok, conf, det = has_genetic_content(None, "Title")
        assert ok is False
        assert det["reason"] == "abstract_too_short"

    def test_short_abstract_rejected(self):
        ok, conf, det = has_genetic_content("Too short.", "Title")
        assert ok is False
        assert det["reason"] == "abstract_too_short"
        assert det["length"] == len("Too short.")

    def test_genetic_abstract_accepted(self):
        abstract = _make_abstract(
            "We found a BRCA1 mutation and TP53 variant in our cohort. "
            "The p.Val600Glu polymorphism was associated with increased risk. "
            "Genotype analysis and sequencing confirmed the somatic deletion."
        )
        ok, conf, det = has_genetic_content(abstract, "Genetic study of cancer")
        assert ok is True
        assert conf > 0.0

    def test_non_genetic_abstract_rejected(self):
        abstract = _make_abstract(
            "This systematic review evaluated the cost-effectiveness of "
            "screening programs and quality of life outcomes in rehabilitation "
            "settings. Public health policy implications are discussed."
        )
        ok, conf, det = has_genetic_content(abstract, "Review of outcomes")
        assert ok is False


# ---------------------------------------------------------------------------
# has_genetic_content — scoring details
# ---------------------------------------------------------------------------

class TestScoringDetails:

    def test_positive_keywords_detected(self):
        abstract = _make_abstract(
            "The mutation in the SNP was confirmed by sequencing of the exon "
            "region, revealing a germline polymorphism and somatic variant."
        )
        ok, conf, det = has_genetic_content(abstract, "")
        # mutation(3) + snp(3) + sequencing(2) + exon(2) + germline(2) + polymorphism(3) + somatic(2) + variant(3)
        assert det["raw_score"] >= 15
        for kw in ["mutation", "snp", "sequencing", "exon"]:
            assert kw in det["positive_keywords"]

    def test_negative_keywords_subtract(self):
        abstract = _make_abstract(
            "This systematic review and meta-analysis provides an overview "
            "of genetic mutation studies."
        )
        _, _, det = has_genetic_content(abstract, "")
        assert "systematic review" in det["negative_keywords"]
        assert "meta-analysis" in det["negative_keywords"]
        # Each negative keyword costs -5, so raw_score should be reduced
        assert det["raw_score"] < 10

    def test_threshold_parameter(self):
        abstract = _make_abstract("The genetic mutation was found.")
        # With very high threshold the paper should be rejected
        ok_high, _, det_high = has_genetic_content(abstract, "", threshold=100)
        assert ok_high is False
        # With threshold=0 it should pass
        ok_low, _, det_low = has_genetic_content(abstract, "", threshold=0)
        assert ok_low is True
        # raw_score is the same regardless of threshold
        assert det_high["raw_score"] == det_low["raw_score"]


# ---------------------------------------------------------------------------
# Gene symbol pattern detection
# ---------------------------------------------------------------------------

class TestGeneSymbolDetection:

    def test_standard_gene_symbols(self):
        abstract = _make_abstract(
            "Mutations in BRCA1, TP53, and EGFR were detected."
        )
        _, _, det = has_genetic_content(abstract, "")
        found = det["gene_symbols_found"]
        assert "BRCA1" in found
        assert "TP53" in found
        assert "EGFR" not in found  # EGFR has no digits, doesn't match pattern

    def test_false_positive_filtering(self):
        abstract = _make_abstract(
            "HIV1 and COVID19 patients showed no H1N1 susceptibility. "
            "However BRCA2 was mutated."
        )
        _, _, det = has_genetic_content(abstract, "")
        found = det["gene_symbols_found"]
        assert "HIV1" not in found
        assert "COVID19" not in found
        assert "H1N1" not in found
        assert "BRCA2" in found

    def test_gene_symbols_add_score(self):
        abstract_no_genes = _make_abstract("A study on disease outcomes and prognosis.")
        abstract_with_genes = _make_abstract(
            "A study on BRCA1 and TP53 disease outcomes and prognosis."
        )
        _, _, det_no = has_genetic_content(abstract_no_genes, "")
        _, _, det_yes = has_genetic_content(abstract_with_genes, "")
        # Each unique gene symbol adds 2 points
        assert det_yes["raw_score"] > det_no["raw_score"]
        assert det_yes["gene_symbol_count"] >= 2

    def test_gene_symbols_in_title_counted(self):
        abstract = _make_abstract("General study about cancer outcomes.")
        _, _, det = has_genetic_content(abstract, "Role of KRAS4 in oncogenesis")
        assert det["gene_symbol_count"] >= 1


# ---------------------------------------------------------------------------
# Variant pattern detection
# ---------------------------------------------------------------------------

class TestVariantPatternDetection:

    def test_protein_notation(self):
        abstract = _make_abstract("The p.Val600Glu variant was pathogenic.")
        _, _, det = has_genetic_content(abstract, "")
        assert det["variant_count"] >= 1
        assert any("Val600Glu" in v for v in det["variant_patterns_found"])

    def test_cdna_notation(self):
        abstract = _make_abstract("We identified c.123A>G in the coding region.")
        _, _, det = has_genetic_content(abstract, "")
        assert det["variant_count"] >= 1

    def test_dbsnp_rsid(self):
        abstract = _make_abstract("The SNP rs12345678 was associated with risk.")
        _, _, det = has_genetic_content(abstract, "")
        assert det["variant_count"] >= 1
        assert any("rs12345678" in v for v in det["variant_patterns_found"])

    def test_single_letter_variant(self):
        abstract = _make_abstract("The L858R and T790M mutations confer resistance.")
        _, _, det = has_genetic_content(abstract, "")
        assert det["variant_count"] >= 2

    def test_variants_increase_score(self):
        abstract = _make_abstract(
            "Variants p.Val600Glu, rs12345678, and L858R were studied."
        )
        _, _, det = has_genetic_content(abstract, "")
        # Each variant adds 3 points
        assert det["variant_count"] >= 3
        assert det["raw_score"] >= 9  # At least 3 * 3 from variants alone


# ---------------------------------------------------------------------------
# Disease-gene phrase detection
# ---------------------------------------------------------------------------

class TestDiseaseGenePhrases:

    def test_phrases_detected(self):
        abstract = _make_abstract(
            "Mutations in BRCA1 associated with breast cancer. "
            "Overexpression of HER2 linked to poor prognosis. "
            "Loss of function variants in TP53."
        )
        _, _, det = has_genetic_content(abstract, "")
        phrases = det["disease_gene_phrases"]
        assert "associated with" in phrases
        assert "linked to" in phrases
        assert "mutations in" in phrases
        assert "overexpression of" in phrases
        assert "loss of" in phrases

    def test_each_phrase_adds_one_point(self):
        base = _make_abstract("A study about cancer.")
        with_phrases = _make_abstract(
            "A study about cancer associated with mutations in genes "
            "and overexpression of proteins."
        )
        _, _, det_base = has_genetic_content(base, "")
        _, _, det_phrases = has_genetic_content(with_phrases, "")
        phrase_count = len(det_phrases["disease_gene_phrases"])
        assert phrase_count >= 2
        # Score should be higher by at least the number of matched phrases
        assert det_phrases["raw_score"] >= det_base["raw_score"] + phrase_count


# ---------------------------------------------------------------------------
# Confidence score
# ---------------------------------------------------------------------------

class TestConfidenceScore:

    def test_confidence_between_zero_and_one(self):
        abstract = _make_abstract(
            "BRCA1 mutation variant polymorphism SNP genotype sequencing "
            "exon germline somatic deletion amplification methylation."
        )
        _, conf, _ = has_genetic_content(abstract, "")
        assert 0.0 <= conf <= 1.0

    def test_confidence_zero_for_rejected_no_positives(self):
        abstract = _make_abstract(
            "This editorial discusses the cost-effectiveness of screening "
            "programs for public health policy purposes."
        )
        _, conf, det = has_genetic_content(abstract, "")
        # Score <= 0 yields confidence 0.0
        if det["raw_score"] <= 0:
            assert conf == 0.0

    def test_confidence_capped_at_one(self):
        # Construct abstract with many strong signals to push score above max_score
        abstract = _make_abstract(
            "BRCA1 TP53 KRAS4 EGFR2 ALK3 ROS1 MET14 BRAF1 PIK3 PTEN2 "
            "mutation variant polymorphism SNP genotype allele sequencing "
            "exon germline somatic deletion amplification methylation genomic "
            "p.Val600Glu c.123A>G rs12345678 L858R T790M "
            "associated with mutations in variants in overexpression of "
            "linked to loss of alterations in downregulation of"
        )
        _, conf, _ = has_genetic_content(abstract, "")
        assert conf <= 1.0


# ---------------------------------------------------------------------------
# Negative keyword handling
# ---------------------------------------------------------------------------

class TestNegativeKeywords:

    def test_heavy_penalty_per_negative(self):
        abstract = _make_abstract("This is a systematic review of genetic mutations.")
        _, _, det = has_genetic_content(abstract, "")
        assert "systematic review" in det["negative_keywords"]
        # "mutation" gives +3, "genetic" gives +1, "systematic review" gives -5 => net -1
        assert det["raw_score"] < 5

    def test_multiple_negatives_stack(self):
        abstract = _make_abstract(
            "This systematic review and meta-analysis provides an overview "
            "of the economic burden and cost-effectiveness of treatments. "
            "A mutation was detected."
        )
        _, _, det = has_genetic_content(abstract, "")
        # Should have at least 3 negative matches
        assert len(det["negative_keywords"]) >= 3
        # Heavy penalties should make score very low
        assert det["raw_score"] < 0


# ---------------------------------------------------------------------------
# screen_papers batch function
# ---------------------------------------------------------------------------

class TestScreenPapers:

    def test_enriches_all_papers(self):
        papers = {
            "123": {
                "title": "BRCA1 mutations",
                "abstract": _make_abstract("The BRCA1 mutation and TP53 variant were studied with sequencing."),
            },
            "456": {
                "title": "Editorial",
                "abstract": _make_abstract("This editorial commentary discusses nursing and palliative care."),
            },
        }
        result = screen_papers(papers)
        assert "123" in result
        assert "456" in result
        for pmid, info in result.items():
            assert "screening_passed" in info
            assert "screening_confidence" in info
            assert "screening_details" in info

    def test_preserves_original_fields(self):
        papers = {
            "99": {
                "title": "Study",
                "abstract": _make_abstract("Genomic sequencing mutation variant allele SNP."),
                "year": 2024,
                "extra": "value",
            }
        }
        result = screen_papers(papers)
        assert result["99"]["year"] == 2024
        assert result["99"]["extra"] == "value"


# ---------------------------------------------------------------------------
# get_passed_pmids
# ---------------------------------------------------------------------------

class TestGetPassedPmids:

    def test_returns_only_passed(self):
        screened = {
            "1": {"screening_passed": True, "screening_confidence": 0.8},
            "2": {"screening_passed": False, "screening_confidence": 0.1},
            "3": {"screening_passed": True, "screening_confidence": 0.5},
        }
        result = get_passed_pmids(screened)
        assert "1" in result
        assert "3" in result
        assert "2" not in result

    def test_sorted_by_confidence_descending(self):
        screened = {
            "a": {"screening_passed": True, "screening_confidence": 0.3},
            "b": {"screening_passed": True, "screening_confidence": 0.9},
            "c": {"screening_passed": True, "screening_confidence": 0.6},
        }
        result = get_passed_pmids(screened)
        assert result == ["b", "c", "a"]

    def test_empty_input(self):
        assert get_passed_pmids({}) == []
