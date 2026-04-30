#!/bin/bash
# Wrapper for figure extraction benchmark.
#
# Usage: bash scripts/run_figure_benchmark.sh [--runs N] [--skip-run] [--verbose]
#
# Required environment:
#   GEMINI_API_KEY   Google Gemini API key
#   ENTREZ_EMAIL     NCBI Entrez email
#
# Optional environment:
#   GEMINI_FALLBACK_API_KEY   retry with this key if the first run fails

set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "ERROR: GEMINI_API_KEY must be set in the environment." >&2
  exit 1
fi

if [[ -z "${ENTREZ_EMAIL:-}" ]]; then
  echo "ERROR: ENTREZ_EMAIL must be set in the environment." >&2
  exit 1
fi

echo "=== Figure Benchmark ==="
python scripts/figure_extraction_benchmark.py "$@" && exit 0

if [[ -n "${GEMINI_FALLBACK_API_KEY:-}" ]]; then
  echo "=== Primary key failed — retrying with fallback key ==="
  GEMINI_API_KEY="$GEMINI_FALLBACK_API_KEY" python scripts/figure_extraction_benchmark.py --skip-run "$@"
fi

exit 1
