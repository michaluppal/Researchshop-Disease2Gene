#!/usr/bin/env python3
"""Live mode server for the pipeline viewer.

Serves the static HTML/JSON and adds two dynamic endpoints:

- ``POST /run``        Start the pipeline on a single PMID (only one run at a
                       time; new runs are rejected with 409 while one is active).
- ``GET  /events``     Server-Sent Events stream of trace events from the
                       active run, plus synthesised ``pipeline/started``,
                       ``pipeline/finished``, ``pipeline/error`` markers.
- ``GET  /status``     JSON status snapshot (is a run active, which PMID).
- ``GET  /<file>``     Static files served from this directory.

Dependencies: Python 3.9+ stdlib only. No Flask, no Tornado, no websockets.

Usage::

    python publication/figures/pipeline-viewer/serve.py [--port 8765]

Then open http://localhost:8765/ in a browser.

Secrets (``GEMINI_API_KEY``, ``ENTREZ_EMAIL``) must be set in the environment
where you run this server — they are inherited by the pipeline subprocess.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent  # publication/figures/pipeline-viewer/ → repo root


# ──────────────────────────────────────────────────────────────────────────────
# Shared run state
# ──────────────────────────────────────────────────────────────────────────────
class RunState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = False
        self.pmid: Optional[str] = None
        self.subscribers: list[queue.Queue] = []
        self.subscribers_lock = threading.Lock()
        self.worker_thread: Optional[threading.Thread] = None
        self.tail_thread: Optional[threading.Thread] = None
        self.live_path: Optional[Path] = None
        self.started_at: Optional[float] = None

    def publish(self, event: dict) -> None:
        # If the subscriber's queue is full we do NOT drop the subscriber — that
        # permanently disconnects the browser and it has no way to recover. Instead
        # we treat full-queue as back-pressure: we short-block with a small timeout,
        # then if still full, drop the *event* (preferring to lose a fn_call over
        # losing the whole stream). Stage events and pipeline/* control events
        # always get a longer timeout so they're never silently lost.
        with self.subscribers_lock:
            subs = list(self.subscribers)
        is_critical = event.get("type") in ("pipeline/started", "pipeline/finished", "pipeline/error", "pipeline/result")
        timeout = 2.0 if is_critical else 0.05
        for q in subs:
            try:
                q.put(event, timeout=timeout)
            except queue.Full:
                # Keep the subscriber — just lose this one event.
                pass

    def subscribe(self) -> queue.Queue:
        # Function tracing can emit ~5000 events in a few seconds. With the old
        # 1000-cap queue the subscriber was dropped on overflow, which explains
        # why the browser never received pipeline/finished. 20000 is safe headroom
        # above the tracer's own 5000-event cap.
        q: queue.Queue = queue.Queue(maxsize=20000)
        with self.subscribers_lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.subscribers_lock:
            if q in self.subscribers:
                self.subscribers.remove(q)


STATE = RunState()


# ──────────────────────────────────────────────────────────────────────────────
# In-memory secret config
# ──────────────────────────────────────────────────────────────────────────────
# Keys are only ever held in this process's memory. They are never written to
# disk and never echoed back over the API — the UI only sees a "has it been set?"
# boolean for the API key. Email is lower-sensitivity so we do echo it back so
# the UI can pre-fill its input.
CONFIG_LOCK = threading.Lock()
CONFIG = {
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
    "ENTREZ_EMAIL":   os.environ.get("ENTREZ_EMAIL", ""),
    # Remember whether each value came from the env so the UI can show the
    # source ("set from environment" vs "set from UI") without exposing values.
    "_api_source":    "env" if os.environ.get("GEMINI_API_KEY") else None,
    "_email_source":  "env" if os.environ.get("ENTREZ_EMAIL")   else None,
}


def get_config_snapshot() -> dict:
    """Return a UI-safe view of the current config (never exposes the API key)."""
    with CONFIG_LOCK:
        return {
            "has_api_key":   bool(CONFIG["GEMINI_API_KEY"]),
            "api_key_source": CONFIG["_api_source"],
            "email":         CONFIG["ENTREZ_EMAIL"],
            "email_source":  CONFIG["_email_source"],
        }


def update_config(api_key: Optional[str], email: Optional[str]) -> None:
    with CONFIG_LOCK:
        # Empty string "" means "leave unchanged"; None means "clear".
        if api_key is not None:
            if api_key == "":
                pass  # leave unchanged (the UI sends "" for "no edit")
            else:
                CONFIG["GEMINI_API_KEY"] = api_key
                CONFIG["_api_source"] = "ui"
        if email is not None:
            if email == "" and CONFIG["ENTREZ_EMAIL"]:
                # Treat "" as clear for email (only field where that's meaningful)
                CONFIG["ENTREZ_EMAIL"] = ""
                CONFIG["_email_source"] = None
            elif email:
                CONFIG["ENTREZ_EMAIL"] = email
                CONFIG["_email_source"] = "ui"


def clear_config(field: str) -> None:
    """Clear one stored value."""
    with CONFIG_LOCK:
        if field == "api_key":
            CONFIG["GEMINI_API_KEY"] = ""
            CONFIG["_api_source"] = None
        elif field == "email":
            CONFIG["ENTREZ_EMAIL"] = ""
            CONFIG["_email_source"] = None


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline runner
# ──────────────────────────────────────────────────────────────────────────────
def tail_live_file(path: Path, stop_event: threading.Event) -> None:
    """Follow *path* line-by-line and publish each trace event via SSE."""
    last_size = 0
    while not stop_event.is_set():
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    f.seek(last_size)
                    new = f.read()
                    last_size = f.tell()
                if new:
                    for line in new.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        STATE.publish({"type": "trace", "event": event})
        except Exception:
            pass
        time.sleep(0.1)


def run_pipeline(pmid: str, output_dir: Path, columns_json: str, trace_functions: bool = False) -> None:
    """Spawn the pipeline subprocess and stream its stdout lines as events."""
    STATE.live_path = output_dir / "live_events.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    # Fresh file per run
    STATE.live_path.unlink(missing_ok=True)

    # Start the tail thread
    stop_tail = threading.Event()
    STATE.tail_thread = threading.Thread(
        target=tail_live_file, args=(STATE.live_path, stop_tail), daemon=True
    )
    STATE.tail_thread.start()

    # Locate run_pipeline.py
    run_script = REPO_ROOT / "pipeline" / "run_pipeline.py"
    if not run_script.exists():
        STATE.publish({"type": "pipeline/error", "error": f"run_pipeline.py not found at {run_script}"})
        _finish(stop_tail)
        return

    # Resolve secrets: in-memory CONFIG (set via /config endpoint) takes
    # precedence over env, which itself was seeded from env at startup.
    env = os.environ.copy()
    with CONFIG_LOCK:
        api_key = CONFIG["GEMINI_API_KEY"]
        email   = CONFIG["ENTREZ_EMAIL"]
    if api_key:
        env["GEMINI_API_KEY"] = api_key
    if email:
        env["ENTREZ_EMAIL"] = email
    missing = [k for k in ("GEMINI_API_KEY", "ENTREZ_EMAIL") if not env.get(k)]
    if missing:
        STATE.publish({
            "type": "pipeline/error",
            "error": f"Missing secrets: {', '.join(missing)}. Set them in the Settings panel.",
        })
        _finish(stop_tail)
        return

    env["TRACE_PMID"] = pmid
    env["TRACE_LIVE_FILE"] = str(STATE.live_path)

    # Prefer the pipeline's own venv interpreter if one exists — it's the only
    # Python with pandas, biopython, google-genai, etc. installed. Fall back to
    # the server's own interpreter (which, for static-mode users running
    # stdlib-only code, won't actually need those deps).
    pipeline_venv = REPO_ROOT / "pipeline" / ".venv" / "bin" / "python"
    python_bin = str(pipeline_venv) if pipeline_venv.exists() else sys.executable

    args = [
        python_bin,
        str(run_script),
        "--query", "",
        "--pmids", json.dumps([pmid]),
        "--authors", "[]",
        "--columns", columns_json,
        "--top-n", "1",
        "--output-dir", str(output_dir),
        "--trace-pmid", pmid,
    ]
    if trace_functions:
        args.append("--trace-functions")

    STATE.publish({"type": "pipeline/started", "pmid": pmid, "command": " ".join(shlex.quote(a) for a in args)})

    try:
        proc = subprocess.Popen(
            args,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout or []:
            line = line.rstrip("\n")
            # Parse the existing IPC protocol lines (PROGRESS:, LOG:, RESULT:)
            if line.startswith("PROGRESS:"):
                try:
                    STATE.publish({"type": "progress", "data": json.loads(line[len("PROGRESS:"):])})
                except Exception:
                    STATE.publish({"type": "log", "level": "info", "msg": line})
            elif line.startswith("LOG:"):
                try:
                    STATE.publish({"type": "log", **json.loads(line[len("LOG:"):])})
                except Exception:
                    STATE.publish({"type": "log", "level": "info", "msg": line})
            elif line.startswith("RESULT:"):
                try:
                    STATE.publish({"type": "pipeline/result", "data": json.loads(line[len("RESULT:"):])})
                except Exception:
                    STATE.publish({"type": "log", "level": "warn", "msg": line})
            else:
                STATE.publish({"type": "log", "level": "info", "msg": line})
        rc = proc.wait()
        # Give the tailer one last chance to catch any trailing writes before we stop it.
        time.sleep(0.3)
        STATE.publish({"type": "pipeline/finished", "pmid": pmid, "returncode": rc})
    except Exception as exc:
        STATE.publish({"type": "pipeline/error", "error": str(exc)})
    finally:
        _finish(stop_tail)


def _finish(stop_tail: threading.Event) -> None:
    stop_tail.set()
    with STATE.lock:
        STATE.active = False
        STATE.pmid = None
        STATE.started_at = None


# ──────────────────────────────────────────────────────────────────────────────
# HTTP server
# ──────────────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        # Keep server output quiet — we're serving a single user
        return

    # ---- static files ----
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/events":
            self._serve_sse()
            return
        if path == "/status":
            self._serve_status()
            return
        if path == "/config":
            self._json(HTTPStatus.OK, get_config_snapshot())
            return
        if path == "/" or path == "":
            path = "/index.html"
        fs_path = (HERE / path.lstrip("/")).resolve()
        try:
            fs_path.relative_to(HERE)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not fs_path.exists() or not fs_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = fs_path.read_bytes()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js":   "application/javascript; charset=utf-8",
            ".css":  "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".md":   "text/markdown; charset=utf-8",
            ".svg":  "image/svg+xml",
            ".png":  "image/png",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(fs_path.suffix.lower(), "application/octet-stream")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    # ---- run / config ----
    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/config":
            self._handle_post_config()
            return
        if path != "/run":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON body"})
            return
        pmid = str(data.get("pmid") or "").strip()
        columns = data.get("columns") or {
            "Key Finding": "Primary genetic or molecular finding about the gene",
            "Disease Association": "Associated condition, phenotype, or clinical context",
        }
        output_dir_raw = data.get("output_dir") or (HERE / "live_runs")
        output_dir = Path(output_dir_raw) / f"run_{pmid}_{int(time.time())}"

        if not pmid or not pmid.isdigit():
            self._json(HTTPStatus.BAD_REQUEST, {"error": "pmid must be a numeric PubMed ID"})
            return

        with STATE.lock:
            if STATE.active:
                self._json(HTTPStatus.CONFLICT, {
                    "error": "a run is already active",
                    "pmid": STATE.pmid,
                })
                return
            STATE.active = True
            STATE.pmid = pmid
            STATE.started_at = time.time()

        columns_json = json.dumps(columns, ensure_ascii=False)
        trace_functions = bool(data.get("trace_functions"))
        STATE.worker_thread = threading.Thread(
            target=run_pipeline, args=(pmid, output_dir, columns_json, trace_functions), daemon=True,
        )
        STATE.worker_thread.start()
        self._json(HTTPStatus.ACCEPTED, {"status": "started", "pmid": pmid, "output_dir": str(output_dir)})

    def _handle_post_config(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON body"})
            return

        action = data.get("action") or "set"
        if action == "clear":
            field = data.get("field")
            if field not in ("api_key", "email"):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "field must be 'api_key' or 'email'"})
                return
            clear_config(field)
            self._json(HTTPStatus.OK, {"status": "cleared", "field": field, **get_config_snapshot()})
            return

        # action == "set"
        api_key = data.get("api_key")
        email   = data.get("email")

        # Loose validation: don't attempt to check Gemini key format (Google
        # doesn't publish one), but refuse obviously malformed emails.
        if email is not None and email != "" and ("@" not in email or "." not in email.split("@")[-1]):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "email does not look valid"})
            return
        if api_key is not None and api_key != "" and len(api_key) < 10:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "API key is too short to be real"})
            return

        update_config(api_key, email)
        self._json(HTTPStatus.OK, {"status": "ok", **get_config_snapshot()})

    # ---- helpers ----
    def _json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_status(self) -> None:
        with STATE.lock:
            payload = {"active": STATE.active, "pmid": STATE.pmid, "started_at": STATE.started_at}
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # CORS: allow a file:// or other-origin static viewer to poll /status for readiness.
        # Scope is intentionally narrow — only /status — so the rest of the API (run, config,
        # events) stays same-origin and can't be hit from a hostile page the user is viewing.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        q = STATE.subscribe()
        # Send an initial status so the client can resync
        with STATE.lock:
            hello = {"type": "hello", "active": STATE.active, "pmid": STATE.pmid}
        try:
            self._send_event(hello)
            while True:
                try:
                    event = q.get(timeout=20)
                except queue.Empty:
                    # heartbeat to keep the connection alive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                if not self._send_event(event):
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            STATE.unsubscribe(q)

    def _send_event(self, event: dict) -> bool:
        try:
            payload = json.dumps(event, ensure_ascii=False, default=str)
            self.wfile.write(b"data: " + payload.encode("utf-8") + b"\n\n")
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Pipeline viewer live mode → http://{args.host}:{args.port}/")
    print(f"Repo root: {REPO_ROOT}")
    snap = get_config_snapshot()
    print("Secrets:")
    print(f"  GEMINI_API_KEY: {'set from ' + snap['api_key_source'] if snap['has_api_key'] else 'NOT SET — configure via Settings in the UI'}")
    print(f"  ENTREZ_EMAIL:   {'set from ' + snap['email_source'] if snap['email'] else 'NOT SET — configure via Settings in the UI'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
