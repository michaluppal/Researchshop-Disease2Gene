# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Disease2Gene is an AI-powered pipeline that extracts gene–disease associations from biomedical literature. It searches PubMed, fetches full text via multiple strategies, uses Google Gemini to extract structured data, and validates gene names against HGNC. The project includes a Flask web GUI, PyInstaller packaging for macOS/Windows, a Docker setup, and a SoftwareX journal article.

## Common Commands

### Run the web GUI
```bash
python gui/app_server.py
# Opens http://localhost:8050
```

### Run via launcher scripts
```bash
bash packaging/start.sh       # macOS/Linux
packaging\start.bat           # Windows
```

### Build standalone macOS app
```bash
cd packaging
python -m PyInstaller Disease2Gene.spec
bash create_custom_dmg.sh     # Creates dist/Disease2Gene.dmg
```

### Compile the SoftwareX paper
```bash
cd publication
pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex
```

### Docker
```bash
cd docker
docker-compose up --build
```

### Tests
No test suite exists yet. When created, it should use pytest:
```bash
pip install pytest pytest-cov
pytest tests/
pytest tests/test_gene_validator.py -v    # single test file
pytest tests/ --cov=modules --cov-report=term-missing
```

## Architecture

### Pipeline (8 stages, all in `modules/`)

The pipeline is orchestrated by `pipeline_orchestrator.py` which calls modules in sequence:

1. **Query definition** — User provides PubMed query, PMIDs, or author names
2. **Literature retrieval** — `pubmed_data_collector.py` searches NCBI E-utilities API, fetches metadata in batches of 50, filters out reviews/meta-analyses/editorials
3. **Full-text acquisition** — `full_text_fetcher.py` (largest module, ~1850 LOC) tries three strategies in fallback order: PMC Open Access → Trafilatura URL extraction → Playwright browser automation. Has publisher-specific CSS selectors for Nature, ScienceDirect, Wiley, Springer, PMC
4. **Citation analysis** — Semantic Scholar API for impact scoring
5. **Abstract screening** — `abstract_screener.py` scores genetic relevance using weighted keywords (genetic terms +1-3, negative terms -5) and regex patterns for gene symbols/variants
6. **Gene discovery** — `gemini_extractor.py` uses Gemini 2.0-Flash to identify genes in paper text
7. **Validation** — `gene_validator.py` validates against local HGNC database (`data/reference/hgnc_genes.json`, 8.1MB) with LRU cache (2000 entries), falls back to HGNC REST API and MyGene.info. `variant_normalizer.py` normalizes to HGVS format
8. **Detailed extraction** — `gemini_extractor.py` uses Gemini 2.5-Flash to extract user-defined columns for each validated gene

### Key design patterns

- **Multiprocessing**: `pipeline_orchestrator.py` uses `_run_pipeline_worker()` as a top-level picklable function for parallel paper processing
- **Thread-safe rate limiting**: `gemini_rate_limiter.py` tracks RPM/TPM/RPD per Gemini model with a 90% safety margin
- **Graceful shutdown**: Global `_pipeline_state` dict + signal handlers enable saving partial results
- **JSON repair**: `gemini_extractor.py` handles truncated LLM JSON responses
- **Config via env vars**: `config.py` reads all tunables from environment variables with sensible defaults

### Web GUI (`gui/`)

- `app_server.py` — Flask server on port 8050 with REST API. Pipeline runs in a background thread. Logs stream to the UI via SSE (`/api/pipeline/logs`). Config persisted to `~/.disease2gene/config.json`
- `static/index.html` — Single-page app (~38K). Three input modes: Query Builder, Author Search, PMID Entry. User defines custom output columns. Live log streaming during pipeline execution

### API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/config` | GET/POST | Load/save persistent config |
| `/api/pubmed/search` | GET | Search PubMed, return paper details |
| `/api/pubmed/count` | GET | Count matching papers |
| `/api/pubmed/resolve` | POST | Resolve PMIDs to titles |
| `/api/pubmed/author` | GET | Search by author name |
| `/api/pipeline/run` | POST | Start pipeline (background thread) |
| `/api/pipeline/status` | GET | Check pipeline state |
| `/api/pipeline/logs` | GET | SSE log stream |
| `/api/pipeline/stop` | POST | Request pipeline stop |

### Packaging (`packaging/`)

- `Disease2Gene.spec` — PyInstaller spec with macOS `.app` bundle (bundle ID: `pl.researchshop.disease2gene`) and Windows `.exe` section. Excludes playwright, tkinter, matplotlib, scipy to reduce size
- `disease2gene_launcher.py` — Entry point for bundled apps. Detects frozen state via `sys._MEIPASS`, sets `DISEASE2GENE_DATA_DIR` to `~/Disease2Gene/` for outputs
- `create_custom_dmg.sh` — Creates DMG with drag-to-Applications layout (1000x640 window, app at 300,300, Applications at 700,300)

### Docker (`docker/`)

**Known issue**: Dockerfile references `run_local.py` which does not exist in the repo. The GUI entry point is `gui/app_server.py`.

## Configuration

All pipeline settings are in `modules/config.py` and can be overridden via environment variables:

- `GEMINI_API_KEY` — Required. Google Gemini API key
- `ENTREZ_EMAIL` — Required. Email for NCBI API access
- `OUTPUT_DIR` — Output directory (default: `data/output`)
- `FETCH_MAX_WORKERS` — Concurrent fetchers (default: 3)
- `FETCH_THREAD_TIMEOUT` — Per-PMID timeout in seconds (default: 120)
- `AI_PER_PAPER_TIMEOUT_SECONDS` — Gemini timeout per paper (default: 600)
- `GENE_BATCH_THRESHOLD` — Genes per batch for detailed extraction (default: 8)

## Evaluation

`evaluation/` contains a ground truth dataset (19 MIS-C papers, 103 gene associations) and `evaluation_analysis.ipynb` for reproducibility analysis including multi-run variance, ablation studies, and comparisons with PubTator/DisGeNET baselines.

## Known Issues

- `softwarex_metadata.tex` contains placeholder GitHub URL and email — must be updated before paper submission
- Windows `.exe` build uses macOS `.icns` icon — needs `.ico` conversion
- No unit tests exist; only end-to-end evaluation via Jupyter notebook
- `pubmed_data_collector.py` lacks docstrings (all other modules have them)
