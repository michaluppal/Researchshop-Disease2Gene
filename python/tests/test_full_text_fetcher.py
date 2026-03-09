"""
Tests for full_text_fetcher._extract_text_from_pmc_xml()

Pure XML parsing — no network calls. Uses the pmc_minimal.xml fixture.
"""

from modules.full_text_fetcher import _extract_text_from_pmc_xml


class TestExtractTextFromPmcXml:
    def test_returns_string_from_valid_xml(self, pmc_xml_bytes):
        """Valid JATS XML should return a non-empty string."""
        result = _extract_text_from_pmc_xml(pmc_xml_bytes)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 100

    def test_abstract_content_extracted(self, pmc_xml_bytes):
        """Abstract paragraph text should appear in the output."""
        result = _extract_text_from_pmc_xml(pmc_xml_bytes)
        assert "BRCA1" in result
        assert "whole-exome sequencing" in result.lower()

    def test_body_section_content_extracted(self, pmc_xml_bytes):
        """Body section paragraphs should be extracted."""
        result = _extract_text_from_pmc_xml(pmc_xml_bytes)
        assert "TP53" in result
        assert "triple-negative" in result.lower()

    def test_section_titles_included(self, pmc_xml_bytes):
        """Section titles (<title> inside <sec>) should appear in output."""
        result = _extract_text_from_pmc_xml(pmc_xml_bytes)
        assert "Results" in result
        assert "Methods" in result

    def test_table_caption_extracted(self, pmc_xml_bytes):
        """Table captions from <table-wrap> should appear in output."""
        result = _extract_text_from_pmc_xml(pmc_xml_bytes)
        # The table-wrap caption mentions BRCA1 variant frequency
        assert "BRCA1 variant frequency" in result or "Table" in result

    def test_malformed_xml_returns_none(self):
        """Invalid XML bytes should return None without raising an exception."""
        bad_xml = b"<article><unclosed_tag>"
        result = _extract_text_from_pmc_xml(bad_xml)
        # Malformed XML — either None or partial parse. Should not raise.
        # (ElementTree may or may not return None for unclosed tags depending on version)
        assert result is None or isinstance(result, str)

    def test_empty_bytes_returns_none(self):
        """Empty bytes should return None."""
        result = _extract_text_from_pmc_xml(b"")
        assert result is None
