# AGENTS.md - ResearchShop Desktop

> This is the active Codex routing file. Keep it compact. Detailed project memory lives in `.codex/rules/`.

## What This Is

Free Electron desktop app for automated biomedical gene/variant extraction from PubMed papers.
Users provide their own Gemini API key. No server. Goal: open-source tool + SoftwareX journal paper.

## Repo Layout

- `app/` - Electron desktop frontend (`app/src/{main,preload,renderer}`, `app/resources/`, `app/scripts/`)
- `pipeline/` - Python backend: modules, scripts, tests, data (HGNC, benchmark, output)
- `docs/` - audit log, roadmap, pipeline references, and generated reference reports
- `publication/` - SoftwareX paper (`main.tex`, `sections/`, `references.bib`, `figures/`, `working/`)
- `.codex/` - Codex rules, task recipes, and hook notes
- `archive/claude/` - legacy Claude Code context kept for history

Build configs live in `config/`. `package.json` scripts pass explicit config paths to Electron Vite, electron-builder, TypeScript, and Vitest. Source is in `app/src/`.

## Key Files

| Layer | File | Purpose |
|---|---|---|
| Entry | `pipeline/run_pipeline.py` | CLI spawned by Electron |
| Orchestration | `pipeline/modules/pipeline_orchestrator.py` | chains all pipeline domains |
| Extraction | `pipeline/modules/paper_analysis/` | Per-paper `candidate_discovery`, `detail_extraction`, `validation`, and evidence gates |
| Validation | `pipeline/modules/gene_validator.py` | HGNC + remote APIs |
| NER | `pipeline/modules/pubtator_tool.py` | high-precision gene NER |
| Config | `pipeline/modules/config.py` | all pipeline feature flags |
| IPC | `app/src/main/python-bridge.ts` | Electron to Python protocol |
| Audit | `docs/audit/AUDIT.md` | source of truth for pipeline quality |

Read before modifying pipeline code: `.codex/rules/memory-pipeline.md`
Full project memory: `.codex/rules/`
Common mistakes log: `.codex/rules/mistakes.md`

## Commands

```bash
# JS
npm install
npm run dev
npx tsc --noEmit -p config/tsconfig.web.json
npx tsc --noEmit -p config/tsconfig.node.json

# Python
cd pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py --help
```

## Non-Negotiables

These constraints exist for scientific accuracy and must not be overridden without explicit user discussion.

- Do not lower confidence thresholds. `FINAL_VALIDATION_MIN_CONFIDENCE=0.7` is a medical accuracy decision, not a performance knob.
- Do not disable pipeline safeguards. Grounding check, deterministic seeding, and strict validation gate are hallucination controls.
- Do not weaken validation logic silently. If a validation rule is relaxed, document it in `docs/audit/AUDIT.md` with reasoning and tradeoff.
- False negatives in `paper_selection` relevance scoring are silent failures. A paper dropped there cannot be recovered.
- Keep `docs/audit/AUDIT.md` synchronized. Any pipeline behavior change requires an audit update.
- Secrets via env vars only. Never pass secrets as CLI args because they can be visible in process listings.
- OA papers only. No paywall bypass and no automated browser scraping for restricted full text.
- No runtime test doubles in committed tests. Prefer pure helper extraction, fixture data, explicit dependency injection for local clients, or clearly marked live/manual tests.
- No over-engineering. Use the minimum complexity for the current task. Replace stale paths instead of adding parallel systems.

## Common Agent Mistakes

The canonical mistakes log lives in `.codex/rules/mistakes.md`. Add to that file when an agent gets something wrong in this codebase so the mistake does not repeat. High-priority reminders:

- Do not normalize only one side of a citation match - normalize both the citation string and paper text before matching. (Caught: 2026-02-25)
- Do not create a static blocklist of clinical abbreviations to suppress false positives - it blocks correct gene extractions across other paper types. (Caught: 2026-02-24, C18 FDA audit)
- Do not test citation validation quality on PMID 34876594 or similar clinical/lab-table papers - valid citation scores are structurally impossible when evidence is table-only. (Caught: 2026-02-25)
- Do not report a single-run citation score as a quality metric - stochastic LLM compliance requires multi-run averaging. (Caught: 2026-02-25)
- Do not assume citation validation is working because it runs without errors - add a smoke test that asserts at least one known-good citation validates true. (Caught: 2026-02-24, C19)
- Do not hardcode or guess AI model names - model availability changes. Fetch official model documentation before choosing a model ID. (Caught: 2026-03-25)
- Do not use stale macOS packaging commands on Apple Silicon - use the current `npm run package:mac:local` script or pass `--arm64 -c.mac.target=dmg`. (Caught: 2026-04-07)

## Memory Updates

Update memory files as useful work happens, not only at the end of a session.

| Trigger | Action |
|---|---|
| Architectural decision made | append to `.codex/rules/memory-decisions.md` with date |
| New coding preference established | update `.codex/rules/memory-preferences.md` |
| New fact about the project learned | update `.codex/rules/memory-profile.md` |
| Substantive session completed | append summary to `.codex/rules/memory-sessions.md` |

## Codex Task Recipes

The old Claude slash commands have Codex-readable replacements in `.codex/tasks/`.

| Recipe | When to use |
|---|---|
| `commit-push-pr.md` | Stage, commit, push, and prepare/open a PR |
| `reflect.md` | End of a substantive session; capture learnings into memory and audit docs |
| `audit-entry.md` | Add a properly formatted finding to `docs/audit/AUDIT.md` |
| `verify.md` | Before commits touching pipeline code: TS typecheck, module imports, smoke tests, pytest |
| `annotate-paper.md` | Add a two-tier benchmark gold-standard entry for a PMID |

## Electron to Python Protocol

Python stdout lines: `PROGRESS:{json}` | `LOG:{json}` | `RESULT:{json}`.
Secrets are passed as env vars in spawn options, never CLI args.

## Pipeline Domains

`paper_selection` -> `oa_filter` -> `paper_reading` -> `candidate_discovery` -> `detail_extraction` -> `validation` -> `output_writing`
