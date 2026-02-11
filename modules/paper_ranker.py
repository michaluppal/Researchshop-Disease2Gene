"""
Paper Quality Ranking Module

Scores and ranks papers based on multiple quality signals: citation count,
journal tier, recency, study type, full-text availability, and query relevance.
Produces a composite quality score used to prioritise papers for downstream analysis.
"""

import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level lazy cache for journal tier data
# ---------------------------------------------------------------------------
_journal_tier_cache: Optional[Dict[str, float]] = None


def _load_journal_tiers() -> Dict[str, float]:
    """Load and flatten journal_tiers.json into a {normalised_name: score} map.

    The file is read once and cached at module level for the lifetime of the
    process.  Journal names are lower-cased for case-insensitive lookup.
    """
    global _journal_tier_cache
    if _journal_tier_cache is not None:
        return _journal_tier_cache

    tiers_path = Path(__file__).parent.parent / "data" / "reference" / "journal_tiers.json"

    lookup: Dict[str, float] = {}
    if tiers_path.exists():
        try:
            with open(tiers_path, "r") as f:
                tiers_data = json.load(f)
            for tier_key, tier_info in tiers_data.items():
                score = tier_info.get("score", 0.30)
                for journal in tier_info.get("journals", []):
                    lookup[journal.lower()] = score
            logger.info(
                "Loaded journal tier data: %d journals across %d tiers",
                len(lookup),
                len(tiers_data),
            )
        except Exception as e:
            logger.warning("Failed to load journal tiers from %s: %s", tiers_path, e)
    else:
        logger.warning("Journal tiers file not found at %s", tiers_path)

    _journal_tier_cache = lookup
    return _journal_tier_cache


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class PaperQualityScore:
    """Composite quality score for a single paper."""

    pmid: str
    composite_score: float = 0.0
    citation_score: float = 0.0
    journal_score: float = 0.0
    recency_score: float = 0.0
    study_type_score: float = 0.0
    availability_score: float = 0.0
    relevance_score: float = 0.0
    explanation: str = ""


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def compute_citation_score(citations: int, year: int) -> float:
    """Normalise citation count by field average, adjusted for publication age.

    Papers accumulate citations over time, so raw counts are misleading.
    We compute *citations per year* and normalise against an approximate
    field average of ~20 citations/year for a well-cited biomedical paper.

    Args:
        citations: Raw citation count.
        year: Publication year (four-digit integer).

    Returns:
        Score in [0.0, 1.0].
    """
    if citations < 0:
        citations = 0

    current_year = datetime.now().year
    years_since = max(current_year - year, 1)
    citations_per_year = citations / years_since

    # Normalise against field average (~20 cit/year)
    field_avg = 20.0
    score = min(citations_per_year / field_avg, 1.0)
    return round(score, 4)


def compute_journal_score(journal_name: str) -> float:
    """Look up journal quality tier.

    Args:
        journal_name: Full journal name as it appears in PubMed metadata.

    Returns:
        Tier score (1.0 for tier-1, down to 0.30 for unknown journals).
    """
    if not journal_name:
        return 0.30

    lookup = _load_journal_tiers()
    normalised = journal_name.strip().lower()

    # Exact match first
    if normalised in lookup:
        return lookup[normalised]

    # Substring match — handle cases like "The New England Journal of Medicine"
    for known_name, score in lookup.items():
        if known_name in normalised or normalised in known_name:
            return score

    return 0.30  # Default: tier 5


def compute_recency_score(year: int) -> float:
    """Exponential decay based on publication age.

    Papers from the last two years receive full score.  Older papers
    decay at rate 0.1/year but never reach zero.

    Args:
        year: Publication year (four-digit integer).

    Returns:
        Score in (0.0, 1.0].
    """
    current_year = datetime.now().year
    years_since = max(current_year - year, 0)

    if years_since <= 2:
        return 1.0

    # Decay starts after the two-year grace period
    score = math.exp(-0.1 * (years_since - 2))
    return round(max(score, 0.05), 4)


def compute_study_type_score(
    title: str, abstract: str, pub_types: Optional[List[str]] = None
) -> float:
    """Score based on study design hierarchy.

    Detection uses the PubMed publication-type field first, then falls back
    to keyword matching in the title and abstract.

    Args:
        title: Paper title.
        abstract: Paper abstract text.
        pub_types: List of PubMed publication type strings (e.g.
            ``["Randomized Controlled Trial", "Journal Article"]``).

    Returns:
        Score in [0.3, 1.0].
    """
    combined = f"{title} {abstract}".lower()
    pub_types_lower = [pt.lower() for pt in (pub_types or [])]

    # Ordered from highest to lowest evidence level
    hierarchy = [
        (1.0, ["meta-analysis"], ["meta-analysis", "meta analysis"]),
        (0.9, ["randomized controlled trial"], ["randomized", "randomised", "rct", "clinical trial"]),
        (0.8, ["observational study", "cohort study"], ["cohort", "prospective", "longitudinal"]),
        (0.7, ["case-control study"], ["case-control", "case control", "retrospective"]),
        (0.6, ["review"], ["systematic review", "review"]),
        (0.5, ["case reports"], ["case report", "case series"]),
        (0.3, ["letter", "comment", "editorial"], ["letter to the editor", "commentary", "editorial"]),
    ]

    for score, pt_matches, kw_matches in hierarchy:
        # Check publication type field
        for pt in pt_matches:
            if any(pt in ptl for ptl in pub_types_lower):
                return score
        # Keyword fallback
        for kw in kw_matches:
            if kw in combined:
                return score

    # Default: assume original research article
    return 0.75


def compute_availability_score(
    pmc_available: bool = False,
    doi: str = "",
    oa_status: str = "",
) -> float:
    """Score based on full-text accessibility.

    Args:
        pmc_available: Whether paper is available in PubMed Central.
        doi: Digital Object Identifier (non-empty implies some access path).
        oa_status: Open-access status string from Unpaywall or similar
            (e.g. ``"gold"``, ``"green"``, ``"hybrid"``).

    Returns:
        Score in [0.2, 1.0].
    """
    if pmc_available:
        return 1.0

    if oa_status and oa_status.lower() in {"gold", "green", "hybrid", "bronze"}:
        return 0.8

    if doi:
        return 0.5

    return 0.2


def compute_relevance_score(
    title: str,
    abstract: str,
    query: str = "",
    rank_position: int = 0,
    total_results: int = 0,
) -> float:
    """Estimate query relevance from PubMed rank position and keyword overlap.

    Args:
        title: Paper title.
        abstract: Paper abstract text.
        query: Original PubMed search query.
        rank_position: 1-based position in PubMed result list.
        total_results: Total number of PubMed results for the query.

    Returns:
        Score in [0.0, 1.0].
    """
    score = 0.0

    # Rank-based component (0 – 0.5)
    if total_results > 0 and rank_position > 0:
        rank_score = 1.0 - (rank_position - 1) / total_results
        score += 0.5 * rank_score

    # Keyword overlap component (0 – 0.5)
    if query:
        query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        # Remove common PubMed operators / stop words
        stop = {"and", "or", "not", "the", "of", "in", "for", "with", "a", "an"}
        query_tokens -= stop

        if query_tokens:
            combined = f"{title} {abstract}".lower()
            matches = sum(1 for t in query_tokens if t in combined)
            keyword_ratio = matches / len(query_tokens)
            score += 0.5 * keyword_ratio

    return round(min(score, 1.0), 4)


# ---------------------------------------------------------------------------
# Main ranking function
# ---------------------------------------------------------------------------

# Default weighting scheme
DEFAULT_WEIGHTS: Dict[str, float] = {
    "citation": 0.25,
    "journal": 0.20,
    "recency": 0.15,
    "study_type": 0.15,
    "availability": 0.10,
    "relevance": 0.15,
}


def rank_papers(
    papers: List[dict],
    query: str = "",
    weights: Optional[Dict[str, float]] = None,
) -> List[PaperQualityScore]:
    """Rank a list of papers by composite quality score.

    Each paper dict is expected to contain some or all of the following keys
    (missing keys are handled gracefully with conservative defaults):

    - ``pmid`` (str)
    - ``citations`` or ``citation_count`` (int)
    - ``year`` or ``pub_year`` (int)
    - ``journal`` or ``journal_title`` (str)
    - ``title`` (str)
    - ``abstract`` (str)
    - ``pub_types`` (list[str])
    - ``pmc_available`` (bool)
    - ``doi`` (str)
    - ``oa_status`` (str)
    - ``rank_position`` (int) — 1-based position in PubMed results
    - ``total_results`` (int) — total PubMed results for the query

    Args:
        papers: List of paper metadata dicts.
        query: Original search query (used for relevance scoring).
        weights: Optional override for component weights.  Keys must be a
            subset of ``DEFAULT_WEIGHTS``.

    Returns:
        List of ``PaperQualityScore`` sorted descending by composite score.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total_papers = len(papers)
    results: List[PaperQualityScore] = []

    for paper in papers:
        pmid = str(paper.get("pmid", "unknown"))
        citations = int(paper.get("citations", paper.get("citation_count", 0)))
        year = int(paper.get("year", paper.get("pub_year", datetime.now().year)))
        journal = paper.get("journal", paper.get("journal_title", ""))
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        pub_types = paper.get("pub_types", [])
        pmc_available = bool(paper.get("pmc_available", False))
        doi = paper.get("doi", "")
        oa_status = paper.get("oa_status", "")
        rank_position = int(paper.get("rank_position", 0))
        total_results = int(paper.get("total_results", total_papers))

        # Compute individual scores
        cit = compute_citation_score(citations, year)
        jnl = compute_journal_score(journal)
        rec = compute_recency_score(year)
        sty = compute_study_type_score(title, abstract, pub_types)
        avl = compute_availability_score(pmc_available, doi, oa_status)
        rel = compute_relevance_score(title, abstract, query, rank_position, total_results)

        composite = (
            w["citation"] * cit
            + w["journal"] * jnl
            + w["recency"] * rec
            + w["study_type"] * sty
            + w["availability"] * avl
            + w["relevance"] * rel
        )
        composite = round(composite, 4)

        explanation = (
            f"cit={cit:.2f} jnl={jnl:.2f} rec={rec:.2f} "
            f"sty={sty:.2f} avl={avl:.2f} rel={rel:.2f}"
        )

        results.append(
            PaperQualityScore(
                pmid=pmid,
                composite_score=composite,
                citation_score=cit,
                journal_score=jnl,
                recency_score=rec,
                study_type_score=sty,
                availability_score=avl,
                relevance_score=rel,
                explanation=explanation,
            )
        )

    results.sort(key=lambda s: s.composite_score, reverse=True)

    if results:
        logger.info(
            "Ranked %d papers. Top score: %.4f (%s), Bottom score: %.4f (%s)",
            len(results),
            results[0].composite_score,
            results[0].pmid,
            results[-1].composite_score,
            results[-1].pmid,
        )

    return results
