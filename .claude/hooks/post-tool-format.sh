#!/bin/bash
# PostToolUse hook: auto-format Python files after Write/Edit
# Uses jq to parse tool input (cleaner than Python subprocess)

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null)

[[ -z "$FILE" || "$FILE" == "null" ]] && exit 0
[[ "$FILE" != *.py ]] && exit 0

RUFF="$CLAUDE_PROJECT_DIR/python/.venv/bin/ruff"
[ -f "$RUFF" ] && "$RUFF" format "$FILE" 2>/dev/null || true
