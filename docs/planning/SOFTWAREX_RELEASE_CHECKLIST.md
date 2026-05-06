# SoftwareX Release Checklist

This checklist tracks publication-hardening work for the SoftwareX submission. It intentionally excludes benchmark expansion; the current submission is framed as a software description and reproducibility paper.

## Required Before Submission

- [x] Freeze feature work for the submission branch.
  - After the 2026-05-06 readiness pass, only release-blocking fixes, packaging fixes, and manuscript corrections should land before SoftwareX submission.
- [x] Document the normalization boundary clearly: paper-level text normalization vs candidate-level gene/variant normalization.
- [x] Rerun the PIMS/MIS-C gold-standard case with stable Gemini responses and confirm IFNG/HLA-C behavior in real output.
  - Live run on 2026-05-06 wrote artifacts to `/private/tmp/rs_pims_35177862_validation_1778055900/`.
  - Offline comparison recovered 16/16 focused expected genes, including `IFNG` via `IFN-gamma` and `HLA-C` via `C*04 -> HLA-C*04`.
  - Additional secondary markers remain review notes, not benchmark-style precision failures, because this fixture is focused recall validation.
- [x] Review output columns for publication readiness; every CSV/JSON/XLSX field should have an explicit reason to exist.
  - Primary CSV/JSON/Excel `Results` fields are now documented in `README.md` and `docs/pipeline/pipeline-contract.md`.
  - Diagnostic fields are metadata-only unless explicitly promoted for researcher review.
  - `test_write_split_output_has_public_column_contract` guards the public column set.
- [x] Do a final public-reader documentation sweep: `README.md` -> pipeline contract -> internals, without forcing readers through historical notes.
  - `docs/README.md` now separates the public reader path from private maintainer materials omitted from the public branch.
  - `docs/pipeline/internals.md` no longer links to private audit/report/watchlist notes.
- [x] Continue consolidating Gemini extraction around one typed schema stack for candidate discovery, figures, and detail extraction.
  - Candidate discovery and figure discovery share the same Pydantic association schema.
  - Detail extraction keeps the dynamic Pydantic schema builder for user columns.
  - Structured SDK responses and fallback text JSON both validate against the same schema.
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
  - GitHub Actions build validation run `25426414134` also passed macOS ARM64 install, typecheck, DMG build, artifact existence check, and artifact upload

## Required Before Final Cross-Platform Release

- [x] Build Windows installer on Windows release runner:
  - GitHub Actions build validation run `25426414134` passed on `windows-latest`
  - command: `npm run package:win -- --x64 --publish never`
  - verified Windows `.exe` installer and `*win.zip` artifacts exist and uploaded `researchshop-windows-x64`
- [ ] Build Linux packages on Linux release runner:
  - `npm run package:linux`
- [ ] Verify first-launch Python setup and Settings flow on Windows and Linux.
- [ ] Create a GitHub release tag and attach installers.

## Manuscript-Specific Checks

- [x] Compile `publication/main.tex` without unresolved references.
- [x] Confirm the title, abstract, metadata table, limitations, and future-work section match the released code.
- [x] Do not claim externally validated precision/recall unless the benchmark expansion is resumed.
- [x] Keep research-use and non-clinical-use limitations explicit.

## Current Scope Decision

Benchmark expansion, inter-rater reliability, and external extraction-accuracy validation are deferred. Detailed internal benchmark and audit working records are omitted from the public release branch, and they are not release blockers for the current SoftwareX submission.

Zenodo archival DOI work is dismissed from this checklist for the current SoftwareX submission. Revisit only if the journal or final release policy explicitly requires an archival software DOI.
