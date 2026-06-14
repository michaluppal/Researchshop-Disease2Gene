#!/usr/bin/env python3
"""Create paper-facing LaTeX tables and TikZ figures for the WSL study."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SESSION = (
    REPO_ROOT
    / "studies/gemini_time_of_day/runs/session_20260609_0100_scheduler"
)
DEFAULT_PUB = REPO_ROOT / "publication"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(value: str | float | int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def inum(value: str | float | int) -> int:
    return int(round(fnum(value)))


def fmt_int(value: float | int) -> str:
    return f"{int(round(value)):,}"


def fmt1(value: float | int) -> str:
    return f"{float(value):.1f}"


def fmt3(value: float | int) -> str:
    return f"{float(value):.3f}"


def tex_escape(value: str) -> str:
    return (
        value.replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("%", "\\%")
        .replace("&", "\\&")
    )


def successful_rows(batch_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in batch_rows if row.get("successful_batch") == "True"]


def descriptive_lookup(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["scope"], row["metric"]): row for row in rows}


def median_stability(stability_rows: list[dict[str, str]], key: str) -> float:
    values = [fnum(row[key]) for row in stability_rows]
    return statistics.median(values) if values else 0.0


def write_summary_table(
    path: Path,
    batch_rows: list[dict[str, str]],
    descriptive_rows: list[dict[str, str]],
    stability_rows: list[dict[str, str]],
) -> None:
    success = successful_rows(batch_rows)
    desc = descriptive_lookup(descriptive_rows)
    total_papers = sum(inum(row["total_papers"]) for row in batch_rows)
    completed_papers = sum(inum(row["completed_papers"]) for row in batch_rows)
    total_calls = sum(inum(row["gemini_api_calls"]) for row in batch_rows)
    total_tokens = sum(inum(row["gemini_total_tokens"]) for row in batch_rows)
    quota_rows = sum(inum(row["quota_limited_rows"]) for row in batch_rows)
    timeouts = sum(inum(row["timeout_count"]) for row in batch_rows)
    upstream = sum(
        1 for row in batch_rows if row["failure_class"] == "upstream_metadata_or_fulltext_failure"
    )
    recovered_events = sum(inum(row["model_unavailable_count"]) for row in batch_rows)

    batch_runtime = desc[("successful_10_paper_batches", "batch_runtime_seconds")]
    paper_runtime = desc[("successful_10_paper_batches", "paper_runtime_seconds")]
    batch_calls = desc[("successful_10_paper_batches", "batch_gemini_api_calls")]
    batch_tokens = desc[("successful_10_paper_batches", "batch_gemini_total_tokens")]

    success_rate = 100 * len(success) / len(batch_rows)
    gene_jaccard = median_stability(stability_rows, "mean_gene_jaccard")
    pair_jaccard = median_stability(stability_rows, "mean_gene_variant_jaccard")

    content = rf"""\begin{{table}}[!ht]
\centering
\caption{{24-hour Gemini free-tier operational summary. Successful-batch summaries exclude the single upstream full-text failure.}}
\label{{tab:gemini-free-tier-summary}}
\scriptsize
\setlength{{\tabcolsep}}{{4pt}}
\begin{{tabular}}{{@{{}}lr@{{}}}}
\toprule
\textbf{{Metric}} & \textbf{{Value}} \\
\midrule
Hourly slots & {len(batch_rows)} \\
Complete batches & {len(success)}/{len(batch_rows)} ({fmt1(success_rate)}\%) \\
Completed papers & {completed_papers}/{total_papers} \\
Median batch runtime & {fmt1(fnum(batch_runtime["median"]) / 60)} min \\
P95 batch runtime & {fmt1(fnum(batch_runtime["p95"]) / 60)} min \\
Median paper runtime & {fmt1(fnum(paper_runtime["median"]) / 60)} min \\
Median calls/batch & {fmt1(fnum(batch_calls["median"]))} \\
Total Gemini calls & {fmt_int(total_calls)} \\
Median tokens/batch & {fmt_int(fnum(batch_tokens["median"]))} \\
Quota-limited rows & {quota_rows} \\
Timeouts & {timeouts} \\
Upstream failures & {upstream} \\
Recovered API events & {recovered_events} \\
Median gene Jaccard & {fmt3(gene_jaccard)} \\
Median gene-variant Jaccard & {fmt3(pair_jaccard)} \\
\bottomrule
\end{{tabular}}
\end{{table}}
"""
    path.write_text(content, encoding="utf-8")


def write_time_block_table(path: Path, block_rows: list[dict[str, str]]) -> None:
    order = {"night": 0, "morning": 1, "afternoon": 2, "evening": 3}
    rows = sorted(block_rows, key=lambda row: order.get(row["time_block"], 99))
    lines = [
        r"\begin{table}[!ht]",
        r"\centering",
        r"\caption{Time-of-day comparison; runtime uses successful batches.}",
        r"\label{tab:gemini-free-tier-blocks}",
        r"\scriptsize",
        r"\setlength{\tabcolsep}{3.2pt}",
        r"\begin{tabular}{@{}lrrrrr@{}}",
        r"\toprule",
        r"Block & Complete & Runtime & Calls & API rec. & Upstr. \\",
        r" & batches & min & med. & runs & fail. \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            "{} & {}/{} & {} & {} & {} & {} \\\\".format(
                tex_escape(row["time_block"].title()),
                inum(row["successful_runs"]),
                inum(row["runs"]),
                fmt1(fnum(row["median_batch_runtime_seconds"]) / 60),
                fmt1(fnum(row["median_gemini_api_calls"])),
                inum(row["model_unavailable_runs"]),
                inum(row["upstream_failure_runs"]),
            )
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def tikz_bar_panel(
    *,
    title: str,
    x: float,
    y: float,
    width: float,
    height: float,
    values: list[float],
    max_value: float,
    labels: list[str],
    statuses: list[str],
    y_ticks: list[float],
    unit_label: str,
    show_x_labels: bool = True,
) -> list[str]:
    elements: list[str] = []
    elements.append(rf"\node[anchor=west, font=\sffamily\scriptsize\bfseries] at ({x:.2f},{y + height + 0.26:.2f}) {{{title}}};")
    elements.append(rf"\draw[rsaxis] ({x:.2f},{y:.2f}) -- ({x:.2f},{y + height:.2f});")
    elements.append(rf"\draw[rsaxis] ({x:.2f},{y:.2f}) -- ({x + width:.2f},{y:.2f});")
    for tick in y_ticks:
        yy = y + height * min(max(tick / max_value, 0), 1)
        elements.append(rf"\draw[rsgrid] ({x:.2f},{yy:.2f}) -- ({x + width:.2f},{yy:.2f});")
        elements.append(rf"\node[anchor=east, text=gray, font=\sffamily\tiny] at ({x - 0.08:.2f},{yy:.2f}) {{{tick:g}}};")
    elements.append(rf"\node[anchor=west, text=gray, font=\sffamily\tiny] at ({x:.2f},{y + height + 0.06:.2f}) {{{unit_label}}};")

    n = len(values)
    gap = width / n
    bar_w = min(0.17, gap * 0.62)
    for idx, value in enumerate(values):
        cx = x + gap * idx + gap / 2
        bar_h = height * min(max(value / max_value, 0), 1)
        status = statuses[idx]
        if status == "clean":
            fill = "rsgreen"
        elif status == "failed":
            fill = "rsred"
        else:
            fill = "rsblue"
        elements.append(
            rf"\draw[draw=none, fill={fill}, opacity=0.78] "
            rf"({cx - bar_w / 2:.2f},{y:.2f}) rectangle ({cx + bar_w / 2:.2f},{y + bar_h:.2f});"
        )
        if status == "failed":
            elements.append(
                rf"\node[text=rsred, font=\sffamily\tiny\bfseries] at ({cx:.2f},{y + 0.22:.2f}) {{x}};"
            )
        if show_x_labels and idx % 4 == 0:
            elements.append(
                rf"\node[anchor=east, rotate=45, font=\sffamily\tiny, text=gray] "
                rf"at ({cx + 0.08:.2f},{y - 0.20:.2f}) {{{labels[idx]}}};"
            )
    return elements


def write_tikz_figure(path: Path, batch_rows: list[dict[str, str]], block_rows: list[dict[str, str]]) -> None:
    ordered = sorted(batch_rows, key=lambda row: row["planned_local_time"])
    labels = [row["planned_local_time"][:2] for row in ordered]
    statuses = [
        "failed"
        if row["failure_class"] == "upstream_metadata_or_fulltext_failure"
        else "clean"
        if row["failure_class"] == "complete_clean"
        else "recovered"
        for row in ordered
    ]
    runtimes = [fnum(row["runtime_seconds"]) / 60 for row in ordered]
    calls = [fnum(row["gemini_api_calls"]) for row in ordered]
    output_rows = [fnum(row["output_rows"]) for row in ordered]

    elements: list[str] = [
        r"\definecolor{rsblue}{HTML}{2563EB}",
        r"\definecolor{rsgreen}{HTML}{15803D}",
        r"\definecolor{rsred}{HTML}{DC2626}",
        r"\definecolor{rsgray}{HTML}{6B7280}",
        r"\definecolor{rsgridgray}{HTML}{E5E7EB}",
        r"\begin{tikzpicture}[x=1cm,y=1cm,",
        r"    rsaxis/.style={draw=gray!55, line width=0.35pt},",
        r"    rsgrid/.style={draw=rsgridgray, line width=0.25pt},",
        r"    every node/.style={font=\sffamily}]",
        r"\node[anchor=west, font=\sffamily\scriptsize\bfseries] at (0,6.82) {Gemini free-tier hourly batches};",
        r"\node[anchor=west, font=\sffamily\tiny, text=gray] at (0,6.55) {Same 10-PMID corpus; red x marks upstream acquisition failure.};",
    ]
    elements.extend(
        tikz_bar_panel(
            title="A. Batch runtime",
            x=0.55,
            y=4.42,
            width=6.25,
            height=1.55,
            values=runtimes,
            max_value=16,
            labels=labels,
            statuses=statuses,
            y_ticks=[0, 8, 16],
            unit_label="minutes",
            show_x_labels=False,
        )
    )
    elements.extend(
        tikz_bar_panel(
            title="B. Gemini calls",
            x=0.55,
            y=2.38,
            width=6.25,
            height=1.55,
            values=calls,
            max_value=25,
            labels=labels,
            statuses=statuses,
            y_ticks=[0, 12, 25],
            unit_label="API calls",
            show_x_labels=False,
        )
    )
    elements.extend(
        tikz_bar_panel(
            title="C. Output rows",
            x=0.55,
            y=0.34,
            width=6.25,
            height=1.55,
            values=output_rows,
            max_value=320,
            labels=labels,
            statuses=statuses,
            y_ticks=[0, 160, 320],
            unit_label="rows",
        )
    )

    elements.extend(
        [
            r"\draw[draw=none, fill=rsgreen, opacity=0.78] (0.55,-0.45) rectangle (0.75,-0.32);",
            r"\node[anchor=west, font=\sffamily\tiny] at (0.82,-0.38) {clean};",
            r"\draw[draw=none, fill=rsblue, opacity=0.78] (1.70,-0.45) rectangle (1.90,-0.32);",
            r"\node[anchor=west, font=\sffamily\tiny] at (1.97,-0.38) {recovered API};",
            r"\draw[draw=none, fill=rsred, opacity=0.78] (3.55,-0.45) rectangle (3.75,-0.32);",
            r"\node[anchor=west, font=\sffamily\tiny] at (3.82,-0.38) {upstream failure};",
            r"\end{tikzpicture}",
            "",
        ]
    )
    path.write_text("\n".join(elements), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-dir", type=Path, default=DEFAULT_SESSION)
    parser.add_argument("--publication-dir", type=Path, default=DEFAULT_PUB)
    args = parser.parse_args()

    report_dir = args.session_dir / "reports"
    batch_rows = read_csv(report_dir / "batch_metrics.csv")
    block_rows = read_csv(report_dir / "time_block_summary.csv")
    descriptive_rows = read_csv(report_dir / "descriptive_summary.csv")
    stability_rows = read_csv(report_dir / "stability_metrics.csv")

    table_dir = args.publication_dir / "tables"
    figure_dir = args.publication_dir / "figures"
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    write_summary_table(
        table_dir / "gemini_free_tier_summary.tex",
        batch_rows,
        descriptive_rows,
        stability_rows,
    )
    write_time_block_table(table_dir / "gemini_free_tier_time_blocks.tex", block_rows)
    write_tikz_figure(
        figure_dir / "gemini_free_tier_operational_tikz.tex",
        batch_rows,
        block_rows,
    )

    print(f"Wrote publication artifacts under {args.publication_dir}")


if __name__ == "__main__":
    main()
