# memory-preferences.md — Coding Preferences

> Codex migration note (2026-04-25): this is the active preference memory for Codex sessions.
> Historical Claude-era wording may remain where it describes old sessions.

> Preferences established during sessions. Update when new ones are confirmed.

---

## Python

- **Style:** Google-style docstrings for all public functions in pipeline modules
- **Types:** Type hints throughout; use `dataclasses` for structured data (not dicts)
- **Formatting:** `ruff` for lint + format (preferred over flake8+black — one tool)
- **Testing:** `pytest` with fixtures for cached API responses (offline tests, no real API calls)
- **Imports:** stdlib → third-party → local, separated by blank lines
- **Logging:** Use the `log_callback` mechanism (emits `LOG:{json}` to stdout); never `print()` in pipeline code
- **No over-engineering:** Don't abstract until there are ≥3 concrete use cases

## TypeScript / React

- **Strict mode on** — both `config/tsconfig.web.json` and `config/tsconfig.node.json`
- **Functional components only** — no class components
- **Path alias:** `@/*` maps to `app/src/renderer/*`
- **Tailwind** for all styling — no inline styles, no CSS modules
- **IPC pattern:** renderer calls `window.api.*` (preload bridge), never directly imports Electron

## General

- **Edit existing files** over creating new ones
- **Minimum complexity** — if 3 lines of code solve it, don't write a helper
- **No backwards-compat shims** — if something is unused, delete it
- **`docs/audit/AUDIT.md` stays synchronized** — pipeline changes always update the audit log
- **Commit style:** imperative mood, ≤72 chars subject, explain *why* not *what*

## SoftwareX Paper Preferences

- Code must be independently reproducible (cached fixtures for tests)
- Benchmark results should be deterministic (fix seeds where applicable)
- All public functions need docstrings before paper submission
- Examples in `examples/` should be Jupyter notebooks, not scripts
