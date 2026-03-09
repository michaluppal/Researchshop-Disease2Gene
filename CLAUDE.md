# CLAUDE.md — ResearchShop Desktop

> This is a **routing file**. Keep it under 150 lines. Detailed specs live in `.claude/rules/`.

## What This Is

Free Electron desktop app for automated biomedical gene/variant extraction from PubMed papers.
Users provide their own Gemini API key. No server. Goal: open-source tool + SoftwareX journal paper.

## Key Files to Know

| Layer | File | Purpose |
|---|---|---|
| Entry | `python/run_pipeline.py` | CLI spawned by Electron |
| Orchestration | `python/modules/pipeline_orchestrator.py` | chains all stages |
| Extraction | `python/modules/gemini_extractor.py` | LLM extraction engine |
| Validation | `python/modules/gene_validator.py` | HGNC + remote APIs |
| NER | `python/modules/pubtator_tool.py` | high-precision gene NER |
| Config | `python/modules/config.py` | all pipeline feature flags |
| IPC | `src/main/python-bridge.ts` | Electron ↔ Python protocol |
| Audit | `AUDIT.md` | source of truth for pipeline quality |

**Read before modifying pipeline code:** `.claude/rules/memory-pipeline.md`
**Full project memory:** `.claude/rules/`

## Commands

```bash
# JS
npm install && npm run dev          # dev mode
npx tsc --noEmit -p tsconfig.web.json   # typecheck renderer
npx tsc --noEmit -p tsconfig.node.json  # typecheck main

# Python
cd python && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py --help
```

## Non-Negotiables (Medical Software)

IMPORTANT: These constraints exist for scientific accuracy and must not be overridden without explicit user discussion.

- **IMPORTANT: Do not lower confidence thresholds** — `FINAL_VALIDATION_MIN_CONFIDENCE=0.7` is a medical
  accuracy decision, not a performance knob. Lowering it increases false gene associations in output.
- **IMPORTANT: Do not disable pipeline safeguards** — grounding check, deterministic seeding, and strict
  validation gate are hallucination controls. Disabling them for speed is never an acceptable tradeoff.
- **Do not weaken validation logic silently** — if a validation rule is relaxed, document in AUDIT.md
  with the reasoning and the tradeoff explicitly accepted.
- **False negatives at abstract screening are silent failures** — a paper dropped there cannot be recovered.
  Do not raise the screening threshold without evaluating recall impact.
- **YOU MUST keep AUDIT.md synchronized** — any change to pipeline behaviour requires an update.
- **Secrets via env vars only** — never CLI args (visible in `ps aux`)
- **OA papers only** — no paywall bypass, no Playwright
- **No over-engineering** — minimum complexity for the current task. Replace, don't deprecate.

Read `.claude/rules/memory-pipeline.md` before modifying any pipeline module.

## Common Mistakes (append when Claude gets something wrong)

> This section grows over time. Every mistake Claude makes in this codebase gets added here so it
> never repeats. When you catch a mistake: add it, note the context, keep it concise.

<!-- Add entries below in format: "- Do not X — [reason]. (Caught: YYYY-MM-DD)" -->

- Do not normalize only one side of a citation match — always normalize **both** the citation string and the paper text before matching. Normalizing only one side fails if the artifact appears in the paper (not just LLM output). (Caught: 2026-02-25)
- Do not create a static blocklist of clinical abbreviations to suppress false positives — it blocks correct gene extractions across all other paper types (ESR1 in breast cancer, PSA/KLK3 in prostate cancer, ACE in pharmacogenomics). Derive rules from the LLM prompt disambiguation clause instead, which reads context. (Caught: 2026-02-24, C18 FDA audit)
- Do not test citation validation quality on PMID 34876594 (MIS-C) or similar clinical/lab-table papers — BNP data is table-only, so valid citation scores are structurally impossible regardless of extraction quality. Use molecular genetics papers for citation benchmarks. (Caught: 2026-02-25)
- Do not report a single-run citation score as a quality metric — scores fluctuate 0/8–8/8 on the same paper due to stochastic LLM compliance. Multi-run averaging is required. (Caught: 2026-02-25)
- Do not assume citation validation is working because it runs without errors — False/0.0/"No validation performed" is structurally indistinguishable from a silent TypeError. Add a smoke test that asserts at least one citation validates True on known-good input before trusting the metric. (Caught: 2026-02-24, C19)

## Auto-Update Memory (MANDATORY)

Update memory files **as you go**, not at the end of the session.

| Trigger | Action |
|---|---|
| Architectural decision made | → append to `.claude/rules/memory-decisions.md` with date |
| New coding preference established | → update `.claude/rules/memory-preferences.md` |
| New fact about the project learned | → update `.claude/rules/memory-profile.md` |
| Substantive session completed | → append summary to `.claude/rules/memory-sessions.md` |

**Do not ask. Just update.**

## Slash Commands (`.claude/commands/`)

| Command | When to use |
|---|---|
| `/commit-push-pr` | Stage, commit, push, open PR in one shot |
| `/reflect` | End of any substantive session — capture learnings into memory + AUDIT.md |
| `/audit-entry` | Add a properly formatted finding to AUDIT.md |
| `/verify` | Before every commit on pipeline code — TS typecheck + all 7 Python modules + smoke tests |

## Electron ↔ Python Protocol

Python stdout lines: `PROGRESS:{json}` | `LOG:{json}` | `RESULT:{json}`
Secrets passed as env vars in spawn options. Never in CLI args.

## Pipeline Stages (in order)

PubMed search → abstract screening → full-text fetch → PubTator NER → Gemini extraction → gene validation → CSV output
