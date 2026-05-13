# ResearchShop SoftwareX Paper Writing Brief

Use this file as the authoritative prompt source when asking Codex or another
writer to draft or revise the SoftwareX manuscript. It centralizes the current
publication claims so the paper does not have to be inferred from scattered
implementation notes.

## Tool Identity

- Tool name: ResearchShop.
- Current code version: v1.0.1.
- License: Apache License 2.0.
- Public repository: https://github.com/michaluppal/Researchshop-Disease2Gene.
- Package identifier/artifact name: `researchshop-desktop`.
- Software type: free, open-source desktop application for biomedical literature
  triage and gene/variant extraction.
- Runtime model: local Electron app plus local Python pipeline. No server
  infrastructure. Users provide their own Gemini API key and NCBI Entrez email.

## Paper Scope

The SoftwareX paper is a software description and reproducibility paper. It
should explain the problem, the architecture, the workflow, the validation
safeguards, the output artifacts, and the intended research use.

Do not frame the submission as a definitive extraction-accuracy benchmark.
Expanded benchmark studies, inter-rater reliability, and external expert
validation are deferred and should not be presented as completed work.

## Authorship And Style Constraints

- Preserve the author order in `publication/main.tex`.
- Preserve the current section structure unless there is a clear SoftwareX
  formatting reason to change it.
- Respect the existing colleague-written motivation and description text. Revise
  for correctness and current implementation, not for unnecessary stylistic
  replacement.
- Use "ResearchShop" consistently as both the project name and the application name.
- Avoid internal agent language, implementation diary language, and private audit
  history in the manuscript.

## Architecture Summary

The canonical pipeline domains are:

`paper_selection -> oa_filter -> paper_reading -> candidate_discovery -> detail_extraction -> validation -> output_writing`

Plain-language workflow:

1. Find relevant PubMed papers from a query, author search, or explicit PMID list.
2. Keep only papers where open-access full text can be fetched.
3. Read the paper through PMC or Europe PMC XML, including body text, tables,
   figure captions, and available figure metadata.
4. Find candidate genes and variants with PubTator3, deterministic HGNC scanning,
   and mandatory full-text Gemini candidate discovery.
5. Ask Gemini to fill the user-defined extraction fields for grounded candidates.
6. Validate gene identity, grounding, variants, evidence quotes, and confidence.
7. Write CSV, JSON, XLSX, metadata, candidate-audit, drop-debug, and optional
   trace artifacts.

The current implementation contract lives in
`docs/pipeline/pipeline-contract.md`. Use that as the source of truth for domain
names and failure/skip behavior.

## Allowed Claims

The manuscript may state that ResearchShop:

- combines PubTator3 NER, deterministic HGNC scanning, and Gemini 2.5 Flash
  Lite extraction by default;
- uses open-access full text from PubMed Central and Europe PMC;
- uses `pubmed_parser` through an adapter for selected JATS parsing tasks;
- validates genes against a bundled HGNC snapshot and remote fallback services;
- checks candidate grounding against fetched paper text and accepted normalized
  mention bridges;
- performs HGVS-style variant pattern checks;
- cross-references LLM-provided supporting quotes against normalized source text;
- provides confidence labels, provenance fields, metadata, candidate audit
  artifacts, and optional trace files for reviewability;
- runs locally on user hardware without a central ResearchShop server.

## Claims To Avoid

Do not claim that ResearchShop:

- has externally validated precision/recall for all supported domains;
- eliminates hallucinations in all cases;
- is a clinical decision-support or diagnostic product;
- extracts paywalled full text or bypasses paywalls;
- guarantees systematic-review recall;
- has a Zenodo DOI before an archival release exists;
- provides Apple-notarized macOS distribution before Developer ID signing and
  notarization are complete.

Prefer "research acceleration", "triage", "auditable extraction", and "expert
review" over "automated truth", "clinical validation", or "fully validated
associations".

## Output Semantics

Primary outputs are the researcher-facing CSV, JSON, and Excel `Results` sheet.
Diagnostic fields belong in the metadata CSV/workbook sheet or debug artifacts
unless there is a clear user-facing reason to surface them.

Current user-facing confidence labels:

| Label | Meaning |
|---|---|
| `CORROBORATED` | Multiple checks agree and matched supporting text was found. |
| `SUPPORTED` | The gene is valid and appears in the paper, but the user should inspect the evidence before use. |
| `LIMITED EVIDENCE` | The gene may be relevant, but evidence is weak, sparse, figure-only, or incomplete. |
| `NEEDS REVIEW` | Extraction was incomplete, fallback-derived, or otherwise requires manual inspection. |

Do not overemphasize raw citation-count or citation-coverage heuristics in the
main user-facing narrative. The app now exposes plain-language confidence reasons
and keeps detailed validation diagnostics in metadata.

## Release State And Caveats

- v1.0.1 is the current public release target.
- The current macOS DMG is unsigned and not Apple-notarized; Gatekeeper may show
  a misleading "damaged" warning. README documents the workaround.
- Windows installer build validation has passed on GitHub Actions, but public
  Windows distribution remains work in progress in the README.
- Linux packaging scripts exist, but Linux release validation remains pending.
- Zenodo DOI work is dismissed for the current SoftwareX submission unless the
  journal explicitly requires it.

## Acknowledgement

The acknowledgements should include ICM support and the project-development grant:

Initial development of ResearchShop was supported by a USD 1,000 Amazon Founders
grant awarded to Michal Bujniewicz-Uppal for this project.

Use LaTeX accenting for author names in the manuscript files, matching
`publication/main.tex`.

## Source Map For Drafting

Before drafting or revising the paper, read these files:

- `publication/main.tex` - title, abstract, authors, metadata input, back matter.
- `publication/softwarex_metadata.tex` - SoftwareX code metadata table.
- `publication/sections/01_motivation.tex` - motivation and tool-comparison framing.
- `publication/sections/02_description.tex` - architecture, GUI, validation.
- `publication/sections/03_examples.tex` - workflow, audit artifacts, parser handling, reproducibility checks.
- `publication/sections/04_impact.tex` - contributions, applications, limitations.
- `publication/sections/05_conclusions.tex` - conclusion and future work.
- `publication/references.bib` - available bibliography keys.
- `README.md` - public release state, installation, usage, output format, limitations.
- `docs/pipeline/pipeline-contract.md` - canonical pipeline and output contracts.
- `docs/planning/SOFTWAREX_RELEASE_CHECKLIST.md` - current release-readiness decisions.

## Final Review Rules

- Compile `publication/main.tex` after manuscript edits.
- Search for stale placeholders before considering the manuscript ready. The
  standard check should cover old tool-name placeholders, the old
  desktop-suffixed product name, old MIT-license wording, the previous repository
  slug, model-name placeholders, and unsupported benchmark claims.
- Keep the non-clinical-use limitation explicit in the abstract, limitations, or
  impact discussion.
- When uncertain, prefer a narrower, defensible claim over a broader marketing
  claim.
