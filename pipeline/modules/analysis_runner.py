"""Worker pool scheduling for per-paper analysis."""

from __future__ import annotations

import logging
import multiprocessing as mp
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd
from tqdm import tqdm

from . import config, pipeline_tracer
from .paper_analysis.pipeline import PaperAnalysisPipeline
from .paper_reading import prepare_paper_inputs
from .pipeline_artifacts import _ensure_unique_columns
from .pipeline_state import JobCancelledException
from .result_enrichment import accumulate_result, finalize_paper_result


@dataclass
class PaperAnalysisRunResult:
    all_results_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    paper_debug_artifacts: list[dict[str, Any]] = field(default_factory=list)
    collected_rows: list[str] = field(default_factory=list)
    full_rows_pmids: set[str] = field(default_factory=set)
    minimal_rows: list[dict[str, Any]] = field(default_factory=list)
    analyzed_attempts: int = 0


def run_pipeline_worker(
    text,
    cols,
    pubtator_genes=None,
    figure_inputs=None,
    abstract_text=None,
    table_inputs=None,
    pmid=None,
    prepared_content=None,
    pipeline_factory=PaperAnalysisPipeline,
):
    """Top-level worker function for multiprocessing pool."""
    trace_this_paper = pipeline_tracer.matches(pmid)
    try:
        if trace_this_paper:
            pipeline_tracer.install_function_tracer()
    except Exception:
        pass

    try:
        with pipeline_tracer.paper(pmid if trace_this_paper else None):
            inst = pipeline_factory(
                text,
                abstract_text=abstract_text or "",
                pubtator_genes=pubtator_genes,
                figure_inputs=figure_inputs,
                table_inputs=table_inputs,
                pmid=pmid,
                prepared_content=prepared_content,
            )
            df = inst.run_pipeline(cols)
            df = _ensure_unique_columns(df)
            return {
                "records": df.to_dict(orient="records"),
                "debug": inst._collect_debug_artifact(),
                "gemini_api_calls": inst._paper_api_calls,
            }
    except Exception as e:
        import traceback

        logging.error(f"Pipeline worker error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}
    finally:
        try:
            pipeline_tracer.flush_worker_partial()
        except Exception:
            pass
        try:
            pipeline_tracer.uninstall_function_tracer()
        except Exception:
            pass


def run_paper_analysis(
    *,
    pmids_to_process: list[str],
    content_dict: dict,
    paper_details: dict,
    pubtator_results: dict,
    citation_records: dict,
    column_descriptions: dict,
    pipeline_stats: dict,
    report_progress: Callable,
    emit_log: Callable,
    check_cancellation: Callable,
    build_minimal_row: Callable,
) -> PaperAnalysisRunResult:
    """Run per-paper workers and collect full or minimal rows."""
    result = PaperAnalysisRunResult()
    total_papers = len(pmids_to_process)

    pool_size = max(1, min(int(getattr(config, "AI_WORKER_POOL_SIZE", 2)), 4))
    worker_pool = mp.Pool(processes=pool_size)
    logging.info(f"AI worker pool created: {pool_size} processes")
    parallel_mode = bool(getattr(config, "PARALLEL_ANALYSIS", False))
    ordered_results = None
    in_flight = {}

    try:
        if parallel_mode:
            emit_log(
                "info",
                f"Parallel AI analysis enabled using the existing worker pool ({pool_size} workers)",
            )
            ordered_results = [None] * total_papers
            submit_idx = 0
            completed_count = 0

            def report_parallel_progress():
                ai_progress = 70 + int((completed_count / max(total_papers, 1)) * 25)
                report_progress(
                    "Per-paper analysis",
                    ai_progress,
                    {"papers_analyzed": completed_count},
                )

            def submit_next():
                nonlocal submit_idx, completed_count
                while len(in_flight) < pool_size and submit_idx < total_papers:
                    pmid = pmids_to_process[submit_idx]
                    idx = submit_idx
                    submit_idx += 1
                    result.analyzed_attempts += 1

                    prepared = prepare_paper_inputs(
                        pmid, content_dict, paper_details, pubtator_results
                    )
                    short_title = (
                        (prepared["title"][:60] + "...")
                        if len(prepared["title"]) > 60
                        else prepared["title"]
                    )

                    if not prepared["paper_text"]:
                        ordered_results[idx] = {
                            "kind": "minimal",
                            "pmid": pmid,
                            "base_info": prepared["base_info"],
                            "debug": {
                                "pmid": pmid,
                                "status": "no_full_text",
                                "reason": "missing_paper_text_after_fetch",
                                "emitted_rows": 0,
                            },
                        }
                        completed_count += 1
                        report_parallel_progress()
                        continue

                    ctx = {
                        **prepared,
                        "submitted_at": time.time(),
                    }
                    ar = worker_pool.apply_async(
                        run_pipeline_worker,
                        args=(
                            prepared["paper_text"],
                            column_descriptions,
                            prepared["pt_gene_symbols"],
                            prepared["figure_inputs"],
                            prepared["abstract"],
                            prepared["table_inputs"],
                            pmid,
                            prepared["prepared_content"],
                        ),
                    )
                    in_flight[pmid] = {"idx": idx, "async_result": ar, "ctx": ctx}
                    emit_log(
                        "info",
                        f"[parallel] Submitted paper {idx + 1}/{total_papers}: {short_title}",
                        f"PMID {pmid}",
                    )

            submit_next()

            while in_flight:
                check_cancellation()

                newly_done = [
                    pmid
                    for pmid, info in list(in_flight.items())
                    if info["async_result"].ready()
                ]
                timed_out = []
                for pmid, info in list(in_flight.items()):
                    if pmid in newly_done:
                        continue
                    elapsed = time.time() - info["ctx"]["submitted_at"]
                    if elapsed > config.AI_PER_PAPER_TIMEOUT_SECONDS:
                        timed_out.append(pmid)

                if not newly_done and not timed_out:
                    time.sleep(0.2)
                    continue

                for pmid in newly_done:
                    info = in_flight.pop(pmid)
                    idx = info["idx"]
                    ctx = info["ctx"]
                    try:
                        payload = info["async_result"].get(timeout=0)
                    except Exception as e:
                        payload = {"error": str(e)}
                    paper_df, debug_artifact = finalize_paper_result(
                        payload,
                        pmid,
                        ctx["base_info"],
                        citation_records,
                        ctx["figure_inputs"],
                        pubtator_results,
                        pipeline_stats,
                        emit_log,
                    )
                    ordered_results[idx] = {
                        "kind": "result",
                        "pmid": pmid,
                        "paper_df": paper_df,
                        "debug": debug_artifact,
                    }
                    completed_count += 1
                    report_parallel_progress()
                    short_title = (
                        (ctx["title"][:60] + "...") if len(ctx["title"]) > 60 else ctx["title"]
                    )
                    emit_log(
                        "info",
                        f"[parallel] Completed paper {idx + 1}/{total_papers}: {short_title}",
                        f"PMID {pmid}",
                    )

                if timed_out:
                    for pmid in timed_out:
                        info = in_flight.pop(pmid, None)
                        if info is None:
                            continue
                        ordered_results[info["idx"]] = {
                            "kind": "timeout",
                            "pmid": pmid,
                            "debug": {
                                "pmid": pmid,
                                "status": "timeout",
                                "reason": f"ai_timeout_{config.AI_PER_PAPER_TIMEOUT_SECONDS}s",
                                "emitted_rows": 0,
                            },
                        }
                        completed_count += 1
                        report_parallel_progress()
                        emit_log(
                            "warn",
                            f"[parallel] Timed out PMID {pmid} - skipping (no retry)",
                        )

                    for pmid, info in list(in_flight.items()):
                        if not info["async_result"].ready():
                            continue
                        try:
                            payload = info["async_result"].get(timeout=0)
                        except Exception as e:
                            payload = {"error": str(e)}
                        paper_df, debug_artifact = finalize_paper_result(
                            payload,
                            pmid,
                            info["ctx"]["base_info"],
                            citation_records,
                            info["ctx"]["figure_inputs"],
                            pubtator_results,
                            pipeline_stats,
                            emit_log,
                        )
                        ordered_results[info["idx"]] = {
                            "kind": "result",
                            "pmid": pmid,
                            "paper_df": paper_df,
                            "debug": debug_artifact,
                        }
                        completed_count += 1
                        report_parallel_progress()
                        del in_flight[pmid]

                    worker_pool.terminate()
                    worker_pool.join()
                    worker_pool = mp.Pool(processes=pool_size)
                    logging.info(f"AI worker pool recreated: {pool_size} processes")

                    for pmid, info in list(in_flight.items()):
                        ctx = info["ctx"]
                        ctx["submitted_at"] = time.time()
                        new_ar = worker_pool.apply_async(
                            run_pipeline_worker,
                            args=(
                                ctx["paper_text"],
                                column_descriptions,
                                ctx["pt_gene_symbols"],
                                ctx["figure_inputs"],
                                ctx["abstract"],
                                ctx["table_inputs"],
                                pmid,
                                ctx["prepared_content"],
                            ),
                        )
                        in_flight[pmid] = {
                            "idx": info["idx"],
                            "async_result": new_ar,
                            "ctx": ctx,
                        }
                        emit_log(
                            "info",
                            f"[parallel] Re-submitted PMID {pmid} after pool restart",
                        )

                submit_next()
        else:
            for i, pmid in enumerate(tqdm(pmids_to_process, desc="Processing papers")):
                result.analyzed_attempts += 1
                ai_progress = 70 + int((i / total_papers) * 25)
                report_progress(
                    "Per-paper analysis",
                    ai_progress,
                    {"papers_analyzed": result.analyzed_attempts},
                )

                prepared = prepare_paper_inputs(
                    pmid, content_dict, paper_details, pubtator_results
                )
                short_title = (
                    (prepared["title"][:60] + "...")
                    if len(prepared["title"]) > 60
                    else prepared["title"]
                )
                emit_log(
                    "info",
                    f"Analyzing paper {i + 1}/{total_papers}: {short_title}",
                    f"PMID {pmid}",
                )

                if not prepared["paper_text"]:
                    result.minimal_rows.append(
                        build_minimal_row(pmid, prepared["base_info"], citation_records)
                    )
                    result.paper_debug_artifacts.append(
                        {
                            "pmid": pmid,
                            "status": "no_full_text",
                            "reason": "missing_paper_text_after_fetch",
                            "emitted_rows": 0,
                        }
                    )
                    continue

                try:
                    ar = worker_pool.apply_async(
                        run_pipeline_worker,
                        args=(
                            prepared["paper_text"],
                            column_descriptions,
                            prepared["pt_gene_symbols"],
                            prepared["figure_inputs"],
                            prepared["abstract"],
                            prepared["table_inputs"],
                            pmid,
                            prepared["prepared_content"],
                        ),
                    )
                    submitted_at = time.time()
                    while not ar.ready():
                        check_cancellation()
                        elapsed = time.time() - submitted_at
                        if elapsed > config.AI_PER_PAPER_TIMEOUT_SECONDS:
                            raise mp.TimeoutError()
                        time.sleep(0.2)
                    try:
                        payload = ar.get(timeout=0)
                    except mp.TimeoutError:
                        emit_log("warn", f"AI analysis timed out for PMID {pmid}, skipping")
                        logging.warning(
                            f"AI analysis timed out for PMID {pmid} after {config.AI_PER_PAPER_TIMEOUT_SECONDS}s; skipping"
                        )
                        result.paper_debug_artifacts.append(
                            {
                                "pmid": pmid,
                                "status": "timeout",
                                "reason": f"ai_timeout_{config.AI_PER_PAPER_TIMEOUT_SECONDS}s",
                                "emitted_rows": 0,
                            }
                        )
                        try:
                            worker_pool.terminate()
                            worker_pool.join()
                        except Exception as e:
                            logging.warning(f"Worker pool cleanup after timeout failed: {e}")
                        worker_pool = mp.Pool(processes=pool_size)
                        logging.info(f"AI worker pool recreated: {pool_size} processes")
                        continue
                except Exception as e:
                    emit_log("error", f"AI analysis failed for PMID {pmid}", str(e))
                    logging.error(f"Failed AI analysis for PMID {pmid}: {e}")
                    paper_df = pd.DataFrame()
                    debug_artifact = {
                        "pmid": pmid,
                        "status": "orchestrator_error",
                        "reason": str(e),
                        "candidate_count": None,
                        "candidates": [],
                        "detail_extraction_status": "",
                        "detail_extraction_error": "",
                        "detail_extraction_rows": None,
                        "validation_drops": [],
                        "strict_gate_drops": [],
                        "evidence_gate_drops": [],
                        "final_associations": [],
                        "emitted_rows": 0,
                    }
                else:
                    paper_df, debug_artifact = finalize_paper_result(
                        payload,
                        pmid,
                        prepared["base_info"],
                        citation_records,
                        prepared["figure_inputs"],
                        pubtator_results,
                        pipeline_stats,
                        emit_log,
                    )

                result.all_results_df = accumulate_result(
                    result.all_results_df,
                    paper_df,
                    pmid,
                    result.collected_rows,
                    result.full_rows_pmids,
                    pipeline_stats,
                    emit_log,
                )
                result.paper_debug_artifacts.append(debug_artifact)

    except JobCancelledException:
        logging.warning("Job cancellation detected! Stopping new paper processing.")
        recorded_pmids = set()
        if ordered_results is not None:
            recorded_pmids = {
                slot["pmid"]
                for slot in ordered_results
                if isinstance(slot, dict) and slot.get("pmid")
            }
        processed_set = (
            set(result.collected_rows)
            | {r["PMID"] for r in result.minimal_rows}
            | recorded_pmids
        )
        remaining = [p for p in pmids_to_process if p not in processed_set]

        for pmid in remaining:
            base_info = paper_details.get(pmid, {})
            result.minimal_rows.append(
                {
                    **build_minimal_row(
                        pmid,
                        base_info,
                        citation_records,
                        gene_group="CANCELLED",
                        variant_name="CANCELLED",
                    ),
                    "Abstract": base_info.get("abstract", "No abstract available - Job Cancelled"),
                }
            )
    finally:
        try:
            worker_pool.terminate()
            worker_pool.join()
        except Exception as e:
            logging.warning(f"Worker pool final cleanup failed: {e}")
        logging.info("AI worker pool terminated")

    if parallel_mode and ordered_results is not None:
        for slot in ordered_results:
            if not isinstance(slot, dict):
                continue
            kind = slot.get("kind")
            if kind == "minimal":
                result.minimal_rows.append(
                    build_minimal_row(slot["pmid"], slot["base_info"], citation_records)
                )
                result.paper_debug_artifacts.append(slot["debug"])
            elif kind == "timeout":
                result.paper_debug_artifacts.append(slot["debug"])
            elif kind == "result":
                result.all_results_df = accumulate_result(
                    result.all_results_df,
                    slot["paper_df"],
                    slot["pmid"],
                    result.collected_rows,
                    result.full_rows_pmids,
                    pipeline_stats,
                    emit_log,
                )
                result.paper_debug_artifacts.append(slot["debug"])

    return result
