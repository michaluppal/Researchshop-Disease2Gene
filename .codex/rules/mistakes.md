# mistakes.md - Common Agent Mistakes

Use this file to record mistakes made by agents working in this repository so future sessions avoid repeating them.

## How To Use This File

- Add a new entry whenever an agent makes a concrete mistake, incorrect assumption, unsafe shortcut, or misleading recommendation.
- Keep entries short and actionable.
- Include the date caught and, when useful, the audit/code context.
- Do not use this for general preferences. Put stable coding preferences in `.codex/rules/memory-preferences.md`.
- Do not delete historical mistakes unless the entry is factually wrong.

## Entries

- Do not normalize only one side of a citation match - normalize both the citation string and paper text before matching. Normalizing only one side fails if the artifact appears in the paper, not just LLM output. (Caught: 2026-02-25)
- Do not create a static blocklist of clinical abbreviations to suppress false positives - it blocks correct gene extractions across other paper types, such as ESR1 in breast cancer, PSA/KLK3 in prostate cancer, and ACE in pharmacogenomics. Prefer context-sensitive disambiguation. (Caught: 2026-02-24, C18 FDA audit)
- Do not test citation validation quality on PMID 34876594 or similar clinical/lab-table papers - BNP data is table-only, so valid prose citation scores are structurally impossible regardless of extraction quality. Use molecular genetics papers for citation benchmarks. (Caught: 2026-02-25)
- Do not report a single-run citation score as a quality metric - scores can fluctuate dramatically on the same paper because of stochastic LLM compliance. Multi-run averaging is required. (Caught: 2026-02-25)
- Do not assume citation validation is working because it runs without errors - False/0.0/"No validation performed" can hide a silent TypeError. Keep a smoke test that asserts at least one citation validates true on known-good input before trusting the metric. (Caught: 2026-02-24, C19)
- Do not hardcode or guess AI model names - model availability changes without warning and deprecated models cause runtime errors. Fetch official documentation before choosing a model ID. (Caught: 2026-03-25)
- Do not use stale macOS packaging commands on Apple Silicon - the release config targets universal arch and can hang on local M-series builds. Use the current `npm run package:mac:local` script or explicitly pass `--arm64 -c.mac.target=dmg`. (Caught: 2026-04-07)
- Do not add runtime test doubles to committed tests - they make integration failures look like implementation bugs and hide contract drift. Extract pure helpers or use explicit dependency injection with fixture data instead. (Caught: 2026-04-30)
