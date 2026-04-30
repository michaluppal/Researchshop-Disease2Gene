"""Pipeline tracer — opt-in flight recorder for one paper.

Enabled by setting the env var ``TRACE_PMID`` to a target PMID.  Every pipeline
stage that has been instrumented calls :func:`capture` with a ``node_id``,
optional ``inputs`` / ``outputs`` / ``meta`` dicts.  Events are buffered in a
process-local list and written to ``$TRACE_OUT_DIR/trace_<pmid>.json`` by the
orchestrator at the end of the run.

The tracer is designed to be **completely free** when the env var is unset —
``capture()`` short-circuits at the guard check with one dict lookup.

Multiprocessing: each worker has its own module-level state, and each worker
writes a partial trace to ``$TRACE_OUT_DIR/trace_<pmid>_pid<N>.jsonl``.  The
orchestrator merges partials at the end.  This avoids IPC serialisation of
potentially large trace payloads.

Design notes:
- Node IDs match the ``NODES`` table in
  ``publication/figures/pipeline-viewer/index.html``.  Keep them in sync.
- Each node is captured at most once per PMID per process.  If a stage fires
  multiple times for the same paper (e.g. Step 1 + Step 1b both tagged
  ``fulltext_pass_*``), give each call a distinct node_id.
- Values in ``inputs`` / ``outputs`` / ``meta`` must be JSON-serialisable.
  Use :func:`summarise` to reduce large blobs (paper text, DataFrames) to
  a size/shape summary instead of dumping the content.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Lock, local
from typing import Any, Dict, Iterable, Optional


_target_pmid: Optional[str] = os.environ.get("TRACE_PMID") or None
_events: list[Dict[str, Any]] = []
_lock = Lock()
_out_dir: Optional[Path] = None
_live_file: Optional[str] = os.environ.get("TRACE_LIVE_FILE") or None
_stage_state = local()
_paper_state = local()


def is_enabled() -> bool:
    """True if tracing is active for this process."""
    return _target_pmid is not None


def target_pmid() -> Optional[str]:
    """The PMID we're tracing, or ``None`` if disabled."""
    return _target_pmid


def matches(pmid: Optional[str]) -> bool:
    """Return True if this PMID is the tracing target."""
    if not _target_pmid:
        return False
    if not pmid:
        return False
    return str(pmid).strip() == str(_target_pmid).strip()


def matches_any(pmids: Iterable[Any]) -> bool:
    """Return True if any PMID in the iterable is the tracing target."""
    if not _target_pmid:
        return False
    for p in pmids or []:
        if matches(p):
            return True
    return False


def capture(
    node_id: str,
    *,
    pmid: Optional[str] = None,
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """Record one trace event.

    Parameters
    ----------
    node_id
        Identifier matching the HTML viewer's NODES table (e.g.
        ``"pubtator_ner"``, ``"grounding_check"``).
    pmid
        If set, the event is recorded only when the PMID matches ``TRACE_PMID``.
        Pass ``None`` to always record (e.g. for pipeline-wide stages like
        ``user_selection``).
    inputs / outputs / meta
        Free-form JSON-serialisable dicts.  Must be small — use :func:`summarise`
        for paper text, DataFrames, and other large payloads.
    duration_ms
        Optional stage duration in milliseconds.
    """
    if not is_enabled():
        return
    if pmid is not None and not matches(pmid):
        return
    event = {
        "node_id": node_id,
        "stage_id": current_stage() or node_id,
        "captured_at": time.time(),
    }
    if inputs is not None:
        event["inputs"] = _safe_jsonable(inputs)
    if outputs is not None:
        event["outputs"] = _safe_jsonable(outputs)
    if meta is not None:
        event["meta"] = _safe_jsonable(meta)
    if duration_ms is not None:
        event["duration_ms"] = float(duration_ms)
    with _lock:
        _events.append(event)

    # Live streaming: append to a shared file that the server tails in real time.
    # POSIX file-append is atomic for lines < PIPE_BUF (typically ≥4 KiB), which
    # covers almost every tracer event. For larger payloads we'd need a lock file,
    # but tracer events are compact on purpose via summarise().
    if _live_file:
        try:
            with open(_live_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass  # live streaming is best-effort; the primary trace file is authoritative


def set_output_dir(path: os.PathLike) -> None:
    """Called by the orchestrator to tell the tracer where to write partials."""
    global _out_dir
    _out_dir = Path(path)
    _out_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TRACE_OUT_DIR"] = str(_out_dir)


def _resolved_output_dir() -> Optional[Path]:
    if _out_dir is not None:
        return _out_dir
    env_dir = os.environ.get("TRACE_OUT_DIR")
    if env_dir:
        out_dir = Path(env_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir
    return None


def flush_worker_partial() -> Optional[Path]:
    """Write this worker's events to a partial file and clear the buffer.

    Called at the end of a worker's lifetime (or at process exit).  Returns the
    path written, or ``None`` if nothing to write.
    """
    if not is_enabled() or not _events:
        return None
    out_dir = _resolved_output_dir()
    if out_dir is None:
        # Fall back to tmp if orchestrator didn't set one
        out_dir = Path(os.environ.get("TMPDIR", "/tmp")) / "rs_trace"
        out_dir.mkdir(parents=True, exist_ok=True)
    pmid = _target_pmid or "unknown"
    path = out_dir / f"trace_{pmid}_pid{os.getpid()}.jsonl"
    with _lock:
        events_to_write = list(_events)
        _events.clear()
    with open(path, "a", encoding="utf-8") as f:
        for ev in events_to_write:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return path


def collect_and_write(pmid: str, output_path: os.PathLike) -> Optional[Path]:
    """Merge partial JSONL files into a single ``trace_<pmid>.json``.

    Should be called by the orchestrator at the end of a traced run, after
    all workers have flushed.  Returns the path written, or ``None`` if no
    trace data was found.
    """
    if not is_enabled():
        return None
    out_dir = _resolved_output_dir()
    if out_dir is None:
        return None
    partials = sorted(out_dir.glob(f"trace_{pmid}_pid*.jsonl"))
    # Also include events still in this process's buffer
    flush_worker_partial()
    partials = sorted(out_dir.glob(f"trace_{pmid}_pid*.jsonl"))

    live_file = Path(_live_file) if _live_file else None
    sources = list(partials)
    if live_file and live_file.exists():
        sources.append(live_file)

    if not sources:
        return None

    nodes: Dict[str, Dict[str, Any]] = {}
    function_events: list[Dict[str, Any]] = []
    function_counts_by_stage: Dict[str, int] = {}
    function_counts_by_name: Dict[str, int] = {}
    for p in sources:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                event_type = ev.get("type")
                if event_type in {"fn_call", "fn_return"}:
                    event_pmid = str(ev.get("pmid") or "").strip()
                    if event_pmid and event_pmid != str(pmid).strip():
                        continue
                    function_events.append(ev)
                    stage = str(ev.get("stage_id") or "unscoped")
                    name = ".".join(
                        part
                        for part in [
                            str(ev.get("module") or "").strip(),
                            str(ev.get("function") or "").strip(),
                        ]
                        if part
                    ) or "unknown"
                    function_counts_by_stage[stage] = function_counts_by_stage.get(stage, 0) + 1
                    function_counts_by_name[name] = function_counts_by_name.get(name, 0) + 1
                    continue

                nid = ev.get("node_id")
                if not nid:
                    continue
                # Last-write-wins for same node_id (re-runs within same PMID are rare)
                nodes[nid] = ev

    out_path = Path(output_path)
    function_trace_path = out_path.with_name(f"{out_path.stem}_functions.jsonl")
    if function_events:
        function_trace_path.parent.mkdir(parents=True, exist_ok=True)
        with open(function_trace_path, "w", encoding="utf-8") as f:
            for ev in function_events:
                f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")

    out = {
        "pmid": pmid,
        "generated_at": time.time(),
        "node_count": len(nodes),
        "nodes": nodes,
        "function_event_count": len(function_events),
        "function_trace_path": str(function_trace_path) if function_events else "",
        "function_counts_by_stage": dict(
            sorted(function_counts_by_stage.items(), key=lambda item: (-item[1], item[0]))
        ),
        "function_counts_by_name": dict(
            sorted(function_counts_by_name.items(), key=lambda item: (-item[1], item[0]))[:200]
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)

    # Clean up partials after successful merge
    for p in partials:
        try:
            p.unlink()
        except Exception:
            pass

    return out_path


def current_stage() -> Optional[str]:
    stack = getattr(_stage_state, "stack", None)
    if not stack:
        return None
    return stack[-1]


def current_pmid() -> Optional[str]:
    return getattr(_paper_state, "pmid", None)


@contextmanager
def paper(pmid: Optional[str]):
    """Tag nested function-trace events with the active PMID."""
    previous = getattr(_paper_state, "pmid", None)
    _paper_state.pmid = str(pmid).strip() if pmid else None
    try:
        yield
    finally:
        _paper_state.pmid = previous


@contextmanager
def stage(stage_id: str):
    """Tag nested function-trace events with the active semantic pipeline stage."""
    if not is_enabled():
        yield
        return
    stack = getattr(_stage_state, "stack", None)
    if stack is None:
        stack = []
        _stage_state.stack = stack
    stack.append(stage_id)
    try:
        yield
    finally:
        if stack:
            stack.pop()


def summarise(obj: Any, *, max_items: int = 10, max_str: int = 200) -> Any:
    """Compress large values into a JSON-friendly summary.

    Use this for paper text, DataFrames, long lists, or anything whose full
    content would bloat the trace file.
    """
    try:
        import pandas as pd  # type: ignore
        if isinstance(obj, pd.DataFrame):
            preview = obj.head(3).copy()
            seen_counts: dict[str, int] = {}
            preview_cols = []
            for col in preview.columns:
                count = seen_counts.get(str(col), 0)
                preview_cols.append(str(col) if count == 0 else f"{col} ({count + 1})")
                seen_counts[str(col)] = count + 1
            preview.columns = preview_cols
            return {
                "__type__": "DataFrame",
                "rows": int(len(obj)),
                "cols": list(obj.columns)[:20],
                "head": preview.to_dict(orient="records") if len(obj) else [],
            }
    except Exception:
        pass

    if isinstance(obj, str):
        if len(obj) <= max_str:
            return obj
        return {
            "__type__": "str",
            "length": len(obj),
            "preview_head": obj[:max_str // 2],
            "preview_tail": obj[-max_str // 2:],
        }

    if isinstance(obj, (list, tuple)):
        if len(obj) <= max_items:
            return [summarise(x, max_items=max_items, max_str=max_str) for x in obj]
        return {
            "__type__": "list",
            "length": len(obj),
            "preview": [summarise(x, max_items=max_items, max_str=max_str) for x in obj[:max_items]],
        }

    if isinstance(obj, dict):
        if len(obj) <= max_items:
            return {k: summarise(v, max_items=max_items, max_str=max_str) for k, v in obj.items()}
        preview_keys = list(obj.keys())[:max_items]
        return {
            "__type__": "dict",
            "size": len(obj),
            "preview": {k: summarise(obj[k], max_items=max_items, max_str=max_str) for k in preview_keys},
        }

    return obj


def _safe_jsonable(obj: Any) -> Any:
    """Ensure the object can be JSON-serialised. Fallback to str() for anything exotic."""
    try:
        json.dumps(obj, default=str)
        return obj
    except Exception:
        try:
            return str(obj)
        except Exception:
            return "<unrepresentable>"


# ──────────────────────────────────────────────────────────────────────────────
# Function-level tracer (opt-in, noisy, developer-oriented)
# ──────────────────────────────────────────────────────────────────────────────
# This is a separate and more aggressive tracing mode. It installs a
# ``sys.setprofile`` hook that emits a ``fn_call`` / ``fn_return`` line for every
# function call inside the pipeline code.  Events are appended to the same live
# file as stage events (when ``TRACE_LIVE_FILE`` is set) so the browser receives
# them through the same SSE channel.
#
# Scope is *aggressively* filtered to avoid drowning the pipeline in profile-
# callback overhead:
#   1. Only modules whose ``__name__`` starts with a pipeline prefix are logged.
#   2. Dunder methods (__init__, __enter__, …) are skipped.
#   3. A hard cap on event count stops runaway generation.
#
# Enabled only when the caller sets ``TRACE_FUNCTIONS=1``.  Zero cost when off.

_fn_tracer_installed: bool = False
_fn_event_count: int = 0
_fn_event_cap: int = 5000
_fn_call_depth: int = 0

# Module name prefixes that count as "ours".  Adjust here if pipeline code
# moves to a different package.
_FN_TRACER_PREFIXES = ("modules.", "pipeline.modules.")

# Hot-path helpers that are called once per XML element / row / token during
# deep parsing loops. They bury everything else in noise — skipping them is
# essentially free precision.  Add to this set rather than raising the cap.
# Functions where we capture full arg + return VALUES (not just names/types).
# These are high-signal transformations where the user wants to see data flow.
# Everything else stays name-only to keep the trace tight and fast.
_FN_TRACER_VALUE_CAPTURE = frozenset({
    # ── Paper-text transformations ────────────────────────────────────────
    "_clean_and_validate_content",              # Greek → Latin, non-ASCII strip
    "_normalize_unicode_slashes",               # slash/μ/LaTeX unification
    "_extract_text_and_figures_from_pmc_xml",
    "parse_pubmed_parser_paragraph_text",
    "parse_pubmed_parser_figures",
    "_extract_supplementary_urls_from_pmc_xml",
    "_extract_supplementary_content",           # downloads & parses supp files
    "_extract_pdf_text",                        # pdfminer extraction
    "_extract_figures_from_pmc_xml",
    "_extract_structured_tables_from_pmc_xml",
    "_build_pmc_figure_url_candidates",
    "_assess_content_quality",
    "generate_fetch_report",

    # ── PMC / Europe PMC fetch ────────────────────────────────────────────
    "_fetch_pmc_efetch",
    "_fetch_europe_pmc_fulltext_xml",
    "_resolve_pmc_cdn_url",                     # the one scraping path
    "_fetch_figure_image",                      # multimodal Gemini input
    "_get_pmcid_for_pmid",
    "_process_single_pmid",

    # ── PubMed metadata + citations ───────────────────────────────────────
    "search_pubmed",
    "search_pubmed_by_author",
    "apply_publication_type_filter",
    "fetch_paper_details",
    "_normalize_pubmed_record",
    "_extract_year",
    "_extract_doi",
    "fetch_icite_citation_counts",
    "_fetch_semantic_citation_records",
    "fetch_citation_counts_with_fallback",
    "_extract_icite_citation_count",

    # ── PubTator NER ──────────────────────────────────────────────────────
    "extract_from_pmid",
    "extract_from_pmids",
    "_parse_document",
    "enrich_genes",
    "enrich_gene_symbols",
    "_enrich_single_gene",

    # ── Abstract screening (forensic) ─────────────────────────────────────
    "has_genetic_content",
    "screen_papers_with_decisions",
    "decisions_to_dicts",

    # ── Gemini candidate discovery + detail extraction ───────────────────
    "extract_gene_names_from_abstract",
    "extract_gene_names",
    "extract_gene_names_from_figures",
    "extract_deterministic_candidates",
    "extract_gene_info",                        # Step 3 — batched detail
    "_ingest_associations",
    "_run_candidate_discovery",
    "_run_grounding_check",
    "_run_validation_and_normalize",
    "_run_detail_extraction",
    "_run_post_validation",
    "_apply_gene_validation_heuristics",
    "_apply_evidence_gate",
    "_add_citation_validation_metadata",
    "_add_candidate_provenance_metadata",
    "_backfill_sparse_row_evidence",
    "_collect_debug_artifact",                  # full candidate_meta lifecycle dump (drop_debug)
    "_merge_duplicate_gene_rows",
    "_validate_and_prepare_paper_text",         # context truncation
    "_split_paper_into_named_sections",
    "_find_evidence_snippet",                   # grounding check interior
    "_build_gemini_image_part",

    # ── HGNC / MyGene validation ──────────────────────────────────────────
    "resolve_gene_symbol",
    "validate_gene_variant",
    "validate_associations",
    "filter_valid_associations",
    "_is_valid_gene",
    "_is_valid_variant",
    "_fuzzy_match_gene",
    "_validate_gene_hgnc",
    "_validate_gene_mygene",
    "get_gene_biotype",
    "_load_local_hgnc_database",
    "_build_local_alias_index",

    # ── Citation validator internals ─────────────────────────────────────
    "_citation_exists_in_paper",
    "_calculate_citation_confidence",
    "_extract_citation_from_response",
    "validate_citations",
    "validate_table_citation",
    "_find_gene_in_table_rows",
    "_extract_numbers",
    "validate_extracted_genes",

    # ── Context-window validator (standalone class) ──────────────────────
    "estimate_token_count",
    "check_context_fit",
    "truncate_text",
    "_truncate_preserve_sections",
    "_split_into_sections",
    "validate_paper_context",
    "validate_paper_context_fit",

    # ── Orchestrator-level plumbing that produces meaningful values ──────
    "_sanitize_user_columns",
    "_prepare_paper_inputs",                    # bundle that goes into worker
    "_accumulate_result",                       # row merge back to global df
    "build_minimal_row",
    "_compute_row_confidence",                  # HIGH/MEDIUM/LOW tier logic
    "_finalize_paper_result",                   # adds Gene Source / NCBI ID / full name / aliases / chromosome per row
    "_get_citation_record",                     # PMID → iCite/SemanticScholar record
    "_write_split_output",                      # returns 4 output paths tuple
    "_run_pipeline_worker",                     # orchestrator↔worker handoff
    "_apply_pubtator_row_enrichment",           # per-paper Gene Source / PubTator IDs
    "_apply_ncbi_metadata_columns",             # batched NCBI metadata column fill
    "_agg_variants",                            # variant-string joiner used in dedup
    "write_candidate_audit_artifact",           # stable candidate lifecycle artifact
    "write_drop_debug_artifact",
})

_FN_TRACER_NOISE = frozenset({
    # XML-parsing per-element helpers
    "_jats_tag_matches",
    "_is_jats_tag",
    "_collect_xml_text",
    "_collect_text",
    "_collect_href",
    "_append",  # closure in _extract_text_and_figures_from_pmc_xml — fires per element
    # Per-token normalisation helpers (called inside tight loops)
    "_norm_token",
    "_assoc_key",
    "_as_string_set",
    "_as_sorted_strings",
    "_candidate_terms_for_row",
    "_gene_key",
    "_get_hgnc_aliases_for_gene",
    "_normalize_empty_placeholder",
    "_normalize_gene_symbol",
    "_normalize_variant_value",
    # Poll-loop helpers — invoked every 200ms while workers run, drowns the trace
    "check_cancellation",
    "report_progress",
    "emit_log",
    # Dataclass/record serialisers — plumbing called per item
    "to_dict",
})


def function_tracer_enabled() -> bool:
    """Is the function-level tracer requested via env var?"""
    return bool(os.environ.get("TRACE_FUNCTIONS"))


def install_function_tracer(max_events: int = 5000) -> None:
    """Install a ``sys.setprofile`` hook that writes function call events to the
    live file. Idempotent; safe to call multiple times.
    """
    global _fn_tracer_installed, _fn_event_cap, _fn_event_count, _fn_call_depth
    if _fn_tracer_installed:
        return
    if not is_enabled() or not function_tracer_enabled() or not _live_file:
        return
    _fn_tracer_installed = True
    _fn_event_cap = max_events
    _fn_event_count = 0
    _fn_call_depth = 0

    import sys as _sys

    def _profile(frame, event, arg):  # noqa: ARG001
        global _fn_event_count, _fn_call_depth
        if _fn_event_count >= _fn_event_cap:
            return
        if event not in ("call", "return"):
            return
        module = frame.f_globals.get("__name__", "") or ""
        if not any(module.startswith(p) or module == p.rstrip(".") for p in _FN_TRACER_PREFIXES):
            return
        # Never trace the tracer itself — every capture() internally calls
        # is_enabled/matches/_safe_jsonable/summarise, which would generate
        # ~10 profile events per *single* semantic operation.
        if module == "modules.pipeline_tracer" or module == "pipeline.modules.pipeline_tracer":
            return
        func = frame.f_code.co_name
        # Skip all dunders (__init__, __enter__, __eq__, __hash__, __new__, etc.).
        # These fire on every dataclass construction, container comparison,
        # and context-manager entry — almost always noise.
        if func.startswith("__") and func.endswith("__"):
            return
        # Anonymous function frames — <genexpr>, <lambda>, <listcomp>, <dictcomp>,
        # <setcomp>. They're interior plumbing with no readable name.
        if func.startswith("<") and func.endswith(">"):
            return
        if func in _FN_TRACER_NOISE:
            return  # high-frequency XML / token / poll helpers

        deep_capture = func in _FN_TRACER_VALUE_CAPTURE

        if event == "call":
            _fn_call_depth += 1
            payload = {
                "type": "fn_call",
                "module": module,
                "function": func,
                "pmid": current_pmid(),
                "stage_id": current_stage(),
                "depth": _fn_call_depth,
                "line": frame.f_code.co_firstlineno,
                "file": frame.f_code.co_filename.replace(os.sep + "pipeline" + os.sep, "/"),
                "ts": time.time(),
            }
            try:
                code = frame.f_code
                nargs = code.co_argcount + code.co_kwonlyargcount
                arg_names = list(code.co_varnames[:nargs])[:8]
                payload["args"] = arg_names
                if deep_capture:
                    # Capture actual argument values for this function.
                    # Each value is run through summarise() so large blobs
                    # (paper text, DataFrames, long lists) become readable
                    # previews rather than multi-megabyte dumps.
                    arg_values: Dict[str, Any] = {}
                    for name in arg_names:
                        # Skip self/cls — their repr is always noisy
                        # ("<modules.stage5.pipeline.Stage5Pipeline object at 0x…>")
                        # and adds nothing to understanding a method's behaviour.
                        if name in ("self", "cls"):
                            continue
                        if name in frame.f_locals:
                            try:
                                arg_values[name] = summarise(
                                    frame.f_locals[name],
                                    max_items=5,
                                    max_str=500,
                                )
                            except Exception:
                                arg_values[name] = "<unsummarisable>"
                    if arg_values:
                        payload["arg_values"] = arg_values
            except Exception:
                pass
        else:  # return
            payload = {
                "type": "fn_return",
                "module": module,
                "function": func,
                "pmid": current_pmid(),
                "stage_id": current_stage(),
                "depth": _fn_call_depth,
                "return_type": type(arg).__name__ if arg is not None else "None",
                "ts": time.time(),
            }
            if deep_capture:
                try:
                    payload["return_value"] = summarise(
                        arg, max_items=5, max_str=500,
                    )
                except Exception:
                    payload["return_value"] = "<unsummarisable>"
            _fn_call_depth = max(0, _fn_call_depth - 1)

        try:
            with open(_live_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass
        _fn_event_count += 1

    _sys.setprofile(_profile)


def uninstall_function_tracer() -> None:
    """Remove the ``sys.setprofile`` hook."""
    global _fn_tracer_installed
    import sys as _sys
    _sys.setprofile(None)
    _fn_tracer_installed = False
