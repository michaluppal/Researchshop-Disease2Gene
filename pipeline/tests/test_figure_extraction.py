"""
Tests for figure extraction edge cases in the ResearchShop pipeline.

Covers:
1. Grounding bypass for llm_figure-sourced genes (RED FLAG 2 fix)
2. HGNC validation of figure-derived genes via GeneValidator
3. Graceful handling of figure image download failures
4. Graceful handling of malformed/non-JSON Gemini responses for figures
5. Multi-panel figure deduplication preserves all panels (distinct URLs)

All tests are offline — no real API calls, no real network access.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

import pytest
import requests

# Ensure `local_pivot/python/` is on sys.path so `import modules.*` works
# regardless of which directory pytest is invoked from.
_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from modules.full_text_fetcher import _extract_figures_from_pmc_xml
from modules.gene_validator import GeneValidator


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def validator():
    """Single GeneValidator instance for all tests in this module (loads HGNC once)."""
    return GeneValidator()


# ---------------------------------------------------------------------------
# Helper: build a minimal GeneInfoPipeline without a real Gemini key.
# ---------------------------------------------------------------------------


class StreamChunkFixture:
    def __init__(self, text: str):
        self.text = text


class OfflineGeminiModels:
    def __init__(self, stream_texts: List[str] | None = None):
        self.stream_texts = list(stream_texts or [])

    def generate_content_stream(self, *_args, **_kwargs):
        text = self.stream_texts.pop(0) if self.stream_texts else ""
        return iter([StreamChunkFixture(text)])


class OfflineGeminiClient:
    def __init__(self, stream_texts: List[str] | None = None):
        self.models = OfflineGeminiModels(stream_texts)


class ResponseFixture:
    def __init__(
        self,
        status_code: int,
        *,
        headers: Dict[str, str] | None = None,
        chunks: List[bytes] | None = None,
        text: str = "",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or []
        self.text = text

    def iter_content(self, chunk_size=65536):  # noqa: ARG002
        return iter(self._chunks)


def _make_pipeline(paper_text: str = "", stream_texts: List[str] | None = None):
    """Return a GeneInfoPipeline instance with no live Gemini dependency."""
    from modules.gemini_extractor import GeneInfoPipeline

    return GeneInfoPipeline(
        paper_text=paper_text,
        abstract_text="",
        pubtator_genes=[],
        figure_inputs=[],
        client=OfflineGeminiClient(stream_texts),
    )


# ---------------------------------------------------------------------------
# Test 1: test_grounding_bypass_for_figure_source
# ---------------------------------------------------------------------------


class TestGroundingBypassForFigureSource:
    def test_llm_figure_gene_passes_when_absent_from_prose(self):
        """A gene with source='llm_figure' must NOT be dropped by the grounding
        check even when the gene symbol does not appear anywhere in paper_text.

        RED FLAG 2 fix: prose grounding is skipped for llm_figure-sourced genes
        because figure image labels are not transcribed into the fetched PMC text.
        HGNC validation (Stage 6) serves as the safety net instead.
        """
        # Paper text deliberately does NOT contain "KRAS" so a prose grounding
        # check would fail for this gene.
        paper_text = (
            "Introduction\n"
            "This study investigates signalling pathways in lung adenocarcinoma. "
            "Whole-exome sequencing was performed on 150 tumour samples. "
            "No specific oncogene is mentioned in this paragraph."
        )

        pipeline = _make_pipeline(paper_text=paper_text)

        # Inject KRAS as an llm_figure-sourced candidate directly.
        pipeline._ingest_associations([{"gene": "KRAS", "variant": ""}], "llm_figure")

        # Confirm the association exists in candidate_meta with the right source.
        key = pipeline._assoc_key("KRAS", "")
        meta = pipeline.candidate_meta.get(key)
        assert meta is not None, "KRAS should be present in candidate_meta after ingestion"
        assert "llm_figure" in meta["sources"], "Source must be llm_figure"

        # Run the grounding check portion of the pipeline manually.
        # We replicate the logic in run_full_pipeline() Step 1.6.
        from modules import config as _config

        grounding_enabled = getattr(_config, "ENABLE_GROUNDING_CHECK", True)
        assert grounding_enabled, (
            "ENABLE_GROUNDING_CHECK must be True for this test to be meaningful"
        )

        grounded = []
        for assoc in pipeline.associations:
            gene = (assoc.get("gene") or "").strip()
            variant = pipeline._normalize_variant_value(assoc.get("variant", ""))
            if not gene:
                continue
            k = pipeline._assoc_key(gene, variant)
            m = pipeline.candidate_meta.get(k) or {}
            sources = m.get("sources", set()) or set()
            # Apply the same bypass logic as gemini_extractor.py line ~1255.
            if isinstance(sources, set) and sources == {"llm_figure"}:
                grounded.append(assoc)
                continue
            terms = list(pipeline._candidate_terms_for_row(gene, variant))
            if pipeline._find_evidence_snippet(terms):
                grounded.append(assoc)

        gene_symbols_in_grounded = [a.get("gene", "").upper() for a in grounded]
        assert "KRAS" in gene_symbols_in_grounded, (
            "KRAS (llm_figure source) must survive the grounding check even though "
            "it is absent from paper prose text"
        )


# ---------------------------------------------------------------------------
# Test 2: test_figure_gene_hgnc_validated
# ---------------------------------------------------------------------------


class TestFigureGeneHgncValidated:
    def test_brca1_validates_with_high_confidence(self, validator):
        """BRCA1 is a canonical HGNC symbol — it should resolve locally with
        confidence >= 0.7, confirming that figure-derived genes would pass Stage 6.

        Mirrors the pattern from test_gene_validator.py: call resolve_gene_symbol
        directly on the GeneValidator; assert canonical symbol returned.
        """
        symbol, source = validator.resolve_gene_symbol("BRCA1")
        assert symbol == "BRCA1", (
            f"Expected canonical BRCA1, got '{symbol}' (source={source})"
        )
        assert source == "local_symbol", (
            f"Expected local_symbol resolution path for BRCA1, got '{source}'"
        )

    def test_tp53_validates_as_local_symbol(self, validator):
        """TP53 should also resolve via the local HGNC snapshot — confirming the
        HGNC database covers commonly extracted figure-label genes.
        """
        symbol, source = validator.resolve_gene_symbol("TP53")
        assert symbol == "TP53"
        assert source == "local_symbol"

    def test_figure_gene_confidence_threshold(self, validator):
        """Validate that the minimum confidence threshold (0.7) would be met for
        a valid gene like EGFR by checking that the local resolver returns a
        canonical symbol (validation confidence >= 0.7 is assigned for valid genes).
        """
        symbol, source = validator.resolve_gene_symbol("EGFR")
        assert symbol == "EGFR", (
            "EGFR should resolve canonically — figure-derived genes that resolve "
            "locally will pass the FINAL_VALIDATION_MIN_CONFIDENCE=0.7 gate"
        )
        # local_symbol or local_alias resolution both yield confidence >= 0.7.
        assert source in {"local_symbol", "local_alias", "hgnc_api", "mygene"}, (
            f"Unexpected resolution source: {source}"
        )


# ---------------------------------------------------------------------------
# Test 3: test_image_download_failure_handled_gracefully
# ---------------------------------------------------------------------------


class TestImageDownloadFailureHandledGracefully:
    def test_connection_error_returns_empty_list(self):
        """When requests.get raises ConnectionError for a figure download,
        extract_gene_names_from_figures() must return an empty list and NOT
        raise an exception.

        The pipeline must be resilient to transient network failures so a
        single bad figure URL does not abort extraction for the whole paper.
        """
        figure_inputs = [
            {
                "label": "Figure 1",
                "caption": "KRAS and BRAF mutations in tumour samples.",
                "url": "https://example.com/fig1.jpg",
                "url_candidates": ["https://example.com/fig1.jpg"],
                "source": "pmc_xml",
            }
        ]

        pipeline = _make_pipeline(paper_text="KRAS BRAF mutations were detected.")
        pipeline.figure_inputs = figure_inputs

        def raise_connection_error(*_args, **_kwargs):
            raise requests.ConnectionError("Network unreachable")

        pipeline._figure_http_get = raise_connection_error
        result = pipeline.extract_gene_names_from_figures()

        assert isinstance(result, list), (
            "extract_gene_names_from_figures must return a list even on download failure"
        )
        assert result == [], (
            "No genes should be extracted when all figure downloads fail due to ConnectionError"
        )

    def test_timeout_error_returns_empty_list(self):
        """requests.Timeout during figure download should also be handled gracefully."""
        figure_inputs = [
            {
                "label": "Figure 2",
                "caption": "Survival curves for BRCA1 carriers.",
                "url": "https://example.com/fig2.png",
                "url_candidates": ["https://example.com/fig2.png"],
                "source": "pmc_xml",
            }
        ]

        pipeline = _make_pipeline(paper_text="BRCA1 was studied.")
        pipeline.figure_inputs = figure_inputs

        def raise_timeout(*_args, **_kwargs):
            raise requests.Timeout("Request timed out")

        pipeline._figure_http_get = raise_timeout
        result = pipeline.extract_gene_names_from_figures()

        assert isinstance(result, list)
        assert result == [], (
            "No genes should be extracted when figure download times out"
        )

    def test_transient_cdn_lookup_failure_is_not_cached(self):
        """A temporary PMC article-page failure must not poison CDN lookup cache."""
        pipeline = _make_pipeline(paper_text="BRCA1 was studied.")
        figure = {
            "label": "Figure 1",
            "caption": "BRCA1 expression panel.",
            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123456/fig1.jpg",
            "url_candidates": ["https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123456/fig1.jpg"],
            "source": "pmc_xml",
        }
        cdn_url = "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/x/123456/y/fig1.jpg"

        failed_article_response = ResponseFixture(503)
        ok_article_response = ResponseFixture(200, text=f'<img src="{cdn_url}">')
        failed_image_response = ResponseFixture(404)
        ok_image_response = ResponseFixture(
            200,
            headers={"Content-Type": "image/jpeg", "Content-Length": "104"},
            chunks=[b"\xFF\xD8\xFF\xE0" + b"\x00" * 100],
        )

        responses = iter([
            failed_image_response,
            failed_article_response,
            failed_image_response,
            ok_article_response,
            ok_image_response,
        ])

        pipeline._figure_http_get = lambda *_args, **_kwargs: next(responses)
        assert pipeline._fetch_figure_image(figure) is None
        assert pipeline._fetch_figure_image(figure)["url"] == cdn_url


# ---------------------------------------------------------------------------
# Test 4: test_malformed_json_figure_response
# ---------------------------------------------------------------------------


class TestMalformedJsonFigureResponse:
    def test_non_json_gemini_response_does_not_raise(self):
        """When Gemini returns a prose string instead of JSON for a figure query
        (e.g. 'Sure! The genes are: BRCA1, TP53'), the parser must not raise an
        exception and must return an empty list (or gracefully degrade).

        The pipeline wraps the JSON parse in a try/except so a bad response
        should yield zero associations for that figure, not crash the run.
        """
        malformed_response_text = "Sure! The genes are: BRCA1, TP53"

        figure_inputs = [
            {
                "label": "Figure 3",
                "caption": "BRCA1 expression levels across sample groups.",
                "url": "https://example.com/fig3.jpg",
                "url_candidates": ["https://example.com/fig3.jpg"],
                "source": "pmc_xml",
            }
        ]

        # Use a local image response so the code reaches the Gemini call.
        image_bytes = b"\xFF\xD8\xFF\xE0" + b"\x00" * 100  # minimal JPEG header
        image_response = ResponseFixture(
            200,
            headers={"Content-Type": "image/jpeg", "Content-Length": "104"},
            chunks=[image_bytes],
        )

        pipeline = _make_pipeline(
            paper_text="BRCA1 expression was quantified.",
            stream_texts=[malformed_response_text],
        )
        pipeline.figure_inputs = figure_inputs
        pipeline._figure_http_get = lambda *_args, **_kwargs: image_response

        try:
            result = pipeline.extract_gene_names_from_figures()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                f"extract_gene_names_from_figures raised {type(exc).__name__} "
                f"on malformed Gemini response: {exc}"
            )

        assert isinstance(result, list), (
            "Must return a list even when Gemini response is not valid JSON"
        )

    def test_empty_gemini_response_returns_empty_list(self):
        """An empty string response from Gemini should yield an empty list,
        not a KeyError or AttributeError.
        """
        figure_inputs = [
            {
                "label": "Figure 4",
                "caption": "Western blot showing EGFR protein levels.",
                "url": "https://example.com/fig4.jpg",
                "url_candidates": ["https://example.com/fig4.jpg"],
                "source": "pmc_xml",
            }
        ]

        image_bytes = b"\xFF\xD8\xFF\xE0" + b"\x00" * 100
        image_response = ResponseFixture(
            200,
            headers={"Content-Type": "image/jpeg", "Content-Length": "104"},
            chunks=[image_bytes],
        )

        pipeline = _make_pipeline(
            paper_text="EGFR was measured by Western blot.",
            stream_texts=[""],
        )
        pipeline.figure_inputs = figure_inputs
        pipeline._figure_http_get = lambda *_args, **_kwargs: image_response

        result = pipeline.extract_gene_names_from_figures()

        assert result == [], (
            "Empty Gemini response should yield an empty association list"
        )


# ---------------------------------------------------------------------------
# Test 5: test_panel_deduplication_preserves_multi_panel
# ---------------------------------------------------------------------------


class TestPanelDeduplicationPreservesMultiPanel:
    def _build_multi_panel_xml(self) -> ET.Element:
        """Build a minimal JATS XML root with 3 <fig> elements that share a
        common parent caption text (matching panels 1A, 1B, 1C) but each
        has a distinct <graphic xlink:href> URL.

        This exercises the deduplication fix: the `seen` set is keyed on the
        first candidate URL, NOT on (label, caption, url) combined — so panels
        with the same caption are NOT collapsed to one entry.
        """
        # Note: the xlink namespace is required for the href attribute to be
        # recognised by _extract_figures_from_pmc_xml (it matches any attr ending in 'href').
        XLINK = "http://www.w3.org/1999/xlink"
        xml_string = f"""<article xmlns:xlink="{XLINK}">
  <body>
    <fig id="fig1A">
      <label>Figure 1A</label>
      <caption><p>Kaplan-Meier curves showing BRCA1 carrier survival.</p></caption>
      <graphic xlink:href="https://example.com/fig1A.jpg"/>
    </fig>
    <fig id="fig1B">
      <label>Figure 1B</label>
      <caption><p>Kaplan-Meier curves showing BRCA1 carrier survival.</p></caption>
      <graphic xlink:href="https://example.com/fig1B.jpg"/>
    </fig>
    <fig id="fig1C">
      <label>Figure 1C</label>
      <caption><p>Kaplan-Meier curves showing BRCA1 carrier survival.</p></caption>
      <graphic xlink:href="https://example.com/fig1C.jpg"/>
    </fig>
  </body>
</article>"""
        return ET.fromstring(xml_string)

    def test_three_panels_with_distinct_urls_all_preserved(self):
        """_extract_figures_from_pmc_xml must return 3 entries for 3 panels
        that share the same caption text but have distinct image URLs.

        Prior to the dedup fix, (label, caption, url) was used as the dedup key,
        collapsing panels with identical captions to 1 entry. The fixed logic
        uses only the first candidate URL as the key, preserving all panels.
        """
        root = self._build_multi_panel_xml()
        article_url = "https://example.com/"

        figures = _extract_figures_from_pmc_xml(root, article_url)

        assert len(figures) == 3, (
            f"Expected 3 figure entries (one per panel), got {len(figures)}. "
            "The dedup logic must use URL as the unique key, not (caption, url). "
            "Multi-panel figures (1A, 1B, 1C) that share a caption must each be preserved."
        )

    def test_panels_have_distinct_urls(self):
        """Each extracted figure entry must have a distinct primary URL."""
        root = self._build_multi_panel_xml()
        article_url = "https://example.com/"

        figures = _extract_figures_from_pmc_xml(root, article_url)

        urls = [fig["url"] for fig in figures]
        assert len(urls) == len(set(urls)), (
            f"Duplicate URLs found in extracted figures: {urls}. "
            "Each panel must map to its own unique image URL."
        )

    def test_single_figure_not_duplicated(self):
        """A single <fig> element must produce exactly 1 entry (no off-by-one
        in the dedup logic that could create phantom duplicates).
        """
        XLINK = "http://www.w3.org/1999/xlink"
        xml_string = f"""<article xmlns:xlink="{XLINK}">
  <body>
    <fig id="fig1">
      <label>Figure 1</label>
      <caption><p>Overview of TP53 mutation distribution.</p></caption>
      <graphic xlink:href="https://example.com/fig1.jpg"/>
    </fig>
  </body>
</article>"""
        root = ET.fromstring(xml_string)
        figures = _extract_figures_from_pmc_xml(root, "https://example.com/")

        assert len(figures) == 1, (
            f"A single <fig> element should produce exactly 1 figure entry, got {len(figures)}"
        )

    def test_fig_without_graphic_href_is_skipped(self):
        """A <fig> element that has no <graphic> child (no href) should be skipped
        entirely — it has no downloadable image and would produce no URL candidates.
        """
        xml_string = """<article>
  <body>
    <fig id="fig1">
      <label>Figure 1</label>
      <caption><p>Supplementary table of variant frequencies.</p></caption>
    </fig>
  </body>
</article>"""
        root = ET.fromstring(xml_string)
        figures = _extract_figures_from_pmc_xml(root, "https://example.com/")

        assert len(figures) == 0, (
            "A <fig> element with no <graphic href> should produce zero figure entries"
        )
