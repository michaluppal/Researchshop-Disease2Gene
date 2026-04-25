#!/usr/bin/env python3
"""Compare current PMC parser output against browser ground-truth fixtures."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Dict, List

from parser_ground_truth_common import (
    DEFAULT_ARTICLES_PATH,
    configure_live_parser_run,
    extract_current_article,
    load_articles,
)


def _count_hits(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def _browser_metrics(article: Dict[str, Any]) -> Dict[str, Any]:
    metrics = article.get("browser_reference") or {}
    return metrics if isinstance(metrics, dict) else {}


def compare_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    configure_live_parser_run()

    rows: List[Dict[str, Any]] = []
    for article in articles:
        pmid = str(article["pmid"])
        pmcid = str(article["pmcid"])
        browser = _browser_metrics(article)
        text, figures, tables = extract_current_article(article)
        current = {
            "chars": len(text),
            "words": len(text.split()),
            "figures": len(figures),
            "tables": len(tables),
            "results_hits": _count_hits(text, r"results?"),
            "table_hits": _count_hits(text, r"tables?"),
            "figure_hits": _count_hits(text, r"figures?"),
        }

        rows.append({
            "pmid": pmid,
            "pmcid": pmcid,
            "browser_source": browser.get("source", ""),
            "browser": browser,
            "current": current,
            "figure_delta": current["figures"] - int(browser.get("figure_count", 0)),
            "table_delta": current["tables"] - int(browser.get("table_count", 0)),
        })

    return rows


def render_markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Current Parser vs Browser Ground Truth",
        "",
        "Current ResearchShop extraction is compared to browser-visible PMC article references.",
        "Parser text is expected to be cleaner and shorter than browser page text.",
        "",
        "| PMID | PMCID | Source | Browser chars | Current chars | Browser words | Current words | Browser figures | Current figures | Browser tables | Current tables | Figure delta | Table delta |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        browser = row["browser"]
        current = row["current"]
        lines.append(
            "| {pmid} | {pmcid} | {source} | {b_chars} | {c_chars} | {b_words} | {c_words} | {b_figs} | {c_figs} | {b_tables} | {c_tables} | {fig_delta} | {table_delta} |".format(
                pmid=row["pmid"],
                pmcid=row["pmcid"],
                source=row["browser_source"],
                b_chars=browser.get("chars", ""),
                c_chars=current["chars"],
                b_words=browser.get("words", ""),
                c_words=current["words"],
                b_figs=browser.get("figure_count", ""),
                c_figs=current["figures"],
                b_tables=browser.get("table_count", ""),
                c_tables=current["tables"],
                fig_delta=row["figure_delta"],
                table_delta=row["table_delta"],
            )
        )

    lines.extend([
        "",
        "## Hit Counts",
        "",
        "| PMID | Browser results | Current results | Browser table hits | Current table hits | Browser figure hits | Current figure hits |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])

    for row in rows:
        browser = row["browser"]
        current = row["current"]
        lines.append(
            "| {pmid} | {b_results} | {c_results} | {b_table_hits} | {c_table_hits} | {b_figure_hits} | {c_figure_hits} |".format(
                pmid=row["pmid"],
                b_results=browser.get("results_hits", ""),
                c_results=current["results_hits"],
                b_table_hits=browser.get("table_hits", ""),
                c_table_hits=current["table_hits"],
                b_figure_hits=browser.get("figure_hits", ""),
                c_figure_hits=current["figure_hits"],
            )
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--articles",
        type=Path,
        default=DEFAULT_ARTICLES_PATH,
        help="JSON fixture containing browser_reference metrics.",
    )
    parser.add_argument("--output", type=Path, help="Optional markdown output path.")
    args = parser.parse_args()

    rows = compare_articles(load_articles(args.articles))
    markdown = render_markdown(rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
