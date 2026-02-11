"""Unit tests for modules/paper_ranker.py"""

import math
import pytest
from datetime import datetime
from unittest.mock import patch

from modules.paper_ranker import (
    compute_citation_score,
    compute_journal_score,
    compute_recency_score,
    compute_study_type_score,
    compute_availability_score,
    compute_relevance_score,
    rank_papers,
    PaperQualityScore,
    DEFAULT_WEIGHTS,
    _load_journal_tiers,
)


CURRENT_YEAR = datetime.now().year


# ---------------------------------------------------------------------------
# compute_citation_score
# ---------------------------------------------------------------------------

class TestComputeCitationScore:

    def test_zero_citations(self):
        assert compute_citation_score(0, CURRENT_YEAR) == 0.0

    def test_negative_citations_treated_as_zero(self):
        assert compute_citation_score(-5, CURRENT_YEAR) == 0.0

    def test_high_citations_capped_at_one(self):
        # 1000 citations in the current year => cpy = 1000/1 = 1000, score = 1.0
        assert compute_citation_score(1000, CURRENT_YEAR) == 1.0

    def test_exact_field_average(self):
        # 20 cit/year => score = 1.0
        score = compute_citation_score(20, CURRENT_YEAR)
        assert score == 1.0

    def test_half_field_average(self):
        # 10 cit in 1 year => 10/20 = 0.5
        score = compute_citation_score(10, CURRENT_YEAR)
        assert score == 0.5

    def test_old_paper_normalised_by_age(self):
        # 40 citations, published 2 years ago => years_since=2, cpy=20 => score=1.0
        score = compute_citation_score(40, CURRENT_YEAR - 2)
        assert score == 1.0

    def test_result_in_range(self):
        score = compute_citation_score(5, CURRENT_YEAR - 3)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# compute_journal_score
# ---------------------------------------------------------------------------

class TestComputeJournalScore:

    def test_tier1_exact_match(self):
        score = compute_journal_score("Nature")
        assert score == 1.0

    def test_tier1_case_insensitive(self):
        score = compute_journal_score("nature")
        assert score == 1.0

    def test_tier2_exact(self):
        score = compute_journal_score("Blood")
        assert score == 0.85

    def test_tier3_exact(self):
        score = compute_journal_score("Oncogene")
        assert score == 0.70

    def test_tier4_exact(self):
        score = compute_journal_score("PLoS ONE")
        assert score == 0.55

    def test_unknown_journal_returns_default(self):
        score = compute_journal_score("Journal of Obscure Studies")
        assert score == 0.30

    def test_empty_journal_returns_default(self):
        score = compute_journal_score("")
        assert score == 0.30

    def test_none_journal_returns_default(self):
        # The function checks `if not journal_name`
        score = compute_journal_score(None)
        assert score == 0.30

    def test_substring_match(self):
        # "The New England Journal of Medicine" contains "new england journal of medicine"
        score = compute_journal_score("The New England Journal of Medicine")
        assert score == 1.0

    def test_whitespace_stripped(self):
        score = compute_journal_score("  Nature  ")
        assert score == 1.0


# ---------------------------------------------------------------------------
# compute_recency_score
# ---------------------------------------------------------------------------

class TestComputeRecencyScore:

    def test_current_year(self):
        assert compute_recency_score(CURRENT_YEAR) == 1.0

    def test_one_year_ago(self):
        assert compute_recency_score(CURRENT_YEAR - 1) == 1.0

    def test_two_years_ago(self):
        assert compute_recency_score(CURRENT_YEAR - 2) == 1.0

    def test_three_years_ago_starts_decay(self):
        score = compute_recency_score(CURRENT_YEAR - 3)
        expected = round(math.exp(-0.1 * 1), 4)
        assert score == expected
        assert score < 1.0

    def test_ten_years_ago(self):
        score = compute_recency_score(CURRENT_YEAR - 10)
        expected = round(math.exp(-0.1 * 8), 4)
        assert score == expected

    def test_very_old_paper_floor(self):
        score = compute_recency_score(1950)
        assert score >= 0.05

    def test_future_year_returns_one(self):
        assert compute_recency_score(CURRENT_YEAR + 5) == 1.0

    def test_result_always_positive(self):
        for yr in range(1900, CURRENT_YEAR + 1, 10):
            assert compute_recency_score(yr) > 0


# ---------------------------------------------------------------------------
# compute_study_type_score
# ---------------------------------------------------------------------------

class TestComputeStudyTypeScore:

    def test_meta_analysis_pub_type(self):
        score = compute_study_type_score("Title", "abstract", ["Meta-Analysis"])
        assert score == 1.0

    def test_rct_pub_type(self):
        score = compute_study_type_score("Title", "abstract",
                                         ["Randomized Controlled Trial"])
        assert score == 0.9

    def test_case_report_pub_type(self):
        score = compute_study_type_score("Title", "abstract", ["Case Reports"])
        assert score == 0.5

    def test_editorial_pub_type(self):
        score = compute_study_type_score("Title", "abstract", ["Editorial"])
        assert score == 0.3

    def test_keyword_fallback_cohort(self):
        score = compute_study_type_score(
            "Cohort study of diabetes",
            "This prospective cohort analysis...",
            [],
        )
        assert score == 0.8

    def test_keyword_fallback_systematic_review(self):
        score = compute_study_type_score(
            "Title",
            "This systematic review examines...",
            [],
        )
        assert score == 0.6

    def test_default_original_research(self):
        score = compute_study_type_score("Generic title", "Generic abstract", [])
        assert score == 0.75

    def test_none_pub_types(self):
        score = compute_study_type_score("Title", "Abstract text", None)
        assert score == 0.75

    def test_pub_type_takes_precedence_over_keyword(self):
        # Even though abstract mentions "review", the pub_type "Meta-Analysis" wins
        score = compute_study_type_score(
            "Title",
            "This review discusses...",
            ["Meta-Analysis"],
        )
        assert score == 1.0

    def test_case_insensitive_pub_type(self):
        score = compute_study_type_score("Title", "text", ["meta-analysis"])
        assert score == 1.0


# ---------------------------------------------------------------------------
# compute_availability_score
# ---------------------------------------------------------------------------

class TestComputeAvailabilityScore:

    def test_pmc_available(self):
        assert compute_availability_score(pmc_available=True) == 1.0

    def test_pmc_trumps_everything(self):
        assert compute_availability_score(
            pmc_available=True, doi="10.1/x", oa_status="gold"
        ) == 1.0

    def test_gold_oa(self):
        assert compute_availability_score(oa_status="gold") == 0.8

    def test_green_oa(self):
        assert compute_availability_score(oa_status="green") == 0.8

    def test_hybrid_oa(self):
        assert compute_availability_score(oa_status="hybrid") == 0.8

    def test_bronze_oa(self):
        assert compute_availability_score(oa_status="bronze") == 0.8

    def test_oa_case_insensitive(self):
        assert compute_availability_score(oa_status="Gold") == 0.8

    def test_doi_only(self):
        assert compute_availability_score(doi="10.1234/test") == 0.5

    def test_nothing_available(self):
        assert compute_availability_score() == 0.2

    def test_unknown_oa_status_with_doi(self):
        assert compute_availability_score(doi="10.1/x", oa_status="closed") == 0.5

    def test_unknown_oa_status_no_doi(self):
        assert compute_availability_score(oa_status="closed") == 0.2


# ---------------------------------------------------------------------------
# compute_relevance_score
# ---------------------------------------------------------------------------

class TestComputeRelevanceScore:

    def test_no_query_no_rank(self):
        score = compute_relevance_score("Title", "Abstract")
        assert score == 0.0

    def test_rank_only(self):
        score = compute_relevance_score(
            "Title", "Abstract", rank_position=1, total_results=10
        )
        # rank_score = 1 - 0/10 = 1.0, component = 0.5 * 1.0 = 0.5
        assert score == 0.5

    def test_last_rank(self):
        score = compute_relevance_score(
            "Title", "Abstract", rank_position=10, total_results=10
        )
        # rank_score = 1 - 9/10 = 0.1, component = 0.5 * 0.1 = 0.05
        assert score == 0.05

    def test_keyword_overlap_full_match(self):
        score = compute_relevance_score(
            "cancer genetics", "BRCA1 mutation analysis",
            query="cancer genetics BRCA1 mutation",
        )
        # All 4 tokens match => 0.5 * 1.0 = 0.5
        assert score == 0.5

    def test_keyword_overlap_partial_match(self):
        score = compute_relevance_score(
            "cancer study", "general text",
            query="cancer genetics BRCA1",
        )
        # "cancer" matches (1/3) => 0.5 * 0.333 ~= 0.1667
        assert 0.1 < score < 0.2

    def test_stop_words_excluded(self):
        score = compute_relevance_score(
            "the cancer", "abstract",
            query="the and or cancer",
        )
        # Only "cancer" remains after stop-word removal => 1/1 = 1.0 => 0.5
        assert score == 0.5

    def test_combined_rank_and_keyword(self):
        score = compute_relevance_score(
            "cancer genetics", "BRCA1 mutation",
            query="cancer genetics BRCA1 mutation",
            rank_position=1, total_results=10,
        )
        # rank component: 0.5, keyword: 0.5 => 1.0
        assert score == 1.0

    def test_result_capped_at_one(self):
        score = compute_relevance_score(
            "cancer genetics", "BRCA1 mutation",
            query="cancer genetics BRCA1 mutation",
            rank_position=1, total_results=1,
        )
        assert score <= 1.0


# ---------------------------------------------------------------------------
# rank_papers — integration of all scoring
# ---------------------------------------------------------------------------

class TestRankPapers:

    def test_empty_input(self):
        assert rank_papers([]) == []

    def test_single_paper(self):
        papers = [{"pmid": "1", "title": "Test", "abstract": "test"}]
        result = rank_papers(papers)
        assert len(result) == 1
        assert isinstance(result[0], PaperQualityScore)
        assert result[0].pmid == "1"

    def test_ordering_descending(self):
        papers = [
            {
                "pmid": "low",
                "citations": 0,
                "year": 1990,
                "journal": "Unknown Journal XYZ",
                "title": "Editorial",
                "abstract": "A letter to the editor.",
                "pub_types": ["Editorial"],
            },
            {
                "pmid": "high",
                "citations": 200,
                "year": CURRENT_YEAR,
                "journal": "Nature",
                "title": "RCT of BRCA1",
                "abstract": "A randomized controlled trial.",
                "pub_types": ["Randomized Controlled Trial"],
                "pmc_available": True,
            },
        ]
        result = rank_papers(papers)
        assert result[0].pmid == "high"
        assert result[1].pmid == "low"
        assert result[0].composite_score > result[1].composite_score

    def test_custom_weights(self):
        papers = [{"pmid": "1", "citations": 100, "year": CURRENT_YEAR, "journal": "Nature"}]
        # Weight citation at 1.0, everything else 0
        custom = {
            "citation": 1.0,
            "journal": 0.0,
            "recency": 0.0,
            "study_type": 0.0,
            "availability": 0.0,
            "relevance": 0.0,
        }
        result = rank_papers(papers, weights=custom)
        assert result[0].composite_score == result[0].citation_score

    def test_missing_fields_use_defaults(self):
        # Paper with absolutely no fields besides pmid
        papers = [{"pmid": "bare"}]
        result = rank_papers(papers)
        assert len(result) == 1
        assert result[0].pmid == "bare"
        # Should not crash — all defaults kick in
        assert result[0].composite_score >= 0

    def test_alternative_field_names(self):
        papers = [
            {
                "pmid": "alt",
                "citation_count": 50,
                "pub_year": CURRENT_YEAR - 1,
                "journal_title": "Nature",
            }
        ]
        result = rank_papers(papers)
        assert result[0].citation_score > 0
        assert result[0].journal_score == 1.0

    def test_explanation_populated(self):
        papers = [{"pmid": "1"}]
        result = rank_papers(papers)
        assert "cit=" in result[0].explanation
        assert "jnl=" in result[0].explanation

    def test_query_affects_relevance(self):
        papers = [
            {"pmid": "1", "title": "cancer genetics", "abstract": "BRCA1 mutation"},
        ]
        no_query = rank_papers(papers, query="")
        with_query = rank_papers(papers, query="cancer genetics BRCA1 mutation")
        assert with_query[0].relevance_score > no_query[0].relevance_score

    def test_three_papers_sorted(self):
        papers = [
            {"pmid": "A", "citations": 0, "year": 1980, "journal": "Unknown"},
            {"pmid": "B", "citations": 100, "year": CURRENT_YEAR, "journal": "Nature", "pmc_available": True},
            {"pmid": "C", "citations": 20, "year": CURRENT_YEAR - 1, "journal": "Blood"},
        ]
        result = rank_papers(papers)
        scores = [r.composite_score for r in result]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Journal tier lookup (_load_journal_tiers)
# ---------------------------------------------------------------------------

class TestJournalTierLookup:

    def test_tiers_loaded(self):
        # Reset cache to force reload
        import modules.paper_ranker as pr
        pr._journal_tier_cache = None
        lookup = _load_journal_tiers()
        assert len(lookup) > 0
        # All keys should be lowercase
        for key in lookup:
            assert key == key.lower()

    def test_tier_scores_present(self):
        lookup = _load_journal_tiers()
        assert lookup.get("nature") == 1.0
        assert lookup.get("blood") == 0.85
        assert lookup.get("oncogene") == 0.70
        assert lookup.get("plos one") == 0.55
