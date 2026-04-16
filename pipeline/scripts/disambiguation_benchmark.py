#!/usr/bin/env python3
"""
P1-D: Disambiguation clause benchmark for ResearchShop.

Tests whether the clinical-vs-molecular disambiguation clause in gemini_extractor.py
correctly:
  1. Suppresses clinical lab-value abbreviations in clinical papers
     (ESR mm/h, CRP mg/L, AST U/L → should NOT appear as extracted genes)
  2. Preserves molecular gene findings in molecular genetics papers
     (ESR1 mutations, ACE polymorphism → MUST appear as extracted genes)

Usage:
    python scripts/disambiguation_benchmark.py [--runs N] [--skip-run] [--verbose]

    --runs N      Number of pipeline runs per paper (default: 3)
    --skip-run    Skip running the pipeline; only analyze existing summaries
    --verbose     Pass --verbose to benchmark_runner.py
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PYTHON_DIR = SCRIPT_DIR.parent
BENCHMARK_DIR = PYTHON_DIR / "data" / "benchmark"
DISAMBIGUATION_JSON = BENCHMARK_DIR / "disambiguation_papers.json"
RUNNER_SCRIPT = SCRIPT_DIR / "benchmark_runner.py"
RESULTS_OUTPUT = BENCHMARK_DIR / "disambiguation_results.json"


def load_papers() -> dict:
    with open(DISAMBIGUATION_JSON) as f:
        return json.load(f)


def summary_path(pmid: str) -> Path:
    return BENCHMARK_DIR / pmid / "repeatability_summary.json"


def run_paper(pmid: str, runs: int, verbose: bool) -> bool:
    """Run benchmark_runner.py for a single PMID. Returns True if run succeeded."""
    sp = summary_path(pmid)
    if sp.exists():
        print(f"  PMID {pmid}: skipping run (summary already exists)", flush=True)
        return True

    cmd = [sys.executable, str(RUNNER_SCRIPT), "--pmid", pmid, "--runs", str(runs)]
    if verbose:
        cmd.append("--verbose")

    print(f"  Running PMID {pmid} ({runs} runs)...", flush=True)
    result = subprocess.run(cmd, cwd=str(PYTHON_DIR), capture_output=not verbose, text=True)
    if result.returncode not in (0, 1):
        print(f"  ERROR running PMID {pmid} (exit {result.returncode})", flush=True)
        if not verbose and result.stderr:
            print(f"    stderr: {result.stderr[:300]}", flush=True)
        return False
    return True


def load_union_genes(pmid: str) -> list[str]:
    """Load union_genes from repeatability_summary.json, normalised to uppercase."""
    sp = summary_path(pmid)
    if not sp.exists():
        return []
    with open(sp) as f:
        s = json.load(f)
    return [g.upper() for g in s.get("union_genes", [])]


def analyse_clinical(paper: dict, union_genes: list[str]) -> dict:
    forbidden = {g.upper() for g in paper.get("forbidden_genes", [])}
    fp = sorted(forbidden & set(union_genes))
    return {
        "pmid": paper["pmid"],
        "type": "clinical",
        "ambiguous_terms": paper.get("ambiguous_terms_present", []),
        "union_genes": sorted(union_genes),
        "false_positives": fp,
        "fp_count": len(fp),
        "passed": len(fp) == 0,
    }


def analyse_molecular(paper: dict, union_genes: list[str]) -> dict:
    must = {g.upper() for g in paper.get("must_extract", [])}
    fn = sorted(must - set(union_genes))
    tp = sorted(must & set(union_genes))
    return {
        "pmid": paper["pmid"],
        "type": "molecular",
        "ambiguous_gene": paper.get("ambiguous_gene"),
        "must_extract": sorted(must),
        "union_genes": sorted(union_genes),
        "true_positives": tp,
        "false_negatives": fn,
        "fn_count": len(fn),
        "passed": len(fn) == 0,
    }


def print_report(clinical_results: list[dict], molecular_results: list[dict]) -> None:
    print()
    print("=" * 64)
    print("P1-D DISAMBIGUATION CLAUSE BENCHMARK")
    print("=" * 64)

    print()
    print("CLINICAL PAPERS — target: 0 clinical-lab genes extracted")
    print("-" * 64)
    clin_pass = 0
    for r in clinical_results:
        status = "PASS" if r["passed"] else "FAIL"
        terms = ",".join(r["ambiguous_terms"]) or "—"
        fp_str = ",".join(r["false_positives"]) if r["false_positives"] else "none"
        genes_str = ",".join(r["union_genes"][:6]) + ("..." if len(r["union_genes"]) > 6 else "")
        print(f"  {r['pmid']}  {status}  terms={terms}  fp={fp_str}")
        if r["union_genes"]:
            print(f"         union_genes=[{genes_str}]")
        if r["passed"]:
            clin_pass += 1

    clin_total = len(clinical_results)
    clin_fp_papers = clin_total - clin_pass
    print(f"\n  Clinical pass rate:        {clin_pass}/{clin_total}")
    print(f"  Papers with false positives: {clin_fp_papers}/{clin_total}")

    print()
    print("MOLECULAR PAPERS — target: gene retained despite ambiguous abbreviation")
    print("-" * 64)
    mol_pass = 0
    for r in molecular_results:
        status = "PASS" if r["passed"] else "FAIL"
        ambig = r["ambiguous_gene"] or "control"
        tp_str = ",".join(r["true_positives"]) if r["true_positives"] else "none"
        fn_str = ",".join(r["false_negatives"]) if r["false_negatives"] else "none"
        print(f"  {r['pmid']}  {status}  test_gene={ambig}  tp={tp_str}  fn={fn_str}")
        if r["passed"]:
            mol_pass += 1

    mol_total = len(molecular_results)
    mol_fn_papers = mol_total - mol_pass
    print(f"\n  Molecular pass rate:       {mol_pass}/{mol_total}")
    print(f"  Papers with false negatives: {mol_fn_papers}/{mol_total}")

    print()
    print("=" * 64)
    print("ACCEPTANCE CRITERIA")
    print("-" * 64)
    crit1 = clin_pass >= 1
    crit2 = mol_fn_papers == 0
    print(f"  [{'✅' if crit1 else '❌'}] At least 1 clinical paper with 0 false positives  ({clin_pass}/{clin_total})")
    print(f"  [{'✅' if crit2 else '❌'}] 0 molecular papers lost their expected gene       ({mol_fn_papers} failures)")
    overall = "PASS" if (crit1 and crit2) else "FAIL"
    print(f"\n  Overall: {overall}")
    print("=" * 64)


def main():
    parser = argparse.ArgumentParser(description="P1-D disambiguation clause benchmark")
    parser.add_argument("--runs", type=int, default=3, help="Runs per paper (default: 3)")
    parser.add_argument("--skip-run", action="store_true", help="Skip pipeline; analyse existing summaries only")
    parser.add_argument("--verbose", action="store_true", help="Verbose pipeline output")
    args = parser.parse_args()

    data = load_papers()
    clinical = data["clinical_papers"]
    molecular = data["molecular_papers"]
    all_papers = clinical + molecular

    # --- Phase 1: Run pipeline for new papers ---
    if not args.skip_run:
        new_papers = [p for p in all_papers if not summary_path(p["pmid"]).exists()]
        if new_papers:
            print(f"\nRunning {len(new_papers)} new papers ({args.runs} runs each)...")
            for p in new_papers:
                run_paper(p["pmid"], args.runs, args.verbose)
        else:
            print("\nAll papers already have summaries — skipping runs.")

    # --- Phase 2: Analyse results ---
    print("\nAnalysing results...", flush=True)
    clinical_results = []
    molecular_results = []

    for p in clinical:
        genes = load_union_genes(p["pmid"])
        if not summary_path(p["pmid"]).exists():
            print(f"  WARNING: no summary for PMID {p['pmid']} — skipping", flush=True)
            continue
        clinical_results.append(analyse_clinical(p, genes))

    for p in molecular:
        genes = load_union_genes(p["pmid"])
        if not summary_path(p["pmid"]).exists():
            print(f"  WARNING: no summary for PMID {p['pmid']} — skipping", flush=True)
            continue
        molecular_results.append(analyse_molecular(p, genes))

    # --- Phase 3: Report ---
    print_report(clinical_results, molecular_results)

    # --- Phase 4: Write results JSON ---
    clin_pass = sum(1 for r in clinical_results if r["passed"])
    mol_fn = sum(1 for r in molecular_results if not r["passed"])
    results = {
        "run_date": datetime.now().isoformat(),
        "runs_per_paper": args.runs,
        "acceptance": {
            "at_least_one_clinical_pass": clin_pass >= 1,
            "zero_molecular_fn": mol_fn == 0,
            "overall": "PASS" if (clin_pass >= 1 and mol_fn == 0) else "FAIL",
        },
        "summary": {
            "clinical_pass_rate": f"{clin_pass}/{len(clinical_results)}",
            "molecular_fn_count": mol_fn,
        },
        "per_paper": clinical_results + molecular_results,
    }
    with open(RESULTS_OUTPUT, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults written to: {RESULTS_OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
