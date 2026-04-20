#!/usr/bin/env bash
# Linux launcher. Make executable with `chmod +x start.sh`, then run it.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

cd "$REPO_ROOT"

PY="python3"
if [ -x "pipeline/.venv/bin/python" ]; then
    PY="pipeline/.venv/bin/python"
fi

# Try common "open URL" commands on Linux
(sleep 2 && (xdg-open "http://localhost:8765/" 2>/dev/null || sensible-browser "http://localhost:8765/" 2>/dev/null || true)) &

exec "$PY" publication/figures/pipeline-viewer/serve.py
