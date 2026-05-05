"""Offline tests for candidate association ingestion metadata."""

import sys
from pathlib import Path


_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))


class FakeGeneValidator:
    _local_gene_db = {}

    def resolve_gene_symbol(self, raw):
        if str(raw).lower() == "interleukin-6":
            return "IL6", "alias_symbol"
        return str(raw).upper(), "symbol"


def _make_candidate_harness():
    from modules.paper_analysis.candidates import CandidateMixin

    class CandidateHarness(CandidateMixin):
        def __init__(self):
            self.associations = []
            self.candidate_meta = {}
            self.gene_validator = FakeGeneValidator()

    return CandidateHarness()


def test_ingest_new_reported_candidate_fields_preserves_metadata():
    harness = _make_candidate_harness()

    added = harness._ingest_associations(
        [
            {
                "reported_gene": "interleukin-6",
                "reported_variant": "rs1800795",
                "original_mentions": ["interleukin-6", "IL-6"],
                "evidence_sentence": "The interleukin-6 rs1800795 variant was reported.",
            }
        ],
        "llm_text",
    )

    key = harness._assoc_key("IL6", "rs1800795")
    meta = harness.candidate_meta[key]

    assert added == 1
    assert meta["gene"] == "IL6"
    assert meta["variant"] == "rs1800795"
    assert meta["reported_gene"] == "interleukin-6"
    assert meta["reported_variant"] == "rs1800795"
    assert meta["original_mentions"] == ["interleukin-6", "IL-6"]
    assert meta["evidence_sentence"] == "The interleukin-6 rs1800795 variant was reported."
    assert meta["raw_gene_labels"] == {"interleukin-6", "IL-6"}
    assert harness.associations == [{"gene": "IL6", "variant": "rs1800795"}]


def test_ingest_legacy_gene_variant_dict_remains_supported():
    harness = _make_candidate_harness()

    added = harness._ingest_associations(
        [{"gene": "TP53", "variant": "N/A"}],
        "llm_text",
    )

    key = harness._assoc_key("TP53", "")
    meta = harness.candidate_meta[key]

    assert added == 1
    assert meta["gene"] == "TP53"
    assert meta["variant"] == ""
    assert meta["reported_gene"] == "TP53"
    assert meta["reported_variant"] == "N/A"
    assert meta["original_mentions"] == []
    assert meta["evidence_sentence"] == ""
    assert meta["raw_gene_labels"] == {"TP53"}
    assert harness.associations == [{"gene": "TP53", "variant": ""}]


def test_ingest_merges_original_mentions_into_existing_candidate():
    harness = _make_candidate_harness()

    harness._ingest_associations([{"gene": "IL6", "variant": ""}], "pubtator")
    added = harness._ingest_associations(
        [
            {
                "reported_gene": "IL6",
                "reported_variant": "",
                "original_mentions": ["IL-6", "interleukin-6"],
                "evidence_sentence": "IL-6 was elevated in serum.",
            }
        ],
        "llm_text",
    )

    key = harness._assoc_key("IL6", "")
    meta = harness.candidate_meta[key]

    assert added == 0
    assert meta["sources"] == {"pubtator", "llm_text"}
    assert meta["original_mentions"] == ["IL-6", "interleukin-6"]
    assert meta["evidence_sentence"] == "IL-6 was elevated in serum."
    assert meta["raw_gene_labels"] == {"IL6", "IL-6", "interleukin-6"}


def test_ingest_singular_original_mention_from_structured_output():
    harness = _make_candidate_harness()

    added = harness._ingest_associations(
        [
            {
                "reported_gene": "IFNG",
                "reported_variant": "",
                "original_mention": "IFN-gamma",
                "evidence_sentence": "IFN-gamma was elevated.",
            }
        ],
        "llm_text",
    )

    key = harness._assoc_key("IFNG", "")
    meta = harness.candidate_meta[key]

    assert added == 1
    assert meta["original_mentions"] == ["IFN-gamma"]
    assert meta["raw_gene_labels"] == {"IFNG", "IFN-gamma"}


def test_ingest_hla_shorthand_variant_normalizes_to_gene_scoped_allele():
    harness = _make_candidate_harness()

    added = harness._ingest_associations(
        [
            {
                "reported_gene": "HLA-C",
                "reported_variant": "C*04",
                "original_mention": "C*04",
                "evidence_sentence": "HLA class I alleles A*02, B*35 and C*04 were enriched.",
            }
        ],
        "llm_text",
    )

    key = harness._assoc_key("HLA-C", "HLA-C*04")
    meta = harness.candidate_meta[key]

    assert added == 1
    assert meta["gene"] == "HLA-C"
    assert meta["variant"] == "HLA-C*04"
    assert meta["reported_variant"] == "C*04"
    assert harness.associations == [{"gene": "HLA-C", "variant": "HLA-C*04"}]


def test_ingest_hla_compact_and_colon_variants_normalize():
    harness = _make_candidate_harness()

    harness._ingest_associations(
        [
            {"reported_gene": "HLA-C", "reported_variant": "C04"},
            {"reported_gene": "HLA-C", "reported_variant": "HLA-C*04:01"},
            {"reported_gene": "HLA-C", "reported_variant": "Cw*06"},
        ],
        "llm_text",
    )

    variants = sorted(meta["variant"] for meta in harness.candidate_meta.values())

    assert variants == ["HLA-C*04", "HLA-C*04:01", "HLA-C*06"]


def test_gene_only_hla_candidate_does_not_inherit_variant_normalization_record():
    from modules.content_preparation import PreparedPaperContent

    harness = _make_candidate_harness()
    harness.prepared_content = PreparedPaperContent.from_raw(
        "The association with HLA class I alleles A*02, B*35 and C*04 was reported."
    )

    harness._ingest_associations(
        [{"reported_gene": "HLA-C", "reported_variant": ""}],
        "llm_text",
    )

    key = harness._assoc_key("HLA-C", "")
    meta = harness.candidate_meta[key]

    assert meta["variant"] == ""
    assert meta["normalization_records"] == []
    assert "C*04" not in meta["original_mentions"]
