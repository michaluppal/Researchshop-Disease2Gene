# ResearchShop Documentation

This directory keeps public project documentation and publication material out of the repository root.

## Public Reader Path

- [`../README.md`](../README.md) - public overview, installation, usage, limitations, and reproducibility commands.
- [`pipeline/pipeline-contract.md`](pipeline/pipeline-contract.md) - canonical pipeline domains, boundaries, skip behavior, trace nodes, normalization boundary, and output artifact contract.
- [`pipeline/internals.md`](pipeline/internals.md) - curated maintainer technical reference. Read after the contract when you need implementation detail.

This is the preferred path for SoftwareX reviewers and new open-source readers. Historical reports and audits are useful context, but they are not required for first-pass understanding.

## Maintainer Routing

- [`pipeline/pipeline-step-table.md`](pipeline/pipeline-step-table.md) - compatibility pointer to the canonical contract.
- [`planning/SOFTWAREX_RELEASE_CHECKLIST.md`](planning/SOFTWAREX_RELEASE_CHECKLIST.md) - remaining publication-hardening checks.

Internal agent routing, audit histories, generated reports, roadmap drafts, benchmark datasets, and working publication notes are intentionally omitted from the public release branch.

## Publication Material

- [`../publication/`](../publication/) - SoftwareX manuscript sources, figures, and references.
