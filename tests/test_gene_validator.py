"""Unit tests for modules/gene_validator.py"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from modules.gene_validator import (
    GeneValidator,
    GeneValidationResult,
    validate_extracted_genes,
    CitationValidationResult,
    ContextWindowValidator,
    validate_paper_context_fit,
    validate_citations,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def validator():
    """Create a GeneValidator with the real local HGNC database."""
    return GeneValidator()


@pytest.fixture
def validator_no_db():
    """Create a GeneValidator with empty local database."""
    v = GeneValidator()
    v._local_gene_db = {}
    v._gene_cache = {}
    # Clear the lru_cache so it doesn't use stale results
    v._validate_gene_hgnc.cache_clear()
    return v


# ---------------------------------------------------------------------------
# GeneValidationResult dataclass
# ---------------------------------------------------------------------------

class TestGeneValidationResult:

    def test_fields(self):
        r = GeneValidationResult(
            gene="BRCA1",
            variant="p.Arg175His",
            is_valid_gene=True,
            is_valid_variant=True,
            confidence_score=1.0,
            validation_source="HGNC_local",
            suggestions=[],
        )
        assert r.gene == "BRCA1"
        assert r.variant == "p.Arg175His"
        assert r.is_valid_gene is True
        assert r.is_valid_variant is True
        assert r.confidence_score == 1.0
        assert r.suggestions == []

    def test_suggestions_default_none(self):
        r = GeneValidationResult(
            gene="X", variant="", is_valid_gene=False,
            is_valid_variant=False, confidence_score=0.0,
            validation_source="none",
        )
        assert r.suggestions is None


# ---------------------------------------------------------------------------
# GeneValidator — local HGNC validation
# ---------------------------------------------------------------------------

class TestLocalHGNCValidation:

    def test_known_gene_brca1(self, validator):
        """BRCA1 must be present in the local HGNC database."""
        result = validator.validate_gene_variant("BRCA1")
        assert result.is_valid_gene is True
        assert "HGNC_local" in result.validation_source

    def test_known_gene_tp53(self, validator):
        result = validator.validate_gene_variant("TP53")
        assert result.is_valid_gene is True

    def test_known_gene_case_insensitive(self, validator):
        result = validator.validate_gene_variant("brca1")
        assert result.is_valid_gene is True

    def test_unknown_gene(self, validator):
        """A clearly fake gene should not validate locally."""
        result = validator.validate_gene_variant("ZZZZFAKEGENE999")
        assert result.is_valid_gene is False

    def test_short_gene_rejected(self, validator):
        """Single character gene names are rejected."""
        result = validator.validate_gene_variant("A")
        assert result.is_valid_gene is False

    def test_empty_gene_rejected(self, validator):
        result = validator.validate_gene_variant("")
        assert result.is_valid_gene is False

    def test_gene_only_confidence_is_one(self, validator):
        """Valid gene with no variant should get confidence 1.0."""
        result = validator.validate_gene_variant("BRCA1")
        assert result.confidence_score == 1.0

    def test_gene_only_variant_true(self, validator):
        """When no variant is specified, is_valid_variant defaults to True."""
        result = validator.validate_gene_variant("BRCA1")
        assert result.is_valid_variant is True

    def test_invalid_gene_confidence_zero(self, validator):
        result = validator.validate_gene_variant("NOTAREALGENE")
        assert result.confidence_score == 0.0


# ---------------------------------------------------------------------------
# GeneValidator — variant validation
# ---------------------------------------------------------------------------

class TestVariantValidation:

    def test_hgvs_protein_variant(self, validator):
        # Regex expects p.Xxx000X? (three-letter + digits + optional single uppercase)
        result = validator.validate_gene_variant("BRCA1", "p.Arg175H")
        assert result.is_valid_variant is True
        assert "hgvs_protein" in result.validation_source

    def test_hgvs_coding_variant(self, validator):
        result = validator.validate_gene_variant("TP53", "c.123A>G")
        assert result.is_valid_variant is True
        assert "hgvs_coding" in result.validation_source

    def test_hgvs_genomic_variant(self, validator):
        result = validator.validate_gene_variant("EGFR", "g.456T>C")
        assert result.is_valid_variant is True

    def test_dbsnp_rsid(self, validator):
        result = validator.validate_gene_variant("BRCA2", "rs12345")
        assert result.is_valid_variant is True
        assert "dbsnp_rsid" in result.validation_source

    def test_amino_acid_substitution(self, validator):
        result = validator.validate_gene_variant("BRAF", "V600E")
        assert result.is_valid_variant is True

    def test_exon_deletion(self, validator):
        result = validator.validate_gene_variant("BRCA1", "exon 5 deletion")
        assert result.is_valid_variant is True

    def test_splice_site(self, validator):
        result = validator.validate_gene_variant("BRCA1", "IVS3+1")
        assert result.is_valid_variant is True

    def test_invalid_variant(self, validator):
        result = validator.validate_gene_variant("BRCA1", "notavariant!!!")
        assert result.is_valid_variant is False

    def test_empty_variant(self, validator):
        result = validator.validate_gene_variant("BRCA1", "")
        # Empty variant is treated as "no variant specified" => True
        assert result.is_valid_variant is True

    def test_valid_gene_valid_variant_confidence(self, validator):
        """Valid gene + valid variant => 0.7 + 0.3 = 1.0."""
        result = validator.validate_gene_variant("BRCA1", "c.123A>G")
        assert result.confidence_score == pytest.approx(1.0)

    def test_valid_gene_invalid_variant_confidence(self, validator):
        """Valid gene + invalid variant => 0.7."""
        result = validator.validate_gene_variant("BRCA1", "badvariant")
        assert result.confidence_score == pytest.approx(0.7)

    def test_invalid_gene_valid_variant_confidence(self, validator):
        """Invalid gene + valid variant => 0.3."""
        result = validator.validate_gene_variant("NOTREAL", "rs12345")
        assert result.confidence_score == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# GeneValidator — variant patterns compilation
# ---------------------------------------------------------------------------

class TestVariantPatterns:

    def test_patterns_compiled(self, validator):
        patterns = validator.variant_patterns
        assert "hgvs_protein" in patterns
        assert "hgvs_coding" in patterns
        assert "hgvs_genomic" in patterns
        assert "dbsnp_rsid" in patterns
        assert "amino_acid_substitution" in patterns
        assert "exon_deletion" in patterns
        assert "splice_site" in patterns

    def test_frameshift_pattern(self, validator):
        valid, name = validator._is_valid_variant("fs123")
        assert valid is True
        assert name == "frameshift"

    def test_nonsense_pattern(self, validator):
        valid, name = validator._is_valid_variant("X42")
        assert valid is True
        assert name == "nonsense"


# ---------------------------------------------------------------------------
# GeneValidator — alias resolution
# ---------------------------------------------------------------------------

class TestAliasResolution:

    def test_alias_resolves(self, validator):
        """A1CF has alias 'ACF' — querying ACF should resolve to A1CF."""
        # ACF is an alias_symbol for A1CF in the HGNC DB
        result = validator.validate_gene_variant("ACF")
        assert result.is_valid_gene is True

    def test_prev_symbol_resolves(self, validator):
        """Previous symbols should also resolve."""
        # NCRNA00181 is a prev_symbol for A1BG-AS1
        result = validator.validate_gene_variant("NCRNA00181")
        assert result.is_valid_gene is True


# ---------------------------------------------------------------------------
# GeneValidator — gene caching
# ---------------------------------------------------------------------------

class TestGeneCaching:

    def test_cache_hit(self, validator):
        """Second lookup should use the cache."""
        validator.validate_gene_variant("BRCA1")
        assert "BRCA1" in validator._gene_cache
        # Second call should still work
        result = validator.validate_gene_variant("BRCA1")
        assert result.is_valid_gene is True


# ---------------------------------------------------------------------------
# GeneValidator — validate_associations
# ---------------------------------------------------------------------------

class TestValidateAssociations:

    def test_tuple_format(self, validator):
        assocs = [("BRCA1", "p.Arg175His"), ("TP53", "")]
        results = validator.validate_associations(assocs)
        assert len(results) == 2
        assert results[0].is_valid_gene is True
        assert results[1].is_valid_gene is True

    def test_dict_format(self, validator):
        assocs = [
            {"gene": "BRCA1", "variant": "p.Arg175His"},
            {"gene": "TP53", "variant": "N/A"},
        ]
        results = validator.validate_associations(assocs)
        assert len(results) == 2
        # N/A should be normalized to empty
        assert results[1].variant == ""

    def test_dict_na_variants(self, validator):
        for placeholder in ["N/A", "NA", "NONE", "None", "n/a"]:
            assocs = [{"gene": "BRCA1", "variant": placeholder}]
            results = validator.validate_associations(assocs)
            assert results[0].variant == ""


# ---------------------------------------------------------------------------
# GeneValidator — filter_valid_associations
# ---------------------------------------------------------------------------

class TestFilterValidAssociations:

    def test_filters_below_threshold(self, validator):
        assocs = [("BRCA1", ""), ("ZZZZNOTREAL", "")]
        filtered = validator.filter_valid_associations(assocs, min_confidence=0.7)
        # BRCA1 confidence=1.0, fake gene confidence=0.0
        assert len(filtered) == 1
        assert filtered[0] == ("BRCA1", "")

    def test_custom_threshold(self, validator):
        assocs = [("BRCA1", "badvariant")]  # confidence = 0.7
        filtered = validator.filter_valid_associations(assocs, min_confidence=0.8)
        assert len(filtered) == 0

    def test_all_valid(self, validator):
        assocs = [("BRCA1", ""), ("TP53", "")]
        filtered = validator.filter_valid_associations(assocs, min_confidence=0.5)
        assert len(filtered) == 2


# ---------------------------------------------------------------------------
# GeneValidator — API fallback (mocked network)
# ---------------------------------------------------------------------------

class TestAPIFallback:

    @patch("modules.gene_validator.GeneValidator._validate_gene_mygene")
    @patch("modules.gene_validator.GeneValidator._validate_gene_hgnc")
    def test_mygene_fallback(self, mock_hgnc, mock_mygene, validator_no_db):
        """When local DB and HGNC API fail, fall back to MyGene.info."""
        mock_hgnc.return_value = None
        mock_mygene.return_value = {
            "symbol": "SOMEGENE",
            "name": "Some gene",
            "source": "MyGene.info",
        }
        result = validator_no_db.validate_gene_variant("SOMEGENE")
        assert result.is_valid_gene is True
        assert "MyGene.info" in result.validation_source

    @patch("modules.gene_validator.GeneValidator._fuzzy_match_gene")
    @patch("modules.gene_validator.GeneValidator._validate_gene_mygene")
    @patch("modules.gene_validator.GeneValidator._validate_gene_hgnc")
    def test_fuzzy_match_suggestions(self, mock_hgnc, mock_mygene, mock_fuzzy, validator_no_db):
        mock_hgnc.return_value = None
        mock_mygene.return_value = None
        mock_fuzzy.return_value = ["BRCA1", "BRCA2"]
        result = validator_no_db.validate_gene_variant("BRCAX")
        assert result.is_valid_gene is False
        assert result.suggestions == ["BRCA1", "BRCA2"]
        assert "fuzzy_match" in result.validation_source


# ---------------------------------------------------------------------------
# validate_extracted_genes (DataFrame integration)
# ---------------------------------------------------------------------------

class TestValidateExtractedGenes:

    def test_adds_validation_columns(self, validator):
        df = pd.DataFrame({
            "gene": ["BRCA1", "TP53"],
            "variant": ["p.Arg175His", ""],
        })
        result_df = validate_extracted_genes(df, validator=validator)
        assert "gene_valid" in result_df.columns
        assert "variant_valid" in result_df.columns
        assert "validation_confidence" in result_df.columns
        assert "validation_source" in result_df.columns
        assert "validation_suggestions" in result_df.columns

    def test_brca1_valid_in_df(self, validator):
        df = pd.DataFrame({"gene": ["BRCA1"], "variant": [""]})
        result_df = validate_extracted_genes(df, validator=validator)
        assert result_df.iloc[0]["gene_valid"] == True

    def test_empty_dataframe(self, validator):
        df = pd.DataFrame(columns=["gene", "variant"])
        result_df = validate_extracted_genes(df, validator=validator)
        assert result_df.empty

    def test_creates_default_validator(self):
        """When no validator is passed, one is created internally."""
        df = pd.DataFrame({"gene": ["BRCA1"], "variant": [""]})
        result_df = validate_extracted_genes(df)
        assert "gene_valid" in result_df.columns

    def test_does_not_modify_original(self, validator):
        df = pd.DataFrame({"gene": ["BRCA1"], "variant": [""]})
        original_cols = list(df.columns)
        validate_extracted_genes(df, validator=validator)
        assert list(df.columns) == original_cols


# ---------------------------------------------------------------------------
# ContextWindowValidator
# ---------------------------------------------------------------------------

class TestContextWindowValidator:

    def test_estimate_token_count_empty(self):
        assert ContextWindowValidator.estimate_token_count("") == 0

    def test_estimate_token_count(self):
        text = "word " * 100  # 100 words
        tokens = ContextWindowValidator.estimate_token_count(text)
        assert tokens == 75  # 100 * 0.75

    def test_check_context_fit_flash(self):
        fits, tokens, limit = ContextWindowValidator.check_context_fit("hello world", "flash")
        assert fits is True
        assert limit == int(1_000_000 * 0.9)

    def test_check_context_fit_pro(self):
        fits, tokens, limit = ContextWindowValidator.check_context_fit("hello world", "pro")
        assert fits is True
        assert limit == int(2_000_000 * 0.9)


# ---------------------------------------------------------------------------
# validate_paper_context_fit
# ---------------------------------------------------------------------------

class TestValidatePaperContextFit:

    def test_short_text_fits(self):
        result = validate_paper_context_fit("short text", "flash")
        assert result["fits"] is True
        assert result["skip_paper"] is False
        assert 0.0 <= result["utilization"] <= 1.0

    def test_result_keys(self):
        result = validate_paper_context_fit("some text", "pro")
        assert "fits" in result
        assert "estimated_tokens" in result
        assert "token_limit" in result
        assert "utilization" in result
        assert "skip_paper" in result


# ---------------------------------------------------------------------------
# Citation validation
# ---------------------------------------------------------------------------

class TestCitationValidation:

    def test_citation_found_in_paper(self):
        ai_response = {
            "finding": 'The gene was mutated. Citation: "The BRCA1 gene showed a frameshift mutation in exon 11"'
        }
        paper_text = "In our cohort, the BRCA1 gene showed a frameshift mutation in exon 11 of the coding region."
        results = validate_citations(ai_response, paper_text)
        assert len(results) == 1
        assert results[0].citation_exists is True
        assert results[0].confidence_score > 0.0

    def test_citation_not_found(self):
        ai_response = {
            "finding": 'Result. Citation: "This text does not appear anywhere in the paper at all whatsoever"'
        }
        paper_text = "Completely different paper content about something else entirely."
        results = validate_citations(ai_response, paper_text)
        assert len(results) == 1
        assert results[0].citation_exists is False
        assert results[0].confidence_score == 0.0

    def test_no_citation_in_response(self):
        ai_response = {"finding": "Just a plain answer with no citation."}
        paper_text = "Some paper text."
        results = validate_citations(ai_response, paper_text)
        assert len(results) == 1
        assert results[0].provided_citation == ""
        assert results[0].citation_exists is False

    def test_empty_response(self):
        ai_response = {"field": ""}
        results = validate_citations(ai_response, "paper text")
        assert len(results) == 1
        assert results[0].provided_citation == ""
