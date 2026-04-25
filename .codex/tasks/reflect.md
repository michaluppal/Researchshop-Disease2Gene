# Reflect Recipe

Use at the end of any substantive session. Skip trivial questions, no-op sessions, and sessions with no new information.

## Gather Context

- Date: `date +%Y-%m-%d`
- Changed files: `git diff HEAD --name-only` or `git status --short`
- Pipeline-related changes: files under `pipeline/` or `app/src/main/`

## Update Memory

1. Decisions made: append to `.codex/rules/memory-decisions.md` using `## YYYY-MM-DD - [short title]`, then Decision/Rationale/Files.
2. Preferences confirmed or established: update `.codex/rules/memory-preferences.md`.
3. Project facts learned: update `.codex/rules/memory-profile.md`.
4. Pipeline module changes: update `docs/audit/AUDIT.md`.
   - Bug fixed: add fixed-entry details with impact, files, and fix.
   - Tradeoff accepted: add warning-entry details with risk and mitigation.
   - Keep the audit maintenance protocol in sync.
5. Session summary: prepend to `.codex/rules/memory-sessions.md` with Done/Context/Next bullets.

Finish by summarizing what was captured in 3-5 bullets.
