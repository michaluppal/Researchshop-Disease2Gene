<div align="center">
  <img src="docs/assets/researchshop-mark.svg" alt="ResearchShop logo" width="96">
  <h1>ResearchShop Desktop</h1>
  <p><strong>AI-powered gene and variant extraction from PubMed literature.</strong></p>
</div>

ResearchShop is a free, open-source desktop app for biomedical researchers. You provide a PubMed query or a list of paper IDs; the pipeline searches the literature, fetches full text from open-access papers, and writes a reviewable artifact bundle of gene/variant associations with supporting evidence, citations, provenance, and diagnostics.

> **Designed for molecular genetics research** — GWAS studies, cancer genomics, RNA-seq differential expression, pharmacogenomics, and rare disease papers.

<p align="center">
  <a href="https://github.com/michaluppal/Researchshop-Disease2Gene/releases/download/v1.0.1/researchshop-desktop-1.0.1.dmg">
    <img alt="Download unsigned macOS DMG" src="https://img.shields.io/badge/macOS-DMG%20unsigned-F59E0B?style=for-the-badge&logo=apple&logoColor=white&labelColor=111827">
  </a>
  &nbsp;
  <img alt="Windows EXE work in progress" src="https://img.shields.io/badge/Windows-EXE%20WIP-9CA3AF?style=for-the-badge&logo=windows&logoColor=white&labelColor=6B7280">
</p>

Installers are published on the [GitHub Releases page](https://github.com/michaluppal/Researchshop-Disease2Gene/releases). The current macOS `.dmg` is an unsigned test build; Windows `.exe` distribution is work in progress. The source-code ZIP files on GitHub are for developers, not normal app installation.

> **macOS security note:** v1.0.1 is not Apple-signed or notarized yet. macOS may show “ResearchShop is damaged and can’t be opened.” For local testing, install the app, then run:
>
> ```bash
> xattr -dr com.apple.quarantine /Applications/ResearchShop.app
> open /Applications/ResearchShop.app
> ```

---

## What it does

1. `paper_selection`: finds relevant PubMed papers or accepts a specific PMID list
2. `oa_filter`: keeps open-access papers for full-text reading
3. `paper_reading`: fetches full text via PubMed Central and Europe PMC fallback
4. `candidate_discovery`: finds candidate genes with PubTator, deterministic scans, and mandatory full-text Gemini discovery
5. `detail_extraction`: asks Gemini to fill the researcher-defined fields for each candidate
6. `validation`: validates gene symbols against HGNC and scores citation evidence
7. `output_writing`: exports CSV, metadata CSV, Excel, JSON, and debug artifacts

---

## System requirements

| Requirement | Version |
|-------------|---------|
| macOS | Apple Silicon unsigned DMG test build validated |
| Windows | x64 installer build validated on GitHub Actions |
| Linux | packaging script present; release validation pending |
| Node.js | 18 or later |
| Python | 3.11 or later |
| Google Gemini API key | free tier sufficient |
| NCBI Entrez email | any valid email |

---

## Installation

For release testing, download the packaged installer from [GitHub Releases](https://github.com/michaluppal/Researchshop-Disease2Gene/releases).

For development:

```bash
git clone https://github.com/michaluppal/Researchshop-Disease2Gene.git
cd Researchshop-Disease2Gene
npm install
npm run dev          # opens the app in development mode
```

In development, Python dependencies are installed into `pipeline/.venv/`. In the packaged desktop app, the bundled pipeline is read-only and dependencies are installed into the app user-data directory, for example `~/Library/Application Support/researchshop-desktop/python/.venv` on macOS.

The app performs this setup on first launch. For command-line development or tests, create the venv manually:

```bash
cd pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

To build a distributable:
```bash
npm run package:mac:local # macOS Apple Silicon DMG for local testing
npm run package:win -- --x64 --publish never # Windows x64 installer on a Windows runner
npm run package:linux # Linux AppImage + deb; validation pending
```

Build-validation workflow: [`.github/workflows/build-validation.yml`](.github/workflows/build-validation.yml). The current release-readiness record lives in [`docs/planning/SOFTWAREX_RELEASE_CHECKLIST.md`](docs/planning/SOFTWAREX_RELEASE_CHECKLIST.md).

---

## Configuration

### Gemini API key

The app uses Google Gemini Flash for gene extraction. The API key is stored locally and never leaves your machine.

1. Go to [aistudio.google.com](https://aistudio.google.com) → **Get API key**
2. Create a key (free tier includes sufficient quota for research use)
3. In the app: open **Settings** → paste the key → **Save**

### NCBI Entrez email

NCBI requires an email address for Entrez API access. Any valid email works — it is used only for API rate-limit attribution.

In Settings: enter your email in the **NCBI Email** field.

---

## Running a query

1. Enter a PubMed search query (e.g. `BRCA1 breast cancer GWAS`) or paste a comma-separated PMID list
2. Set the number of top papers to analyse (default: 10)
3. Define the columns you want extracted — each column is a name + description:
   - `Key Finding` → `The main genetic finding or association reported for this gene`
   - `Variant` → `The specific variant or mutation identified (HGVS notation if available)`
4. Click **Run Pipeline**
5. Download the CSV when the run completes

### Command-line usage

The pipeline can also be run headlessly. For explicit PMID lists, omit `--top-n`; the provided PMID list is the intended paper set:

```bash
cd pipeline
python3 -m venv .venv
source .venv/bin/activate   # or .venv/Scripts/activate on Windows
pip install -r requirements.txt
export GEMINI_API_KEY="..."
export ENTREZ_EMAIL="you@example.org"

python run_pipeline.py \
  --pmids '["19915526","20129251"]' \
  --columns '{"Key Finding": "The main genetic finding"}' \
  --output-dir /tmp/results
```

For PubMed query mode, use `--top-n` to choose how many open-access, full-review papers to keep after search, filtering, and ranking:

```bash
python run_pipeline.py \
  --query 'BRCA1 breast cancer GWAS' \
  --columns '{"Key Finding": "The main genetic finding"}' \
  --top-n 5 \
  --output-dir /tmp/results
```

---

## Output format

ResearchShop writes a small artifact bundle for each run:

| Artifact | Purpose |
|----------|---------|
| `final_enriched_results_*.csv` | Primary researcher-facing table |
| `final_enriched_results_*.json` | Same primary table as JSON records |
| `final_enriched_results_*.xlsx` | Excel workbook with `Results`, `Metadata`, and optional association-group sheets |
| `final_enriched_results_*_metadata.csv` | Full provenance, validation, citation, NCBI, and context diagnostics |
| `drop_debug_*.json`, `candidate_audit_*.json` | Debug artifacts for candidate lifecycle and gate decisions |

The primary CSV/JSON/Excel `Results` sheet contains one row per emitted gene-paper association. It intentionally keeps validation internals out of the main view; those remain in the metadata CSV/workbook sheet.

| Column | Description |
|--------|-------------|
| `Gene`, `Variant` | HGNC-normalized gene symbol and reported variant, if any |
| User columns, for example `Key Finding` | Gemini-extracted fields requested by the user |
| `{User Column} Citation` | Supporting sentence for the corresponding user field |
| `Confidence`, `Confidence Note` | Human-readable review tier and reason |
| `Association Group`, `Association Type` | Result grouping such as disease signature, primary genetic association, mechanistic/pathway signal, or animal model signal |
| `Original Paper Mention`, `Grounding Match`, `Grounding Source`, `Normalization Rule` | How the emitted gene was connected back to the paper text |
| `extraction_mode`, `evidence_backfilled`, `evidence_specificity`, `context_modifications` | Visibility into fallback extraction, evidence quality, and context truncation |
| `PMID`, `Title`, `Year`, `Journal`, `Authors`, `Citations`, `DOI` | Source-paper metadata |

Diagnostic fields such as `validation_confidence`, `Candidate Source`, `Gene Source`, citation-validation booleans, NCBI metadata, and raw gate details are metadata-only by design.

---

## Pipeline architecture

```
paper_selection → oa_filter → paper_reading → candidate_discovery
                                                          ↓
                         output_writing ← validation ← detail_extraction
```

The canonical step contract, including the normalization boundary between `paper_reading` and per-paper extraction, lives in [`docs/pipeline/pipeline-contract.md`](docs/pipeline/pipeline-contract.md).

**Domain details:**

| Domain | Module | Role |
|-------|--------|------|
| `paper_selection` | `pubmed_data_collector.py`, renderer selection UI | Fetches candidate papers, ranks by citation count, and preserves user selections |
| `oa_filter` | `pubmed_data_collector.py`, `full_text_fetcher.py` | Keeps the workflow limited to open-access papers where full text can be fetched legally |
| `paper_reading` | `full_text_fetcher.py` | PMC JATS XML via Entrez; Europe PMC fallback; `pubmed_parser` adapter for paragraphs/figure metadata |
| `candidate_discovery` | `pubtator_tool.py`, `paper_analysis/` | Finds candidate genes and variants with PubTator, deterministic scans, mandatory full-text Gemini discovery, and optional abstract/figure/recall passes |
| `detail_extraction` | `paper_analysis/` | Uses Gemini to fill structured user-defined columns for validated candidates |
| `validation` | `gene_validator.py`, `paper_analysis/` | HGNC validation, grounding, citation checks, confidence gates, and evidence gates |
| `output_writing` | `pipeline_artifacts.py`, `pipeline_orchestrator.py` | Deduplication, citation ranking, CSV/metadata/Excel/JSON/debug artifact writes |

---

## Safety & Limitations

> **ResearchShop is a research tool, not a clinical or diagnostic product.**
> Results must be independently verified before use in publications, clinical decisions, or downstream analyses.

### Harm model

AI-extracted gene/variant associations can contain false positives that are syntactically and semantically plausible. If accepted without verification, these can:

- Propagate into downstream analyses and literature reviews
- Inflate apparent gene-disease evidence in meta-analyses that aggregate automated extraction outputs
- Mislead clinical researchers who treat high-confidence scores as validated findings

The `validation_confidence` score (≥0.7 gate) reflects multi-source corroboration, **not clinical validation**. A score of 1.0 means the gene was found by both PubTator NER and Gemini and validated against HGNC — it does not mean the association is biologically correct.

### Required cross-checks before publication

For any association you intend to report or build upon:

1. **HGNC** ([genenames.org](https://www.genenames.org)) — confirm the gene symbol is current and refers to the expected locus
2. **ClinVar** ([ncbi.nlm.nih.gov/clinvar](https://www.ncbi.nlm.nih.gov/clinvar)) — for variant assertions, check clinical significance and evidence level
3. **Primary literature** — read the source paper. The `Key Finding Citation` column provides the verbatim supporting sentence; verify it in context

### Known failure modes

- **Clinical biomarker papers.** Papers that report CRP, ESR, AST, ALT primarily as inflammatory/liver markers (not as gene expression data) can produce false gene extractions. The pipeline's disambiguation and evidence gates reduce but do not eliminate this. Inspect the metadata sheet fields such as `Candidate Source`, grounding details, and citation-validation fields before using a result.

- **Open-access papers only.** Full text is fetched only from PMC and Europe PMC. Paywalled papers are excluded from extraction; if no OA full text is fetched, the output contains metadata-only rows for review.

- **Gemini is required for normal extraction.** Every analyzed full-text paper gets a mandatory full-text Gemini candidate-discovery call before detail extraction. Empty Gemini candidate output can continue with PubTator and deterministic candidates, but transport/authentication/parsing failures are surfaced as paper-analysis failures rather than silently falling back to deterministic-only extraction.

- **Table-heavy results sections.** The citation validator matches LLM-extracted quotes against prose sentences. Papers where findings appear only in supplementary tables will show low or zero citation coverage — this is expected behaviour, not a pipeline error.

- **Gene symbol ambiguity.** Common clinical abbreviations (ESR mm/h, AST U/L, CRP mg/L) overlap with gene symbols (ESR1, GOT1). The corroboration gate provides a hard backstop, but stochastic LLM compliance means rare misclassifications occur.

### Validation status

ResearchShop includes offline unit and integration tests for the parser, PubTator integration, per-paper extraction gates, citation grounding, output writing, and pipeline tracing. Public documentation summarizes the validation boundaries and known failure modes maintainers should keep in view.

The safest interpretation is: high-confidence rows are **prioritised candidates for expert review**, not validated biomedical facts. Precision and recall depend on paper type, full-text availability, user-defined columns, Gemini model behavior, and whether evidence appears in prose, tables, figures, or supplementary files.

---

## Reproducibility

To run the local verification suite:

```bash
npm install
npm run typecheck
npm run test
cd pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v --tb=short
```

This is the public reproducibility path for the software workflow. Internal audit fixtures and historical validation notes are kept in the repository for maintainers, but they are not part of the public quick-start path.

---

## How to cite

> ResearchShop Desktop v1.0.1. GitHub: <https://github.com/michaluppal/Researchshop-Disease2Gene>.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

The ResearchShop name and logo are project identifiers and may not be used to imply endorsement by the project authors.
