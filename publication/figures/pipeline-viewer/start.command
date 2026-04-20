#!/usr/bin/env bash
# Double-click this file in Finder to launch the pipeline viewer's live server.
# macOS will open it in Terminal and run the commands below.
#
# What this does:
#   1. cd to the pipeline-viewer folder
#   2. cd up to the repo root
#   3. run `python pipeline/run_pipeline.py`'s companion viewer server
#   4. open your browser at http://localhost:8765/
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "→ Pipeline Viewer launcher"
echo "  script dir: $SCRIPT_DIR"
echo "  repo root:  $REPO_ROOT"
echo

cd "$REPO_ROOT"

# Prefer the pipeline venv if it exists, else system python3
PY="python3"
if [ -x "pipeline/.venv/bin/python" ]; then
    PY="pipeline/.venv/bin/python"
    echo "→ Using pipeline/.venv interpreter"
fi

# Open the browser in 2 seconds (after the server has started)
(sleep 2 && open "http://localhost:8765/") &

exec "$PY" publication/figures/pipeline-viewer/serve.py
