#!/usr/bin/env python3
"""Run one Gemini free-tier time-of-day study batch.

This wrapper keeps the benchmark settings fixed, calls the existing
ResearchShop pipeline CLI, timestamps pipeline logs, and writes a compact run
manifest that the analyzer can aggregate later.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import selectors
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
STUDY_DIR = Path(__file__).resolve().parent
PIPELINE_CLI = REPO_ROOT / "pipeline" / "run_pipeline.py"
DEFAULT_PIPELINE_PYTHON = REPO_ROOT / "pipeline" / ".venv" / "bin" / "python"

FREE_TIER_ENV = {
    "GEMINI_USAGE_PROFILE": "free",
    "GEMINI_GENE_EXTRACTION_MODEL": "gemini-3.1-flash-lite",
    "GEMINI_DATA_EXTRACTION_MODEL": "gemini-3.1-flash-lite",
    "PARALLEL_ANALYSIS": "false",
    "AI_WORKER_POOL_SIZE": "1",
    "GEMINI_MAX_CALLS_PER_PAPER": "3",
    "GEMINI_INTER_CALL_DELAY_SECONDS": "6",
    "AI_PER_PAPER_TIMEOUT_SECONDS": "600",
    "ENABLE_FIGURE_ANALYSIS": "false",
    "ENABLE_PDF_OCR": "false",
    "ENABLE_ABSTRACT_GENE_DISCOVERY": "false",
    "ENABLE_SECOND_GENE_DISCOVERY_PASS": "false",
}

DEFAULT_COLUMNS = STUDY_DIR / "columns.json"
DEFAULT_CORPUS = STUDY_DIR / "corpus.json"
DEFAULT_SCHEDULE = STUDY_DIR / "schedule.json"
DEFAULT_RUN_ROOT = STUDY_DIR / "runs"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        fh.write("\n")


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def git_dirty() -> bool:
    try:
        output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return bool(output.strip())
    except Exception:
        return False


def pipeline_python() -> str:
    configured = os.environ.get("RESEARCHSHOP_PIPELINE_PYTHON", "").strip()
    if configured:
        return configured
    if DEFAULT_PIPELINE_PYTHON.exists():
        return str(DEFAULT_PIPELINE_PYTHON)
    return sys.executable


def load_pmids(corpus_path: Path, *, allow_unverified: bool, pilot_count: int = 0) -> list[str]:
    corpus = load_json(corpus_path)
    if not corpus.get("verified") and not allow_unverified:
        raise SystemExit(
            f"{corpus_path} is not marked verified. Run a pilot first, then set "
            "verified=true after replacing any unsuitable PMIDs."
        )
    entries = corpus.get("pmids") or []
    pmids = [str(entry.get("pmid", "")).strip() for entry in entries]
    pmids = [pmid for pmid in pmids if pmid]
    if pilot_count:
        return pmids[:pilot_count]
    if len(pmids) != 10:
        raise SystemExit(f"Expected exactly 10 PMIDs in {corpus_path}, found {len(pmids)}")
    return pmids


def pmid_fingerprint(pmids: list[str]) -> str:
    normalized = "\n".join(str(pmid).strip() for pmid in pmids)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def schedule_entry(schedule_path: Path, run_id: str) -> dict[str, Any]:
    schedule = load_json(schedule_path)
    for item in schedule.get("runs", []):
        if item.get("run_id") == run_id:
            entry = dict(item)
            entry["cadence_minutes"] = schedule.get("cadence_minutes")
            return entry
    known = ", ".join(item.get("run_id", "") for item in schedule.get("runs", []))
    raise SystemExit(f"Unknown run_id {run_id!r}. Known run IDs: {known}")


def scheduled_datetime(planned_entry: dict[str, Any], timezone_name: str) -> datetime | None:
    planned_date = str(planned_entry.get("planned_date", "")).strip()
    planned_time = str(planned_entry.get("planned_local_time", "")).strip()
    if not planned_date or not planned_time:
        return None
    return datetime.fromisoformat(f"{planned_date}T{planned_time}:00").replace(
        tzinfo=ZoneInfo(timezone_name)
    )


def schedule_timezone(schedule_path: Path) -> str:
    schedule = load_json(schedule_path)
    return str(schedule.get("timezone") or "Europe/Warsaw")


def validate_schedule_time(
    planned_entry: dict[str, Any],
    *,
    timezone_name: str,
    now: datetime | None = None,
) -> None:
    planned_at = scheduled_datetime(planned_entry, timezone_name)
    if planned_at is None:
        return
    current = now or datetime.now(ZoneInfo(timezone_name))
    if current < planned_at:
        raise SystemExit(
            "Refusing to start before scheduled local time: "
            f"{planned_entry.get('run_id', '')} is planned for "
            f"{planned_at.isoformat(timespec='minutes')}, current time is "
            f"{current.isoformat(timespec='minutes')}."
        )


def parse_pipeline_line(line: str) -> tuple[str, Any] | None:
    for prefix in ("PROGRESS:", "LOG:", "RESULT:"):
        if line.startswith(prefix):
            raw = line[len(prefix):]
            try:
                return prefix[:-1].lower(), json.loads(raw)
            except json.JSONDecodeError:
                return prefix[:-1].lower(), raw
    return None


def extract_result(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("kind") == "result" and isinstance(event.get("payload"), dict):
            return event["payload"]
    return {}


def derive_paper_timings(events: list[dict[str, Any]], pmids: list[str], end_epoch: float) -> dict[str, float]:
    starts: dict[str, float] = {}
    ordered_starts: list[tuple[str, float]] = []
    pattern = re.compile(r"PMID\s+(\d+)")

    for event in events:
        if event.get("kind") != "log":
            continue
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        detail = str(payload.get("detail") or "")
        msg = str(payload.get("msg") or "")
        if "Analyzing paper" not in msg:
            continue
        match = pattern.search(detail)
        if not match:
            continue
        pmid = match.group(1)
        starts[pmid] = float(event["epoch"])
        ordered_starts.append((pmid, float(event["epoch"])))

    timings: dict[str, float] = {}
    for idx, (pmid, start_epoch) in enumerate(ordered_starts):
        if idx + 1 < len(ordered_starts):
            next_epoch = ordered_starts[idx + 1][1]
        else:
            next_epoch = end_epoch
        timings[pmid] = max(0.0, next_epoch - start_epoch)
    return {pmid: timings.get(pmid, 0.0) for pmid in pmids}


def count_csv_rows(path: str) -> int:
    if not path:
        return 0
    csv_path = Path(path)
    if not csv_path.exists():
        return 0
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def load_optional_json(path: str) -> dict[str, Any]:
    if not path:
        return {}
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        return load_json(json_path)
    except Exception:
        return {}


def summarize_run(
    *,
    run_id: str,
    planned_entry: dict[str, Any],
    pmids: list[str],
    start_epoch: float,
    end_epoch: float,
    return_code: int,
    events: list[dict[str, Any]],
    output_dir: Path,
    corpus_fingerprint: str,
    timezone_name: str,
    quota_snapshot_path: Path | None,
    usage_before: int | None,
    usage_after: int | None,
) -> dict[str, Any]:
    result = extract_result(events)
    debug = load_optional_json(result.get("debug_path", ""))
    candidate_audit = load_optional_json(result.get("candidate_audit_path", ""))
    paper_timings = derive_paper_timings(events, pmids, end_epoch)
    paper_debug = {str(p.get("pmid", "")): p for p in debug.get("paper_debug", [])}
    fetch_by_pmid = {
        str(item.get("pmid", "")): item
        for item in debug.get("fetch_outcomes", [])
        if isinstance(item, dict)
    }
    audit_by_pmid = {
        str(item.get("pmid", "")): item
        for item in candidate_audit.get("papers", [])
        if isinstance(item, dict)
    }
    quota_warnings = [
        event
        for event in events
        if event.get("kind") == "log"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("level") == "warn"
        and "quota" in str(event["payload"].get("msg", "")).lower()
    ]
    event_texts = [json.dumps(event.get("payload", ""), ensure_ascii=False, default=str) for event in events]
    gemini_error_count = sum(
        1
        for text in event_texts
        if "PERMISSION_DENIED" in text
        or "RESOURCE_EXHAUSTED" in text
        or "UNAVAILABLE" in text
        or "503" in text
        or "google.genai.errors" in text
    )
    permission_denied_count = sum(1 for text in event_texts if "PERMISSION_DENIED" in text)
    unavailable_count = sum(1 for text in event_texts if "UNAVAILABLE" in text or "503" in text)
    timezone = ZoneInfo(timezone_name)

    per_paper = []
    for pmid in pmids:
        dbg = paper_debug.get(pmid, {})
        audit = audit_by_pmid.get(pmid, {})
        fetch = fetch_by_pmid.get(pmid, {})
        per_paper.append(
            {
                "pmid": pmid,
                "runtime_seconds": round(paper_timings.get(pmid, 0.0), 3),
                "status": dbg.get("status", ""),
                "reason": dbg.get("reason", ""),
                "fetch_source": fetch.get("source") or fetch.get("method") or "",
                "text_chars": fetch.get("content_chars") or fetch.get("chars") or None,
                "candidate_count": dbg.get("candidate_count"),
                "emitted_rows": dbg.get("emitted_rows", audit.get("emitted_rows", 0)),
                "strict_gate_drops": len(dbg.get("strict_gate_drops") or []),
                "citation_gate_drops": len(dbg.get("evidence_gate_drops") or []),
                "quota_limited": bool(dbg.get("quota_limited")),
                "detail_extraction_status": dbg.get("detail_extraction_status", ""),
                "detail_extraction_error": dbg.get("detail_extraction_error", ""),
            }
        )

    pipeline_stats = debug.get("pipeline_stats", {})
    completed = sum(1 for item in per_paper if item["status"] == "ok")
    quota_limited_papers = sum(1 for item in per_paper if item["quota_limited"])
    timeout_count = sum(1 for item in per_paper if item["status"] == "timeout")
    failed_papers = sum(
        1
        for item in per_paper
        if item["status"] and item["status"] not in {"ok", "timeout", "no_full_text"}
    )

    return {
        "schema_version": "gemini_time_of_day_run_v1",
        "run_id": run_id,
        "time_block": planned_entry.get("time_block", ""),
        "repeat": planned_entry.get("repeat"),
        "planned_local_time": planned_entry.get("planned_local_time", ""),
        "planned_date": planned_entry.get("planned_date", ""),
        "quota_window_start_date": planned_entry.get("quota_window_start_date", ""),
        "cadence_minutes": planned_entry.get("cadence_minutes"),
        "started_at": datetime.fromtimestamp(start_epoch, timezone).isoformat(timespec="seconds"),
        "ended_at": datetime.fromtimestamp(end_epoch, timezone).isoformat(timespec="seconds"),
        "runtime_seconds": round(end_epoch - start_epoch, 3),
        "return_code": return_code,
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "settings": FREE_TIER_ENV,
        "pmids": pmids,
        "corpus_fingerprint": corpus_fingerprint,
        "quota_snapshot_path": str(quota_snapshot_path) if quota_snapshot_path else "",
        "usage_before": usage_before,
        "usage_after": usage_after,
        "usage_delta": (
            usage_after - usage_before
            if usage_before is not None and usage_after is not None
            else None
        ),
        "batch": {
            "completed_papers": completed,
            "total_papers": len(pmids),
            "quota_limited_papers": quota_limited_papers,
            "quota_limited_rows": int(pipeline_stats.get("quota_limited_rows", 0) or 0),
            "quota_warning_count": len(quota_warnings),
            "timeout_count": timeout_count,
            "failed_papers": failed_papers,
            "gemini_api_calls": int(pipeline_stats.get("gemini_api_calls", 0) or 0),
            "gemini_error_count": gemini_error_count,
            "model_unavailable_count": unavailable_count,
            "permission_denied_count": permission_denied_count,
            "output_rows": count_csv_rows(result.get("local_path", "")),
        },
        "outputs": {
            "output_dir": str(output_dir),
            "csv": result.get("local_path", ""),
            "metadata_csv": result.get("metadata_path", ""),
            "xlsx": result.get("excel_path", ""),
            "json": result.get("json_path", ""),
            "candidate_audit": result.get("candidate_audit_path", ""),
            "debug": result.get("debug_path", ""),
        },
        "per_paper": per_paper,
        "warning": result.get("warning", ""),
        "error": result.get("error", ""),
    }


def run_batch(args: argparse.Namespace) -> int:
    run_id = args.run_id or "pilot"
    planned = {"run_id": run_id, "time_block": "pilot", "repeat": 0, "planned_date": ""}
    timezone_name = schedule_timezone(args.schedule)
    if args.run_id:
        planned = schedule_entry(args.schedule, args.run_id)
        if not args.allow_early_run:
            validate_schedule_time(planned, timezone_name=timezone_name)
    pmids = load_pmids(
        args.corpus,
        allow_unverified=args.allow_unverified_corpus or args.pilot,
        pilot_count=args.pilot_count if args.pilot else 0,
    )
    corpus_fingerprint = pmid_fingerprint(pmids)
    columns = load_json(args.columns)

    output_dir = args.output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "pipeline_events.jsonl"
    manifest_path = output_dir / "study_run.json"
    if manifest_path.exists() and not args.overwrite_run:
        raise SystemExit(
            f"{manifest_path} already exists. Use --overwrite-run only for an intentional rerun."
        )

    env = os.environ.copy()
    env.update(FREE_TIER_ENV)

    command = [
        pipeline_python(),
        str(PIPELINE_CLI),
        "--pmids",
        json.dumps(pmids),
        "--columns",
        json.dumps(columns),
        "--top-n",
        str(len(pmids)),
        "--output-dir",
        str(output_dir),
    ]

    if not env.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY must be set in the environment")
    if not env.get("ENTREZ_EMAIL"):
        raise SystemExit("ENTREZ_EMAIL must be set in the environment")

    events: list[dict[str, Any]] = []

    def record_event(kind: str, payload: Any, event_fh) -> None:
        now = time.time()
        event = {
            "epoch": now,
            "timestamp": datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds"),
            "kind": kind,
            "payload": payload,
        }
        events.append(event)
        event_fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        event_fh.flush()

    started = time.time()
    with events_path.open("w", encoding="utf-8") as event_fh:
        record_event(
            "study",
            {
                "msg": "starting pipeline command",
                "run_id": run_id,
                "pmids": pmids,
                "corpus_fingerprint": corpus_fingerprint,
                "max_runtime_seconds": args.max_runtime_seconds,
            },
            event_fh,
        )
        proc = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert proc.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        timed_out = False
        while proc.poll() is None:
            if args.max_runtime_seconds and (time.time() - started) > args.max_runtime_seconds:
                timed_out = True
                record_event(
                    "study",
                    {
                        "msg": "max runtime exceeded; terminating pipeline command",
                        "max_runtime_seconds": args.max_runtime_seconds,
                    },
                    event_fh,
                )
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                break
            for key, _ in selector.select(timeout=1.0):
                line = key.fileobj.readline()
                if not line:
                    continue
                line = line.rstrip("\n")
                parsed = parse_pipeline_line(line)
                if parsed:
                    kind, payload = parsed
                else:
                    kind, payload = "stdout", line
                record_event(kind, payload, event_fh)
                if not args.quiet:
                    print(line, flush=True)
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            parsed = parse_pipeline_line(line)
            if parsed:
                kind, payload = parsed
            else:
                kind, payload = "stdout", line
            record_event(kind, payload, event_fh)
            if not args.quiet:
                print(line, flush=True)
        return_code = proc.returncode if proc.returncode is not None else proc.wait()
        if timed_out:
            return_code = 124
    ended = time.time()

    manifest = summarize_run(
        run_id=run_id,
        planned_entry=planned,
        pmids=pmids,
        start_epoch=started,
        end_epoch=ended,
        return_code=return_code,
        events=events,
        output_dir=output_dir,
        corpus_fingerprint=corpus_fingerprint,
        timezone_name=timezone_name,
        quota_snapshot_path=args.quota_snapshot,
        usage_before=args.usage_before,
        usage_after=args.usage_after,
    )
    if return_code == 124:
        manifest["timed_out"] = True
        manifest["error"] = manifest.get("error") or "study_runner_max_runtime_exceeded"
    write_json(manifest_path, manifest)
    print(f"Study manifest written: {manifest_path}")
    return return_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Run ID from schedule.json, e.g. rep1_0300")
    parser.add_argument("--pilot", action="store_true", help="Run a pilot subset outside the formal schedule")
    parser.add_argument("--pilot-count", type=int, default=2)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--columns", type=Path, default=DEFAULT_COLUMNS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--quota-snapshot", type=Path)
    parser.add_argument("--usage-before", type=int)
    parser.add_argument("--usage-after", type=int)
    parser.add_argument("--allow-unverified-corpus", action="store_true")
    parser.add_argument(
        "--allow-early-run",
        action="store_true",
        help="Allow a formal run before its scheduled local time. Intended only for dry-study debugging.",
    )
    parser.add_argument(
        "--overwrite-run",
        action="store_true",
        help="Overwrite an existing run directory/manifest for the same run ID.",
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=int,
        default=0,
        help="Terminate the pipeline if wall-clock runtime exceeds this value. 0 disables.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.run_id and not args.pilot:
        parser.error("Provide --run-id for formal runs or --pilot for a pilot run")
    if args.run_id and args.pilot:
        parser.error("--run-id and --pilot are mutually exclusive")

    return run_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())
