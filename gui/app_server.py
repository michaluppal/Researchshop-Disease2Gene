#!/usr/bin/env python3
"""Disease2Gene — Lightweight local web GUI.

Usage:
    pip install flask
    python3 gui/app_server.py

Opens http://localhost:8050 in your default browser.
"""

import json, os, sys, threading, time, queue, logging, webbrowser, re
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, request, jsonify, Response, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")

# ── Config persistence ───────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".disease2gene"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    except Exception:
        return {}


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ── Pipeline state ───────────────────────────────────────────────────
pipeline_state = {
    "running": False,
    "stage": "",
    "logs": [],
    "result": None,
    "error": None,
}
log_queue = queue.Queue()
stop_flag = threading.Event()


# ── Routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
def set_config():
    cfg = load_config()
    cfg.update(request.json)
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/pubmed/count", methods=["GET"])
def pubmed_count():
    """Get count of papers matching a PubMed query."""
    import urllib.request, urllib.parse
    q = request.args.get("query", "")
    if not q:
        return jsonify({"count": 0})
    try:
        url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={urllib.parse.quote(q)}&retmax=0&retmode=json"
        )
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        count = int(data.get("esearchresult", {}).get("count", 0))
        return jsonify({"count": count, "query": q})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pubmed/resolve", methods=["POST"])
def pubmed_resolve():
    """Resolve PMIDs to titles via NCBI eSummary."""
    import urllib.request
    pmids = request.json.get("pmids", [])
    if not pmids:
        return jsonify({"papers": []})
    try:
        batch = ",".join(pmids[:100])
        url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            f"?db=pubmed&id={batch}&retmode=json"
        )
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read())
        result = data.get("result", {})
        papers = []
        for pmid in pmids:
            if pmid in result and isinstance(result[pmid], dict):
                papers.append({
                    "pmid": pmid,
                    "title": result[pmid].get("title", ""),
                    "authors": ", ".join(
                        a.get("name", "") for a in result[pmid].get("authors", [])[:3]
                    ),
                    "year": result[pmid].get("pubdate", "")[:4],
                    "journal": result[pmid].get("fulljournalname", ""),
                })
        return jsonify({"papers": papers})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pubmed/author", methods=["GET"])
def pubmed_author_search():
    """Search PubMed for papers by an author."""
    import urllib.request, urllib.parse
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"papers": []})
    try:
        # Pass name directly — PubMed handles "LastName Initial" natively
        author_q = f"{name}[au]"

        # Search
        url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={urllib.parse.quote(author_q)}&retmax=25&retmode=json&sort=date"
        )
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        pmids = data.get("esearchresult", {}).get("idlist", [])
        total = int(data.get("esearchresult", {}).get("count", 0))

        if not pmids:
            return jsonify({"papers": [], "total": 0})

        # Resolve
        batch = ",".join(pmids)
        url2 = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            f"?db=pubmed&id={batch}&retmode=json"
        )
        with urllib.request.urlopen(url2, timeout=15) as resp2:
            summ = json.loads(resp2.read())
        result = summ.get("result", {})
        papers = []
        for pmid in pmids:
            if pmid in result and isinstance(result[pmid], dict):
                papers.append({
                    "pmid": pmid,
                    "title": result[pmid].get("title", f"PMID:{pmid}"),
                    "year": result[pmid].get("pubdate", "")[:4],
                    "journal": result[pmid].get("fulljournalname", ""),
                })
        return jsonify({"papers": papers, "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pubmed/search", methods=["GET"])
def pubmed_search():
    """Search PubMed and return paper details for preview/selection."""
    import urllib.request, urllib.parse
    q = request.args.get("query", "")
    retmax = min(int(request.args.get("retmax", 50)), 200)
    if not q:
        return jsonify({"papers": [], "total": 0})
    try:
        # 1. Search for PMIDs
        url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={urllib.parse.quote(q)}&retmax={retmax}&retmode=json"
        )
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        total = int(data.get("esearchresult", {}).get("count", 0))
        pmids = data.get("esearchresult", {}).get("idlist", [])

        if not pmids:
            return jsonify({"papers": [], "total": total})

        # 2. Fetch summaries
        batch = ",".join(pmids)
        url2 = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            f"?db=pubmed&id={batch}&retmode=json"
        )
        with urllib.request.urlopen(url2, timeout=20) as resp2:
            summ = json.loads(resp2.read())
        result = summ.get("result", {})

        papers = []
        for pmid in pmids:
            if pmid in result and isinstance(result[pmid], dict):
                d = result[pmid]
                authors = [a.get("name", "") for a in d.get("authors", [])[:3]]
                papers.append({
                    "pmid": pmid,
                    "title": d.get("title", f"PMID:{pmid}"),
                    "year": d.get("pubdate", "")[:4],
                    "journal": d.get("fulljournalname", ""),
                    "authors": ", ".join(authors) + (" et al." if len(d.get("authors", [])) > 3 else ""),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}",
                })
        return jsonify({"papers": papers, "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pipeline/run", methods=["POST"])
def run_pipeline():
    """Start the pipeline in a background thread."""
    if pipeline_state["running"]:
        return jsonify({"error": "Pipeline already running"}), 409

    data = request.json
    pipeline_state.update(running=True, stage="starting", logs=[], result=None, error=None)
    stop_flag.clear()

    def execute():
        try:
            _log("Loading pipeline modules...")
            pipeline_state["stage"] = "loading"

            gemini_key = data.get("gemini_key", "")
            email = data.get("email", "")
            os.environ["GEMINI_API_KEY"] = gemini_key
            os.environ["ENTREZ_EMAIL"] = email

            from modules.pipeline_orchestrator import run_complete_pipeline
            from modules import config as cfg
            from Bio import Entrez

            cfg.GEMINI_API_KEY = gemini_key
            cfg.ENTREZ_EMAIL = email
            Entrez.email = email

            query = data.get("query", "").strip()
            pmids = data.get("pmids", [])
            authors = data.get("authors", [])
            columns = data.get("columns", {})

            _log(f"Query: {query or '(none)'}")
            _log(f"Selected PMIDs: {len(pmids)}")
            _log(f"Authors: {authors}")
            _log(f"Columns: {list(columns.keys())}")

            pipeline_state["stage"] = "searching"
            _log("Starting pipeline execution...")

            result = run_complete_pipeline(
                query=query if query else None,
                specific_pmids=pmids,
                specific_authors=authors,
                user_columns=columns,
                top_n_cited=None,  # user already selected papers, no limit
                max_results=len(pmids) + 200 if query else None,
            )

            pipeline_state["stage"] = "done"
            if result:
                pipeline_state["result"] = str(result)
                _log(f"✅ Done! Output: {result}")
            else:
                _log("⚠️ Pipeline finished but no output file produced.")

        except Exception as e:
            import traceback
            pipeline_state["error"] = str(e)
            pipeline_state["stage"] = "error"
            _log(f"❌ Error: {e}")
            _log(traceback.format_exc())
        finally:
            pipeline_state["running"] = False

    threading.Thread(target=execute, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/pipeline/status", methods=["GET"])
def pipeline_status():
    return jsonify({
        "running": pipeline_state["running"],
        "stage": pipeline_state["stage"],
        "result": pipeline_state["result"],
        "error": pipeline_state["error"],
    })


@app.route("/api/pipeline/logs", methods=["GET"])
def pipeline_logs():
    """SSE stream of pipeline logs."""
    def stream():
        idx = 0
        while True:
            while idx < len(pipeline_state["logs"]):
                msg = pipeline_state["logs"][idx]
                yield f"data: {json.dumps({'log': msg})}\n\n"
                idx += 1
            if not pipeline_state["running"] and idx >= len(pipeline_state["logs"]):
                yield f"data: {json.dumps({'done': True, 'result': pipeline_state['result'], 'error': pipeline_state['error']})}\n\n"
                break
            time.sleep(0.3)

    return Response(stream(), mimetype="text/event-stream")


@app.route("/api/pipeline/stop", methods=["POST"])
def stop_pipeline():
    stop_flag.set()
    pipeline_state["running"] = False
    _log("⏹ Stop requested.")
    return jsonify({"ok": True})


def _log(msg):
    pipeline_state["logs"].append(msg)


# ── Redirect pipeline logging to our log list ────────────────────────
class PipelineLogHandler(logging.Handler):
    def emit(self, record):
        _log(self.format(record))


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Capture pipeline logs
    handler = PipelineLogHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    port = int(os.environ.get("PORT", 8050))
    url = f"http://localhost:{port}"

    # Open browser after a short delay
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    print(f"\n  🧬 Disease2Gene is running at {url}\n")
    app.run(host="127.0.0.1", port=port, debug=False)
