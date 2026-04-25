"""Shared helpers for parser/browser ground-truth scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from Bio import Entrez

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTICLES_PATH = PIPELINE_ROOT / "tests" / "fixtures" / "pmc_browser_ground_truth.json"

if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from modules import config  # noqa: E402
from modules.full_text_fetcher import (  # noqa: E402
    StructuredTable,
    _extract_text_and_figures_from_pmc_xml,
)


def load_articles(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected list of article records in {path}")
    return data


def configure_live_parser_run() -> None:
    config.ENABLE_FIGURE_ANALYSIS = True
    config.ENABLE_SUPPLEMENTARY_EXTRACTION = False
    Entrez.email = getattr(config, "ENTREZ_EMAIL", None) or "researchshop@example.com"


def article_url(pmcid: str) -> str:
    return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"


def fetch_pmc_xml(pmcid: str) -> bytes:
    handle = Entrez.efetch(db="pmc", id=pmcid.replace("PMC", ""), rettype="full", retmode="xml")
    try:
        xml_bytes = handle.read()
    finally:
        handle.close()
    if isinstance(xml_bytes, str):
        return xml_bytes.encode("utf-8")
    return xml_bytes


def extract_current_article(
    article: Dict[str, Any],
) -> Tuple[str, List[Dict[str, Any]], List[StructuredTable]]:
    pmcid = str(article["pmcid"])
    text, figures, tables = _extract_text_and_figures_from_pmc_xml(
        fetch_pmc_xml(pmcid),
        article_url=article_url(pmcid),
    )
    return text or "", figures, tables
