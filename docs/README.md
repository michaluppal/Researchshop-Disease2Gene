# ResearchShop Documentation

This directory keeps public project documentation, maintainer notes, audit history, and publication material out of the repository root.

## Public Reader Path

- [`../README.md`](../README.md) - public overview, installation, usage, limitations, and reproducibility commands.
- [`pipeline/pipeline-contract.md`](pipeline/pipeline-contract.md) - canonical pipeline domains, boundaries, skip behavior, trace nodes, normalization boundary, and output artifact contract.
- [`pipeline/internals.md`](pipeline/internals.md) - curated maintainer technical reference. Read after the contract when you need implementation detail.

This is the preferred path for SoftwareX reviewers and new open-source readers. Historical reports and audits are useful context, but they are not required for first-pass understanding.

## Maintainer Routing

- [`../AGENTS.md`](../AGENTS.md) - active routing file for coding agents and maintainer constraints.
- [`pipeline/pipeline-step-table.md`](pipeline/pipeline-step-table.md) - compatibility pointer to the canonical contract.
- [`planning/SOFTWAREX_RELEASE_CHECKLIST.md`](planning/SOFTWAREX_RELEASE_CHECKLIST.md) - remaining publication-hardening checks.
- [`planning/ROADMAP.md`](planning/ROADMAP.md) - historical roadmap with limited current carry-forward items.

## Historical And Audit References

- [`pipeline/understanding.md`](pipeline/understanding.md) - historical walkthrough built during pipeline tracing.
- [`pipeline/bug-hunting.md`](pipeline/bug-hunting.md) - historical/maintainer review checklist, not a current issue tracker.
- [`pipeline/reports/`](pipeline/reports/) - generated or report-style pipeline artifacts retained for traceability.
- [`audit/AUDIT.md`](audit/AUDIT.md) - source of truth for pipeline quality history, bugs, fixes, and accepted tradeoffs.
- [`audit/final-audit.md`](audit/final-audit.md) - end-to-end cleanup audit and follow-up findings.
- [`audit/pmid-41017238.md`](audit/pmid-41017238.md) - focused paper audit notes.

## Publication Material

- [`../publication/`](../publication/) - SoftwareX manuscript, figures, references, and working publication material.
