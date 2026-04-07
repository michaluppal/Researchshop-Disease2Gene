#!/usr/bin/env python3
"""
Benchmark analysis: computes Precision/Recall/F1 + 95% CIs from gold standard + pipeline outputs.

Reads:
  - data/benchmark/gold_standard.json
  - data/benchmark/{pmid}/repeatability_summary.json (for each paper)

Writes:
  - data/benchmark/benchmark_results.csv

Usage:
    python scripts/benchmark_analysis.py
    python scripts/benchmark_analysis.py --output-csv data/benchmark/benchmark_results.csv
"""

import argparse
import csv
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PYTHON_DIR = SCRIPT_DIR.parent
BENCHMARK_DIR = PYTHON_DIR / "data" / "benchmark"
GOLD_STANDARD_PATH = BENCHMARK_DIR / "gold_standard.json"


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score interval for a proportion k/n at confidence z."""
    if n == 0:
        return (0.0, 0.0)
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * (p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) ** 0.5 / denom
    return (max(0.0, round(center - margin, 4)), min(1.0, round(center + margin, 4)))


def f1_score(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def f1_ci(p_lo: float, p_hi: float, r_lo: float, r_hi: float) -> tuple:
    """Approximate F1 CI by computing F1 at the CI corners (conservative bounds)."""
    f1_lo = f1_score(p_lo, r_lo)
    f1_hi = f1_score(p_hi, r_hi)
    return (round(f1_lo, 4), round(f1_hi, 4))


def _metrics_for_gene_set(gold_genes: set, extracted_genes: set) -> dict:
    """Compute P/R/F1 + 95% Wilson CIs against a given gold gene set."""
    tp = gold_genes & extracted_genes
    n_tp = len(tp)
    n_extracted = len(extracted_genes)
    n_gold = len(gold_genes)

    precision = n_tp / n_extracted if n_extracted else 0.0
    recall = n_tp / n_gold if n_gold else 0.0
    f1 = f1_score(precision, recall)

    p_ci = wilson_ci(n_tp, n_extracted)
    r_ci = wilson_ci(n_tp, n_gold)
    f_ci = f1_ci(p_ci[0], p_ci[1], r_ci[0], r_ci[1])

    return {
        "gold_gene_count": n_gold,
        "extracted_gene_count": n_extracted,
        "true_positives": n_tp,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "precision_ci_lo": p_ci[0],
        "precision_ci_hi": p_ci[1],
        "recall_ci_lo": r_ci[0],
        "recall_ci_hi": r_ci[1],
        "f1_ci_lo": f_ci[0],
        "f1_ci_hi": f_ci[1],
        "tp_genes": sorted(tp),
        "fp_genes": sorted(extracted_genes - gold_genes),
        "fn_genes": sorted(gold_genes - extracted_genes),
    }


def compute_metrics(paper: dict, summary: dict) -> dict:
    """Compute P/R/F1 + 95% Wilson CIs for one paper (core + comprehensive gene sets)."""
    extracted_genes = {g.upper() for g in summary.get("union_genes", [])}
    core_genes = {g.upper() for g in paper.get("expected_genes", [])}
    comp_genes = {g.upper() for g in paper.get("expected_genes_comprehensive", [])}

    core = _metrics_for_gene_set(core_genes, extracted_genes)
    has_comp = bool(comp_genes)
    comp = _metrics_for_gene_set(comp_genes, extracted_genes) if has_comp else {}

    row = {
        "pmid": paper["pmid"],
        "type": paper["type"],
        # Core (expected_genes) metrics
        **{k: core[k] for k in core if k not in ("tp_genes", "fp_genes", "fn_genes")},
        "tp_genes": core["tp_genes"],
        "fp_genes": core["fp_genes"],
        "fn_genes": core["fn_genes"],
        # Comprehensive metrics (prefixed)
        "comp_gold_gene_count": comp.get("gold_gene_count", None),
        "comp_true_positives": comp.get("true_positives", None),
        "comp_precision": comp.get("precision", None),
        "comp_recall": comp.get("recall", None),
        "comp_f1": comp.get("f1", None),
        "comp_precision_ci_lo": comp.get("precision_ci_lo", None),
        "comp_precision_ci_hi": comp.get("precision_ci_hi", None),
        "comp_recall_ci_lo": comp.get("recall_ci_lo", None),
        "comp_recall_ci_hi": comp.get("recall_ci_hi", None),
        "comp_f1_ci_lo": comp.get("f1_ci_lo", None),
        "comp_f1_ci_hi": comp.get("f1_ci_hi", None),
        # Shared
        "citation_grounding_mean": summary.get("citation_coverage_mean"),
        "citation_grounding_std": summary.get("citation_coverage_std"),
        "jaccard_min": summary.get("min_jaccard"),
        "jaccard_mean": summary.get("mean_jaccard"),
    }
    return row


def run_figure_compare(gold, output_csv):
    """Compare figure-on vs figure-off benchmark results for each paper."""
    rows = []
    for paper in gold["papers"]:
        pmid = paper["pmid"]
        if pmid.startswith("TBD"):
            continue
        path_on = BENCHMARK_DIR / pmid / "repeatability_summary.json"
        path_off = BENCHMARK_DIR / pmid / "figure_off" / "repeatability_summary.json"
        if not path_on.exists():
            print(f"  WARNING: no figure-ON results for PMID {pmid} — skipping")
            continue
        if not path_off.exists():
            print(f"  WARNING: no figure-OFF results for PMID {pmid} — skipping")
            continue

        with open(path_on) as f:
            summary_on = json.load(f)
        with open(path_off) as f:
            summary_off = json.load(f)

        m_on = compute_metrics(paper, summary_on)
        m_off = compute_metrics(paper, summary_off)

        expected_genes = {g.upper() for g in paper.get("expected_genes", [])}
        union_on = {g.upper() for g in summary_on.get("union_genes", [])}
        union_off = {g.upper() for g in summary_off.get("union_genes", [])}
        figure_exclusive = union_on - union_off
        figure_exclusive_gold = len(figure_exclusive & expected_genes)

        rows.append({
            "pmid": pmid,
            "type": paper["type"],
            "has_figure_genes": paper.get("has_figure_genes"),
            "f1_on": m_on["f1"],
            "f1_off": m_off["f1"],
            "delta_f1": round(m_on["f1"] - m_off["f1"], 4),
            "recall_on": m_on["recall"],
            "recall_off": m_off["recall"],
            "delta_recall": round(m_on["recall"] - m_off["recall"], 4),
            "precision_on": m_on["precision"],
            "precision_off": m_off["precision"],
            "figure_exclusive_gene_count": len(figure_exclusive),
            "figure_exclusive_gold_count": figure_exclusive_gold,
            "figure_exclusive_genes": sorted(figure_exclusive),
        })

    if not rows:
        print("ERROR: no paired results found. Run benchmark_runner.py --figure-mode both first.")
        return

    csv_cols = ["pmid", "type", "has_figure_genes", "f1_on", "f1_off", "delta_f1",
                "recall_on", "recall_off", "delta_recall", "precision_on", "precision_off",
                "figure_exclusive_gene_count", "figure_exclusive_gold_count"]
    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Figure comparison written to: {output_csv}")

    # Print table
    print()
    print(f"{'PMID':<12} {'Type':<20} {'F1-on':>7} {'F1-off':>7} {'ΔF1':>8} {'ΔRec':>7} {'FigGenes':>9} {'FigGold':>8}")
    print("-" * 84)
    by_type = {}
    for row in sorted(rows, key=lambda r: (r["type"], r["pmid"])):
        print(f"{row['pmid']:<12} {row['type']:<20} {row['f1_on']:>7.3f} {row['f1_off']:>7.3f} "
              f"{row['delta_f1']:>+8.3f} {row['delta_recall']:>+7.3f} "
              f"{row['figure_exclusive_gene_count']:>9} {row['figure_exclusive_gold_count']:>8}")
        by_type.setdefault(row["type"], []).append(row)

    print()
    print("Aggregate by type:")
    for ptype, type_rows in sorted(by_type.items()):
        n = len(type_rows)
        mean_delta = sum(r["delta_f1"] for r in type_rows) / n
        mean_fig = sum(r["figure_exclusive_gene_count"] for r in type_rows) / n
        print(f"  {ptype}: mean ΔF1={mean_delta:+.3f}, mean figure-exclusive genes={mean_fig:.1f} (n={n})")


def main():
    parser = argparse.ArgumentParser(description="Benchmark analysis: P/R/F1 + CIs from results")
    parser.add_argument("--output-csv", default=str(BENCHMARK_DIR / "benchmark_results.csv"))
    parser.add_argument("--figure-compare", action="store_true",
                        help="Compare figure-on vs figure-off results")
    args = parser.parse_args()

    if args.figure_compare:
        if args.output_csv == str(BENCHMARK_DIR / "benchmark_results.csv"):
            args.output_csv = str(BENCHMARK_DIR / "benchmark_figure_comparison.csv")
        with open(GOLD_STANDARD_PATH) as f:
            gold = json.load(f)
        run_figure_compare(gold, args.output_csv)
        return

    with open(GOLD_STANDARD_PATH) as f:
        gold = json.load(f)

    rows = []
    missing = []

    for paper in gold["papers"]:
        pmid = paper["pmid"]
        if pmid.startswith("TBD"):
            continue

        summary_path = BENCHMARK_DIR / pmid / "repeatability_summary.json"
        if not summary_path.exists():
            print(f"  WARNING: no results for PMID {pmid} — skipping")
            missing.append(pmid)
            continue

        with open(summary_path) as f:
            summary = json.load(f)

        metrics = compute_metrics(paper, summary)
        rows.append(metrics)

    if not rows:
        print("ERROR: no results found. Run benchmark_runner.py first.")
        return

    # Write CSV
    csv_columns = [
        "pmid", "type",
        # Core (expected_genes) metrics
        "gold_gene_count", "extracted_gene_count", "true_positives",
        "precision", "recall", "f1",
        "precision_ci_lo", "precision_ci_hi",
        "recall_ci_lo", "recall_ci_hi",
        "f1_ci_lo", "f1_ci_hi",
        # Comprehensive (expected_genes_comprehensive) metrics
        "comp_gold_gene_count", "comp_true_positives",
        "comp_precision", "comp_recall", "comp_f1",
        "comp_precision_ci_lo", "comp_precision_ci_hi",
        "comp_recall_ci_lo", "comp_recall_ci_hi",
        "comp_f1_ci_lo", "comp_f1_ci_hi",
        # Repeatability
        "citation_grounding_mean", "citation_grounding_std",
        "jaccard_min", "jaccard_mean",
    ]
    with open(args.output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Results written to: {args.output_csv}")

    # Print table grouped by type
    print()
    print(f"{'PMID':<12} {'Type':<20} {'Gold':>5} {'Extr':>5} {'TP':>4} "
          f"{'P':>6} {'R':>6} {'F1':>6} {'CompF1':>8} {'F1 CI 95%':>14} {'Cit':>6} {'Jac':>6}")
    print("-" * 102)

    by_type: dict = {}
    for row in sorted(rows, key=lambda r: (r["type"], r["pmid"])):
        cit = f"{row['citation_grounding_mean']:.2f}" if row["citation_grounding_mean"] is not None else "n/a"
        jac = f"{row['jaccard_min']:.3f}" if row["jaccard_min"] is not None else "n/a"
        f1_range = f"[{row['f1_ci_lo']:.3f}, {row['f1_ci_hi']:.3f}]"
        comp_f1 = f"{row['comp_f1']:.3f}" if row["comp_f1"] is not None else "n/a"
        print(f"{row['pmid']:<12} {row['type']:<20} {row['gold_gene_count']:>5} "
              f"{row['extracted_gene_count']:>5} {row['true_positives']:>4} "
              f"{row['precision']:>6.3f} {row['recall']:>6.3f} {row['f1']:>6.3f} "
              f"{comp_f1:>8} {f1_range:>14} {cit:>6} {jac:>6}")
        t = row["type"]
        by_type.setdefault(t, []).append(row)

    # Aggregate by type
    print()
    print("Aggregate by paper type:")
    print(f"{'Type':<20} {'n':>4} {'Macro F1':>10} {'Macro CompF1':>14} {'Weighted F1':>13} {'Mean CI':>18}")
    print("-" * 84)
    for ptype, type_rows in sorted(by_type.items()):
        n = len(type_rows)
        macro_f1 = sum(r["f1"] for r in type_rows) / n
        comp_rows = [r for r in type_rows if r["comp_f1"] is not None]
        macro_comp_f1 = f"{sum(r['comp_f1'] for r in comp_rows) / len(comp_rows):.3f}" if comp_rows else "n/a"
        total_gold = sum(r["gold_gene_count"] for r in type_rows)
        weighted_f1 = (
            sum(r["f1"] * r["gold_gene_count"] for r in type_rows) / total_gold
            if total_gold > 0 else 0.0
        )
        mean_ci_lo = sum(r["f1_ci_lo"] for r in type_rows) / n
        mean_ci_hi = sum(r["f1_ci_hi"] for r in type_rows) / n
        ci_str = f"[{mean_ci_lo:.3f}, {mean_ci_hi:.3f}]"
        print(f"{ptype:<20} {n:>4} {macro_f1:>10.3f} {macro_comp_f1:>14} {weighted_f1:>13.3f} {ci_str:>18}")

    # Overall summary
    print()
    overall_f1 = sum(r["f1"] for r in rows) / len(rows)
    total_gold_all = sum(r["gold_gene_count"] for r in rows)
    overall_weighted_f1 = (
        sum(r["f1"] * r["gold_gene_count"] for r in rows) / total_gold_all
        if total_gold_all > 0 else 0.0
    )
    best = max(rows, key=lambda r: r["f1"])
    worst = min(rows, key=lambda r: r["f1"])
    zero_count = sum(1 for r in rows if r["extracted_gene_count"] == 0)
    print(f"Overall macro F1:    {overall_f1:.3f}")
    print(f"Overall weighted F1: {overall_weighted_f1:.3f}")
    print(f"Best paper:  PMID {best['pmid']} ({best['type']}) F1={best['f1']:.3f} [{best['f1_ci_lo']:.3f}, {best['f1_ci_hi']:.3f}]")
    print(f"Worst paper: PMID {worst['pmid']} ({worst['type']}) F1={worst['f1']:.3f} [{worst['f1_ci_lo']:.3f}, {worst['f1_ci_hi']:.3f}]")
    print(f"Papers with 0 extracted genes: {zero_count}")
    if missing:
        print(f"Missing results (no repeatability_summary.json): {missing}")

    # Write per-category CSVs
    out_dir = Path(args.output_csv).parent
    for ptype, type_rows in by_type.items():
        cat_path = out_dir / f"benchmark_{ptype}.csv"
        with open(cat_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(type_rows)
        print(f"  {ptype}: {cat_path}")
    print()

    # Check acceptance criteria
    best_type_f1 = max(
        sum(r["f1"] for r in type_rows) / len(type_rows)
        for type_rows in by_type.values()
    )
    print()
    print(f"Acceptance criteria check:")
    print(f"  Papers benchmarked: {len(rows)} (need >=10): {'PASS' if len(rows) >= 10 else 'FAIL'}")
    print(f"  Best paper type F1: {best_type_f1:.3f} (need >=0.6): {'PASS' if best_type_f1 >= 0.6 else 'FAIL'}")


if __name__ == "__main__":
    main()
