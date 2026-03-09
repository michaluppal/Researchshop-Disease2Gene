"""
Tests for PubTatorTool._parse_document()

Tests the BioC JSON parsing logic directly — no HTTP calls.
The fixture dict matches the PubTator3 API BioC JSON response format.
"""

import pytest

from modules.pubtator_tool import PubTatorGene, PubTatorTool, PubTatorVariant


@pytest.fixture(scope="module")
def pubtator_tool():
    return PubTatorTool()


class TestPubTatorDocumentParsing:
    def test_genes_extracted_from_bioc_doc(self, pubtator_tool, pubtator_bioc_doc):
        """Gene annotations with type='Gene' should produce PubTatorGene objects."""
        genes, variants = pubtator_tool._parse_document(pubtator_bioc_doc)
        assert len(genes) >= 2, f"Expected ≥2 genes, got {len(genes)}: {[g.symbol for g in genes]}"

    def test_brca1_gene_present(self, pubtator_tool, pubtator_bioc_doc):
        """BRCA1 should be in the extracted gene list."""
        genes, _ = pubtator_tool._parse_document(pubtator_bioc_doc)
        symbols = [g.symbol for g in genes]
        assert "BRCA1" in symbols, f"Expected BRCA1 in {symbols}"

    def test_tp53_gene_present(self, pubtator_tool, pubtator_bioc_doc):
        """TP53 should be in the extracted gene list."""
        genes, _ = pubtator_tool._parse_document(pubtator_bioc_doc)
        symbols = [g.symbol for g in genes]
        assert "TP53" in symbols, f"Expected TP53 in {symbols}"

    def test_gene_ncbi_id_captured(self, pubtator_tool, pubtator_bioc_doc):
        """NCBI Gene IDs from the 'identifier' infon should be stored on the gene object."""
        genes, _ = pubtator_tool._parse_document(pubtator_bioc_doc)
        brca1 = next((g for g in genes if g.symbol == "BRCA1"), None)
        assert brca1 is not None
        assert brca1.ncbi_gene_id == "672"

    def test_variant_extracted_from_bioc_doc(self, pubtator_tool, pubtator_bioc_doc):
        """Annotations with type='Variant' should produce PubTatorVariant objects."""
        _, variants = pubtator_tool._parse_document(pubtator_bioc_doc)
        assert len(variants) >= 1, f"Expected ≥1 variant, got {len(variants)}"

    def test_variant_rsid_captured(self, pubtator_tool, pubtator_bioc_doc):
        """rs-prefixed normalized ID in variant annotation should populate rsid field."""
        _, variants = pubtator_tool._parse_document(pubtator_bioc_doc)
        rsids = [v.rsid for v in variants if v.rsid]
        assert len(rsids) >= 1, "Expected at least one variant with an rsid"

    def test_empty_document_returns_empty_lists(self, pubtator_tool):
        """Document with no passages/annotations should return empty lists."""
        empty_doc = {"pmid": "99999999", "passages": []}
        genes, variants = pubtator_tool._parse_document(empty_doc)
        assert genes == []
        assert variants == []

    def test_gene_objects_are_correct_type(self, pubtator_tool, pubtator_bioc_doc):
        genes, variants = pubtator_tool._parse_document(pubtator_bioc_doc)
        for g in genes:
            assert isinstance(g, PubTatorGene)
        for v in variants:
            assert isinstance(v, PubTatorVariant)
