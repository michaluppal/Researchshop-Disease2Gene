"""
Tests for PubTatorTool._parse_document()

Tests the BioC JSON parsing logic directly — no HTTP calls.
The fixture dict matches the PubTator3 API BioC JSON response format.
"""

import pytest

from modules.pubtator_tool import NCBIGeneTool, PubTatorGene, PubTatorTool, PubTatorVariant


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


class ResponseFixture:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} error")


class SessionFixture:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        if not self.responses:
            raise AssertionError("Unexpected extra NCBI request")
        return self.responses.pop(0)


def _esearch_payload(gene_id="672"):
    return {"esearchresult": {"idlist": [gene_id]}}


def _esummary_payload(gene_id="672", symbol="BRCA1"):
    return {
        "result": {
            gene_id: {
                "name": symbol,
                "description": f"{symbol} full name",
                "otheraliases": "Alias1, Alias2",
                "chromosome": "17",
                "maplocation": "17q21",
                "genetictype": "protein-coding",
                "organism": {"scientificname": "Homo sapiens"},
            }
        }
    }


class TestNCBIGeneTool:
    def test_symbol_cache_avoids_duplicate_requests(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        tool = NCBIGeneTool()
        tool._session = SessionFixture([
            ResponseFixture(_esearch_payload()),
            ResponseFixture(_esummary_payload()),
        ])

        first = tool.get_gene_by_symbol("BRCA1")
        second = tool.get_gene_by_symbol("BRCA1")

        assert first is second
        assert len(tool._session.calls) == 2

    def test_uses_gene_id_before_symbol_search(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        tool = NCBIGeneTool()
        tool._session = SessionFixture([
            ResponseFixture(_esummary_payload(gene_id="7157", symbol="TP53")),
        ])

        enriched = tool.enrich_gene_symbols(["TP53"], symbol_gene_ids={"TP53": "7157"})

        assert enriched["TP53"].gene_id == "7157"
        assert "esummary.fcgi" in tool._session.calls[0][0]
        assert len(tool._session.calls) == 1

    def test_invalid_gene_id_falls_back_to_symbol_search(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        tool = NCBIGeneTool()
        tool._session = SessionFixture([
            ResponseFixture({"result": {}}),
            ResponseFixture(_esearch_payload(gene_id="7157")),
            ResponseFixture(_esummary_payload(gene_id="7157", symbol="TP53")),
        ])

        enriched = tool.enrich_gene_symbols(["TP53"], symbol_gene_ids={"TP53": "999999"})

        assert enriched["TP53"].gene_id == "7157"
        assert [call[0].split("/")[-1] for call in tool._session.calls] == [
            "esummary.fcgi",
            "esearch.fcgi",
            "esummary.fcgi",
        ]

    def test_429_retries_before_success(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr("time.sleep", lambda value: sleeps.append(value))
        tool = NCBIGeneTool()
        tool._session = SessionFixture([
            ResponseFixture({}, status_code=429, headers={"Retry-After": "0.2"}),
            ResponseFixture(_esummary_payload()),
        ])

        meta = tool.get_gene_metadata("672")

        assert meta is not None
        assert len(tool._session.calls) == 2
        assert any(value >= 0.2 for value in sleeps)

    def test_429_exhaustion_is_not_cached_as_negative(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        tool = NCBIGeneTool()
        tool._session = SessionFixture([
            ResponseFixture({}, status_code=429),
            ResponseFixture({}, status_code=429),
            ResponseFixture({}, status_code=429),
        ])

        assert tool.get_gene_by_symbol("BRCA1") is None

        assert "BRCA1" not in tool._symbol_negative_cache
        assert "BRCA1" not in tool._symbol_cache
