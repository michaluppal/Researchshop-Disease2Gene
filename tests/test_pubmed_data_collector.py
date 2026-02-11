"""Unit tests for modules/pubmed_data_collector.py"""

import pytest
from unittest.mock import patch, MagicMock
from modules.pubmed_data_collector import (
    apply_publication_type_filter,
    search_pubmed,
    fetch_semantic_citation_counts,
    fetch_paper_details,
)


# ---------------------------------------------------------------------------
# apply_publication_type_filter
# ---------------------------------------------------------------------------

class TestApplyPublicationTypeFilter:

    def test_appends_not_clause_to_query(self):
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = True
            mock_cfg.EXCLUDED_PUBLICATION_TYPES = ["Review", "Editorial"]
            result = apply_publication_type_filter("cancer AND BRCA1")
        assert result.startswith("(cancer AND BRCA1) NOT (")
        assert "Review[Publication Type]" in result
        assert "Editorial[Publication Type]" in result
        assert " OR " in result

    def test_disabled_filter_returns_original(self):
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = False
            result = apply_publication_type_filter("some query")
        assert result == "some query"

    def test_empty_excluded_types_returns_original(self):
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = True
            mock_cfg.EXCLUDED_PUBLICATION_TYPES = []
            result = apply_publication_type_filter("test query")
        assert result == "test query"

    def test_empty_query_with_filters(self):
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = True
            mock_cfg.EXCLUDED_PUBLICATION_TYPES = ["Review"]
            result = apply_publication_type_filter("")
        assert result == "NOT (Review[Publication Type])"

    def test_single_excluded_type(self):
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = True
            mock_cfg.EXCLUDED_PUBLICATION_TYPES = ["Meta-Analysis"]
            result = apply_publication_type_filter("diabetes")
        assert result == "(diabetes) NOT (Meta-Analysis[Publication Type])"

    def test_multi_word_types_not_quoted(self):
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = True
            mock_cfg.EXCLUDED_PUBLICATION_TYPES = ["Systematic Review", "Case Reports"]
            result = apply_publication_type_filter("q")
        # Multi-word types should NOT be quoted per the code comments
        assert '"' not in result
        assert "Systematic Review[Publication Type]" in result


# ---------------------------------------------------------------------------
# search_pubmed — mock requests.get
# ---------------------------------------------------------------------------

class TestSearchPubmed:

    ESEARCH_XML = b"""<?xml version="1.0" encoding="UTF-8" ?>
    <eSearchResult>
        <Count>3</Count>
        <IdList>
            <Id>111</Id>
            <Id>222</Id>
            <Id>333</Id>
        </IdList>
    </eSearchResult>"""

    ESEARCH_EMPTY_XML = b"""<?xml version="1.0" encoding="UTF-8" ?>
    <eSearchResult>
        <Count>0</Count>
        <IdList/>
    </eSearchResult>"""

    ESEARCH_ERROR_XML = b"""<?xml version="1.0" encoding="UTF-8" ?>
    <eSearchResult>
        <Count>0</Count>
        <ErrorList><Error>Invalid query</Error></ErrorList>
        <IdList/>
    </eSearchResult>"""

    def _mock_response(self, content):
        resp = MagicMock()
        resp.content = content
        resp.url = "https://example.com"
        resp.raise_for_status = MagicMock()
        resp.ok = True
        return resp

    @patch("modules.pubmed_data_collector.requests.get")
    def test_returns_pmids(self, mock_get):
        mock_get.return_value = self._mock_response(self.ESEARCH_XML)
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = False
            mock_cfg.PUBMED_SORT = "date"
            mock_cfg.ENTREZ_API_KEY = None
            pmids = search_pubmed("cancer", 10)
        assert pmids == ["111", "222", "333"]

    @patch("modules.pubmed_data_collector.requests.get")
    def test_returns_empty_on_no_results(self, mock_get):
        mock_get.return_value = self._mock_response(self.ESEARCH_EMPTY_XML)
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = False
            mock_cfg.PUBMED_SORT = "date"
            mock_cfg.ENTREZ_API_KEY = None
            pmids = search_pubmed("xyz", 5)
        assert pmids == []

    @patch("modules.pubmed_data_collector.requests.get")
    def test_handles_error_in_response(self, mock_get):
        mock_get.return_value = self._mock_response(self.ESEARCH_ERROR_XML)
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = False
            mock_cfg.PUBMED_SORT = "date"
            mock_cfg.ENTREZ_API_KEY = None
            pmids = search_pubmed("bad query", 10)
        assert pmids == []

    @patch("modules.pubmed_data_collector.requests.get")
    def test_request_exception_raises(self, mock_get):
        import requests as real_requests
        mock_get.side_effect = real_requests.exceptions.ConnectionError("timeout")
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = False
            mock_cfg.PUBMED_SORT = "date"
            mock_cfg.ENTREZ_API_KEY = None
            with pytest.raises(real_requests.exceptions.ConnectionError):
                search_pubmed("q", 5)

    @patch("modules.pubmed_data_collector.requests.get")
    def test_api_key_added_when_present(self, mock_get):
        mock_get.return_value = self._mock_response(self.ESEARCH_XML)
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENABLE_PUBLICATION_TYPE_FILTER = False
            mock_cfg.PUBMED_SORT = "date"
            mock_cfg.ENTREZ_API_KEY = "mykey123"
            search_pubmed("cancer", 10)
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["api_key"] == "mykey123"


# ---------------------------------------------------------------------------
# fetch_paper_details — MEDLINE parsing
# ---------------------------------------------------------------------------

class TestFetchPaperDetails:

    MEDLINE_RECORD = (
        "PMID- 12345\n"
        "TI  - A study of BRCA1 mutations\n"
        "AU  - Smith J\n"
        "AU  - Doe A\n"
        "DP  - 2023 Jan\n"
        "JT  - Nature\n"
        "AB  - We studied BRCA1.\n"
        "PT  - Journal Article\n"
        "PT  - Randomized Controlled Trial\n"
        "LID - 10.1234/test.2023 [doi]\n"
        "AD  - University of Testing\n"
    )

    MEDLINE_NO_DOI = (
        "PMID- 99999\n"
        "TI  - Another paper\n"
        "AU  - Lee B\n"
        "DP  - 2020 Mar 15\n"
        "JT  - PLoS ONE\n"
        "AB  - Abstract text here.\n"
        "PT  - Journal Article\n"
        "LID - PMC7654321 [pii]\n"
    )

    def _mock_post_response(self, text):
        resp = MagicMock()
        resp.text = text
        resp.raise_for_status = MagicMock()
        return resp

    @patch("modules.pubmed_data_collector.time.sleep")
    @patch("modules.pubmed_data_collector.requests.post")
    def test_extracts_pub_types(self, mock_post, mock_sleep):
        mock_post.return_value = self._mock_post_response(self.MEDLINE_RECORD)
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENTREZ_API_KEY = None
            result = fetch_paper_details(["12345"])
        assert "12345" in result
        assert "Journal Article" in result["12345"]["pub_types"]
        assert "Randomized Controlled Trial" in result["12345"]["pub_types"]

    @patch("modules.pubmed_data_collector.time.sleep")
    @patch("modules.pubmed_data_collector.requests.post")
    def test_extracts_doi(self, mock_post, mock_sleep):
        mock_post.return_value = self._mock_post_response(self.MEDLINE_RECORD)
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENTREZ_API_KEY = None
            result = fetch_paper_details(["12345"])
        assert result["12345"]["doi"] == "10.1234/test.2023"

    @patch("modules.pubmed_data_collector.time.sleep")
    @patch("modules.pubmed_data_collector.requests.post")
    def test_no_doi_when_pii(self, mock_post, mock_sleep):
        mock_post.return_value = self._mock_post_response(self.MEDLINE_NO_DOI)
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENTREZ_API_KEY = None
            result = fetch_paper_details(["99999"])
        assert result["99999"]["doi"] == ""

    @patch("modules.pubmed_data_collector.time.sleep")
    @patch("modules.pubmed_data_collector.requests.post")
    def test_extracts_year(self, mock_post, mock_sleep):
        mock_post.return_value = self._mock_post_response(self.MEDLINE_RECORD)
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENTREZ_API_KEY = None
            result = fetch_paper_details(["12345"])
        assert result["12345"]["year"] == "2023"

    @patch("modules.pubmed_data_collector.time.sleep")
    @patch("modules.pubmed_data_collector.requests.post")
    def test_extracts_authors_list(self, mock_post, mock_sleep):
        mock_post.return_value = self._mock_post_response(self.MEDLINE_RECORD)
        with patch("modules.pubmed_data_collector.config") as mock_cfg:
            mock_cfg.ENTREZ_API_KEY = None
            result = fetch_paper_details(["12345"])
        assert result["12345"]["authors"] == ["Smith J", "Doe A"]

    def test_empty_input_returns_empty(self):
        assert fetch_paper_details([]) == {}


# ---------------------------------------------------------------------------
# fetch_semantic_citation_counts — mock requests.get
# ---------------------------------------------------------------------------

class TestFetchSemanticCitationCounts:

    @patch("modules.pubmed_data_collector.requests.get")
    def test_returns_citation_counts(self, mock_get):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {"citationCount": 42}
        mock_get.return_value = resp
        result = fetch_semantic_citation_counts(["111"])
        assert result == {"111": 42}

    @patch("modules.pubmed_data_collector.requests.get")
    def test_returns_zero_on_failure(self, mock_get):
        resp = MagicMock()
        resp.ok = False
        mock_get.return_value = resp
        result = fetch_semantic_citation_counts(["222"])
        assert result == {"222": 0}

    @patch("modules.pubmed_data_collector.requests.get")
    def test_returns_zero_on_exception(self, mock_get):
        mock_get.side_effect = Exception("network error")
        result = fetch_semantic_citation_counts(["333"])
        assert result == {"333": 0}

    def test_empty_input_returns_empty(self):
        assert fetch_semantic_citation_counts([]) == {}

    @patch("modules.pubmed_data_collector.requests.get")
    def test_multiple_pmids(self, mock_get):
        resp1 = MagicMock()
        resp1.ok = True
        resp1.json.return_value = {"citationCount": 10}
        resp2 = MagicMock()
        resp2.ok = True
        resp2.json.return_value = {"citationCount": 20}
        mock_get.side_effect = [resp1, resp2]
        result = fetch_semantic_citation_counts(["aaa", "bbb"])
        assert result == {"aaa": 10, "bbb": 20}
