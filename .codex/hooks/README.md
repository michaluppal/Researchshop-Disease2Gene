# Codex Hook Notes

The Claude Code project previously used automatic hooks, now archived in `archive/claude/hooks/`:

- `session-start.sh` prepared the local JS and Python environments for remote Claude sessions.
- `post-tool-format.sh` attempted to run `ruff format` after Python writes.
- `stop-hook.sh` reminded the agent to update memory files and audit notes at session end.

Those scripts are preserved as legacy reference. This Codex migration intentionally does not enable automatic hooks yet. Treat the behavior as manual workflow guidance:

- Run formatting and tests explicitly from the relevant task recipe in `.codex/tasks/verify.md`.
- Update `.codex/rules/` and `docs/audit/AUDIT.md` during substantive work.
- Do not rely on Claude-specific environment variables such as `CLAUDE_PROJECT_DIR`.

If Codex hook automation is added later, use this file as the compatibility checklist and keep the hooks opt-in until verified on macOS and CI.
