"""
Tests for F10b strict-gate drop aggregation in pipeline_orchestrator.

The aggregation logic lives in ``_aggregate_strict_gate_drops``, a pure helper
factored out of ``_finalize_paper_result`` specifically to enable direct unit
testing without the surrounding pandas/pubtator/citation machinery.

Each test constructs a minimal ``pipeline_stats`` dict (mirroring the shape
built in ``run_complete_pipeline``) + one or more synthetic ``worker_debug``
payloads and verifies:
  - per-paper drops flow into the run-level list
  - each drop is tagged with the calling ``pmid``
  - the ``strict_gate_drops_count`` counter stays in sync with the list length
"""

from __future__ import annotations

import pytest

from modules.pipeline_orchestrator import _aggregate_strict_gate_drops


@pytest.fixture
def fresh_pipeline_stats() -> dict:
    """Minimal pipeline_stats dict, shaped like the one built in run_complete_pipeline."""
    return {
        "strict_gate_drops": [],
        "strict_gate_drops_count": 0,
    }


# ---------------------------------------------------------------------------
# 10. Empty across all papers → count stays zero, list stays empty.
# ---------------------------------------------------------------------------

def test_aggregation_empty_across_papers(fresh_pipeline_stats):
    """
    Three papers, none of which produce strict-gate drops. The run-level list
    and counter must remain empty after all three calls.
    """
    pipeline_stats = fresh_pipeline_stats

    # Case A: key missing entirely
    _aggregate_strict_gate_drops(pipeline_stats, {}, pmid="11111")

    # Case B: key present but empty list
    _aggregate_strict_gate_drops(pipeline_stats, {"strict_gate_drops": []}, pmid="22222")

    # Case C: key present but explicit None
    _aggregate_strict_gate_drops(pipeline_stats, {"strict_gate_drops": None}, pmid="33333")

    assert pipeline_stats["strict_gate_drops_count"] == 0
    assert pipeline_stats["strict_gate_drops"] == []


# ---------------------------------------------------------------------------
# 11. Single paper with 2 drops → both tagged with pmid, original keys preserved.
# ---------------------------------------------------------------------------

def test_aggregation_single_paper_with_drops(fresh_pipeline_stats):
    """
    One paper contributes two strict-gate drops. Each run-level entry must be
    tagged with the calling PMID and keep every original field intact.
    """
    pipeline_stats = fresh_pipeline_stats
    worker_debug = {
        "strict_gate_drops": [
            {
                "gene": "BRCA1",
                "variant": "",
                "reason": "below_final_validation_threshold",
                "validation_confidence": 0.5,
                "threshold": 0.7,
            },
            {
                "gene": "TP53",
                "variant": "R175H",
                "reason": "below_final_validation_threshold",
                "validation_confidence": 0.45,
                "threshold": 0.7,
            },
        ],
    }

    _aggregate_strict_gate_drops(pipeline_stats, worker_debug, pmid="12345")

    assert pipeline_stats["strict_gate_drops_count"] == 2
    assert len(pipeline_stats["strict_gate_drops"]) == 2

    # Every aggregated entry must carry the pmid of the calling paper
    assert all(d["pmid"] == "12345" for d in pipeline_stats["strict_gate_drops"])

    # Original keys from each worker_debug drop must survive the copy
    brca1 = pipeline_stats["strict_gate_drops"][0]
    assert brca1["gene"] == "BRCA1"
    assert brca1["variant"] == ""
    assert brca1["reason"] == "below_final_validation_threshold"
    assert brca1["validation_confidence"] == 0.5
    assert brca1["threshold"] == 0.7

    tp53 = pipeline_stats["strict_gate_drops"][1]
    assert tp53["gene"] == "TP53"
    assert tp53["variant"] == "R175H"
    assert tp53["reason"] == "below_final_validation_threshold"
    assert tp53["validation_confidence"] == 0.45
    assert tp53["threshold"] == 0.7


# ---------------------------------------------------------------------------
# 12. Multiple papers, variable drop counts → pmid tagging + list order correct.
# ---------------------------------------------------------------------------

def test_aggregation_multiple_papers_preserves_pmid(fresh_pipeline_stats):
    """
    Three papers: paper 1 contributes 1 drop, paper 2 contributes 0 (no placeholder),
    paper 3 contributes 2. Total count must be 3, list order must reflect paper order,
    and each drop must be tagged with its source PMID.
    """
    pipeline_stats = fresh_pipeline_stats

    paper1_debug = {
        "strict_gate_drops": [
            {
                "gene": "EGFR",
                "variant": "L858R",
                "reason": "below_final_validation_threshold",
                "validation_confidence": 0.55,
                "threshold": 0.7,
            },
        ],
    }
    paper2_debug = {"strict_gate_drops": []}
    paper3_debug = {
        "strict_gate_drops": [
            {
                "gene": "KRAS",
                "variant": "G12D",
                "reason": "below_final_validation_threshold",
                "validation_confidence": 0.60,
                "threshold": 0.7,
            },
            {
                "gene": "PIK3CA",
                "variant": "H1047R",
                "reason": "below_final_validation_threshold",
                "validation_confidence": 0.65,
                "threshold": 0.7,
            },
        ],
    }

    _aggregate_strict_gate_drops(pipeline_stats, paper1_debug, pmid="12345")
    _aggregate_strict_gate_drops(pipeline_stats, paper2_debug, pmid="67890")
    _aggregate_strict_gate_drops(pipeline_stats, paper3_debug, pmid="11111")

    assert pipeline_stats["strict_gate_drops_count"] == 3
    drops = pipeline_stats["strict_gate_drops"]
    assert len(drops) == 3

    # List order: paper 1's drop, then paper 3's two drops (paper 2 contributes nothing)
    assert drops[0]["pmid"] == "12345"
    assert drops[0]["gene"] == "EGFR"

    assert drops[1]["pmid"] == "11111"
    assert drops[1]["gene"] == "KRAS"

    assert drops[2]["pmid"] == "11111"
    assert drops[2]["gene"] == "PIK3CA"

    # No placeholder entry should have been created for paper 2
    assert all(d["pmid"] in {"12345", "11111"} for d in drops)
    assert not any(d.get("pmid") == "67890" for d in drops)


# ---------------------------------------------------------------------------
# Extra guard: the helper must not mutate the caller's worker_debug dicts.
# ---------------------------------------------------------------------------

def test_aggregation_does_not_mutate_worker_debug(fresh_pipeline_stats):
    """Each aggregated entry should be a shallow copy, not a live reference."""
    worker_debug = {
        "strict_gate_drops": [
            {"gene": "BRCA2", "reason": "below_final_validation_threshold"},
        ],
    }
    original_drop = worker_debug["strict_gate_drops"][0]
    assert "pmid" not in original_drop

    _aggregate_strict_gate_drops(fresh_pipeline_stats, worker_debug, pmid="99999")

    # The source dict inside worker_debug must be untouched
    assert "pmid" not in original_drop, (
        "Helper should copy each drop before tagging; source dict must not be mutated"
    )
    # The aggregated copy must carry the pmid
    assert fresh_pipeline_stats["strict_gate_drops"][0]["pmid"] == "99999"
