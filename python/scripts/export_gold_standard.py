#!/usr/bin/env python3
"""
Export gold_standard.json to per-category CSVs for human review.

Writes one CSV per paper type to data/benchmark/review/
Each row = one paper with pmid, title, expected_genes, expected_genes_comprehensive.

Usage:
    python scripts/export_gold_standard.py
"""

import csv
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BENCHMARK_DIR = SCRIPT_DIR.parent / "data" / "benchmark"
GOLD_STANDARD_PATH = BENCHMARK_DIR / "gold_standard.json"
OUT_DIR = BENCHMARK_DIR / "review"
OUT_DIR.mkdir(exist_ok=True)

COLUMNS = [
    "pmid",
    "title",
    "pmcid",
    "oa_confirmed",
    "expected_genes",
    "expected_genes_comprehensive",
    "gold_standard_source",
    "notes",
]


def flatten_genes(gene_list: list) -> str:
    """Convert gene list (strings or rich objects) to a semicolon-separated string."""
    symbols = []
    for g in gene_list:
        if isinstance(g, str):
            symbols.append(g)
        elif isinstance(g, dict):
            symbols.append(g.get("symbol", ""))
    return "; ".join(symbols)


def main():
    with open(GOLD_STANDARD_PATH) as f:
        gold = json.load(f)

    by_type: dict = {}
    for paper in gold["papers"]:
        t = paper["type"]
        by_type.setdefault(t, []).append(paper)

    for ptype, papers in sorted(by_type.items()):
        out_path = OUT_DIR / f"review_{ptype}.csv"
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            for p in papers:
                writer.writerow({
                    "pmid": p["pmid"],
                    "title": p.get("title", ""),
                    "pmcid": p.get("pmcid", ""),
                    "oa_confirmed": p.get("oa_confirmed", ""),
                    "expected_genes": flatten_genes(p.get("expected_genes", [])),
                    "expected_genes_comprehensive": flatten_genes(p.get("expected_genes_comprehensive", [])),
                    "gold_standard_source": p.get("gold_standard_source", ""),
                    "notes": p.get("notes", ""),
                })
        print(f"  {ptype} ({len(papers)} papers) → {out_path}")

    print(f"\nTotal: {sum(len(v) for v in by_type.values())} papers across {len(by_type)} categories")


if __name__ == "__main__":
    main()
