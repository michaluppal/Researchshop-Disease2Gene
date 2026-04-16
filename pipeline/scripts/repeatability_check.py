#!/usr/bin/env python3
"""
Repeatability harness for the ResearchShop extraction pipeline.

Runs the same PMID N times and computes:
  - Pairwise Jaccard similarity on extracted gene sets
  - Citation coverage mean ± std (fraction of filled citations that scored True)

Fails with exit code 1 if the minimum pairwise Jaccard falls below the
configured threshold.

Usage:
    python3 scripts/repeatability_check.py --pmid 34876594 --runs 5
    python3 scripts/repeatability_check.py --pmid 34876594 --runs 5 --threshold 0.6
    python3 scripts/repeatability_check.py --pmid 34876594 --runs 3 --verbose
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from itertools import combinations
from pathlib import Path
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
PYTHON_DIR = SCRIPT_DIR.parent
RUN_PIPELINE = PYTHON_DIR / "run_pipeline.py"
DEFAULT_RUNS = 5
DEFAULT_THRESHOLD = 0.6  # min pairwise Jaccard to pass
DEFAULT_COLUMNS = json.dumps({
    "Key Finding": "The main finding reported for this gene",
})


def _citation_coverage_from_csv(csv_path: Path) -> Optional[float]:
    """Return fraction of filled citation fields that scored True.

    Scans columns whose names contain both 'citation' and 'valid' (case-insensitive).
    Denominator = cells with a non-empty value (True or False — LLM returned a citation).
    Numerator   = cells with value True/1/yes.
    Returns None if no citation-valid columns are found or all cells are empty.
    """
    import csv as csvmod
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csvmod.DictReader(fh)
            rows = list(reader)
        if not rows:
            return None
        cit_cols = [
            c for c in rows[0].keys()
            if "citation" in c.lower() and "valid" in c.lower()
        ]
        if not cit_cols:
            return None
        true_count = 0
        total_count = 0
        for row in rows:
            for col in cit_cols:
                val = (row.get(col) or "").strip().lower()
                if val:
                    total_count += 1
                    if val in ("true", "1", "yes"):
                        true_count += 1
        return (true_count / total_count) if total_count > 0 else None
    except Exception:
        return None


def run_once(pmid: str, output_dir: Path, run_idx: int, verbose: bool,
             columns: str = DEFAULT_COLUMNS,
             skip_abstract_screening: bool = False) -> Tuple[set, Optional[float]]:
    """Run the pipeline for a single PMID and return (gene_set, citation_coverage)."""
    cmd = [
        sys.executable, str(RUN_PIPELINE),
        "--pmids", json.dumps([pmid]),
        "--columns", columns,
        "--top-n", "1",
        "--output-dir", str(output_dir),
    ]
    if skip_abstract_screening:
        cmd.append("--skip-abstract-screening")
    # Inherit env (GEMINI_API_KEY, ENTREZ_EMAIL must be set)
    env = os.environ.copy()

    if verbose:
        print(f"  [run {run_idx+1}] launching pipeline...", flush=True)

    result = subprocess.run(
        cmd,
        capture_output=not verbose,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        stderr = result.stderr or ""
        print(f"  [run {run_idx+1}] WARNING: pipeline exited {result.returncode}")
        if stderr:
            print(f"    stderr: {stderr[:400]}")
        # Don't return early — check if CSV was produced despite non-zero exit
        # (e.g. exit 144 from worker pool cleanup signal after successful extraction)

    # Find the most recently written CSV in the output dir
    csvs = sorted(
        [p for p in output_dir.glob("final_enriched_results_*.csv")
         if "_metadata.csv" not in p.name],
        key=lambda p: p.stat().st_mtime,
    )
    if not csvs:
        print(f"  [run {run_idx+1}] WARNING: no output CSV found")
        return set(), None

    latest_csv = csvs[-1]
    # Rename so we can track each run separately
    dest = output_dir / f"run_{run_idx:02d}_results.csv"
    latest_csv.rename(dest)

    genes = set()
    try:
        import csv as csvmod
        with open(dest, newline="", encoding="utf-8") as fh:
            reader = csvmod.DictReader(fh)
            for row in reader:
                gene = (row.get("Gene") or row.get("Gene/Group") or "").strip()
                if gene:
                    genes.add(gene)
    except Exception as e:
        print(f"  [run {run_idx+1}] WARNING: failed to parse CSV: {e}")

    coverage = _citation_coverage_from_csv(dest)

    if verbose:
        cov_str = f"{coverage:.2f}" if coverage is not None else "n/a"
        print(f"  [run {run_idx+1}] genes: {sorted(genes)}  citation_coverage={cov_str}")
    return genes, coverage


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def main():
    parser = argparse.ArgumentParser(description="Repeatability harness for ResearchShop pipeline")
    parser.add_argument("--pmid", required=True, help="PMID to test (repeat N times)")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help=f"Number of runs (default: {DEFAULT_RUNS})")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Minimum pairwise Jaccard to pass (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--verbose", action="store_true", help="Print per-run gene sets")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for run outputs (default: temp dir, auto-cleaned)")
    parser.add_argument("--columns", default=DEFAULT_COLUMNS,
                        help="JSON object of column name->description to pass to pipeline")
    parser.add_argument("--skip-abstract-screening", action="store_true",
                        help="Pass --skip-abstract-screening to pipeline (papers pre-validated)")
    args = parser.parse_args()

    if not RUN_PIPELINE.exists():
        print(f"ERROR: run_pipeline.py not found at {RUN_PIPELINE}", file=sys.stderr)
        sys.exit(2)

    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(2)

    use_tempdir = args.output_dir is None
    if use_tempdir:
        tmpdir = tempfile.mkdtemp(prefix="repeatability_")
        output_dir = Path(tmpdir)
    else:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Repeatability check: PMID={args.pmid}, runs={args.runs}, threshold={args.threshold}")
    print(f"Output dir: {output_dir}")
    print()

    gene_sets = []
    coverages: list = []
    for i in range(args.runs):
        t0 = time.time()
        genes, coverage = run_once(args.pmid, output_dir, i, args.verbose,
                                   columns=args.columns,
                                   skip_abstract_screening=args.skip_abstract_screening)
        elapsed = time.time() - t0
        cov_str = f"  cit={coverage:.2f}" if coverage is not None else ""
        print(f"  Run {i+1:2d}/{args.runs}: {len(genes):2d} genes in {elapsed:.0f}s{cov_str}  {sorted(genes)}")
        gene_sets.append(genes)
        if coverage is not None:
            coverages.append(coverage)
        if i < args.runs - 1:
            time.sleep(2)  # brief pause between runs to avoid rate limiting

    print()

    # Union and intersection across all runs
    all_genes = set()
    for gs in gene_sets:
        all_genes |= gs
    common_genes = all_genes.copy()
    for gs in gene_sets:
        common_genes &= gs

    print(f"Union across all runs ({len(all_genes)} genes):       {sorted(all_genes)}")
    print(f"Intersection across all runs ({len(common_genes)} genes): {sorted(common_genes)}")
    print()

    # Pairwise Jaccard
    if args.runs < 2:
        print("Need at least 2 runs for Jaccard comparison.")
        # For single-run mode: write a minimal summary so downstream analysis can still proceed.
        summary_path = output_dir / "repeatability_summary.json"
        cov_mean = (sum(coverages) / len(coverages)) if coverages else None
        import math as _math
        cov_std = _math.sqrt(sum((c - cov_mean)**2 for c in coverages) / len(coverages)) if coverages and cov_mean is not None else None
        summary = {
            "pmid": args.pmid,
            "runs": args.runs,
            "threshold": args.threshold,
            "min_jaccard": 1.0,  # single run: trivially consistent with itself
            "mean_jaccard": 1.0,
            "union_genes": sorted(all_genes),
            "intersection_genes": sorted(common_genes),
            "per_run_genes": [sorted(gs) for gs in gene_sets],
            "per_run_citation_coverage": [round(c, 4) for c in coverages],
            "citation_coverage_mean": round(cov_mean, 4) if cov_mean is not None else None,
            "citation_coverage_std": round(cov_std, 4) if cov_std is not None else None,
            "passed": True,
        }
        with open(summary_path, "w") as fh:
            json.dump(summary, fh, indent=2)
        print(f"Summary written to: {summary_path}")
        sys.exit(0)

    scores = []
    for (i, a), (j, b) in combinations(enumerate(gene_sets), 2):
        j_score = jaccard(a, b)
        scores.append(j_score)
        if args.verbose:
            print(f"  Jaccard(run {i+1}, run {j+1}) = {j_score:.3f}  "
                  f"overlap={sorted(a & b)}  diff={sorted(a ^ b)}")

    min_j = min(scores)
    mean_j = sum(scores) / len(scores)

    print(f"Pairwise Jaccard    — min: {min_j:.3f}  mean: {mean_j:.3f}  (threshold: {args.threshold})")

    # Citation coverage mean ± std
    cov_mean: Optional[float] = None
    cov_std: Optional[float] = None
    if coverages:
        cov_mean = sum(coverages) / len(coverages)
        variance = sum((c - cov_mean) ** 2 for c in coverages) / len(coverages)
        cov_std = math.sqrt(variance)
        print(f"Citation coverage   — mean: {cov_mean:.2f} ± {cov_std:.2f}  (n={len(coverages)} runs with citation columns)")
    else:
        print("Citation coverage   — n/a (no citation-valid columns found in output CSVs)")
    print()

    # Emit JSON summary
    summary = {
        "pmid": args.pmid,
        "runs": args.runs,
        "threshold": args.threshold,
        "min_jaccard": round(min_j, 4),
        "mean_jaccard": round(mean_j, 4),
        "union_genes": sorted(all_genes),
        "intersection_genes": sorted(common_genes),
        "per_run_genes": [sorted(gs) for gs in gene_sets],
        "per_run_citation_coverage": [round(c, 4) for c in coverages],
        "citation_coverage_mean": round(cov_mean, 4) if cov_mean is not None else None,
        "citation_coverage_std": round(cov_std, 4) if cov_std is not None else None,
        "passed": min_j >= args.threshold,
    }
    summary_path = output_dir / "repeatability_summary.json"
    with open(summary_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"Summary written to: {summary_path}")

    if min_j >= args.threshold:
        print(f"\nPASS — min Jaccard {min_j:.3f} >= threshold {args.threshold}")
        sys.exit(0)
    else:
        print(f"\nFAIL — min Jaccard {min_j:.3f} < threshold {args.threshold}")
        print("Gene set drift exceeds acceptable threshold. Investigate run differences above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
