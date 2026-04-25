#!/bin/bash
set -euo pipefail

# Only run in Claude Code remote (web) sessions
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

echo "[session-start] Installing JS dependencies..."
cd "$PROJECT_DIR"
npm install

echo "[session-start] Setting up Python venv..."
cd "$PROJECT_DIR/python"
python3 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt

echo "[session-start] Done."
