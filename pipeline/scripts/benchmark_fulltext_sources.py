#!/usr/bin/env python3
"""
Benchmark full-text source quality across API and scraping paths.

Usage:
  python scripts/benchmark_fulltext_sources.py --pmids 31452104,30049270 --out benchmark.csv
"""

import argparse
import csv
import os
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from modules import full_text_fetcher  # noqa: E402


def _run_pmc_efetch(pmid: str):
    pmc_id = full_text_fetcher._get_pmcid_for_pmid(pmid)
    if not pmc_id:
        return None
    return full_text_fetcher._fetch_pmc_efetch(pmid, pmc_id)


def _run_europe_pmc(pmid: str):
    return full_text_fetcher._fetch_europe_pmc_fulltext_xml(pmid)


def _run_scrape_path(pmid: str):
    urls = full_text_fetcher._get_multiple_article_urls(pmid)
    if not urls:
        return None
    # First URL only for deterministic benchmark cost
    result = full_text_fetcher._extract_content_robust(urls[0])
    result.pmid = pmid
    return result


def _to_row(pmid: str, method: str, result):
    if not result:
        return {
            "pmid": pmid,
            "method": method,
            "success": 0,
            "content_length": 0,
            "quality_score": 0.0,
            "content_type": "",
            "is_paywalled": "",
            "url": "",
            "error_message": "no_result",
        }
    return {
        "pmid": pmid,
        "method": method,
        "success": 1 if (result.content and len(result.content) > 0) else 0,
        "content_length": result.content_length,
        "quality_score": result.quality_score,
        "content_type": result.content_type or "",
        "is_paywalled": str(result.is_paywalled),
        "url": result.url or "",
        "error_message": result.error_message or "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmids", required=True, help="Comma-separated PMID list")
    ap.add_argument("--out", default=f"benchmark_fulltext_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv")
    args = ap.parse_args()

    pmids = [p.strip() for p in args.pmids.split(",") if p.strip()]
    rows = []
    for pmid in pmids:
        rows.append(_to_row(pmid, "pmc_efetch", _run_pmc_efetch(pmid)))
        rows.append(_to_row(pmid, "europe_pmc_xml", _run_europe_pmc(pmid)))
        rows.append(_to_row(pmid, "scrape_first_url", _run_scrape_path(pmid)))

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "pmid",
                "method",
                "success",
                "content_length",
                "quality_score",
                "content_type",
                "is_paywalled",
                "url",
                "error_message",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote benchmark rows: {len(rows)} -> {args.out}")


if __name__ == "__main__":
    main()
