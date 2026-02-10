#!/bin/bash
# Disease2Gene — One-click launcher for macOS/Linux
# Double-click this file or run: bash start.sh

set -e
cd "$(dirname "$0")"

echo ""
echo "  🧬 Disease2Gene — Research Pipeline"
echo "  ════════════════════════════════════"
echo ""

# Check Python
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo "  ❌ Python not found!"
    echo ""
    echo "  Please install Python 3.8+ from https://www.python.org/downloads/"
    echo "  Then run this script again."
    echo ""
    read -p "  Press Enter to exit..."
    exit 1
fi

echo "  ✓ Using $($PY --version)"

# Install dependencies (only if needed)
echo "  📦 Checking dependencies..."
$PY -m pip install -q -r requirements.txt 2>/dev/null || {
    echo "  📦 Installing dependencies (first run only)..."
    $PY -m pip install --user -r requirements.txt
}
echo "  ✓ All dependencies installed"
echo ""

# Launch
echo "  🚀 Starting Disease2Gene..."
echo "  → Your browser will open automatically"
echo "  → To stop: press Ctrl+C or close this window"
echo ""
$PY gui/app_server.py
