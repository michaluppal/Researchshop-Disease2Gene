# ResearchShop Desktop

**AI-powered gene and variant extraction from PubMed literature.**

ResearchShop is a free, open-source desktop app for biomedical researchers. You provide a PubMed query or a list of paper IDs; the pipeline searches the literature, fetches full text from open-access papers, and produces a structured CSV of gene/variant associations with supporting evidence and citations — ready for downstream analysis or manual review.

> **Designed for molecular genetics research** — GWAS studies, cancer genomics, RNA-seq differential expression, pharmacogenomics, and rare disease papers.

---

## What it does

1. Searches PubMed for relevant papers (or accepts a specific PMID list)
2. Screens abstracts to filter out non-genetics papers
3. Fetches full text for open-access papers via PubMed Central
4. Runs PubTator NER for high-precision gene identification
5. Extracts structured gene/variant associations using Google Gemini
6. Validates all gene symbols against HGNC and scores citation evidence
7. Exports a CSV with every extracted association, its evidence, and grounding score

---

## System requirements

| Requirement | Version |
|-------------|---------|
| macOS / Windows / Linux | any recent |
| Node.js | 18 or later |
| Python | 3.11 or later |
| Google Gemini API key | free tier sufficient |
| NCBI Entrez email | any valid email |

---

## Installation

```bash
git clone https://github.com/michaluppal/RS_SOFTWAREX.git
cd RS_SOFTWAREX
npm install
npm run dev          # opens the app in development mode
```

Python dependencies are installed automatically on first launch into a local virtual environment (`pipeline/.venv/`). No manual `pip install` needed.

To build a distributable:
```bash
npm run package:mac:local # macOS Apple Silicon DMG for local testing
npm run package      # macOS universal DMG + ZIP, intended for release builders
npm run package:win  # Windows NSIS installer, intended for Windows release builders
npm run package:linux # Linux AppImage + deb
```

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

The pipeline can also be run headlessly:

```bash
cd pipeline
source .venv/bin/activate   # or .venv/Scripts/activate on Windows

python run_pipeline.py \
  --pmids '["19915526","20129251"]' \
  --columns '{"Key Finding": "The main genetic finding"}' \
  --top-n 5 \
  --output-dir /tmp/results
```

---

## Output format

The output CSV contains one row per gene-paper pair with the following key columns:

| Column | Description |
|--------|-------------|
| `Gene/Group` | HGNC-validated gene symbol |
| `Key Finding` | LLM-extracted description of the genetic finding |
| `Key Finding Citation` | Verbatim sentence from the paper supporting the finding |
| `Key Finding_citation_valid` | `True` if the citation was verified in the paper text |
| `Variant Name` | HGVS variant string (if reported) |
| `Variant Citation` | Verbatim supporting sentence for the variant |
| `validation_confidence` | Confidence score 0–1 (≥0.7 passes the output gate) |
| `Candidate Source` | What found the gene: `pubtator`, `llm`, `deterministic_lexicon` |
| `PMID` | Source paper |
| `Citations` | Paper citation count (used for ranking) |

---

## Pipeline architecture

```
PubMed Search → Abstract Screening → Full Text Fetch → PubTator NER
                                                              ↓
                                          CSV Output ← Gene Validation ← Stage 5 Extraction
```

**Stage details:**

| Stage | Module | Role |
|-------|--------|------|
| 1. PubMed Search | `pubmed_data_collector.py` | Fetches papers, ranks by citation count (iCite) |
| 2. Abstract Screening | `abstract_screener.py` | Keyword filter — removes non-genetics papers |
| 3. Full Text Fetch | `full_text_fetcher.py` | PMC JATS XML via Entrez; Europe PMC fallback; `pubmed_parser` adapter for paragraphs/figure metadata |
| 4. PubTator NER | `pubtator_tool.py` | NCBI NER — high-precision gene/variant tagging |
| 5. Stage 5 Extraction | `stage5/` | Candidate discovery, Gemini structured extraction, grounding, validation, and evidence gates |
| 6. Gene Validation | `gene_validator.py` | HGNC validation, citation grounding (≥0.85 match) |
| 7. CSV Output | `pipeline_orchestrator.py` | Deduplication, citation ranking, CSV write |

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

- **Clinical biomarker papers.** Papers that report CRP, ESR, AST, ALT primarily as inflammatory/liver markers (not as gene expression data) can produce false gene extractions. The pipeline's disambiguation clause reduces but does not eliminate this. Example: an MIS-C cytokine paper produced false-positive ESR, CRP, and IL-6 extractions in early testing. Inspect `Candidate Source` — deterministic-only genes without LLM corroboration require additional scrutiny.

- **Open-access papers only.** Full text is fetched only from PMC and Europe PMC. Approximately 40–60% of PubMed papers are paywalled; these receive abstract-only extraction with substantially lower recall. The `Candidate Source` column will show `pubtator` or `deterministic_lexicon` only for paywall papers, never `llm`.

- **GWAS and pharmacogenomics papers require LLM.** Novel GWAS loci not yet indexed by PubTator's NER model depend entirely on Gemini extraction. Runs with an invalid or expired API key fall back to deterministic + PubTator mode, which has near-zero recall on GWAS papers.

- **Table-heavy results sections.** The citation validator matches LLM-extracted quotes against prose sentences. Papers where findings appear only in supplementary tables will show low or zero citation coverage — this is expected behaviour, not a pipeline error.

- **Gene symbol ambiguity.** Common clinical abbreviations (ESR mm/h, AST U/L, CRP mg/L) overlap with gene symbols (ESR1, GOT1). The corroboration gate provides a hard backstop, but stochastic LLM compliance means rare misclassifications occur.

### Validation status

ResearchShop includes offline unit and integration tests for the parser, PubTator integration, Stage 5 extraction gates, citation grounding, output writing, and pipeline tracing. The audit log records historical benchmark experiments and known failure modes, but the current SoftwareX submission is framed as a software description and reproducibility paper rather than a definitive clinical accuracy benchmark.

The safest interpretation is: high-confidence rows are **prioritised candidates for expert review**, not validated biomedical facts. Precision and recall depend on paper type, full-text availability, user-defined columns, Gemini model behavior, and whether evidence appears in prose, tables, figures, or supplementary files.

---

## Reproducibility

To run the local verification suite:

```bash
npm run typecheck
cd pipeline
source .venv/bin/activate
python -m pytest tests/ -v --tb=short
```

Historical benchmark scripts and data live under `pipeline/data/benchmark/` and `pipeline/scripts/`. They are retained for auditability, but they are not required for normal installation or SoftwareX reproduction of the software workflow.

If you do run historical benchmark scripts, provide credentials via environment variables only:

```bash
cd pipeline
source .venv/bin/activate
export GEMINI_API_KEY="..."
export ENTREZ_EMAIL="you@example.org"
python scripts/benchmark_runner.py --all --runs 3
python scripts/benchmark_analysis.py
```

Results are written to `data/benchmark/benchmark_results.csv`. See `docs/audit/AUDIT.md § Benchmark Results` for the full evaluation.

---

## How to cite

> ResearchShop Desktop v1.0.0. GitHub: <https://github.com/michaluppal/RS_SOFTWAREX>. DOI to be added after archival release.

---

## License

MIT — see [LICENSE](LICENSE).
