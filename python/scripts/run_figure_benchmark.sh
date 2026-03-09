#!/bin/bash
# Wrapper for figure extraction benchmark with API key rotation.
# Primary key tried first; if it fails mid-run, re-run with the fallback key.
#
# Usage: bash scripts/run_figure_benchmark.sh [--runs N] [--skip-run] [--verbose]

set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate

PRIMARY_KEY="AIzaSyDY0oxBSzTuC7XF_siX00b3FlpdD53MKKk"
FALLBACK_KEY="AIzaSyABCKX7zSv5VRJno4ITHsKVtYRxHbRI8ac"
EMAIL="michal.uppal@gmail.com"

echo "=== Figure Benchmark — using primary key ==="
GEMINI_API_KEY="$PRIMARY_KEY" ENTREZ_EMAIL="$EMAIL" \
  python scripts/figure_extraction_benchmark.py "$@" && exit 0

echo "=== Primary key failed — retrying with fallback key ==="
GEMINI_API_KEY="$FALLBACK_KEY" ENTREZ_EMAIL="$EMAIL" \
  python scripts/figure_extraction_benchmark.py --skip-run "$@"
