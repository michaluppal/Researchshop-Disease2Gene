#!/usr/bin/env python3
"""
P2-A: Figure extraction benchmark for ResearchShop.

Measures the recall uplift from enabling figure analysis (ENABLE_FIGURE_ANALYSIS=true)
versus disabling it (ENABLE_FIGURE_ANALYSIS=false). Runs the pipeline under both
conditions for each paper and compares the union gene sets.

Figure-only genes — those appearing in the FIGURE-ON union but not in the FIGURE-OFF
union — represent genes that the pipeline found exclusively through figure analysis
(heatmaps, volcano plots, survival curves, etc.).

Usage:
    python scripts/figure_extraction_benchmark.py [--runs N] [--skip-run] [--verbose]
        [--papers data/benchmark/figure_extraction_papers.json]

    --runs N      Number of pipeline runs per condition per paper (default: 3)
    --skip-run    Skip running the pipeline; only analyse existing summaries
    --verbose     Pass --verbose to repeatability_check.py
    --papers PATH Path to figure_extraction_papers.json registry
                  (default: data/benchmark/figure_extraction_papers.json)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PYTHON_DIR = SCRIPT_DIR.parent
BENCHMARK_DIR = PYTHON_DIR / "data" / "benchmark"
DEFAULT_PAPERS_JSON = BENCHMARK_DIR / "figure_extraction_papers.json"
REPEATABILITY_SCRIPT = SCRIPT_DIR / "repeatability_check.py"
RESULTS_OUTPUT = BENCHMARK_DIR / "figure_extraction_results.json"

DEFAULT_COLUMNS = json.dumps({
    "Key Finding": "The main finding reported for this gene",
})


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def summary_path_for(pmid: str, condition: str) -> Path:
    """Return path to repeatability_summary.json for the given condition.

    condition: "figure_on" | "figure_off"
    """
    return BENCHMARK_DIR / f"{pmid}_{condition}" / "repeatability_summary.json"


def output_dir_for(pmid: str, condition: str) -> Path:
    """Return the output directory for a pmid+condition run."""
    return BENCHMARK_DIR / f"{pmid}_{condition}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_condition(pmid: str, condition: str, runs: int, verbose: bool) -> bool:
    """Run repeatability_check.py for one PMID under a given figure-analysis condition.

    condition: "figure_on" | "figure_off"
    Returns True if the run completed successfully (summary file now exists).
    """
    out_dir = output_dir_for(pmid, condition)
    out_dir.mkdir(parents=True, exist_ok=True)

    enable_figures = "true" if condition == "figure_on" else "false"

    cmd = [
        sys.executable, str(REPEATABILITY_SCRIPT),
        "--pmid", pmid,
        "--runs", str(runs),
        "--output-dir", str(out_dir),
        "--columns", DEFAULT_COLUMNS,
        "--skip-abstract-screening",
        "--threshold", "0.0",  # don't fail on low Jaccard — we only want data
    ]
    if verbose:
        cmd.append("--verbose")

    env = {**os.environ, "ENABLE_FIGURE_ANALYSIS": enable_figures}

    label = "ON " if condition == "figure_on" else "OFF"
    print(f"  PMID {pmid} [figure {label}] — running {runs} runs...", flush=True)

    result = subprocess.run(
        cmd,
        capture_output=not verbose,
        text=True,
        cwd=str(PYTHON_DIR),
        env=env,
    )

    if result.returncode not in (0, 1):  # 0=pass, 1=Jaccard threshold fail (still valid data)
        print(
            f"  ERROR: PMID {pmid} [figure {label}] exited {result.returncode}",
            flush=True,
        )
        if not verbose and result.stderr:
            print(f"    stderr: {result.stderr[:400]}", flush=True)
        return False

    sp = summary_path_for(pmid, condition)
    if sp.exists():
        with open(sp) as f:
            s = json.load(f)
        gene_count = len(s.get("union_genes", []))
        print(
            f"  PMID {pmid} [figure {label}] — done: {gene_count} genes in union",
            flush=True,
        )
        return True
    else:
        print(
            f"  WARNING: PMID {pmid} [figure {label}] — no summary file produced",
            flush=True,
        )
        return False


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def load_union_genes(pmid: str, condition: str) -> list[str]:
    """Load union_genes from repeatability_summary.json, normalised to uppercase."""
    sp = summary_path_for(pmid, condition)
    if not sp.exists():
        return []
    with open(sp) as f:
        s = json.load(f)
    return [g.upper() for g in s.get("union_genes", [])]


def analyse_paper(paper: dict) -> dict:
    """Compute figure-on vs figure-off gene set delta for one paper."""
    pmid = paper["pmid"]
    genes_off = set(load_union_genes(pmid, "figure_off"))
    genes_on = set(load_union_genes(pmid, "figure_on"))

    figure_only = sorted(genes_on - genes_off)
    shared = sorted(genes_on & genes_off)
    prose_only = sorted(genes_off - genes_on)

    return {
        "pmid": pmid,
        "figure_type": paper.get("figure_type", "unknown"),
        "figure_off_genes": sorted(genes_off),
        "figure_on_genes": sorted(genes_on),
        "figure_only_genes": figure_only,
        "shared_genes": shared,
        "prose_only_genes": prose_only,
        "figure_uplift": len(figure_only),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(papers: list[dict], results: list[dict]) -> None:
    print()
    print("=" * 64)
    print("P2-A FIGURE EXTRACTION BENCHMARK")
    print("=" * 64)
    print()

    for paper, r in zip(papers, results):
        pmid = r["pmid"]
        fig_type = r["figure_type"]
        title = paper.get("title", "")
        title_short = (title[:50] + "...") if len(title) > 50 else title

        print(f"Paper {pmid} ({fig_type}):")
        if title_short:
            print(f"  Title: {title_short}")

        sp_off = summary_path_for(pmid, "figure_off")
        sp_on = summary_path_for(pmid, "figure_on")
        if not sp_off.exists():
            print(f"  WARNING: no figure-off summary — skipping analysis", flush=True)
            continue
        if not sp_on.exists():
            print(f"  WARNING: no figure-on summary — skipping analysis", flush=True)
            continue

        off_str = ", ".join(r["figure_off_genes"]) if r["figure_off_genes"] else "(none)"
        on_str = ", ".join(r["figure_on_genes"]) if r["figure_on_genes"] else "(none)"
        fig_only_str = ", ".join(r["figure_only_genes"]) if r["figure_only_genes"] else "(none)"
        shared_str = ", ".join(r["shared_genes"]) if r["shared_genes"] else "(none)"

        print(f"  Figure-OFF union ({len(r['figure_off_genes'])} genes): [{off_str}]")
        print(f"  Figure-ON  union ({len(r['figure_on_genes'])} genes): [{on_str}]")
        if r["figure_only_genes"]:
            print(f"  Figure-only genes:  [{fig_only_str}]  <- found ONLY via figure analysis")
        else:
            print(f"  Figure-only genes:  (none)")
        print(f"  Shared genes:       [{shared_str}]")
        if r["prose_only_genes"]:
            prose_str = ", ".join(r["prose_only_genes"])
            print(f"  Prose-only genes:   [{prose_str}]  <- lost when figures enabled")
        print()

    # --- Summary ---
    uplift_papers = [r for r in results if r["figure_uplift"] > 0]
    total_figure_only = sum(r["figure_uplift"] for r in results)

    print("=" * 64)
    print("SUMMARY")
    print("-" * 64)
    print(f"  Papers with figure-only genes: {len(uplift_papers)}/{len(results)}")
    print(f"  Total figure-only gene discoveries: {total_figure_only}")

    print()
    print("=" * 64)
    print("ACCEPTANCE CRITERIA")
    print("-" * 64)
    crit = len(uplift_papers) >= 1
    status = "PASS" if crit else "FAIL"
    tick = "\u2705" if crit else "\u274c"
    print(f"  [{tick}] At least 1 paper with >= 1 figure-only gene  ({len(uplift_papers)}/{len(results)})")
    print()
    print(f"  Overall: {status}")
    print("=" * 64)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_papers(papers_path: Path) -> list[dict]:
    if not papers_path.exists():
        print(f"ERROR: papers registry not found: {papers_path}", file=sys.stderr)
        print(
            "  Create data/benchmark/figure_extraction_papers.json before running.",
            file=sys.stderr,
        )
        sys.exit(2)
    with open(papers_path) as f:
        data = json.load(f)
    # Support both a bare list and a dict with a "papers" key
    if isinstance(data, list):
        return data
    return data.get("papers", [])


def main():
    parser = argparse.ArgumentParser(description="P2-A figure extraction benchmark")
    parser.add_argument("--runs", type=int, default=3, help="Runs per paper per condition (default: 3)")
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Skip pipeline; analyse existing summaries only",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose pipeline output")
    parser.add_argument(
        "--papers",
        default=str(DEFAULT_PAPERS_JSON),
        help=f"Path to figure_extraction_papers.json (default: {DEFAULT_PAPERS_JSON})",
    )
    args = parser.parse_args()

    papers = load_papers(Path(args.papers))
    if not papers:
        print("ERROR: no papers found in registry", file=sys.stderr)
        sys.exit(2)

    print(f"Figure extraction benchmark: {len(papers)} papers, {args.runs} runs per condition")
    print()

    # --- Phase 1: Run pipeline (figure-off then figure-on for each paper) ---
    if not args.skip_run:
        print("Phase 1: Running pipeline under both conditions...")
        print()
        for paper in papers:
            pmid = paper["pmid"]
            for condition in ("figure_off", "figure_on"):
                sp = summary_path_for(pmid, condition)
                if sp.exists():
                    label = "ON " if condition == "figure_on" else "OFF"
                    print(
                        f"  PMID {pmid} [figure {label}] — summary exists, skipping run",
                        flush=True,
                    )
                    continue
                run_condition(pmid, condition, args.runs, args.verbose)
        print()
    else:
        print("Phase 1: Skipped (--skip-run specified).")
        print()

    # --- Phase 2: Analyse results ---
    print("Phase 2: Analysing results...")
    results = []
    skipped = []
    for paper in papers:
        pmid = paper["pmid"]
        sp_off = summary_path_for(pmid, "figure_off")
        sp_on = summary_path_for(pmid, "figure_on")

        if not sp_off.exists() and not sp_on.exists():
            print(f"  WARNING: no summaries for PMID {pmid} — skipping", flush=True)
            skipped.append(pmid)
            continue

        if not sp_off.exists():
            print(
                f"  WARNING: no figure-off summary for PMID {pmid} — skipping",
                flush=True,
            )
            skipped.append(pmid)
            continue

        if not sp_on.exists():
            print(
                f"  WARNING: no figure-on summary for PMID {pmid} — skipping",
                flush=True,
            )
            skipped.append(pmid)
            continue

        results.append(analyse_paper(paper))

    if skipped:
        print(f"  Skipped {len(skipped)} papers with missing summaries: {skipped}")
    print()

    # --- Phase 3: Print report ---
    analysed_papers = [p for p in papers if p["pmid"] not in skipped]
    print_report(analysed_papers, results)

    # --- Phase 4: Write results JSON ---
    uplift_papers = [r for r in results if r["figure_uplift"] > 0]
    figure_uplift_found = len(uplift_papers) >= 1
    overall = "PASS" if figure_uplift_found else "FAIL"

    output = {
        "run_date": datetime.now().isoformat(),
        "runs_per_condition": args.runs,
        "acceptance": {
            "figure_uplift_found": figure_uplift_found,
            "papers_with_uplift": len(uplift_papers),
            "total_papers": len(results),
            "overall": overall,
        },
        "per_paper": [
            {
                "pmid": r["pmid"],
                "figure_type": r["figure_type"],
                "figure_off_genes": r["figure_off_genes"],
                "figure_on_genes": r["figure_on_genes"],
                "figure_only_genes": r["figure_only_genes"],
                "shared_genes": r["shared_genes"],
                "prose_only_genes": r["prose_only_genes"],
                "figure_uplift": r["figure_uplift"],
            }
            for r in results
        ],
    }

    with open(RESULTS_OUTPUT, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults written to: {RESULTS_OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
