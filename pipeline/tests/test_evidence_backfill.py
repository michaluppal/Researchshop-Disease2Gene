"""
Tests for F12: gene-specific vs co-mention evidence backfill.

Exercises:
  - _find_gene_specific_snippet (two-phase search over paper_text)
  - _backfill_sparse_row_evidence (peer-aware row backfill)
  - pipeline_orchestrator._compute_row_confidence co-mention note suffix

All tests are offline — no real API calls. The Gemini client is mocked; only
deterministic helpers that touch paper_text directly are exercised.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))


# ---------------------------------------------------------------------------
# Helper: build a minimal GeneInfoPipeline without a real Gemini key.
# Mirrors the pattern in test_figure_extraction.py (same module patching).
# ---------------------------------------------------------------------------


def _make_pipeline(paper_text: str = ""):
    """Return a GeneInfoPipeline instance with the Gemini client mocked out."""
    from modules import config as _config

    original_key = _config.GEMINI_API_KEY
    _config.GEMINI_API_KEY = "fake-api-key-for-testing"

    try:
        with patch("modules.gemini_extractor.config.GEMINI_API_KEY", "fake-api-key-for-testing"):
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


def _empty_row(gene: str, variant: str = "") -> Dict[str, Any]:
    """A minimal row dict matching the shape the backfill method inspects."""
    return {
        "gene_name": gene,
        "variant_name": variant,
        "Key Finding": "",
        "Key Finding Citation": "",
    }


COLS = {"Key Finding": "primary finding about the gene"}


# ---------------------------------------------------------------------------
# 1. Gene-specific preferred over co-mention when both exist.
# ---------------------------------------------------------------------------


def test_gene_specific_preferred():
    """Paper has BOTH a gene-specific ITPKC sentence AND a three-gene co-mention.

    ITPKC row must pick up the gene-specific sentence (phase 1 success).
    CASP3 and FCGR2A rows only appear in the co-mention, so both fall through
    to phase 2 and are tagged as co_mention with the two peers listed.
    """
    # 39 chars for sentence 1, 252 chars of padding (pushes co-mention past
    # ITPKC's +220 snippet window), then 58 chars for the co-mention sentence.
    padding = "This study focuses on immune dysregulation in Kawasaki disease. " * 4
    paper = (
        "ITPKC was elevated in severe KD cases. "
        + padding
        + "Furthermore, ITPKC, CASP3, and FCGR2A contribute together."
    )

    pipeline = _make_pipeline(paper_text=paper)
    rows = [_empty_row("ITPKC"), _empty_row("CASP3"), _empty_row("FCGR2A")]

    pipeline._backfill_sparse_row_evidence(rows, COLS)

    # ITPKC — gene-specific path.
    itpkc = rows[0]
    assert "ITPKC was elevated" in itpkc["Key Finding"], (
        f"ITPKC should backfill from the gene-specific sentence, got: "
        f"{itpkc['Key Finding']!r}"
    )
    assert "CASP3" not in itpkc["Key Finding"]
    assert "FCGR2A" not in itpkc["Key Finding"]
    assert itpkc["evidence_specificity"] == "gene_specific"
    assert itpkc["co_mentioned_genes"] == ""

    # CASP3 and FCGR2A — only in co-mention sentence.
    for row, peers in [(rows[1], {"ITPKC", "FCGR2A"}), (rows[2], {"ITPKC", "CASP3"})]:
        assert "Furthermore" in row["Key Finding"] or "contribute together" in row["Key Finding"], (
            f"{row['gene_name']} should backfill from the co-mention sentence, got: "
            f"{row['Key Finding']!r}"
        )
        assert row["evidence_specificity"] == "co_mention"
        got_peers = set(row["co_mentioned_genes"].split(";")) if row["co_mentioned_genes"] else set()
        assert got_peers == peers, (
            f"{row['gene_name']} peers: expected {peers}, got {got_peers}"
        )


# ---------------------------------------------------------------------------
# 2. Pure co-mention (only sentence mentions all three genes together).
# ---------------------------------------------------------------------------


def test_pure_co_mention():
    """Every mention of each gene is in the same co-mention sentence.

    All three rows must tag as co_mention with the two peers listed.
    """
    paper = "ITPKC, CASP3, and FCGR2A all contribute to Kawasaki disease."

    pipeline = _make_pipeline(paper_text=paper)
    rows = [_empty_row("ITPKC"), _empty_row("CASP3"), _empty_row("FCGR2A")]

    pipeline._backfill_sparse_row_evidence(rows, COLS)

    for row, peers in [
        (rows[0], {"CASP3", "FCGR2A"}),
        (rows[1], {"ITPKC", "FCGR2A"}),
        (rows[2], {"ITPKC", "CASP3"}),
    ]:
        assert row["Key Finding"], f"{row['gene_name']} was not backfilled"
        assert row["evidence_specificity"] == "co_mention"
        got_peers = set(row["co_mentioned_genes"].split(";"))
        assert got_peers == peers, f"{row['gene_name']}: expected {peers}, got {got_peers}"


# ---------------------------------------------------------------------------
# 3. Pure gene-specific (three separate sentences, no overlap).
# ---------------------------------------------------------------------------


def test_pure_gene_specific():
    """Three gene-specific sentences with enough padding that no snippet bleeds
    into another gene's sentence. All three rows should tag as gene_specific.
    """
    pad = "Additional commentary fills this segment of the paper. " * 5  # ~275 chars
    paper = (
        "ITPKC is elevated. " + pad +
        "CASP3 is cleaved. " + pad +
        "FCGR2A binds IgG."
    )

    pipeline = _make_pipeline(paper_text=paper)
    rows = [_empty_row("ITPKC"), _empty_row("CASP3"), _empty_row("FCGR2A")]

    pipeline._backfill_sparse_row_evidence(rows, COLS)

    seen_snippets = []
    for row in rows:
        assert row["Key Finding"], f"{row['gene_name']} not backfilled"
        assert row["evidence_specificity"] == "gene_specific"
        assert row["co_mentioned_genes"] == ""
        seen_snippets.append(row["Key Finding"])

    # Each gene's snippet should be distinct (phase 1 walked separate matches).
    assert len(set(seen_snippets)) == 3, (
        f"Expected 3 distinct snippets, got duplicates: {seen_snippets}"
    )


# ---------------------------------------------------------------------------
# 4. Single gene with no peers — always gene_specific.
# ---------------------------------------------------------------------------


def test_single_gene_no_peers():
    """One row, empty peer set — phase 1 returns the first match immediately."""
    paper = "ITPKC is elevated in severe cases of Kawasaki disease."

    pipeline = _make_pipeline(paper_text=paper)
    rows = [_empty_row("ITPKC")]

    pipeline._backfill_sparse_row_evidence(rows, COLS)

    assert rows[0]["Key Finding"], "ITPKC was not backfilled"
    assert rows[0]["evidence_specificity"] == "gene_specific"
    assert rows[0]["co_mentioned_genes"] == ""


# ---------------------------------------------------------------------------
# 5. Peer word-boundary: IL6 must not flag IL6R by substring.
# ---------------------------------------------------------------------------


def test_peer_word_boundary():
    """IL6 and IL6R appear in separate sentences. The word-boundary regex must
    distinguish them — IL6 should NOT be treated as present in IL6R's sentence
    (and vice versa).
    """
    pad = "Additional measurements were performed in parallel cohorts. " * 5  # ~305 chars
    paper = "IL6 increased in patients. " + pad + "IL6R was upregulated separately."

    pipeline = _make_pipeline(paper_text=paper)
    rows = [_empty_row("IL6"), _empty_row("IL6R")]

    pipeline._backfill_sparse_row_evidence(rows, COLS)

    # IL6's snippet must not reach IL6R's sentence — gene_specific expected.
    assert rows[0]["evidence_specificity"] == "gene_specific", (
        f"IL6 row: expected gene_specific, got "
        f"{rows[0]['evidence_specificity']} "
        f"(snippet: {rows[0]['Key Finding']!r})"
    )
    assert rows[0]["co_mentioned_genes"] == ""

    # IL6R's snippet must not treat IL6 (in "IL6R") as a separate peer hit.
    assert rows[1]["evidence_specificity"] == "gene_specific", (
        f"IL6R row: expected gene_specific, got "
        f"{rows[1]['evidence_specificity']} "
        f"(snippet: {rows[1]['Key Finding']!r})"
    )
    assert rows[1]["co_mentioned_genes"] == ""

    # The two snippets should be different (different positions in paper).
    assert rows[0]["Key Finding"] != rows[1]["Key Finding"]


# ---------------------------------------------------------------------------
# 6. Backfill preserves existing row values.
# ---------------------------------------------------------------------------


def test_backfill_preserves_existing_values():
    """A row with a pre-populated Key Finding must be left untouched. The
    backfill loop short-circuits on _row_has_user_evidence(); no new columns
    (evidence_specificity / co_mentioned_genes / evidence_backfilled) should
    be added.
    """
    paper = "ITPKC is elevated in severe cases."

    pipeline = _make_pipeline(paper_text=paper)
    row = _empty_row("ITPKC")
    row["Key Finding"] = "Pre-existing value."

    pipeline._backfill_sparse_row_evidence([row], COLS)

    assert row["Key Finding"] == "Pre-existing value."
    assert "evidence_specificity" not in row
    assert "co_mentioned_genes" not in row
    assert "evidence_backfilled" not in row


def test_fill_missing_statistical_and_conclusion_fields():
    """Partially-filled LLM rows should not leave common result fields empty."""
    paper = (
        "IL1B expression was significantly higher in infected cells compared with mock. "
        "These findings suggest that IL1B contributes to the inflammatory response."
    )
    pipeline = _make_pipeline(paper_text=paper)
    row = {
        "gene_name": "IL1B",
        "variant_name": "",
        "Disease Association": "IL1B expression changed after infection.",
        "Disease Association Citation": "IL1B expression was significantly higher in infected cells compared with mock.",
        "Key Finding": "IL1B expression was significantly higher in infected cells compared with mock.",
        "Key Finding Citation": "IL1B expression was significantly higher in infected cells compared with mock.",
        "Statistical Evidence": "",
        "Statistical Evidence Citation": "",
        "Conclusion": "",
        "Conclusion Citation": "",
    }
    cols = {
        "Disease Association": "Disease context",
        "Key Finding": "Main finding",
        "Statistical Evidence": "P-values, odds ratios, or other statistical measures",
        "Conclusion": "Author conclusions about this gene",
    }

    pipeline._fill_missing_requested_fields([row], cols)

    assert "significantly higher" in row["Statistical Evidence"]
    assert row["Statistical Evidence Citation"] == row["Statistical Evidence"]
    assert row["Conclusion"] == row["Key Finding"]
    assert row["Conclusion Citation"] == row["Key Finding Citation"]


# ---------------------------------------------------------------------------
# 7. Peer alias match — TP53's alias "p53" flags a co-mention for OTHER.
# ---------------------------------------------------------------------------


def test_peer_with_alias_match():
    """Paper mentions TP53 by alias 'p53' in the same sentence as OTHER.

    The peer term-set for TP53 includes the alias 'p53', so when OTHER is
    backfilled the sentence is detected as a co-mention with TP53 listed as
    the peer — even though the literal symbol 'TP53' never appears.
    """
    paper = "p53 suppresses growth; OTHER also suppresses growth."

    pipeline = _make_pipeline(paper_text=paper)

    # Deterministic alias lookup: TP53 -> ['p53'], OTHER -> [].
    def _aliases(gene: str) -> List[str]:
        return ["p53"] if gene.upper() == "TP53" else []

    rows = [_empty_row("TP53"), _empty_row("OTHER")]

    with patch.object(pipeline, "_get_hgnc_aliases_for_gene", side_effect=_aliases):
        pipeline._backfill_sparse_row_evidence(rows, COLS)

    # OTHER should be tagged co_mention with TP53 listed.
    other_row = rows[1]
    assert other_row["Key Finding"], "OTHER was not backfilled"
    assert other_row["evidence_specificity"] == "co_mention", (
        f"OTHER: expected co_mention via alias, got "
        f"{other_row['evidence_specificity']} "
        f"(snippet: {other_row['Key Finding']!r})"
    )
    assert "TP53" in other_row["co_mentioned_genes"].split(";"), (
        f"OTHER's co_mentioned_genes: {other_row['co_mentioned_genes']!r}"
    )


# ---------------------------------------------------------------------------
# 8. Truncation hides a peer — snippet capped to 240 chars before peer appears.
# ---------------------------------------------------------------------------


def test_truncation_hides_peer():
    """GENEB sits inside the +220-char raw match window but past the 240-char
    truncated snippet, so the peer check misses it and phase 1 returns
    gene_specific.
    """
    # GENEA at position 101 (100 filler chars + space, so the word-boundary
    # lookbehind succeeds). raw window = match_start-80 .. match_end+220
    # = 21 .. 326. The raw window length (305 chars) exceeds the 240-char cap
    # so the snippet is truncated to 237 chars + "...". GENEB sits inside the
    # raw window but past the truncation, so the peer check doesn't see it.
    paper = (
        ("A" * 100)
        + " GENEA is elevated. "             # leading space => word-boundary
        + ("B" * 195)
        + " GENEB nearby."                   # leading space => word-boundary
    )

    pipeline = _make_pipeline(paper_text=paper)
    rows = [_empty_row("GENEA"), _empty_row("GENEB")]

    pipeline._backfill_sparse_row_evidence(rows, COLS)

    genea = rows[0]
    assert genea["Key Finding"], "GENEA was not backfilled"
    assert "GENEB" not in genea["Key Finding"], (
        f"GENEA's snippet should have been truncated before GENEB, got: "
        f"{genea['Key Finding']!r}"
    )
    assert genea["evidence_specificity"] == "gene_specific"
    assert genea["co_mentioned_genes"] == ""


# ---------------------------------------------------------------------------
# 9. Same gene, multiple variant rows — identity-keyed peer sets.
# ---------------------------------------------------------------------------


def test_same_gene_multiple_variants():
    """Two rows for the same gene (ITPKC) with different variants. Each row's
    peer set must exclude its own (gene, variant) identity — otherwise row 1
    would see row 2's ITPKC term-set as a peer and always tag co_mention.
    """
    paper = "ITPKC is elevated in KD patients."

    pipeline = _make_pipeline(paper_text=paper)
    rows = [
        _empty_row("ITPKC", variant=""),
        _empty_row("ITPKC", variant="rs28493229"),
    ]

    pipeline._backfill_sparse_row_evidence(rows, COLS)

    for row in rows:
        assert row["Key Finding"], f"row {row} was not backfilled"
        assert row["evidence_specificity"] == "gene_specific", (
            f"Row keyed by (ITPKC, {row['variant_name']!r}) expected "
            f"gene_specific, got {row['evidence_specificity']}. Peer-set "
            f"must exclude the row's own identity key."
        )
        assert row["co_mentioned_genes"] == ""


# ---------------------------------------------------------------------------
# 10. Backfill disabled — no new columns added.
# ---------------------------------------------------------------------------


def test_backfill_disabled_no_new_columns(monkeypatch):
    """When ENABLE_EVIDENCE_BACKFILL is False, the backfill method must be a
    no-op — rows unchanged, no new keys added.
    """
    from modules import config as _config

    monkeypatch.setattr(_config, "ENABLE_EVIDENCE_BACKFILL", False)

    pipeline = _make_pipeline(paper_text="ITPKC is elevated.")
    row = _empty_row("ITPKC")

    pipeline._backfill_sparse_row_evidence([row], COLS)

    assert row["Key Finding"] == ""
    assert "evidence_specificity" not in row
    assert "co_mentioned_genes" not in row
    assert "evidence_backfilled" not in row


# ---------------------------------------------------------------------------
# 11. EVIDENCE_BACKFILL_MAX_SCAN_MATCHES cap is respected.
# ---------------------------------------------------------------------------


def test_max_scan_matches_respected(monkeypatch):
    """Construct a paper with 54 co-mention occurrences of GENEA (each paired
    with GENEB) followed by 1 gene-specific occurrence.

    With cap=50, phase 1 gives up before reaching the 55th match → co_mention.
    With cap=100, phase 1 finds the 55th match → gene_specific.
    """
    from modules import config as _config

    co_mention_sentence = "GENEA and GENEB are co-mentioned. "  # 34 chars
    padding_before_lone = "X" * 260   # ensures the last GENEA's window does
                                      # not reach back into the final co-mention
    lone_sentence = "Then GENEA acts alone here."
    paper = (co_mention_sentence * 54) + padding_before_lone + lone_sentence

    # --- cap=50 -> phase 1 fails on both patterns -> phase 2 -> co_mention ---
    monkeypatch.setattr(_config, "EVIDENCE_BACKFILL_MAX_SCAN_MATCHES", 50)
    pipeline = _make_pipeline(paper_text=paper)
    rows = [_empty_row("GENEA"), _empty_row("GENEB")]
    pipeline._backfill_sparse_row_evidence(rows, COLS)
    assert rows[0]["evidence_specificity"] == "co_mention", (
        f"With cap=50, GENEA should fall through to co_mention, got "
        f"{rows[0]['evidence_specificity']} (snippet: {rows[0]['Key Finding']!r})"
    )
    assert "GENEB" in rows[0]["co_mentioned_genes"].split(";")

    # --- cap=100 -> phase 1 reaches the 55th match -> gene_specific ---
    monkeypatch.setattr(_config, "EVIDENCE_BACKFILL_MAX_SCAN_MATCHES", 100)
    pipeline2 = _make_pipeline(paper_text=paper)
    rows2 = [_empty_row("GENEA"), _empty_row("GENEB")]
    pipeline2._backfill_sparse_row_evidence(rows2, COLS)
    assert rows2[0]["evidence_specificity"] == "gene_specific", (
        f"With cap=100, GENEA should find the lone mention, got "
        f"{rows2[0]['evidence_specificity']} (snippet: {rows2[0]['Key Finding']!r})"
    )
    assert rows2[0]["co_mentioned_genes"] == ""


# ---------------------------------------------------------------------------
# 12. _compute_row_confidence appends the co-mention suffix.
# ---------------------------------------------------------------------------


def test_confidence_note_suffix_applied():
    """Unit test of pipeline_orchestrator._compute_row_confidence.

    Given a skeleton-branch row with evidence_specificity='co_mention' and
    co_mentioned_genes='CASP3;FCGR2A', the returned note must end with
    ' | co-mention with CASP3, FCGR2A' (semicolons converted to ', ').
    """
    from modules.pipeline_orchestrator import _compute_row_confidence

    row = {
        "Gene/Group": "ITPKC",
        "extraction_mode": "skeleton",
        "evidence_backfilled": True,
        "evidence_specificity": "co_mention",
        "co_mentioned_genes": "CASP3;FCGR2A",
        "detail_extraction_error": "some error",
    }

    level, note = _compute_row_confidence(row, user_cols=["Key Finding"])

    assert level == "REVIEW", f"Expected REVIEW for skeleton row, got {level}"
    assert note.endswith(" | co-mention with CASP3, FCGR2A"), (
        f"Expected note to end with ' | co-mention with CASP3, FCGR2A', got: {note!r}"
    )
