---
allowed-tools: Read, Edit, Write
description: Capture session learnings into memory files and AUDIT.md
---

## Context

- Today's date: !`date +%Y-%m-%d`
- Files changed this session: !`git diff HEAD --name-only 2>/dev/null || git status --short`
- Pipeline modules touched: !`git diff HEAD --name-only 2>/dev/null | grep -E "^pipeline/|^app/src/main/" || echo "none"`

## Your task

Review what happened this session and update memory files **now**:

1. **Decisions made** → append to `.claude/rules/memory-decisions.md` with today's date.
   Use format: `## YYYY-MM-DD — [short title]` followed by Decision/Rationale/Files.

2. **Preferences confirmed or established** → update `.claude/rules/memory-preferences.md`.

3. **Project facts learned** (new API, new constraint, clarification from user) → update `.claude/rules/memory-profile.md`.

4. **Pipeline module changes** → update `AUDIT.md`.
   - Bug fixed → add to Fixed section as `FN: description | impact | files | fix`
   - Tradeoff accepted → add to Warnings section as `WN: description | risk | mitigation`
   - Keep the Audit Maintenance Protocol at the bottom of AUDIT.md in sync.

5. **Session summary** → prepend to `.claude/rules/memory-sessions.md` (newest at top).
   Format: `## YYYY-MM-DD — [one-line summary]` + Done/Context/Next bullets.

Then summarize what was captured in 3–5 bullet points.

**Skip:** trivial questions, no-op sessions, sessions with no new information.
