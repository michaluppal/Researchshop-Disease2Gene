#!/usr/bin/env python3
"""
Benchmark runner for ResearchShop P0-A molecular genetics benchmark.

Reads gold_standard.json and runs repeatability_check.py for each paper.

Usage:
    python scripts/benchmark_runner.py --pmid 20360068 --runs 3
    python scripts/benchmark_runner.py --all --runs 3
    python scripts/benchmark_runner.py --pmids 21873635 17554300 20525088 --runs 3
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PYTHON_DIR = SCRIPT_DIR.parent
GOLD_STANDARD_PATH = PYTHON_DIR / "data" / "benchmark" / "gold_standard.json"
BENCHMARK_DIR = PYTHON_DIR / "data" / "benchmark"
REPEATABILITY_SCRIPT = SCRIPT_DIR / "repeatability_check.py"


def load_gold_standard():
    with open(GOLD_STANDARD_PATH) as f:
        return json.load(f)


def run_paper(pmid: str, columns_json: str, runs: int, verbose: bool,
              figure_mode: str = "on", output_subdir: str = "") -> dict:
    """Run repeatability_check.py for a single PMID. Returns summary dict."""
    output_dir = BENCHMARK_DIR / pmid / output_subdir if output_subdir else BENCHMARK_DIR / pmid
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(REPEATABILITY_SCRIPT),
        "--pmid", pmid,
        "--runs", str(runs),
        "--output-dir", str(output_dir),
        "--columns", columns_json,
        "--threshold", "0.0",  # don't fail on low Jaccard — we just want data
    ]
    if verbose:
        cmd.append("--verbose")

    # When figure_mode is "off", disable figure analysis via environment variable
    env = None
    if figure_mode == "off":
        env = os.environ.copy()
        env["ENABLE_FIGURE_ANALYSIS"] = "false"

    mode_label = f" [figures={figure_mode}]" if output_subdir else ""
    print(f"\n{'='*60}", flush=True)
    print(f"Running PMID {pmid} ({runs} runs){mode_label}...", flush=True)
    print(f"Output dir: {output_dir}", flush=True)

    result = subprocess.run(
        cmd,
        capture_output=not verbose,
        text=True,
        cwd=str(PYTHON_DIR),
        env=env,
    )

    if result.returncode not in (0, 1):  # 0=pass, 1=fail threshold (still valid data)
        print(f"  ERROR: repeatability_check.py exited {result.returncode}", flush=True)
        if not verbose and result.stderr:
            print(f"  stderr: {result.stderr[:500]}", flush=True)

    # Read summary
    summary_path = output_dir / "repeatability_summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            summary = json.load(f)
        gene_count = len(summary.get("union_genes", []))
        cov_mean = summary.get("citation_coverage_mean")
        cov_str = f"{cov_mean:.2f}" if cov_mean is not None else "n/a"
        print(f"  Result: {gene_count} genes in union, citation_coverage={cov_str}", flush=True)
        print(f"  Genes: {summary.get('union_genes', [])}", flush=True)
        return summary
    else:
        print(f"  WARNING: no repeatability_summary.json found for PMID {pmid}", flush=True)
        return {"pmid": pmid, "union_genes": [], "error": "no summary file"}


def main():
    parser = argparse.ArgumentParser(description="Benchmark runner for P0-A")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pmid", help="Single PMID to benchmark")
    group.add_argument("--pmids", nargs="+", help="List of PMIDs to benchmark")
    group.add_argument("--all", action="store_true", help="Run all papers in gold_standard.json")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per paper (default: 3)")
    parser.add_argument("--verbose", action="store_true", help="Verbose per-run output")
    parser.add_argument("--figure-mode", choices=["on", "off", "both"], default="on",
                        help="Figure analysis mode: on (default), off (ENABLE_FIGURE_ANALYSIS=false), both (run both)")
    args = parser.parse_args()

    gold = load_gold_standard()
    columns_json = json.dumps(gold["columns"])

    # Build list of PMIDs to run
    if args.pmid:
        pmids_to_run = [args.pmid]
    elif args.pmids:
        pmids_to_run = args.pmids
    else:  # --all
        pmids_to_run = [
            p["pmid"] for p in gold["papers"]
            if not p["pmid"].startswith("TBD")
        ]

    print(f"Benchmark runner: {len(pmids_to_run)} papers, {args.runs} runs each, figure-mode={args.figure_mode}", flush=True)
    print(f"Papers: {pmids_to_run}", flush=True)
    print(f"Columns: {columns_json}", flush=True)

    results = {}
    zero_gene_papers = []

    for pmid in pmids_to_run:
        if args.figure_mode in ("on", "both"):
            summary = run_paper(pmid, columns_json, args.runs, args.verbose,
                                figure_mode="on", output_subdir="")
            results[pmid] = summary
            if not summary.get("union_genes"):
                zero_gene_papers.append(pmid)
        if args.figure_mode in ("off", "both"):
            summary_off = run_paper(pmid, columns_json, args.runs, args.verbose,
                                    figure_mode="off", output_subdir="figure_off")
            results[f"{pmid}_off"] = summary_off
            if not summary_off.get("union_genes"):
                zero_gene_papers.append(f"{pmid}_off")

    # Count only real PMIDs for the zero-gene check (not _off variants)
    real_pmid_count = sum(1 for k in results if not k.endswith("_off"))
    real_zero = [p for p in zero_gene_papers if not p.endswith("_off")]

    print(f"\n{'='*60}", flush=True)
    print("BENCHMARK RUNNER COMPLETE", flush=True)
    print(f"Papers run: {len(results)}", flush=True)
    print(f"Papers with 0 genes: {zero_gene_papers}", flush=True)

    if real_zero and len(real_zero) == real_pmid_count and real_pmid_count > 0:
        print("ERROR: ALL papers produced 0 genes — likely API error", flush=True)
        sys.exit(1)

    print("\nPer-paper summary:", flush=True)
    for key, summary in results.items():
        genes = summary.get("union_genes", [])
        cov = summary.get("citation_coverage_mean")
        cov_str = f"{cov:.2f}" if cov is not None else "n/a"
        jac = summary.get("min_jaccard", "n/a")
        print(f"  {key}: {len(genes)} genes, cit={cov_str}, jaccard_min={jac}", flush=True)


if __name__ == "__main__":
    main()
