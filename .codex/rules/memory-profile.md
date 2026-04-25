# memory-profile.md — Project Facts

> Codex migration note (2026-04-25): this is the active project profile for Codex sessions.
> Keep legacy Claude-era facts only when they are historical context.

> Auto-updated during agent sessions. Last section: bootstrapped 2026-02-24.

## Project

- **Name:** ResearchShop Desktop
- **Type:** Electron desktop app (free, open-source)
- **Status:** Active product (standalone repo)
- **Goal:** Open-source release + SoftwareX journal paper publication
- **License:** MIT (`LICENSE`)

## What It Does

Automated biomedical research pipeline: user submits a PubMed query or list of PMIDs → UI scores
papers for gene relevance (users see badges, can toggle hidden low-relevance papers) → user selects
papers → pipeline fetches full text, extracts gene/variant data via Gemini LLM, validates against
HGNC, outputs CSV. Users bring their own Gemini API key.

## Target Users

- Biomedical researchers
- Geneticists and genomicists
- Bioinformaticians without dedicated data engineering support
- Labs that need structured gene data from literature quickly

## Infrastructure

- **No server** — fully local, privacy-preserving
- **Python venv** auto-created at `pipeline/.venv/` on first app launch
- **Local HGNC database** — 44,943 genes bundled at `pipeline/data/reference/hgnc_genes.json` (6.6 MB, refreshed 2026-02-28)
- **electron-store** — encrypted settings (API key, email)
- **better-sqlite3** — local job history; `jobs.db` now stores primary CSV plus metadata/Excel/JSON artifact paths so History can reopen full result bundles

## External APIs Used

- Google Gemini API (user-provided key) — LLM extraction
- NCBI Entrez — PubMed search + PMC full text
- PubTator3 — NER gene/variant extraction
- HGNC REST API — gene validation (fallback to local)
- MyGene.info — gene validation (second fallback)
- iCite (NIH) — citation ranking (primary)
- Semantic Scholar — citation ranking (fallback)

## Benchmark Infrastructure

- **Gold standard:** `pipeline/data/benchmark/gold_standard.json` — 24 papers, 5 types; 23/24 have v2 two-tier schema (21076407 paywalled)
- **Gold standard creation:** `.codex/tasks/annotate-paper.md` recipe — PubMed metadata, OA full text, figure review, and Codex synthesis
- **Figure extraction:** `pipeline/scripts/extract_pmc_figures.js` — Playwright headless Chromium, per-figure screenshots
- **Runner:** `pipeline/scripts/benchmark_runner.py` — calls `repeatability_check.py` per paper
- **Analysis:** `pipeline/scripts/benchmark_analysis.py` — computes P/R/F1 from summaries
- **Per-paper results:** `pipeline/data/benchmark/{pmid}/` — `run_0{n}_results.csv` + `repeatability_summary.json`
- **Per-run full text:** `content_dict_{hash}.pkl.gz` — full text fetched during that run (gzipped pickle)
- **Preliminary F1 (full-LLM mode):** cancer_genomics=0.668, gwas=0.611, rare_disease=0.167, rna_seq/pharmacogenomics TBD
- **Playwright:** installed globally (`/opt/homebrew/bin/playwright` v1.55.0) + as devDependency; Chromium browser cached

## Repository

- Standalone repo: `RS_SOFTWAREX` (migrated from `ResearchShop-Website/local_pivot/` on 2026-03-09)
- SoftwareX paper: `publication/` directory
