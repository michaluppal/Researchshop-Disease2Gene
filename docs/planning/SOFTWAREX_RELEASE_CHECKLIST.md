# SoftwareX Release Checklist

This checklist tracks publication-hardening work for the SoftwareX submission. It intentionally excludes benchmark expansion; the current submission is framed as a software description and reproducibility paper.

## Required Before Submission

- [ ] Freeze feature work for the submission branch.
- [x] Run repository secret scan:
  - `rg -n "AIza|GEMINI_API_KEY=.*AIza|PRIMARY_KEY=|FALLBACK_KEY=|EMAIL=|password|secret" . -S --hidden --glob '!node_modules/**' --glob '!dist/**' --glob '!out/**' --glob '!.git/**'`
- [x] Run verification:
  - `npm run typecheck`
  - `npm run test`
  - `pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v --tb=short`
  - `git diff --check`
- [x] Build and smoke-test macOS Apple Silicon DMG:
  - `npm run package:mac:local`
  - mounted `dist/researchshop-desktop-1.0.0.dmg` and launched the packaged app from the read-only image
  - verified first-launch Python setup uses userData, not the app bundle
  - verified Query, Paper Analysis, Settings, History, app version, PubMed metadata IPC, PubMed count IPC, and Gemini usage IPC

## Required Before Final Cross-Platform Release

- [ ] Build Windows installer on Windows release runner:
  - `npm run package:win`
- [ ] Build Linux packages on Linux release runner:
  - `npm run package:linux`
- [ ] Verify first-launch Python setup and Settings flow on Windows and Linux.
- [ ] Create a GitHub release tag and attach installers.
- [ ] After SoftwareX acceptance or final release freeze, archive the exact release to Zenodo or another DOI provider.
- [ ] Add the archival DOI to `README.md` and `publication/softwarex_metadata.tex`.

## Manuscript-Specific Checks

- [x] Compile `publication/main.tex` without unresolved references.
- [x] Confirm the title, abstract, metadata table, limitations, and future-work section match the released code.
- [x] Do not claim externally validated precision/recall unless the benchmark expansion is resumed.
- [x] Keep research-use and non-clinical-use limitations explicit.

## Current Scope Decision

Benchmark expansion, inter-rater reliability, and external extraction-accuracy validation are deferred. Historical benchmark records remain in `docs/audit/` and `publication/working/` for transparency, but they are not release blockers for the current SoftwareX submission.
