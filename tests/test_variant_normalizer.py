"""Unit tests for modules/variant_normalizer.py"""

import pytest
import pandas as pd

from modules.variant_normalizer import normalize_variant, normalize_variants_in_dataframe


# ---------------------------------------------------------------------------
# normalize_variant — empty / None input
# ---------------------------------------------------------------------------

class TestNormalizeVariantEmpty:

    def test_empty_string(self):
        assert normalize_variant("") == ""

    def test_none(self):
        assert normalize_variant(None) == ""

    def test_non_string(self):
        assert normalize_variant(123) == ""

    def test_whitespace_only(self):
        assert normalize_variant("   ") == ""


# ---------------------------------------------------------------------------
# normalize_variant — generic patterns filtered out
# ---------------------------------------------------------------------------

class TestGenericFiltering:

    def test_mutation(self):
        assert normalize_variant("MUTATION") == ""

    def test_mutations(self):
        assert normalize_variant("mutations") == ""

    def test_rare_deleterious_variant(self):
        assert normalize_variant("RARE DELETERIOUS MISSENSE VARIANT") == ""

    def test_pathogenic_variant(self):
        assert normalize_variant("pathogenic variant") == ""

    def test_truncating_mutation(self):
        assert normalize_variant("Truncating mutation") == ""

    def test_na(self):
        assert normalize_variant("N/A") == ""

    def test_na_lowercase(self):
        assert normalize_variant("na") == ""

    def test_none_string(self):
        assert normalize_variant("NONE") == ""

    def test_long_description(self):
        """More than 3 words is treated as a description."""
        assert normalize_variant("some long variant description text") == ""


# ---------------------------------------------------------------------------
# normalize_variant — insertion pattern
# ---------------------------------------------------------------------------

class TestInsertionPattern:

    def test_uppercase_insc(self):
        assert normalize_variant("5382INSC") == "c.5382insC"

    def test_lowercase_ins(self):
        assert normalize_variant("100insATG") == "c.100insATG"

    def test_mixed_case_ins(self):
        assert normalize_variant("200InsTGA") == "c.200insTGA"


# ---------------------------------------------------------------------------
# normalize_variant — deletion patterns
# ---------------------------------------------------------------------------

class TestDeletionPattern:

    def test_del_bases(self):
        assert normalize_variant("1100DELC") == "c.1100delC"

    def test_del_number(self):
        assert normalize_variant("6633DEL5") == "c.6633del5"

    def test_del_lowercase(self):
        assert normalize_variant("200del3") == "c.200del3"


# ---------------------------------------------------------------------------
# normalize_variant — protein single-letter to three-letter
# ---------------------------------------------------------------------------

class TestProteinNormalization:

    def test_p_i157t(self):
        assert normalize_variant("P.I157T") == "p.Ile157Thr"

    def test_p_v600e(self):
        assert normalize_variant("p.V600E") == "p.Val600Glu"

    def test_p_r175h(self):
        assert normalize_variant("p.R175H") == "p.Arg175His"

    def test_all_amino_acids(self):
        """Verify each single-letter amino acid maps correctly."""
        expected = {
            'A': 'Ala', 'R': 'Arg', 'N': 'Asn', 'D': 'Asp', 'C': 'Cys',
            'Q': 'Gln', 'E': 'Glu', 'G': 'Gly', 'H': 'His', 'I': 'Ile',
            'L': 'Leu', 'K': 'Lys', 'M': 'Met', 'F': 'Phe', 'P': 'Pro',
            'S': 'Ser', 'T': 'Thr', 'W': 'Trp', 'Y': 'Tyr', 'V': 'Val',
        }
        for letter, three in expected.items():
            # p.X100Y pattern
            result = normalize_variant(f"p.{letter}100A")
            assert result.startswith(f"p.{three}100"), f"Failed for {letter}"


# ---------------------------------------------------------------------------
# normalize_variant — semicolon-separated variants
# ---------------------------------------------------------------------------

class TestSemicolonSeparated:

    def test_first_valid_returned(self):
        result = normalize_variant("1100DELC; P.I157T")
        # First part normalizes to "c.1100delC"
        assert result == "c.1100delC"

    def test_skips_generic_takes_second(self):
        result = normalize_variant("MUTATION; P.V600E")
        # MUTATION -> "", P.V600E -> "p.Val600Glu"
        assert result == "p.Val600Glu"

    def test_all_generic_returns_empty(self):
        result = normalize_variant("MUTATION; N/A")
        assert result == ""


# ---------------------------------------------------------------------------
# normalize_variant — already HGVS (pass-through)
# ---------------------------------------------------------------------------

class TestHGVSPassthrough:

    def test_c_dot(self):
        assert normalize_variant("c.1234A>G") == "c.1234A>G"

    def test_g_dot(self):
        assert normalize_variant("g.5678T>C") == "g.5678T>C"

    def test_p_dot_three_letter(self):
        # Already three-letter format — the regex p.X100Y won't match
        # because these are lowercase three-letter, so it hits the HGVS passthrough
        assert normalize_variant("p.Arg175His") == "p.Arg175His"

    def test_rs_id(self):
        assert normalize_variant("rs12345") == "rs12345"

    def test_rs_id_uppercase(self):
        assert normalize_variant("RS12345") == "RS12345"

    def test_amino_acid_simple(self):
        """Single-letter amino acid substitution like V600E."""
        assert normalize_variant("V600E") == "V600E"

    def test_l858r(self):
        assert normalize_variant("L858R") == "L858R"


# ---------------------------------------------------------------------------
# normalize_variant — short non-matching strings returned as-is
# ---------------------------------------------------------------------------

class TestShortNonMatching:

    def test_two_word_unknown(self):
        """2-3 words that don't match any pattern are returned as-is."""
        result = normalize_variant("exon skip")
        assert result == "exon skip"

    def test_single_word_unknown(self):
        result = normalize_variant("XYZ")
        assert result == "XYZ"


# ---------------------------------------------------------------------------
# normalize_variants_in_dataframe
# ---------------------------------------------------------------------------

class TestDataFrameNormalization:

    def test_normalizes_column(self):
        df = pd.DataFrame({"Variant Name": ["5382INSC", "MUTATION", "rs12345"]})
        normalize_variants_in_dataframe(df)
        assert df["Variant Name"].tolist() == ["c.5382insC", "", "rs12345"]

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["Variant Name"])
        normalize_variants_in_dataframe(df)  # Should not raise
        assert df.empty

    def test_missing_column(self):
        df = pd.DataFrame({"Other": ["value"]})
        normalize_variants_in_dataframe(df)  # Should not raise
        assert "Variant Name" not in df.columns

    def test_modifies_in_place(self):
        df = pd.DataFrame({"Variant Name": ["P.V600E"]})
        normalize_variants_in_dataframe(df)
        assert df["Variant Name"].iloc[0] == "p.Val600Glu"
