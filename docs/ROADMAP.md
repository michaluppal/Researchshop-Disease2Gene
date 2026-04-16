# ResearchShop Desktop — Roadmap to Paper-Ready

**Goal:** Reach a stable, frozen architecture that is good enough to publish in SoftwareX and
impress the genomics crowd. Every open item below is framed as: what it is, why it matters,
and exactly how to execute it.

Last updated: 2026-03-09

---

## How to read this document

- **P0** — Blocking. The paper cannot exist without these. ✅ All done.
- **P1** — Architecture-freeze prerequisites. ✅ All done.
- **P2** — Paper depth. Strengthen claims and figures. ✅ All done.
- **P3** — Pre-submission work identified post-Elicit analysis (2026-03-09). Blocking or high priority.
- **P4** — Polish. Low-effort items, do during other work.

Remaining work order (P0-P2 complete):
`P3-A (benchmark expansion) → P3-B (smoke test) → P3-C (limitations in paper) → P3-D (future work in paper) → P4 polish → submit`

---

## P0 — Blocking

### P0-A · Benchmark on molecular genetics papers ✅ Done (2026-02-25)

**Why it's P0:** The SoftwareX paper's Results section is empty without this. All evaluation
to date is on PMID 34876594 — a clinical outcomes paper that is a structurally poor fit for
a gene extraction tool (BNP data is table-only, cytokines are in supplementary tables). Without
a benchmark on papers the tool is actually designed for, there is nothing to publish.

**Goal:** Run the pipeline on 10–15 molecular genetics papers with known gene associations.
Measure precision, recall, F1 for gene discovery. Measure citation grounding rate. Report
Jaccard stability across 3 runs per paper.

**Status (2026-02-25):** Complete. Full LLM pipeline benchmarked on all 12 papers.
- cancer_genomics mean F1=0.668 ✅, gwas mean F1=0.611 ✅, rna_seq mean F1=0.600 ✅
- Best paper: PMID 17463248 (T2D GWAS) F1=1.000 — perfect recall and precision
- Overall mean F1=0.448 (full-LLM) vs 0.317 (hybrid baseline: deterministic lexicon + PubTator)
- P0-C citation grounding confirmed: 95% accuracy on 17463248, 67% on 19915526 ✅

**Commit:** `4dd91f0b` — See `AUDIT.md ## Benchmark Results (P0-A + P0-C, 2026-02-25)`.

**Acceptance criteria:** ≥10 papers benchmarked ✅. Precision/recall/F1 in AUDIT.md ✅.
At least one paper type F1 > 0.6 ✅ (3 types pass). Citation grounding ≥60% ✅. Dataset committed ✅.

---

### P0-B · LICENSE file ✅ Done (2026-02-25)

**Why it's P0:** SoftwareX requires an open-source license. Without one, the submission is
immediately rejected. Takes 5 minutes.

**Goal:** Add MIT license to repo root and `local_pivot/`.

**Acceptance criteria:** `LICENSE` file present at repo root ✅. `local_pivot/LICENSE` present ✅.

---

### P0-C · Validate citation grounding on molecular genetics papers ✅ Done (2026-02-25)

**Why it's P0:** The citation validator has only been confirmed working on one clinical paper
(PMID 34876594) where data is table-only and citation scores are structurally uninformative.
Before reporting "X% of extracted associations have grounded citations" in the paper, the
validator needs to be confirmed working on prose-rich genetics papers with explicit Results
sentences.

**Goal:** Confirm that citation fields score correctly on 3+ molecular genetics papers —
valid verbatim quotes score True/1.0, empty or paraphrased citations score False.

**Status (2026-02-25):** Complete. Full LLM benchmark ran with active Gemini key.
Citation validator confirmed working on molecular genetics papers:
- 17463248 (T2D GWAS): 19/20 citation fields valid (95%), 5/5 manual spot-check verbatim ✅
- 19915526 (Miller syndrome): 12/18 valid (67%) ✅
Both exceed the ≥60% acceptance criterion. Stochastic LLM compliance causes run-to-run variance
(0.32±0.45 mean coverage on 17463248) but when citations are provided they are accurate.
See `AUDIT.md ## Benchmark Results (P0-A + P0-C) → P0-C citation spot-check`.

**Acceptance criteria:** Manual spot-check documented. Citation grounding rate on molecular
genetics papers recorded in AUDIT.md. Known-good rate ≥60% on papers with explicit prose findings.

---

## P1 — Architecture-freeze prerequisites

### P1-A · Remove dead `enable_abstract_discovery` variable ✅ Done (2026-02-25, commit 0f2d15bc)

**Why it's P1:** `pipeline_orchestrator.py` contained `enable_abstract_discovery = False`
with a comment "per user request" but the variable was never read.

**Acceptance criteria:** `enable_abstract_discovery` does not appear anywhere in the codebase ✅.
(Verified: `grep -r enable_abstract_discovery python/modules/` → no output)

---

### P1-B · pytest suite with cached fixtures ✅ Done (2026-02-25, commit 58fcc239)

**Why it's P1:** SoftwareX reviewers expect reproducible, runnable code. Zero tests is an
immediate credibility concern. Also: multiple silent regressions have occurred in these sessions
(citation validator silent TypeError for months, grounding check using wrong label set) that
tests would have caught before merging.

**Goal:** One test per pipeline stage using cached API responses. Must pass in CI without
a Gemini API key, NCBI email, or network access.

**Execution:**
1. Create `local_pivot/python/tests/` with `__init__.py` and `conftest.py`.
2. Create `local_pivot/python/tests/fixtures/` with cached responses:
   - `pmc_efetch_34876594.xml` — raw PMC XML for one paper
   - `pubtator_34876594.json` — PubTator batch response for one PMID
   - `gemini_stage1_response.json` — cached Gemini gene discovery response
   - `gemini_stage3_response.json` — cached Gemini detail extraction response
3. Write the following test files:
   - `test_abstract_screener.py` — known-good molecular genetics abstract scores ≥5;
     known-bad (pure epidemiology) scores <5.
   - `test_gene_validator.py` — valid HGNC symbol (BRCA1) validates to confidence 1.0;
     invalid symbol fails; alias resolution (BNP→NPPB) works; citation grounding on a
     verbatim quote returns True, on a paraphrase returns False.
   - `test_full_text_fetcher.py` — PMC XML parse produces section dict with non-empty
     `results` and `abstract` keys; table text is extracted.
   - `test_pubtator.py` — batch response parse returns expected gene list.
   - `test_pipeline_orchestrator.py` — smoke test: orchestrator instantiates without error;
     `run_complete_pipeline` with mocked workers returns a DataFrame.
4. Add `[tool.pytest.ini_options]` to `pyproject.toml` pointing at `tests/`.
5. Add `pytest python/tests/` to the `/verify` slash command in `.claude/commands/verify.md`.
6. Add pytest run to GitHub Actions CI workflow.

**Acceptance criteria:** `pytest local_pivot/python/tests/` passes with no env vars set.
All 5 test files exist. CI runs tests on push to main.

---

### P1-C · Abstract screening threshold calibration ✅ Done (2026-02-25)

**Why it's P1:** The threshold (score ≥5) was calibrated on one MIS-C paper. For the
benchmark run (P0-A), every false-negative (good paper screened out) is a silent gap in
the reported recall. Calibration must happen before the benchmark, not after.

**Goal:** Verify that all benchmark papers pass the screener. Adjust threshold if any
molecular genetics paper is incorrectly rejected.

**Execution:**
1. Write a small script (or use Python REPL) to run `abstract_screener.should_process()`
   on all benchmark paper abstracts + titles. Log the score for each.
2. Also run on 10 clearly-irrelevant papers (psychology, nutrition, epidemiology).
3. Inspect results:
   - Any benchmark paper scoring <5: lower threshold or add missing keywords to the
     positive scoring list (e.g., if a CRISPR screen paper is rejected, add 'screen' keyword).
   - Any irrelevant paper scoring ≥5: raise threshold or add negative keywords.
4. Document final threshold and calibration set in AUDIT.md.

**Acceptance criteria:** All benchmark molecular genetics papers pass screening.
Zero false negatives in the benchmark set. Threshold + calibration documented in AUDIT.md.

---

### P1-D · Disambiguation clause benchmark ✅ Done (2026-02-26)

**Why it's P1:** The clinical-vs-molecular disambiguation clause (C18) is a core precision
mechanism. The paper needs a number: "the disambiguation clause reduced false-positive clinical
biomarker genes by X% on clinical papers while preserving Y% of molecular gene findings."

**Status (2026-02-26):** Complete. 10 papers benchmarked (5 clinical + 5 molecular), 3 runs each.
- **Molecular false negatives: 0/5** — ESR1 (breast cancer) and ACE (pharmacogenomics, including
  adversarial dual-sense paper with both gene AND enzyme measurements) correctly extracted in all runs.
- **Clinical false positives: 4/5 papers had ≥1 FP** — CRP is the persistent failure case.
  The 1 clean paper (34876594, MIS-C) satisfies the acceptance criterion.
- Key finding: the clause reliably distinguishes structural false-positive scenarios (ESR → ESR1,
  ACE gene vs enzyme) but struggles with inflammatory-disease papers where CRP/IL6 are both
  measured clinically AND relevant molecularly.

**Commit:** See `AUDIT.md ## Disambiguation Benchmark (P1-D, 2026-02-26)`.
**Results JSON:** `python/data/benchmark/disambiguation_results.json`

**Acceptance criteria:**
- Benchmark results documented ✅
- Clause confirmed not to cause false negatives on molecular genetics papers ✅ (0/5 FN)
- At least one clinical paper produces 0 clinical-lab gene rows ✅ (34876594 MIS-C)

---

### P1-E · pyproject.toml with ruff and mypy ✅ Done (2026-02-25)

**Why it's P1:** Open-source code quality signal. SoftwareX reviewers will clone the repo
and inspect the code.

**Acceptance criteria:** `pyproject.toml` present at `local_pivot/python/` ✅. Ruff, mypy, and
pytest configured ✅.

---

## P2 — Paper depth

### P2-A · Figure extraction benchmark ✅ Done (2026-02-26)

**Why P2:** Figure analysis (Gemini Vision on PMC figures) is implemented but unvalidated.
The paper claims it as a feature. A reviewer will ask: "does this actually improve recall?"
Need at least one paper where the answer is demonstrably yes.

**Status (2026-02-26):** Complete. 4 papers benchmarked (figure_on vs figure_off, 1–3 runs each).
- **166 total figure-only genes across 3/4 papers** ✅
- **24132290 (pan-cancer oncoprint): 130 figure-only genes** ✅ — canonical result; the SMG heatmap
  contains 127 labeled gene rows that the text-only pipeline completely misses (PubTator found only
  CTNNB1; figure analysis recovered KRAS, PTEN, TP53, APC, and 126 others)
- **23000897 (TCGA breast oncoprint): 1 figure-only gene (NCOR1)** ✅
- **21720365 (TCGA ovarian): 0 figure-only genes** — as expected; pipeline already achieves 100% text recall
- **32416070 (COVID RNA-seq): 0 figure-only genes** — IL6 only in both conditions; API rate limits
  likely prevented full figure vision analysis

**Infrastructure fixes required before benchmark could run:**
- PMC CDN URL resolution: `_resolve_pmc_cdn_url()` added to `gemini_extractor.py`
- Gemini Vision 429 retry-with-backoff + 4s inter-call delay
- `llm_figure` grounding bypass (RED FLAG 2 — figure genes were silently dropped)
- Panel deduplication fix in `full_text_fetcher.py`

**Commit:** See `AUDIT.md ## Figure Extraction Benchmark (P2-A, 2026-02-26)`.

**Acceptance criteria:** ≥1 gene found exclusively via figure analysis on ≥1 paper ✅
(131 figure-only genes across 2 papers). Documented in AUDIT.md ✅.

---

### P2-B · Multi-run citation coverage metric ✅ Done (2026-02-25, commit fbbcca9c)

**Why P2:** Citation scores fluctuate 0/8–8/8 on the same paper due to stochastic LLM
compliance (C22, L16). Single-run point estimates are unreliable for paper reporting.
Mean ± std across N runs is the correct metric.

**Goal:** Extend `repeatability_check.py` to aggregate citation coverage across runs and
report mean ± std alongside Jaccard gene-set stability.

**Execution:**
1. In `python/scripts/repeatability_check.py`, after each run parse the output CSV for
   `*_citation_valid` columns.
2. For each run: `coverage = sum(True values) / count(non-empty citation fields)`.
3. After all runs: compute `mean(coverage)` and `std(coverage)`.
4. Add to the printed summary: `Citation coverage: {mean:.2f} ± {std:.2f} (n={runs})`.
5. Test on a molecular genetics benchmark paper from P0-A.

**Acceptance criteria:** `repeatability_check.py --runs 5` reports both Jaccard and
citation coverage with std. Output documented for at least one benchmark paper.

---

### P2-C · README for local_pivot/ ✅ Done (2026-02-25)

**Why P2:** Required for open-source release and SoftwareX submission.

**Acceptance criteria:** `local_pivot/README.md` present ✅. Covers all 10 required sections ✅.

---

## P3 — Pre-submission (new items from Elicit gap analysis, 2026-03-09)

### P3-A · Expand benchmark to 20-30 papers 🔴 Blocking

**Why it's P3-A (blocking):** Elicit benchmarked 58 systematic reviews for screening and ~128 gold
standard answers for extraction. RS's 12-paper benchmark is statistically underpowered — SoftwareX
reviewers will notice. Need 20-30 papers with external validation from a domain expert (Suski).

**Goal:** Add 8-18 papers to `gold_standard.json` covering rare disease, pharmacogenomics, RNA-seq,
and multi-ethnic GWAS. Have Suski independently verify gold standard gene lists for ≥3 papers.

**Acceptance criteria:** ≥20 papers in benchmark. ≥3 externally validated. Updated F1 numbers in paper.

---

### P3-B · Citation smoke test

**Why it matters:** The citation validator silently returned False/0.0 for months (C19). A single
regression test on known-good input prevents this from recurring.

**Goal:** Add a test asserting >0 citations validate True on PMID 17463248 (T2D GWAS, 95% accuracy).

**Acceptance criteria:** `pytest python/tests/test_gene_validator.py::test_citation_smoke` passes.

---

### P3-C · Document Elicit-identified limitations in paper

**Why it matters:** Honest comparison with Elicit strengthens the paper. Reviewers respect
self-awareness of gaps more than omission.

**Goal:** Add to paper Section 6 (Limitations): (a) no search quality eval pipeline, (b) benchmark
underpowered vs commercial tools, (c) single-shot batch vs interactive workspace, (d) gene-relevance
screening is hardcoded vs user-defined criteria.

**Acceptance criteria:** Four limitation paragraphs in `publication/main.tex` Section 6.

---

### P3-D · Future work items (document in paper, do not implement)

These items emerged from the Elicit competitive analysis. They are out of scope for SoftwareX
but should be mentioned as future work directions:

- **Claim-level verification for Key Findings** — factored verification (Elicit's approach) applied
  to free-text extraction fields
- **LLM-assisted PubMed query construction** — use Gemini + HGNC aliases to expand user queries
- **ClinicalTrials.gov integration** — trials as first-class data source (highest-value for pharmacogenomics)
- **Cross-run CSV aggregation UI** — notebook-style result exploration across multiple pipeline runs

**Acceptance criteria:** Future work section in paper mentions all 4 directions.

---

## P4 — Polish (carry-forward from previous P3)

- **`--runs` flag on repeatability harness** — currently hardcoded, should be a CLI arg. 5-minute fix.
- **HGNC snapshot refresh** — the bundled `hgnc_genes.json` was generated at 44,933 genes.
  Refresh before submission to capture genes approved in 2025–2026.
- **Full forensic run-analytics** ✅ Done (2026-02-28) — per-stage artifact persistence implemented.
- **Table-aware citation path** ✅ Done (2026-02-28) — `StructuredTable` extraction + table-cell validation.

---

## Current state summary (as of 2026-03-09)

> Updated after Elicit competitive analysis (12 articles). See `publication/elicit_research/README.md`.

| Component | Status |
|-----------|--------|
| Pipeline architecture (7 stages) | ✅ Stable |
| Multi-source gene discovery (LLM + PubTator + lexicon) | ✅ Working |
| Hallucination controls (grounding check, validation gate, corroboration gate) | ✅ Working |
| Clinical-vs-molecular disambiguation | ✅ Working (stochastic, but confirmed end-to-end) |
| Citation validation | ✅ Working (confirmed post-C19 fix) |
| Citation encoding normalization | ✅ Fixed (C22) |
| Electron desktop app (UI, IPC, Python bridge) | ✅ Working |
| GitHub Actions build (macOS/Windows/Linux) | ✅ Working |
| Benchmark dataset | ⚠️ 12 papers done — needs expansion to 20-30 (P3-A) |
| pytest test suite | ✅ Done (47 tests, all offline) |
| LICENSE file | ✅ Done |
| README | ✅ Done (local_pivot/README.md) |
| pyproject.toml | ✅ Done |
| Abstract screener calibration | ✅ Done (5/5 pass, 10/10 reject, threshold=5 confirmed) |
| Disambiguation clause benchmark | ✅ Done (P1-D: 0/5 molecular FN, 1/5 clinical FP-free) |
| Citation validation on real genetics papers | ✅ Done (P0-C: 95% accuracy on T2D GWAS) |
| Figure extraction benchmark | ✅ Done (P2-A: 166 figure-only genes across 3/4 papers; oncoprint 130×, COVID volcano 35×) |
| Figure-on vs figure-off controlled F1 comparison | ✅ Done (A4 YELLOW #4, 2026-03-03: 36 runs, ΔF1=+0.833 on GBM) |
| Elicit competitive analysis | ✅ Done (2026-03-09: 12 articles, `publication/elicit_research/`) |
| Inter-rater reliability | ⬜ Pending (Suski — A3 RED #4) |
| Paper co-author sections | ⬜ Pending (Suski: bio methods; Gorski: AI methods + reproducibility) |
| Windows EXE build | ⬜ Pending |
