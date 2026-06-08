#!/usr/bin/env python3
"""Run the Gemini time-of-day study as an unattended hourly session.

Designed for WSL/tmux use. The script creates a per-session schedule under the
ignored runs/ directory, launches the existing run_study.py once per scheduled
local hour, and summarizes results after the session.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
STUDY_DIR = Path(__file__).resolve().parent
RUN_STUDY = STUDY_DIR / "run_study.py"
ANALYZE_RESULTS = STUDY_DIR / "analyze_results.py"
DEFAULT_RUN_ROOT = STUDY_DIR / "runs"
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_QUOTA_LIMIT = 500
DEFAULT_MAX_CALLS = 480
DEFAULT_ESTIMATED_CALLS = 22


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def next_full_hour(now: datetime) -> datetime:
    rounded = now.replace(minute=0, second=0, microsecond=0)
    if now == rounded:
        return rounded
    return rounded + timedelta(hours=1)


def time_block(hour: int) -> str:
    if hour < 6:
        return "night"
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "evening"


def quota_window_start(dt: datetime, reset_hour: int = 9) -> str:
    reset = dt.replace(hour=reset_hour, minute=0, second=0, microsecond=0)
    if dt < reset:
        return (dt.date() - timedelta(days=1)).isoformat()
    return dt.date().isoformat()


def generate_schedule(start_at: datetime, hours: int, timezone_name: str) -> dict[str, Any]:
    runs = []
    for idx in range(hours):
        planned = start_at + timedelta(hours=idx)
        runs.append(
            {
                "run_id": f"hour{planned.hour:02d}",
                "repeat": 1,
                "time_block": time_block(planned.hour),
                "planned_local_time": planned.strftime("%H:%M"),
                "planned_date": planned.date().isoformat(),
                "quota_window_start_date": quota_window_start(planned),
            }
        )
    return {
        "schema_version": "gemini_time_of_day_schedule_session_v1",
        "timezone": timezone_name,
        "cadence_minutes": 60,
        "quota_policy": {
            "active_daily_limit_requests": DEFAULT_QUOTA_LIMIT,
            "active_model": "gemini-3.1-flash-lite",
            "quota_source": "User-confirmed AI Studio active limit on 2026-06-08",
            "estimated_requests_per_10_paper_batch": DEFAULT_ESTIMATED_CALLS,
            "estimated_total_24_hour_requests": DEFAULT_ESTIMATED_CALLS * hours,
            "max_requests_per_quota_window": DEFAULT_MAX_CALLS,
        },
        "policy": {
            "same_pmids_every_run": True,
            "skip_if_previous_batch_running": True,
            "run_hourly_when_quota_headroom_allows": True,
        },
        "runs": runs,
    }


def quota_snapshot(run_id: str, planned: dict[str, Any], captured_by: str) -> dict[str, Any]:
    return {
        "captured_at": datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds"),
        "captured_by": captured_by,
        "google_project": "",
        "api_key_label": "",
        "model": "gemini-3.1-flash-lite",
        "tier": "free",
        "limits_source": {
            "rate_limits_url": "https://ai.google.dev/gemini-api/docs/rate-limits",
            "pricing_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "notes": "AI Studio showed 500 RPD for this model before the study.",
        },
        "observed_limits": {
            "rpm": None,
            "tpm": None,
            "rpd": DEFAULT_QUOTA_LIMIT,
            "daily_reset": "midnight Pacific time",
        },
        "run_id": run_id,
        "planned_date": planned.get("planned_date", ""),
        "planned_local_time": planned.get("planned_local_time", ""),
        "notes": "",
    }


def append_log(path: Path, message: str) -> None:
    timestamp = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {message}\n")
        fh.flush()


def read_manifest(session_dir: Path, run_id: str) -> dict[str, Any]:
    manifest_path = session_dir / run_id / "study_run.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def compact_manifest_line(manifest: dict[str, Any]) -> str:
    batch = manifest.get("batch", {})
    return (
        "result "
        f"run_id={manifest.get('run_id', '')} "
        f"started={manifest.get('started_at', '')} "
        f"ended={manifest.get('ended_at', '')} "
        f"runtime_s={manifest.get('runtime_seconds', 0)} "
        f"completed={batch.get('completed_papers', 0)}/{batch.get('total_papers', 0)} "
        f"calls={batch.get('gemini_api_calls', 0)} "
        f"quota_rows={batch.get('quota_limited_rows', 0)} "
        f"unavailable={batch.get('model_unavailable_count', 0)} "
        f"timeouts={batch.get('timeout_count', 0)} "
        f"rows={batch.get('output_rows', 0)}"
    )


def completion_rate(manifest: dict[str, Any]) -> float:
    batch = manifest.get("batch", {})
    total = int(batch.get("total_papers", 0) or 0)
    if total <= 0:
        return 0.0
    return float(batch.get("completed_papers", 0) or 0) / float(total)


def run_command(command: list[str], env: dict[str, str], log_path: Path) -> int:
    append_log(log_path, "command " + " ".join(command))
    with log_path.open("a", encoding="utf-8") as log_fh:
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
        for line in proc.stdout:
            log_fh.write(line)
            log_fh.flush()
            print(line, end="", flush=True)
        return proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--timezone", default="Europe/Warsaw")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--max-runtime-seconds", type=int, default=7200)
    parser.add_argument("--max-gemini-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--late-grace-minutes", type=int, default=10)
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument("--captured-by", default="WSL hourly driver")
    args = parser.parse_args()

    timezone = ZoneInfo(args.timezone)
    env = os.environ.copy()
    env.update(load_env_file(args.env_file))
    if not env.get("GEMINI_API_KEY"):
        raise SystemExit(f"GEMINI_API_KEY is missing. Add it to {args.env_file}.")
    if not env.get("ENTREZ_EMAIL"):
        raise SystemExit(f"ENTREZ_EMAIL is missing. Add it to {args.env_file}.")

    start_at = next_full_hour(datetime.now(timezone))
    session_id = args.session_id or f"session_{start_at.strftime('%Y%m%d_%H%M')}"
    session_dir = args.run_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "driver.log"
    schedule_path = session_dir / "schedule.json"
    schedule = generate_schedule(start_at, args.hours, args.timezone)
    write_json(schedule_path, schedule)

    append_log(log_path, f"session_start id={session_id} start_at={start_at.isoformat(timespec='minutes')}")
    append_log(log_path, f"env_file={args.env_file} run_root={session_dir}")

    cumulative_calls = 0
    calls_by_quota_window: dict[str, int] = {}
    completed_runs = 0
    consecutive_failures = 0
    session_records: list[dict[str, Any]] = []

    for planned in schedule["runs"]:
        run_id = planned["run_id"]
        planned_at = datetime.fromisoformat(
            f"{planned['planned_date']}T{planned['planned_local_time']}:00"
        ).replace(tzinfo=timezone)
        now = datetime.now(timezone)
        quota_window = str(planned.get("quota_window_start_date") or "")
        window_calls = calls_by_quota_window.get(quota_window, 0)
        projected_next_calls = (
            max(DEFAULT_ESTIMATED_CALLS, round(cumulative_calls / completed_runs))
            if completed_runs
            else DEFAULT_ESTIMATED_CALLS
        )
        if window_calls + projected_next_calls > args.max_gemini_calls:
            append_log(
                log_path,
                "skip "
                f"run_id={run_id} reason=quota_window_headroom "
                f"quota_window={quota_window} window_calls={window_calls} "
                f"projected_next={projected_next_calls}",
            )
            session_records.append(
                {
                    "run_id": run_id,
                    "status": "skipped_call_headroom",
                    "quota_window_start_date": quota_window,
                    "window_calls": window_calls,
                    "projected_next_calls": projected_next_calls,
                }
            )
            continue
        if now > planned_at + timedelta(minutes=args.late_grace_minutes):
            append_log(log_path, f"skip run_id={run_id} reason=late planned={planned_at.isoformat(timespec='minutes')}")
            session_records.append({"run_id": run_id, "status": "skipped_late", "planned_at": planned_at.isoformat()})
            continue
        if now < planned_at:
            sleep_seconds = (planned_at - now).total_seconds()
            append_log(log_path, f"sleep run_id={run_id} seconds={int(sleep_seconds)}")
            time.sleep(sleep_seconds)

        snapshot_path = session_dir / f"{run_id}_quota_snapshot.json"
        write_json(snapshot_path, quota_snapshot(run_id, planned, args.captured_by))
        append_log(log_path, f"start run_id={run_id}")
        rc = run_command(
            [
                sys.executable,
                str(RUN_STUDY),
                "--run-id",
                run_id,
                "--schedule",
                str(schedule_path),
                "--output-root",
                str(session_dir),
                "--quota-snapshot",
                str(snapshot_path),
                "--max-runtime-seconds",
                str(args.max_runtime_seconds),
            ],
            env,
            log_path,
        )
        manifest = read_manifest(session_dir, run_id)
        if manifest:
            append_log(log_path, compact_manifest_line(manifest))
            batch = manifest.get("batch", {})
            run_calls = int(batch.get("gemini_api_calls", 0) or 0)
            cumulative_calls += run_calls
            calls_by_quota_window[quota_window] = calls_by_quota_window.get(quota_window, 0) + run_calls
            completed_runs += 1
            if int(batch.get("quota_limited_rows", 0) or 0) > 0:
                append_log(log_path, f"stop reason=quota_limited run_id={run_id}")
                session_records.append({"run_id": run_id, "status": "quota_limited", "return_code": rc})
                break
            failure = rc != 0 or completion_rate(manifest) < 0.7
        else:
            append_log(log_path, f"missing_manifest run_id={run_id} return_code={rc}")
            failure = True
        consecutive_failures = consecutive_failures + 1 if failure else 0
        session_records.append({"run_id": run_id, "status": "finished", "return_code": rc})
        if consecutive_failures >= args.max_consecutive_failures:
            append_log(log_path, f"stop reason=consecutive_failures count={consecutive_failures}")
            break

    report_dir = session_dir / "reports"
    run_command(
        [
            sys.executable,
            str(ANALYZE_RESULTS),
            "--run-root",
            str(session_dir),
            "--report-dir",
            str(report_dir),
        ],
        env,
        log_path,
    )
    write_json(
        session_dir / "session_summary.json",
        {
            "session_id": session_id,
            "session_dir": str(session_dir),
            "schedule_path": str(schedule_path),
            "cumulative_gemini_calls": cumulative_calls,
            "calls_by_quota_window": calls_by_quota_window,
            "completed_runs": completed_runs,
            "records": session_records,
            "report_dir": str(report_dir),
        },
    )
    append_log(log_path, f"session_done completed_runs={completed_runs} cumulative_calls={cumulative_calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
