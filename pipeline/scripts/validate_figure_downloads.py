#!/usr/bin/env python3
"""Validate extracted PMC figure URLs against live downloadable image bytes."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from parser_ground_truth_common import (  # noqa: E402
    DEFAULT_ARTICLES_PATH,
    configure_live_parser_run,
    extract_current_article,
    load_articles,
)
from modules.stage5.figures import FigureMixin  # noqa: E402


class FigureDownloadProbe(FigureMixin):
    pass


def validate_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    configure_live_parser_run()

    probe = FigureDownloadProbe()
    rows: List[Dict[str, Any]] = []

    for article in articles:
        pmid = str(article["pmid"])
        pmcid = str(article["pmcid"])
        _text, figures, _tables = extract_current_article(article)

        if not figures:
            rows.append({
                "pmid": pmid,
                "pmcid": pmcid,
                "label": "",
                "downloadable": "n/a",
                "mime_type": "",
                "bytes": 0,
                "resolved_url": "",
                "primary_url": "",
            })
            continue

        for figure in figures:
            resolved = probe._resolve_figure_download_url(figure)
            rows.append({
                "pmid": pmid,
                "pmcid": pmcid,
                "label": figure.get("label") or "",
                "downloadable": "yes" if resolved else "no",
                "mime_type": (resolved or {}).get("mime_type", ""),
                "bytes": (resolved or {}).get("bytes", 0),
                "resolved_url": (resolved or {}).get("url", ""),
                "primary_url": figure.get("url") or "",
            })

    return rows


def render_markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Figure Download Validation",
        "",
        "Live validation that current extracted figure metadata resolves to downloadable image bytes.",
        "",
        "| PMID | PMCID | Figure | Downloadable | MIME | Bytes | Resolved URL |",
        "|---|---|---|---|---|---:|---|",
    ]
    for row in rows:
        bytes_value = row["bytes"] if row["bytes"] else ""
        lines.append(
            "| {pmid} | {pmcid} | {label} | {downloadable} | {mime_type} | {bytes} | {url} |".format(
                pmid=row["pmid"],
                pmcid=row["pmcid"],
                label=row["label"],
                downloadable=row["downloadable"],
                mime_type=row["mime_type"],
                bytes=bytes_value,
                url=row["resolved_url"],
            )
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--articles",
        type=Path,
        default=DEFAULT_ARTICLES_PATH,
        help="JSON fixture containing pmid and pmcid records.",
    )
    parser.add_argument("--output", type=Path, help="Optional markdown output path.")
    args = parser.parse_args()

    rows = validate_articles(load_articles(args.articles))
    markdown = render_markdown(rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
