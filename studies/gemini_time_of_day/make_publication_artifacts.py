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


def metric_lookup(rows: list[dict[str, str]]) -> dict[str, int]:
    return {row["metric"]: inum(row["value"]) for row in rows}


def median_stability(stability_rows: list[dict[str, str]], key: str) -> float:
    values = [fnum(row[key]) for row in stability_rows]
    return statistics.median(values) if values else 0.0


def write_summary_table(
    path: Path,
    batch_rows: list[dict[str, str]],
    descriptive_rows: list[dict[str, str]],
    stability_rows: list[dict[str, str]],
    gate_rows: list[dict[str, str]],
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
    gates = metric_lookup(gate_rows)

    content = rf"""\begin{{table}}[!ht]
\centering
\caption{{24-hour Gemini free-tier operational summary. Successful-batch summaries exclude the single upstream full-text failure; candidate and row dispositions use independent denominators.}}
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
Candidate records & {fmt_int(gates.get("candidate_records", 0))} \\
Candidate records rejected & {fmt_int(gates.get("candidate_rejected", 0))} \\
Citation-gate row drops & {fmt_int(gates.get("row_citation_gate_drops", 0))} \\
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


def tikz_series_panel(
    *,
    title: str,
    x: float,
    y: float,
    width: float,
    height: float,
    values: list[float],
    min_value: float,
    max_value: float,
    labels: list[str],
    statuses: list[str],
    y_ticks: list[float],
    median_value: float,
    show_x_labels: bool = True,
) -> list[str]:
    elements: list[str] = []
    value_range = max_value - min_value

    def y_coord(value: float) -> float:
        normalized = min(max((value - min_value) / value_range, 0), 1)
        return y + height * normalized

    elements.append(
        rf"\node[rspanel] at ({x:.2f},{y + height + 0.14:.2f}) {{{title}}};"
    )
    elements.append(rf"\draw[rsaxis] ({x:.2f},{y:.2f}) -- ({x + width:.2f},{y:.2f});")
    for tick in y_ticks:
        yy = y_coord(tick)
        elements.append(rf"\draw[rsgrid] ({x:.2f},{yy:.2f}) -- ({x + width:.2f},{yy:.2f});")
        elements.append(rf"\node[anchor=east, text=gray, font=\sffamily\tiny] at ({x - 0.08:.2f},{yy:.2f}) {{{tick:g}}};")

    n = len(values)
    gap = width / n
    failed_centres: list[float] = []
    for idx, status in enumerate(statuses):
        if status != "failed":
            continue
        cx = x + gap * idx + gap / 2
        failed_centres.append(cx)
        elements.append(
            rf"\fill[rsred!7] ({cx - gap * 0.34:.2f},{y:.2f}) "
            rf"rectangle ({cx + gap * 0.34:.2f},{y + height:.2f});"
        )
        elements.append(
            rf"\draw[rsfailure] ({cx:.2f},{y:.2f}) -- ({cx:.2f},{y + height:.2f});"
        )

    median_y = y_coord(median_value)
    elements.append(
        rf"\draw[rsmedian] ({x:.2f},{median_y:.2f}) -- ({x + width:.2f},{median_y:.2f});"
    )
    elements.append(
        rf"\node[anchor=south east, font=\sffamily\tiny, text=rsgray] "
        rf"at ({x + width - 0.04:.2f},{median_y + 0.02:.2f}) "
        rf"{{median {median_value:g}}};"
    )

    segment: list[tuple[float, float]] = []
    segments: list[list[tuple[float, float]]] = []
    for idx, value in enumerate(values):
        cx = x + gap * idx + gap / 2
        status = statuses[idx]
        if status == "failed":
            if segment:
                segments.append(segment)
                segment = []
            continue
        segment.append((cx, y_coord(value)))
    if segment:
        segments.append(segment)

    for points in segments:
        if len(points) < 2:
            continue
        path = " -- ".join(f"({px:.2f},{py:.2f})" for px, py in points)
        elements.append(rf"\draw[rsline] {path};")

    for idx, value in enumerate(values):
        cx = x + gap * idx + gap / 2
        status = statuses[idx]
        if status == "clean":
            yy = y_coord(value)
            elements.append(rf"\fill[rsgreen] ({cx:.2f},{yy:.2f}) circle (0.058);")
        elif status == "failed":
            cy = y + height / 2
            elements.append(
                rf"\draw[rsfailmark] ({cx - 0.055:.2f},{cy - 0.055:.2f}) "
                rf"-- ({cx + 0.055:.2f},{cy + 0.055:.2f});"
            )
            elements.append(
                rf"\draw[rsfailmark] ({cx - 0.055:.2f},{cy + 0.055:.2f}) "
                rf"-- ({cx + 0.055:.2f},{cy - 0.055:.2f});"
            )
        else:
            yy = y_coord(value)
            elements.append(
                rf"\fill[rsamber] ({cx - 0.055:.2f},{yy - 0.055:.2f}) "
                rf"rectangle ({cx + 0.055:.2f},{yy + 0.055:.2f});"
            )

        if show_x_labels and (idx % 4 == 0 or idx == n - 1):
            elements.append(
                rf"\node[anchor=north, font=\sffamily\tiny, text=gray] "
                rf"at ({cx:.2f},{y - 0.12:.2f}) {{{labels[idx]}}};"
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
    successful_indexes = [idx for idx, status in enumerate(statuses) if status != "failed"]

    def successful_median(values: list[float]) -> float:
        return statistics.median(values[idx] for idx in successful_indexes)

    elements: list[str] = [
        r"\definecolor{rsgreen}{HTML}{2F855A}",
        r"\definecolor{rsamber}{HTML}{D97706}",
        r"\definecolor{rsred}{HTML}{C2413A}",
        r"\definecolor{rsink}{HTML}{475569}",
        r"\definecolor{rsgray}{HTML}{64748B}",
        r"\definecolor{rsgridgray}{HTML}{E2E8F0}",
        r"\begin{tikzpicture}[x=1cm,y=1cm,",
        r"    rsaxis/.style={draw=rsink!60, line width=0.35pt},",
        r"    rsgrid/.style={draw=rsgridgray, line width=0.25pt},",
        r"    rsline/.style={draw=rsink!70, line width=0.55pt, line join=round},",
        r"    rsmedian/.style={draw=rsink!35, dashed, line width=0.35pt},",
        r"    rsfailure/.style={draw=rsred!70, densely dashed, line width=0.4pt},",
        r"    rsfailmark/.style={draw=rsred, line width=0.45pt},",
        r"    rspanel/.style={anchor=south west, font=\sffamily\scriptsize\bfseries, text=rsink},",
        r"    every node/.style={font=\sffamily}]",
    ]
    elements.extend(
        tikz_series_panel(
            title="A. Batch runtime (min)",
            x=0.62,
            y=4.62,
            width=6.05,
            height=1.25,
            values=runtimes,
            min_value=8,
            max_value=16,
            labels=labels,
            statuses=statuses,
            y_ticks=[8, 12, 16],
            median_value=round(successful_median(runtimes), 1),
            show_x_labels=False,
        )
    )
    elements.extend(
        tikz_series_panel(
            title="B. Gemini calls",
            x=0.62,
            y=2.73,
            width=6.05,
            height=1.25,
            values=calls,
            min_value=18,
            max_value=26,
            labels=labels,
            statuses=statuses,
            y_ticks=[18, 22, 26],
            median_value=round(successful_median(calls), 1),
            show_x_labels=False,
        )
    )
    elements.extend(
        tikz_series_panel(
            title="C. Output rows",
            x=0.62,
            y=0.84,
            width=6.05,
            height=1.25,
            values=output_rows,
            min_value=260,
            max_value=320,
            labels=labels,
            statuses=statuses,
            y_ticks=[260, 290, 320],
            median_value=round(successful_median(output_rows), 1),
        )
    )

    elements.extend(
        [
            r"\node[anchor=north, font=\sffamily\tiny, text=rsgray] at (3.65,0.43) {Warsaw local hour};",
            r"\fill[rsgreen] (0.70,0.02) circle (0.058);",
            r"\node[anchor=west, font=\sffamily\tiny] at (0.84,0.02) {clean};",
            r"\fill[rsamber] (1.92,-0.035) rectangle (2.03,0.075);",
            r"\node[anchor=west, font=\sffamily\tiny] at (2.12,0.02) {API recovered};",
            r"\draw[rsfailmark] (3.81,-0.035) -- (3.91,0.075);",
            r"\draw[rsfailmark] (3.81,0.075) -- (3.91,-0.035);",
            r"\node[anchor=west, font=\sffamily\tiny] at (4.02,0.02) {07:00 upstream failure};",
            r"\end{tikzpicture}",
            "",
        ]
    )
    path.write_text("\n".join(elements), encoding="utf-8")


def write_gate_dispositions_figure(
    path: Path,
    gate_rows: list[dict[str, str]],
) -> None:
    gates = metric_lookup(gate_rows)
    candidate_total = max(gates.get("candidate_records", 0), 1)
    candidate_passed = gates.get("candidate_passed", 0)
    candidate_rejected = gates.get("candidate_rejected", 0)
    row_total = max(gates.get("row_decisions", 0), 1)
    row_emitted = gates.get("row_emitted", 0)
    row_citation_drops = gates.get("row_citation_gate_drops", 0)
    row_strict_drops = gates.get("row_strict_gate_drops", 0)

    bar_width = 5.45
    candidate_pass_width = bar_width * candidate_passed / candidate_total
    candidate_reject_width = bar_width - candidate_pass_width
    row_emit_width = bar_width * row_emitted / row_total
    row_drop_width = bar_width - row_emit_width

    content = rf"""\definecolor{{rsgreen}}{{HTML}}{{2F855A}}
\definecolor{{rsamber}}{{HTML}}{{D97706}}
\definecolor{{rsred}}{{HTML}}{{C2413A}}
\definecolor{{rsink}}{{HTML}}{{334155}}
\definecolor{{rsmuted}}{{HTML}}{{64748B}}
\begin{{tikzpicture}}[x=1cm,y=1cm,every node/.style={{font=\sffamily}}]
\node[anchor=west,font=\sffamily\scriptsize\bfseries,text=rsink] at (0,4.25) {{Mechanical gate dispositions}};
\node[anchor=west,font=\sffamily\tiny,text=rsmuted] at (0,3.98) {{Independent candidate and row denominators}};

\node[anchor=west,font=\sffamily\tiny\bfseries,text=rsink] at (0,3.55) {{Candidate records (n={fmt_int(candidate_total)})}};
\fill[rsgreen] (0,3.05) rectangle ({candidate_pass_width:.3f},3.40);
\fill[rsamber] ({candidate_pass_width:.3f},3.05) rectangle ({bar_width:.3f},3.40);
\node[anchor=west,font=\sffamily\tiny,text=rsink] at (0,2.76) {{retained {fmt_int(candidate_passed)} ({100 * candidate_passed / candidate_total:.1f}\%)}};
\node[anchor=east,font=\sffamily\tiny,text=rsink] at ({bar_width:.3f},2.76) {{rejected {fmt_int(candidate_rejected)} ({100 * candidate_rejected / candidate_total:.1f}\%)}};
\node[anchor=west,font=\sffamily\tiny,text=rsmuted] at (0,2.47) {{rejected: {fmt_int(gates.get("candidate_rejected_uncorroborated_deterministic", 0))} uncorroborated deterministic;}};
\node[anchor=west,font=\sffamily\tiny,text=rsmuted] at (0,2.22) {{{fmt_int(gates.get("candidate_rejected_low_confidence", 0))} low confidence; {fmt_int(gates.get("candidate_rejected_ungrounded", 0))} ungrounded}};

\node[anchor=west,font=\sffamily\tiny\bfseries,text=rsink] at (0,1.72) {{Final row decisions (n={fmt_int(row_total)})}};
\fill[rsgreen] (0,1.22) rectangle ({row_emit_width:.3f},1.57);
\fill[rsred] ({row_emit_width:.3f},1.22) rectangle ({bar_width:.3f},1.57);
\node[anchor=west,font=\sffamily\tiny,text=rsink] at (0,0.93) {{emitted {fmt_int(row_emitted)} ({100 * row_emitted / row_total:.1f}\%)}};
\node[anchor=east,font=\sffamily\tiny,text=rsink] at ({bar_width:.3f},0.93) {{citation drops {fmt_int(row_citation_drops)} ({100 * row_citation_drops / row_total:.1f}\%)}};
\node[anchor=west,font=\sffamily\tiny,text=rsmuted] at (0,0.60) {{strict-gate drops: {fmt_int(row_strict_drops)}}};

\fill[rsgreen] (0,0.08) rectangle (0.16,0.24);
\node[anchor=west,font=\sffamily\tiny] at (0.23,0.16) {{retained/emitted}};
\fill[rsamber] (2.02,0.08) rectangle (2.18,0.24);
\node[anchor=west,font=\sffamily\tiny] at (2.25,0.16) {{candidate rejection}};
\fill[rsred] (4.02,0.08) rectangle (4.18,0.24);
\node[anchor=west,font=\sffamily\tiny] at (4.25,0.16) {{row drop}};
\end{{tikzpicture}}
"""
    path.write_text(content, encoding="utf-8")


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
    gate_rows = read_csv(report_dir / "gate_summary.csv")

    table_dir = args.publication_dir / "tables"
    figure_dir = args.publication_dir / "figures"
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    write_summary_table(
        table_dir / "gemini_free_tier_summary.tex",
        batch_rows,
        descriptive_rows,
        stability_rows,
        gate_rows,
    )
    write_time_block_table(table_dir / "gemini_free_tier_time_blocks.tex", block_rows)
    write_tikz_figure(
        figure_dir / "gemini_free_tier_operational_tikz.tex",
        batch_rows,
        block_rows,
    )
    write_gate_dispositions_figure(
        figure_dir / "gemini_gate_dispositions_tikz.tex",
        gate_rows,
    )

    print(f"Wrote publication artifacts under {args.publication_dir}")


if __name__ == "__main__":
    main()
