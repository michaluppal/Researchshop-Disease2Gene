"""Adapter around pubmed_parser for PMC/Europe PMC JATS XML.

ResearchShop owns fetching, OA gating, quality checks, figure downloads, and
output schemas. This module only asks pubmed_parser to parse selected XML
metadata, then normalizes the results into the existing internal shapes.
"""

import logging
import os
import tempfile
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


@contextmanager
def _temporary_nxml(xml_bytes: bytes) -> Iterator[str]:
    """Write XML bytes to a .nxml path so pubmed_parser strips namespaces."""
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".nxml")
    try:
        handle.write(xml_bytes)
        handle.close()
        yield handle.name
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


def _coerce_xml_bytes(xml_bytes: bytes) -> bytes:
    if isinstance(xml_bytes, bytes):
        return xml_bytes
    if isinstance(xml_bytes, str):
        return xml_bytes.encode("utf-8")
    return bytes(xml_bytes)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\t", " ").strip()


def _dedupe_urls(urls: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def _is_useful_graphic_ref(graphic_ref: str) -> bool:
    """Return whether pubmed_parser produced an image-like graphic ref."""
    if not graphic_ref:
        return False

    normalized = graphic_ref.strip().lower()
    if normalized in {"anchor", "float"}:
        return False

    return True


def parse_pubmed_parser_paragraph_text(xml_bytes: bytes) -> Optional[str]:
    """Return body paragraph text parsed by pubmed_parser, or None on failure."""
    try:
        import pubmed_parser as pp
    except Exception as exc:  # pragma: no cover - exercised only when dependency missing
        logger.debug("pubmed_parser is unavailable for paragraph parsing: %s", exc)
        return None

    try:
        with _temporary_nxml(_coerce_xml_bytes(xml_bytes)) as path:
            try:
                paragraphs = pp.parse_pubmed_paragraph(path, all_paragraph=True) or []
            except TypeError:
                paragraphs = pp.parse_pubmed_paragraph(path) or []
    except Exception as exc:
        logger.debug("pubmed_parser paragraph parsing failed: %s", exc)
        return None

    parts: List[str] = []
    last_section = None
    for row in paragraphs:
        if not isinstance(row, dict):
            continue
        text = _clean_text(row.get("text"))
        if not text:
            continue
        section = _clean_text(row.get("section"))
        if section and section != last_section:
            parts.append(f"\n{section}\n")
            last_section = section
        parts.append(text)

    body_text = "\n\n".join(parts).strip()
    return body_text if body_text else None


def parse_pubmed_parser_figures(xml_bytes: bytes, article_url: str) -> List[Dict[str, Any]]:
    """Return figure metadata parsed by pubmed_parser in ResearchShop's shape."""
    if not article_url:
        return []

    try:
        import pubmed_parser as pp
    except Exception as exc:  # pragma: no cover - exercised only when dependency missing
        logger.debug("pubmed_parser is unavailable for figure parsing: %s", exc)
        return []

    try:
        with _temporary_nxml(_coerce_xml_bytes(xml_bytes)) as path:
            captions = pp.parse_pubmed_caption(path) or []
    except Exception as exc:
        logger.debug("pubmed_parser figure parsing failed: %s", exc)
        return []

    try:
        from .full_text_fetcher import _build_pmc_figure_url_candidates
    except Exception as exc:  # pragma: no cover - protects unusual import cycles
        logger.debug("Figure URL candidate builder unavailable: %s", exc)
        return []

    figures: List[Dict[str, Any]] = []
    seen_primary_urls = set()
    for row in captions:
        if not isinstance(row, dict):
            continue
        graphic_ref = _clean_text(row.get("graphic_ref"))
        if not _is_useful_graphic_ref(graphic_ref):
            continue

        url_candidates = _dedupe_urls(_build_pmc_figure_url_candidates(article_url, graphic_ref))
        if not url_candidates:
            continue

        primary_url = url_candidates[0]
        if primary_url in seen_primary_urls:
            continue
        seen_primary_urls.add(primary_url)

        figures.append({
            "label": _clean_text(row.get("fig_label")),
            "caption": _clean_text(row.get("fig_caption")),
            "url": primary_url,
            "url_candidates": url_candidates,
            "source": "pmc_xml",
            "parser": "pubmed_parser",
            "fig_id": _clean_text(row.get("fig_id")),
            "graphic_ref": graphic_ref,
        })

    return figures


def parse_pmc_text_and_figures(
    xml_bytes: bytes,
    article_url: str,
) -> Tuple[Optional[str], List[Dict[str, Any]], List[Any]]:
    """Parse selected PMC XML fields through pubmed_parser.

    The third return value is reserved for future table support. It remains
    empty because production table extraction stays with ResearchShop's parser.
    """
    text = parse_pubmed_parser_paragraph_text(xml_bytes)
    figures = parse_pubmed_parser_figures(xml_bytes, article_url)
    return text, figures, []
