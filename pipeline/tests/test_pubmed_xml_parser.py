"""Tests for the pubmed_parser adapter used by full_text_fetcher."""

import sys
from pathlib import Path

_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from modules.full_text_fetcher import (
    _extract_text_and_figures_from_pmc_xml,
    _extract_text_from_pmc_xml,
)
from modules import config, pubmed_xml_parser


XLINK = "http://www.w3.org/1999/xlink"


class TemporaryNxmlFixture:
    def __enter__(self):
        return "/tmp/fixture.nxml"

    def __exit__(self, *_args):
        return False


def _article_xml(figures: str = "", body: str = "") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:xlink="{XLINK}">
  <front>
    <article-meta>
      <article-id pub-id-type="pmid">12345678</article-id>
      <article-id pub-id-type="pmc">7654321</article-id>
      <abstract>
        <p>Abstract text mentions BRCA1 and whole-exome sequencing.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    {body}
    {figures}
  </body>
</article>""".encode("utf-8")


def test_pubmed_parser_figures_map_caption_label_and_graphic_ref():
    xml_bytes = _article_xml(
        figures="""
    <fig id="fig1">
      <label>Figure 1</label>
      <caption><p>TP53 expression across tumor samples.</p></caption>
      <graphic xlink:href="fig1-image"/>
    </fig>
"""
    )

    figures = pubmed_xml_parser.parse_pubmed_parser_figures(
        xml_bytes,
        "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7654321/",
    )

    assert len(figures) == 1
    assert figures[0]["label"] == "Figure 1"
    assert "TP53 expression" in figures[0]["caption"]
    assert figures[0]["graphic_ref"] == "fig1-image"
    assert figures[0]["url"].endswith("/fig1-image")
    assert figures[0]["url_candidates"]


def test_pubmed_parser_namespace_xml_preserves_distinct_multi_panel_figures():
    xml_bytes = _article_xml(
        figures="""
    <fig id="fig1A">
      <label>Figure 1A</label>
      <caption><p>Shared BRCA1 survival caption.</p></caption>
      <graphic xlink:href="fig1A.jpg"/>
    </fig>
    <fig id="fig1B">
      <label>Figure 1B</label>
      <caption><p>Shared BRCA1 survival caption.</p></caption>
      <graphic xlink:href="fig1B.jpg"/>
    </fig>
    <fig id="fig1C">
      <label>Figure 1C</label>
      <caption><p>Shared BRCA1 survival caption.</p></caption>
      <graphic xlink:href="fig1C.jpg"/>
    </fig>
"""
    )

    figures = pubmed_xml_parser.parse_pubmed_parser_figures(xml_bytes, "https://example.com/")

    assert len(figures) == 3
    urls = [fig["url"] for fig in figures]
    assert len(urls) == len(set(urls))
    assert [fig["label"] for fig in figures] == ["Figure 1A", "Figure 1B", "Figure 1C"]


def test_pubmed_parser_figure_without_graphic_ref_is_skipped():
    xml_bytes = _article_xml(
        figures="""
    <fig id="fig1">
      <label>Figure 1</label>
      <caption><p>Supplementary variant frequency chart.</p></caption>
    </fig>
"""
    )

    figures = pubmed_xml_parser.parse_pubmed_parser_figures(xml_bytes, "https://example.com/")

    assert figures == []


def test_pubmed_parser_generic_non_image_graphic_ref_is_skipped(monkeypatch):
    monkeypatch.setattr(
        pubmed_xml_parser,
        "_temporary_nxml",
        lambda _xml: TemporaryNxmlFixture(),
    )

    class PubmedParserFixture:
        @staticmethod
        def parse_pubmed_caption(_path):
            return [{
                "fig_label": "Figure 1",
                "fig_caption": "Caption linked to a floating anchor.",
                "fig_id": "fig1",
                "graphic_ref": "float",
            }]

    monkeypatch.setitem(sys.modules, "pubmed_parser", PubmedParserFixture)

    figures = pubmed_xml_parser.parse_pubmed_parser_figures(
        b"<article />",
        "https://example.com/",
    )

    assert figures == []


def test_pubmed_parser_paragraph_text_includes_sections_and_body_text():
    xml_bytes = _article_xml(
        body="""
    <sec>
      <title>Results</title>
      <p>BRCA1 variants were detected in the body text.</p>
    </sec>
    <sec>
      <title>Methods</title>
      <p>Sequencing was performed with a validated workflow.</p>
    </sec>
"""
    )

    text = pubmed_xml_parser.parse_pubmed_parser_paragraph_text(xml_bytes)

    assert text is not None
    assert "Results" in text
    assert "BRCA1 variants were detected" in text
    assert "Methods" in text


def test_full_text_parser_keeps_abstract_and_table_when_adapter_supplies_body(
    monkeypatch,
    pmc_xml_bytes,
):
    monkeypatch.setattr(
        pubmed_xml_parser,
        "parse_pubmed_parser_paragraph_text",
        lambda _xml: "Results\n\nAdapter body text mentioning ERBB2.",
    )

    result = _extract_text_from_pmc_xml(pmc_xml_bytes)

    assert result is not None
    assert "BRCA1" in result
    assert "Adapter body text mentioning ERBB2" in result
    assert "BRCA1 variant frequency" in result or "Table" in result


def test_full_text_parser_merges_partial_pubmed_parser_figures(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_FIGURE_ANALYSIS", True)

    xml_bytes = _article_xml(
        figures="""
    <fig id="fig1">
      <label>Figure 1</label>
      <caption><p>TP53 expression panel.</p></caption>
      <graphic xlink:href="fig1.jpg"/>
    </fig>
    <fig id="fig2">
      <label>Figure 2</label>
      <caption><p>BRCA1 validation panel.</p></caption>
      <graphic xlink:href="fig2.jpg"/>
    </fig>
"""
    )

    monkeypatch.setattr(
        pubmed_xml_parser,
        "parse_pubmed_parser_figures",
        lambda _xml, article_url: [{
            "label": "Figure 1",
            "caption": "TP53 expression panel.",
            "url": f"{article_url}fig1.jpg",
            "url_candidates": [f"{article_url}fig1.jpg"],
            "source": "pmc_xml",
            "parser": "pubmed_parser",
            "fig_id": "fig1",
            "graphic_ref": "fig1.jpg",
        }],
    )

    text, figures, _ = _extract_text_and_figures_from_pmc_xml(
        xml_bytes,
        article_url="https://example.com/",
    )

    assert len(figures) == 2
    assert figures[0]["parser"] == "pubmed_parser"
    assert [fig["label"] for fig in figures] == ["Figure 1", "Figure 2"]
    assert text is not None
    assert "Figure: Figure 1: TP53 expression panel." in text
    assert "Figure: Figure 2: BRCA1 validation panel." in text


def test_pubmed_parser_malformed_xml_returns_empty_outputs():
    bad_xml = b"<article><unclosed_tag>"

    assert pubmed_xml_parser.parse_pubmed_parser_paragraph_text(bad_xml) is None
    assert pubmed_xml_parser.parse_pubmed_parser_figures(bad_xml, "https://example.com/") == []
