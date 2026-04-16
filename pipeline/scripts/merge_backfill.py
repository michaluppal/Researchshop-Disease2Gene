#!/usr/bin/env python3
"""
Merge backfill/{PMID}.json files into gold_standard.json.

Reads all JSON files from data/benchmark/backfill/, adds
expected_genes_comprehensive to matching papers in gold_standard.json,
and updates benchmark_version to 2.0.

Usage:
    python scripts/merge_backfill.py [--dry-run]
"""

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PYTHON_DIR = SCRIPT_DIR.parent
BENCHMARK_DIR = PYTHON_DIR / "data" / "benchmark"
BACKFILL_DIR = BENCHMARK_DIR / "backfill"
GOLD_STANDARD_PATH = BENCHMARK_DIR / "gold_standard.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    with open(GOLD_STANDARD_PATH) as f:
        gold = json.load(f)

    backfill_files = list(BACKFILL_DIR.glob("*.json"))
    if not backfill_files:
        print("No backfill files found in", BACKFILL_DIR)
        return

    backfill_by_pmid = {}
    for path in backfill_files:
        with open(path) as f:
            data = json.load(f)
        backfill_by_pmid[data["pmid"]] = data

    updated = 0
    skipped = 0
    for paper in gold["papers"]:
        pmid = paper["pmid"]
        if pmid not in backfill_by_pmid:
            print(f"  MISSING backfill: {pmid}")
            skipped += 1
            continue
        bf = backfill_by_pmid[pmid]
        comp = bf.get("expected_genes_comprehensive", [])
        if not comp:
            print(f"  EMPTY comprehensive list for {pmid} — skipping")
            skipped += 1
            continue
        if not args.dry_run:
            paper["expected_genes_comprehensive"] = comp
        print(f"  {pmid}: {len(paper['expected_genes'])} core → {len(comp)} comprehensive")
        updated += 1

    if not args.dry_run:
        gold["benchmark_version"] = "2.0"
        with open(GOLD_STANDARD_PATH, "w") as f:
            json.dump(gold, f, indent=2)
        print(f"\nUpdated {updated} papers, skipped {skipped}. benchmark_version → 2.0")
    else:
        print(f"\n[DRY RUN] Would update {updated} papers, skip {skipped}.")


if __name__ == "__main__":
    main()
