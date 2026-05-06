# modules/full_text_fetcher.py
#
# OA-first full-text fetcher.
#
# OA enforcement happens at three points upstream of this module (F2):
#
#   1. Query-mode runs — PubMed search applies the `loattrfull text[sb]`
#      subset filter (`ENABLE_OA_FILTER=True`, default). Results are pre-filtered
#      to papers with freely available full text.
#   2. Paste-box runs (SmartInput.tsx in the renderer) — surfaces a green
#      "Full text" / amber "No OA full text" badge per pasted PMID and excludes
#      PMIDs without an open-access full-text record.
#   3. CLI / scripted invocations — `pipeline_orchestrator.run_complete_pipeline`
#      applies the same OA gate for `specific_pmids` + author-search PMIDs.
#      Backstop for users who bypass the UI.
#
# Fetch strategy (OA APIs only — no scraping, no browser automation):
#
#   1. PMC Entrez efetch      — structured JATS XML from NCBI (preferred)
#   2. Europe PMC fullTextXML — alternative OA XML endpoint
#
# Playwright browser automation, Trafilatura web scraping, paywall detection,
# and publisher-specific DOM selectors are intentionally absent from the public
# pipeline. Full-text fetching is limited to OA XML APIs.
# If any legacy call path bypasses the layers above AND a paywalled PMID reaches this
# module, `_fetch_pmc_efetch` returns `extraction_method="no_oa_full_text"`
# and the paper continues through the pipeline with abstract-only content.
# That fallback is retained for downstream compatibility, not as a supported
# user-facing mode.

import csv
import dataclasses
import gzip
import io
import logging
import pickle
import re
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
import trafilatura  # still used for supplementary HTML fallback extraction
from Bio import Entrez
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

from . import config, pubmed_xml_parser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP session (used for supplementary file downloads and Europe PMC calls)
# ---------------------------------------------------------------------------

def _build_http_session() -> requests.Session:
    """Create a requests session with retries and sane headers."""
    session = requests.Session()
    retry = Retry(
        total=config.REQUEST_RETRIES,
        connect=config.REQUEST_RETRIES,
        read=config.REQUEST_RETRIES,
        backoff_factor=config.BACKOFF_FACTOR,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("HEAD", "GET", "OPTIONS"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    return session

_SESSION = _build_http_session()


# ---------------------------------------------------------------------------
# PMC ID lookup
# ---------------------------------------------------------------------------

def _get_pmcid_for_pmid(pmid: str) -> Optional[str]:
    """Return the PMC ID for a PMID, or None if not available."""
    try:
        base_url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        params = {'ids': pmid, 'format': 'json', 'tool': 'disease2gene', 'email': config.ENTREZ_EMAIL}
        response = _SESSION.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        record = data.get('records', [{}])[0]
        # Cross-validate: ensure the returned record's PMID matches what we asked for
        if record.get('pmid') and str(record.get('pmid')) != str(pmid):
            logger.warning(f"PMID mismatch in ID converter: asked for {pmid}, got {record.get('pmid')}")
            return None
        pmcid = record.get('pmcid')
        if pmcid:
            return pmcid
    except Exception as e:
        logger.debug(f"PMC ID lookup failed for PMID {pmid}: {e}")
    return None


# ---------------------------------------------------------------------------
# Supplementary file extraction
# ---------------------------------------------------------------------------

def _extract_supplementary_urls_from_pmc_xml(root, article_url: str) -> List[Tuple[str, str]]:
    """
    Collect supplementary file URLs from JATS XML.
    Returns list of tuples: (supplement_label, absolute_url)
    """
    links: List[Tuple[str, str]] = []

    def _is_jats_tag(elem, target: str) -> bool:
        tag = getattr(elem, 'tag', '')
        return tag == target or str(tag).endswith('}' + target)

    def _collect_href(elem) -> Optional[str]:
        # xlink:href often appears namespaced
        for k, v in elem.attrib.items():
            if str(k).endswith('href') and v:
                return v
        return None

    def _collect_text(elem) -> str:
        parts: List[str] = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(_collect_text(child))
            if child.tail:
                parts.append(child.tail)
        return ''.join(parts)

    for elem in root.iter():
        if not (_is_jats_tag(elem, 'supplementary-material') or _is_jats_tag(elem, 'supplementary-material-wrap') or _is_jats_tag(elem, 'media')):
            continue
        href = _collect_href(elem)
        if not href:
            continue

        label_text = ""
        for child in elem:
            if _is_jats_tag(child, 'label'):
                label_text = _collect_text(child).strip()
                break
        if not label_text:
            for child in elem:
                if _is_jats_tag(child, 'caption'):
                    label_text = _collect_text(child).strip()
                    break
        if not label_text:
            label_text = "Supplementary file"

        abs_url = urljoin(article_url, href)
        links.append((label_text, abs_url))

    dedup: List[Tuple[str, str]] = []
    seen = set()
    for label, u in links:
        if u in seen:
            continue
        seen.add(u)
        dedup.append((label, u))
    return dedup


def _extract_pdf_text(pdf_bytes: bytes) -> Optional[str]:
    """Extract text from PDF bytes if pdfminer.six is available."""
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams
        output = io.StringIO()
        laparams = LAParams(
            char_margin=getattr(config, 'PDFM_CHAR_MARGIN', 2.0),
            line_margin=getattr(config, 'PDFM_LINE_MARGIN', 0.5),
            word_margin=getattr(config, 'PDFM_WORD_MARGIN', 0.1),
        )
        with io.BytesIO(pdf_bytes) as fh:
            extract_text_to_fp(fh, output, laparams=laparams, output_type='text', codec=None)
        text = output.getvalue()
        if text and len(text.strip()) > 0:
            return text
    except Exception:
        return None
    return None


def _extract_supplementary_content(url: str) -> Optional[str]:
    """Fetch and extract textual/tabular content from supplementary file URL."""
    try:
        r = _SESSION.get(url, timeout=config.REQUEST_TIMEOUT, allow_redirects=True)
        if r.status_code != 200:
            return None

        content_type = (r.headers.get('Content-Type') or '').lower()
        lower_url = url.lower()

        # CSV/TSV/TXT
        if any(lower_url.endswith(ext) for ext in ('.csv', '.tsv', '.txt')) or 'text/csv' in content_type or 'text/tab-separated-values' in content_type:
            text = r.text
            if not text:
                return None
            delim = '\t' if ('.tsv' in lower_url or 'tab-separated' in content_type) else ','
            reader = csv.reader(io.StringIO(text), delimiter=delim)
            rows = []
            for i, row in enumerate(reader):
                if i >= 200:
                    break
                rows.append('\t'.join([c.strip() for c in row if c is not None]))
            return '\n'.join(rows) if rows else text[:5000]

        # Excel
        if any(lower_url.endswith(ext) for ext in ('.xlsx', '.xls')) or 'spreadsheet' in content_type or 'excel' in content_type:
            try:
                import openpyxl  # type: ignore
                wb = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True, data_only=True)
                lines: List[str] = []
                for ws in wb.worksheets[:2]:
                    lines.append(f"[Sheet] {ws.title}")
                    for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
                        if row_idx >= 200:
                            break
                        vals = [str(c).strip() for c in row if c is not None and str(c).strip()]
                        if vals:
                            lines.append('\t'.join(vals))
                return '\n'.join(lines) if lines else None
            except Exception:
                return None

        # ZIP archives containing tabular files
        if lower_url.endswith('.zip') or 'application/zip' in content_type:
            try:
                out_parts: List[str] = []
                with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                    for name in zf.namelist()[:10]:
                        lname = name.lower()
                        if not any(lname.endswith(ext) for ext in ('.csv', '.tsv', '.txt')):
                            continue
                        with zf.open(name) as fh:
                            raw = fh.read(200000).decode('utf-8', errors='ignore')
                            out_parts.append(f"[File] {name}\n{raw[:5000]}")
                        if len(out_parts) >= 3:
                            break
                return '\n\n'.join(out_parts) if out_parts else None
            except Exception:
                return None

        # PDF
        if lower_url.endswith('.pdf') or 'application/pdf' in content_type:
            return _extract_pdf_text(r.content)

        # Generic HTML fallback
        extracted = trafilatura.extract(
            r.text,
            include_comments=False,
            include_tables=True,
            deduplicate=True,
            favor_precision=True,
            include_links=False
        ) if r.text else None
        return extracted
    except Exception:
        return None


# ---------------------------------------------------------------------------
# JATS XML parsing helpers
# ---------------------------------------------------------------------------

def _jats_tag_matches(elem, target: str) -> bool:
    tag = str(getattr(elem, 'tag', ''))
    return tag == target or tag.endswith('}' + target)


def _collect_xml_text(elem) -> str:
    parts: List[str] = []

    def _append(s: str) -> None:
        if not s:
            return
        # Insert a space when adjacent text boundaries have no whitespace (e.g. "adm171" → "adm 171").
        # This happens when inline elements (<sup>, <sub>, <bold>) abut surrounding text with no space.
        if parts and parts[-1] and not parts[-1][-1].isspace() and not s[0].isspace():
            parts.append(' ')
        parts.append(s)

    if elem.text:
        _append(elem.text)
    for child in elem:
        _append(_collect_xml_text(child))
        if child.tail:
            _append(child.tail)
    return ''.join(parts)


@dataclass
class StructuredTable:
    """A table extracted from JATS XML with separate headers and data rows."""
    table_id: str        # XML id attribute, or f"table_{idx}" if missing
    label: str           # "Table 1" (from <label>)
    caption: str         # from <caption>
    headers: List[str]   # from first <tr> containing <th> cells
    rows: List[List[str]]  # remaining data rows
    footnotes: str       # from <table-wrap-foot>
    source_section: str  # "body"

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class FetchOutcome:
    """Forensic summary of a single paper's fetch result."""
    pmid: str
    method_succeeded: Optional[str]
    content_length: int
    figure_count: int
    table_count: int
    error_message: Optional[str]


def _build_pmc_figure_url_candidates(article_url: str, href: str) -> List[str]:
    """Build candidate image URLs for a PMC figure href."""
    if not href:
        return []

    href_clean = href.strip()
    if not href_clean:
        return []

    candidates: List[str] = []
    if href_clean.startswith('http://') or href_clean.startswith('https://'):
        candidates.append(href_clean)
    else:
        rel = href_clean.lstrip('./')
        candidates.append(urljoin(article_url, rel))
        candidates.append(urljoin(article_url, f"bin/{rel}"))

    # If XML omits extension, probe common image extensions used by PMC.
    has_ext = bool(re.search(r'\.[A-Za-z0-9]{2,5}$', href_clean))
    if not has_ext:
        expanded: List[str] = []
        for base in candidates:
            expanded.append(base)
            for ext in ('.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.webp'):
                expanded.append(base + ext)
        candidates = expanded

    deduped: List[str] = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def _extract_figures_from_pmc_xml(root, article_url: str) -> List[Dict[str, Any]]:
    figures: List[Dict[str, Any]] = []
    seen = set()

    for fig in root.iter():
        if not _jats_tag_matches(fig, 'fig'):
            continue

        label_text = ""
        caption_text = ""
        href_values: List[str] = []

        for child in fig:
            if _jats_tag_matches(child, 'label'):
                label_text = _collect_xml_text(child).strip()
            elif _jats_tag_matches(child, 'caption'):
                caption_text = _collect_xml_text(child).strip()

        for elem in fig.iter():
            if not (_jats_tag_matches(elem, 'graphic') or _jats_tag_matches(elem, 'inline-graphic') or _jats_tag_matches(elem, 'media')):
                continue
            for attr_name, attr_value in elem.attrib.items():
                if str(attr_name).endswith('href') and attr_value:
                    href_values.append(str(attr_value))

        if not href_values:
            continue

        candidate_urls: List[str] = []
        for href in href_values:
            candidate_urls.extend(_build_pmc_figure_url_candidates(article_url, href))

        dedup_candidates: List[str] = []
        candidate_seen = set()
        for url in candidate_urls:
            if url in candidate_seen:
                continue
            candidate_seen.add(url)
            dedup_candidates.append(url)

        if not dedup_candidates:
            continue

        # Use URL alone as the dedup key: multi-panel figures (1A, 1B, 1C) share a parent
        # caption but have distinct image URLs — (label, caption, url) collapses them to
        # just the first panel. Deduping by URL preserves all panels independently.
        figure_key = dedup_candidates[0]
        if figure_key in seen:
            continue
        seen.add(figure_key)

        figures.append({
            "label": label_text,
            "caption": caption_text,
            "url": dedup_candidates[0],
            "url_candidates": dedup_candidates,
            "source": "pmc_xml",
        })

    return figures


def _figure_identity_keys(figure: Dict[str, Any]) -> set[str]:
    """Return stable keys for deduping figure metadata from multiple parsers."""
    keys = set()

    graphic_ref = str(figure.get("graphic_ref") or "").strip()
    if graphic_ref:
        keys.add(f"graphic:{graphic_ref}")

    url = str(figure.get("url") or "").strip()
    if url:
        keys.add(f"url:{url}")

    for candidate in figure.get("url_candidates") or []:
        candidate_url = str(candidate or "").strip()
        if candidate_url:
            keys.add(f"url:{candidate_url}")

    return keys


def _merge_figure_metadata(
    pubmed_parser_figures: List[Dict[str, Any]],
    researchshop_figures: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge pubmed_parser figures with ResearchShop's JATS figure parser.

    pubmed_parser can provide useful IDs and graphic refs, but browser ground
    truth showed it may return only a subset of article figures. Treat it as an
    enrichment source, not an exclusive replacement.
    """
    merged: List[Dict[str, Any]] = []
    key_to_index: Dict[str, int] = {}

    def _add_or_merge(figure: Dict[str, Any]) -> None:
        keys = _figure_identity_keys(figure)
        existing_indices = {key_to_index[key] for key in keys if key in key_to_index}

        if not existing_indices:
            merged.append(dict(figure))
            index = len(merged) - 1
            for key in keys:
                key_to_index[key] = index
            return

        index = min(existing_indices)
        existing = merged[index]

        for field in ("label", "caption", "url", "source", "parser", "fig_id", "graphic_ref"):
            if not existing.get(field) and figure.get(field):
                existing[field] = figure[field]

        existing_candidates = list(existing.get("url_candidates") or [])
        for candidate in figure.get("url_candidates") or []:
            if candidate and candidate not in existing_candidates:
                existing_candidates.append(candidate)
        if existing_candidates:
            existing["url_candidates"] = existing_candidates

        for key in _figure_identity_keys(existing):
            key_to_index[key] = index

    for figure in pubmed_parser_figures:
        _add_or_merge(figure)
    for figure in researchshop_figures:
        _add_or_merge(figure)

    return merged


def _extract_structured_tables_from_pmc_xml(root) -> List[StructuredTable]:
    """Parse <table-wrap> elements into StructuredTable objects.

    This is ADDITIVE to the existing flat-text table embedding in
    _extract_text_and_figures_from_pmc_xml (lines 450-490) which must remain
    unchanged for grounding check compatibility.
    """
    tables: List[StructuredTable] = []
    max_tables = getattr(config, 'TABLE_MAX_PER_PAPER', 20)
    auto_idx = 0

    for table_wrap in root.iter():
        if not _jats_tag_matches(table_wrap, 'table-wrap'):
            continue
        if len(tables) >= max_tables:
            break

        # Table ID from XML attribute
        table_id = table_wrap.attrib.get('id', '')
        if not table_id:
            table_id = f"table_{auto_idx}"
        auto_idx += 1

        # Label
        label = ""
        for child in list(table_wrap):
            if _jats_tag_matches(child, 'label'):
                label = _collect_xml_text(child).strip()
                break

        # Caption
        caption = ""
        for child in list(table_wrap):
            if _jats_tag_matches(child, 'caption'):
                caption = _collect_xml_text(child).strip()
                break

        # Footnotes
        footnotes = ""
        for fn in table_wrap.iter():
            if _jats_tag_matches(fn, 'table-wrap-foot'):
                footnotes = _collect_xml_text(fn).strip()
                break

        # Headers and data rows
        headers: List[str] = []
        data_rows: List[List[str]] = []

        for table in table_wrap.iter():
            if not _jats_tag_matches(table, 'table'):
                continue
            for row in table.iter():
                if not _jats_tag_matches(row, 'tr'):
                    continue
                cells = []
                has_th = False
                for cell in list(row):
                    if _jats_tag_matches(cell, 'th'):
                        has_th = True
                        cells.append(_collect_xml_text(cell).strip())
                    elif _jats_tag_matches(cell, 'td'):
                        cells.append(_collect_xml_text(cell).strip())
                if not cells:
                    continue
                # First row with <th> cells becomes the header
                if has_th and not headers:
                    headers = cells
                else:
                    data_rows.append(cells)

        tables.append(StructuredTable(
            table_id=table_id,
            label=label,
            caption=caption,
            headers=headers,
            rows=data_rows,
            footnotes=footnotes,
            source_section="body",
        ))

    return tables


def _extract_body_sections_from_pmc_root(root) -> List[str]:
    """Fallback body-section parser used when pubmed_parser yields no body text."""
    sections: List[str] = []

    for body in root.iter():
        if not _jats_tag_matches(body, 'body'):
            continue

        # Collect <p> elements that are direct children of <body> (not inside <sec>)
        for child in list(body):
            if _jats_tag_matches(child, 'p'):
                text = _collect_xml_text(child).strip()
                if text:
                    sections.append(text)

        for sec in body.iter():
            if not _jats_tag_matches(sec, 'sec'):
                continue
            title_text = ""
            for child in list(sec):
                if _jats_tag_matches(child, 'title'):
                    title_text = _collect_xml_text(child).strip()
                    break
            if title_text:
                sections.append(f"\n{title_text}\n")
            for p in list(sec):
                if _jats_tag_matches(p, 'p'):
                    text = _collect_xml_text(p).strip()
                    if text:
                        sections.append(text)

    return sections


def _extract_text_and_figures_from_pmc_xml(xml_bytes: bytes, article_url: Optional[str] = None) -> Tuple[Optional[str], List[Dict[str, Any]], List[StructuredTable]]:
    """
    Parse PMC full-text XML and extract text + figure metadata + structured tables.

    pubmed_parser is used first for body paragraphs and figure metadata because
    it understands standard PMC OA JATS. ResearchShop's parser remains the
    fallback and still owns abstract, tables, supplementary files, and schema
    normalization.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.debug(f"Failed to parse PMC XML: {e}")
        return None, [], []

    sections: List[str] = []
    figures: List[Dict[str, Any]] = []

    # Extract abstract from <front>
    for abstract in root.iter():
        if not _jats_tag_matches(abstract, 'abstract'):
            continue
        for p in abstract.iter():
            if _jats_tag_matches(p, 'p'):
                text = _collect_xml_text(p).strip()
                if text:
                    sections.append(text)

    # Extract body sections. Prefer pubmed_parser, but keep the previous parser
    # as the fallback for unusual JATS structures or parser failures.
    body_text = pubmed_xml_parser.parse_pubmed_parser_paragraph_text(xml_bytes)
    if body_text:
        sections.append(body_text)
    else:
        sections.extend(_extract_body_sections_from_pmc_root(root))

    if not sections:
        # Fallback: grab all <p> elements anywhere in the document
        for p in root.iter():
            if _jats_tag_matches(p, 'p'):
                text = _collect_xml_text(p).strip()
                if text:
                    sections.append(text)

    # Extract tables — convert <table-wrap> elements to plain text
    for table_wrap in root.iter():
        if not _jats_tag_matches(table_wrap, 'table-wrap'):
            continue

        table_parts: List[str] = []

        for child in list(table_wrap):
            if _jats_tag_matches(child, 'caption'):
                caption_text = _collect_xml_text(child).strip()
                if caption_text:
                    table_parts.append(f"Table: {caption_text}")
            elif _jats_tag_matches(child, 'label'):
                label_text = _collect_xml_text(child).strip()
                if label_text and not table_parts:
                    table_parts.append(f"Table: {label_text}")

        for fn in table_wrap.iter():
            if _jats_tag_matches(fn, 'table-wrap-foot'):
                fn_text = _collect_xml_text(fn).strip()
                if fn_text:
                    table_parts.append(f"Note: {fn_text}")

        for table in table_wrap.iter():
            if not _jats_tag_matches(table, 'table'):
                continue
            rows: List[str] = []
            for row in table.iter():
                if not _jats_tag_matches(row, 'tr'):
                    continue
                cells = []
                for cell in list(row):
                    if _jats_tag_matches(cell, 'td') or _jats_tag_matches(cell, 'th'):
                        cells.append(_collect_xml_text(cell).strip())
                if cells:
                    rows.append('\t'.join(cells))
            if rows:
                table_parts.append('\n'.join(rows))

        if table_parts:
            sections.append('\n'.join(table_parts))

    # Extract figure metadata and include captions in text context.
    if article_url and getattr(config, 'ENABLE_FIGURE_ANALYSIS', True):
        figures = _merge_figure_metadata(
            pubmed_xml_parser.parse_pubmed_parser_figures(xml_bytes, article_url),
            _extract_figures_from_pmc_xml(root, article_url),
        )
        for fig in figures:
            label = (fig.get("label") or "").strip()
            caption = (fig.get("caption") or "").strip()
            if caption:
                prefix = f"{label}: " if label else ""
                sections.append(f"Figure: {prefix}{caption}")

    if article_url and getattr(config, 'ENABLE_SUPPLEMENTARY_EXTRACTION', True):
        supp_links = _extract_supplementary_urls_from_pmc_xml(root, article_url)
        if supp_links:
            sections.append("Supplementary files:")
            max_files = max(getattr(config, 'SUPPLEMENTARY_MAX_FILES', 3), 0)
            max_chars = max(getattr(config, 'SUPPLEMENTARY_MAX_CHARS', 200000), 1000)
            total_chars = 0
            for idx, (label, s_url) in enumerate(supp_links):
                if idx >= max_files:
                    break
                sections.append(f"- {label}: {s_url}")
                supp_text = _extract_supplementary_content(s_url)
                if supp_text:
                    remaining = max_chars - total_chars
                    if remaining <= 0:
                        break
                    clipped = supp_text[:remaining]
                    total_chars += len(clipped)
                    sections.append(f"[Supplementary extracted]\n{clipped}")

    # Extract structured tables (additive — existing flat-text embedding above is unchanged)
    structured_tables = _extract_structured_tables_from_pmc_xml(root)

    if not sections:
        return None, figures, structured_tables

    return '\n\n'.join(sections), figures, structured_tables


def _extract_text_from_pmc_xml(xml_bytes: bytes, article_url: Optional[str] = None) -> Optional[str]:
    """
    Backward-compatible wrapper: returns only text content.
    """
    text, _, _ = _extract_text_and_figures_from_pmc_xml(xml_bytes, article_url=article_url)
    return text


# ---------------------------------------------------------------------------
# Content quality helpers
# ---------------------------------------------------------------------------

@dataclass
class ContentExtractionResult:
    """Result of content extraction with quality metrics."""
    pmid: str
    url: str
    content: str
    extraction_method: str
    content_length: int
    quality_score: float
    is_paywalled: bool = False  # Always False; retained for downstream dict compatibility
    content_type: str = "unknown"
    error_message: Optional[str] = None
    figures: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[StructuredTable] = field(default_factory=list)

    def is_good_quality(self, min_length: int = 1000, min_quality: float = 0.3) -> bool:
        """Check if extracted content meets quality thresholds."""
        return (self.content_length >= min_length and
                self.quality_score >= min_quality and
                self.error_message is None and
                self.content_type in ["full_article", "substantial_content"])


def _clean_and_validate_content(content: str, url: str) -> Tuple[str, str]:
    """
    Clean and validate extracted content.

    Returns:
        Tuple of (cleaned_content, content_type)
        content_type: 'full_article', 'abstract_only', 'access_page', or 'empty'
    """
    if not content:
        return "", "empty"

    # Transliterate common Greek letters used in biomedical text, then remove remaining non-ASCII
    greek_map = {'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta', 'ε': 'epsilon',
                 'κ': 'kappa', 'λ': 'lambda', 'μ': 'mu', 'π': 'pi', 'σ': 'sigma', 'τ': 'tau',
                 'Α': 'Alpha', 'Β': 'Beta', 'Γ': 'Gamma', 'Δ': 'Delta',
                 '±': '+/-', '≥': '>=', '≤': '<=', '→': '->', '×': 'x', '−': '-',
                 'Ω': 'Omega', 'ω': 'omega', 'θ': 'theta', 'φ': 'phi', 'χ': 'chi', 'ψ': 'psi'}
    cleaned = content
    for char, repl in greek_map.items():
        cleaned = cleaned.replace(char, repl)
    cleaned = re.sub(r'[^\x00-\x7F\t\n]+', ' ', cleaned)  # Remove non-ASCII but keep tab and newline
    # Normalize whitespace while preserving structural separators:
    #   \t separates table columns, \n separates table rows and paragraphs.
    # re.sub(r'\s+', ' ') would destroy this structure, converting tab-separated table data
    # into an unreadable run-on string. Instead, normalise each type independently.
    cleaned = re.sub(r'[ \r]+', ' ', cleaned)    # Collapse spaces/carriage-returns only
    cleaned = re.sub(r'\t+', '\t', cleaned)       # Collapse consecutive tabs to one
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Max two consecutive newlines
    cleaned = cleaned.strip()

    # Determine content type based on URL and content characteristics
    url_lower = url.lower()
    content_lower = cleaned.lower()

    # Check for academic content indicators
    academic_indicators = [
        'abstract', 'introduction', 'methods', 'results', 'discussion', 'conclusion',
        'figure', 'table', 'references', 'acknowledgment'
    ]

    academic_score = sum(1 for indicator in academic_indicators if indicator in content_lower)

    # Validate content quality
    if len(cleaned) < 100:
        return "", "empty"

    # Classify content type
    if len(cleaned) > 5000 and academic_score >= 3:
        content_type = "full_article"
    elif len(cleaned) > 1000 and academic_score >= 2:
        content_type = "substantial_content"
    elif len(cleaned) > 500 and academic_score >= 1:
        content_type = "abstract_content"
    elif any(term in url_lower for term in ['pmc', 'articles']):
        content_type = "full_article"  # PMC articles should be full
    else:
        content_type = "minimal_content"

    # Check for obvious non-content (just navigation, ads, etc.)
    non_content_indicators = [
        'advertisement',
        'sponsored content',
        'related articles',
        'recommended reading',
        'most popular',
        'trending now'
    ]

    content_lower = cleaned.lower()
    non_content_count = sum(1 for indicator in non_content_indicators if indicator in content_lower)

    if non_content_count > 2:  # If multiple non-content indicators
        logger.warning(f"Content may be low quality for {url}: too many non-content indicators")
        content_type = "low_quality"

    return cleaned, content_type


def _assess_content_quality(content: str, url: str) -> float:
    """Assess the quality of extracted content."""
    if not content or len(content) < 100:
        return 0.0

    score = 0.0

    # Length factor (longer content is generally better)
    content_len = len(content)
    if content_len > 5000:
        score += 0.3
    elif content_len > 2000:
        score += 0.2
    elif content_len > 1000:
        score += 0.1

    # Word count factor
    word_count = len(content.split())
    if word_count > 1000:
        score += 0.2
    elif word_count > 500:
        score += 0.1

    # Content diversity (sentences vs. repetitive text)
    sentences = len(re.split(r'[.!?]+', content))
    if sentences > 20:
        score += 0.2
    elif sentences > 10:
        score += 0.1

    # Check for academic content indicators
    academic_indicators = [
        'abstract', 'introduction', 'methods', 'results', 'discussion', 'conclusion',
        'figure', 'table', 'references', 'acknowledgment'
    ]

    academic_score = sum(1 for indicator in academic_indicators if indicator in content.lower())
    score += min(academic_score * 0.05, 0.2)  # Cap at 0.2

    # Penalize obvious non-content
    if any(indicator in content.lower() for indicator in ['advertisement', 'sponsored', 'login required']):
        score -= 0.3

    return min(max(score, 0.0), 1.0)  # Clamp between 0 and 1


# ---------------------------------------------------------------------------
# OA API fetch paths
# ---------------------------------------------------------------------------

def _fetch_pmc_efetch(pmid: str, pmc_id: str) -> Optional[ContentExtractionResult]:
    """
    Fetch full text directly from PMC using Entrez.efetch.

    This is the fastest and most reliable path for PMC-available papers.
    Returns a ContentExtractionResult on success, or None to fall through
    to the Europe PMC path.
    """
    pmc_num = pmc_id.replace('PMC', '')

    try:
        time.sleep(0.34)  # Rate limit: 3 req/sec for NCBI
        handle = Entrez.efetch(db='pmc', id=pmc_num, rettype='full', retmode='xml')
        xml_bytes = handle.read()
        handle.close()

        if not xml_bytes:
            logger.debug(f"PMC efetch returned empty response for {pmc_id}")
            return None

        # Ensure we have bytes for XML parsing
        if isinstance(xml_bytes, str):
            xml_bytes = xml_bytes.encode('utf-8')

        article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
        body_text, figures, tables = _extract_text_and_figures_from_pmc_xml(xml_bytes, article_url=article_url)

        if not body_text or len(body_text.strip()) < 500:
            logger.debug(f"PMC efetch XML for {pmc_id} yielded insufficient text "
                        f"({len(body_text.strip()) if body_text else 0} chars)")
            return None

        cleaned_content, content_type = _clean_and_validate_content(body_text, article_url)
        quality_score = _assess_content_quality(cleaned_content, f"pmc_efetch:{pmc_id}")

        logger.info(f"PMC efetch succeeded for PMID {pmid} ({pmc_id}): "
                    f"{len(cleaned_content)} chars, quality {quality_score:.2f}")

        return ContentExtractionResult(
            pmid=pmid,
            url=article_url,
            content=cleaned_content,
            extraction_method="pmc_efetch",
            content_length=len(cleaned_content),
            quality_score=quality_score,
            is_paywalled=False,
            content_type=content_type,
            figures=figures,
            tables=tables,
        )

    except Exception as e:
        logger.debug(f"PMC efetch failed for {pmc_id}: {e}")
        return None


def _fetch_europe_pmc_fulltext_xml(pmid: str) -> Optional[ContentExtractionResult]:
    """
    Fetch full-text XML from Europe PMC as OA API fallback.
    """
    if not getattr(config, 'ENABLE_EUROPE_PMC_FALLBACK', True):
        return None

    pmc_id = _get_pmcid_for_pmid(pmid)
    if not pmc_id:
        return None

    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc_id}/fullTextXML"
    try:
        r = requests.get(url, timeout=max(config.REQUEST_TIMEOUT, 20))
        if r.status_code != 200 or not r.content:
            return None

        # Use NCBI PMC article base for figure/supplement relative href resolution.
        article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
        body_text, figures, tables = _extract_text_and_figures_from_pmc_xml(r.content, article_url=article_url)
        if not body_text or len(body_text.strip()) < 500:
            return None

        cleaned_content, content_type = _clean_and_validate_content(body_text, article_url)
        quality_score = _assess_content_quality(cleaned_content, f"europe_pmc:{pmid}")

        return ContentExtractionResult(
            pmid=pmid,
            url=article_url,
            content=cleaned_content,
            extraction_method="europe_pmc_xml",
            content_length=len(cleaned_content),
            quality_score=quality_score,
            is_paywalled=False,
            content_type=content_type,
            figures=figures,
            tables=tables,
        )
    except Exception as e:
        logger.debug(f"Europe PMC fullTextXML failed for PMID {pmid}: {e}")
        return None


# ---------------------------------------------------------------------------
# Per-PMID orchestration
# ---------------------------------------------------------------------------

def _process_single_pmid(pmid: str) -> Optional[ContentExtractionResult]:
    """
    Fetch full text for a single PMID using OA API paths only.

    Path 1: PMC Entrez efetch (structured JATS XML — fastest, preferred)
    Path 2: Europe PMC fullTextXML (alternative OA XML endpoint)

    Returns a ContentExtractionResult; content will be empty if neither path
    succeeds (paper has no PMC record or JATS full text is not deposited).
    """
    # Path 1: PMC efetch
    pmc_id = _get_pmcid_for_pmid(pmid)
    if pmc_id:
        efetch_result = _fetch_pmc_efetch(pmid, pmc_id)
        if efetch_result and efetch_result.is_good_quality():
            return efetch_result
        elif efetch_result:
            logger.debug(f"PMC efetch content for PMID {pmid} below quality threshold, "
                        f"falling through to Europe PMC")

    # Path 2: Europe PMC fullTextXML
    europe_result = _fetch_europe_pmc_fulltext_xml(pmid)
    if europe_result and europe_result.is_good_quality():
        return europe_result
    elif europe_result:
        logger.debug(f"Europe PMC XML content for PMID {pmid} below quality threshold")

    # No OA full text available
    logger.warning(f"No full text available for PMID {pmid} via OA APIs (PMC efetch + Europe PMC)")
    return ContentExtractionResult(
        pmid=pmid,
        url="",
        content="",
        extraction_method="no_oa_full_text",
        content_length=0,
        quality_score=0.0,
        is_paywalled=False,
        error_message="No full text available via OA APIs (PMC efetch + Europe PMC)"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_fetching(pmids: list, output_path: str):
    """
    Fetch full text for a list of PMIDs (OA papers only) and write a
    gzip-pickled content_dict to output_path.
    """
    content_dict = {}
    success_count = 0
    failure_count = 0
    figures_count = 0
    tables_count = 0

    for pmid in tqdm(pmids, desc="Extracting Full-Text Content"):
        try:
            result = _process_single_pmid(pmid)

            if result:
                content_dict[result.pmid] = {
                    'pmid': result.pmid,
                    'url': result.url,
                    'content': result.content,
                    'extraction_method': result.extraction_method,
                    'content_length': result.content_length,
                    'quality_score': result.quality_score,
                    'is_paywalled': False,
                    'content_type': result.content_type,
                    'error_message': result.error_message,
                    'figures': result.figures or [],
                    'tables': [t.to_dict() for t in (result.tables or [])],
                    'type': 'text' if result.content else 'failed'
                }
                if result.figures:
                    figures_count += len(result.figures)
                if result.tables:
                    tables_count += len(result.tables)

                if result.content_length > 0:
                    success_count += 1
                else:
                    failure_count += 1

        except Exception as e:
            logger.error(f"Unexpected error processing PMID {pmid}: {e}")
            failure_count += 1

        # Small delay to be respectful to NCBI rate limits
        time.sleep(1)

    total_processed = success_count + failure_count
    if total_processed > 0:
        logger.info("Full-text extraction summary:")
        logger.info(f"  Successfully extracted: {success_count}/{total_processed} ({success_count/total_processed*100:.1f}%)")
        logger.info(f"  No full text found:     {failure_count}/{total_processed} ({failure_count/total_processed*100:.1f}%)")
        logger.info(f"  Figures discovered:     {figures_count}")
        logger.info(f"  Tables discovered:      {tables_count}")

    try:
        with gzip.open(output_path, 'wb') as f:
            pickle.dump(content_dict, f)
        logger.info(f"Saved extracted content for {len(content_dict)} PMIDs to {output_path}")
    except IOError as e:
        logger.error(f"Failed to save content dictionary: {e}")
        return None

    return content_dict


# ---------------------------------------------------------------------------
# Fetch forensics
# ---------------------------------------------------------------------------

def generate_fetch_report(content_dict: Dict) -> List[Dict]:
    """Build a FetchOutcome summary for each paper in content_dict."""
    outcomes: List[Dict] = []
    for pmid, entry in content_dict.items():
        method = entry.get('extraction_method')
        error = entry.get('error_message')
        outcomes.append(dataclasses.asdict(FetchOutcome(
            pmid=str(pmid),
            method_succeeded=method if method and method != 'no_oa_full_text' else None,
            content_length=entry.get('content_length', 0),
            figure_count=len(entry.get('figures', [])),
            table_count=len(entry.get('tables', [])),
            error_message=error,
        )))
    return outcomes
