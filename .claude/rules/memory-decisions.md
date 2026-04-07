# memory-decisions.md — Architectural Decisions

> Append new decisions with date. Never delete entries — they explain why code is the way it is.

---

## 2026-04-07 — Pipeline cancellation remains single-flight until child exit

**Decision:** Keep `currentProcess` and `currentJobId` populated after a cancel request until the Python child actually emits `close`/`error`. Do not clear bridge state immediately after `SIGTERM`.
**Rationale:** Pipeline IPC events are broadcast on global `pipeline:*` channels with no job ID. Clearing bridge state early allowed a new run to start while the old process was still draining, which could mix stale logs/progress/results into the next run. The bridge must remain busy until shutdown completes.
**Files:** `src/main/python-bridge.ts`

## 2026-04-07 — Persist auxiliary artifact paths in jobs.db

**Decision:** Store `metadata_path`, `excel_path`, and `json_path` alongside `result_path` in the local jobs database, with a startup migration that adds missing columns for existing installs.
**Rationale:** The Results page needs those paths to reopen metadata and export artifacts from historical runs. Persisting only the primary CSV path silently degraded old runs when opened from History.
**Files:** `src/main/job-store.ts`, `src/main/python-bridge.ts`, `src/renderer/pages/History.tsx`, `src/preload/index.ts`, `src/renderer/hooks/useJobHistory.ts`

## 2026-04-07 — Query-builder Gemini model ID explicitly verified

**Decision:** Treat `gemini-2.5-flash-lite` in the PubMed query-builder IPC path as an explicitly verified model ID, not an inferred replacement.
**Rationale:** `CLAUDE.md` forbids guessing model names because stale IDs fail at runtime. The model was checked after review and confirmed valid/stable, so the current hardcoded query-builder endpoint is acceptable until it is next intentionally revised.
**Files:** `src/main/ipc-handlers.ts`

## 2026-03-15 — Gold standard v2 schema: agent team backfill strategy

**Decision:** Use one Sonnet background agent per paper to backfill `expected_genes_comprehensive`. Each agent independently runs PubTator + pubmed_gene eLink + PMC full text and saves to `/tmp/backfill/{PMID}.json`. Human reviews all results before writing to `gold_standard.json`.
**Rationale:** Parallelism is safe here because papers are independent. Keeping output in temp files (not directly writing to gold_standard) forces human review before committing. The three-source cross-reference (PT/PG/FT) is the same methodology as the annotate-paper skill.
**Files:** `python/data/benchmark/gold_standard.json`

## 2026-03-15 — OA indicator uses pmc field presence, not esummary availablefull

**Decision:** Show "Full text" / "Abstract only" badge based on whether `pmc` field is populated in the fetchDetails response, rather than trying to extract `availablefull`/`freefull` from esummary.
**Rationale:** The PubMed search already applies `"loattrfull text"[sb]`, so results are pre-filtered for OA. The `pmc` field (PMC ID) is the clearest signal that PMC full text is accessible — if PMC ID exists, the pipeline can fetch it. The `availablefull` esummary field is less reliable.
**Files:** `src/renderer/components/TopicResultsModal.tsx`

## 2026-03-15 — Publication type from esummary pubtype, not query-time filter

**Decision:** Expose `publicationTypes` per paper by extracting `d.pubtype` in the `fetchDetails` IPC handler and threading it through to the UI for display. Previously, publication type filtering was applied only at query-build time (as a NOT clause) and was invisible per-paper.
**Rationale:** Users need to see which papers are reviews/meta-analyses so they can make informed selection decisions. The query filter catches most reviews but some slip through. Showing a per-paper badge is more transparent than silently filtering.
**Files:** `src/main/ipc-handlers.ts`, `src/preload/index.ts`, `src/renderer/components/TopicResultsModal.tsx`

---

## 2026-03-14 — `/annotate-paper` Skill for Automated Gold Standard Creation

### Automated gold standard creation over manual curation
**Decision:** Build a Claude Code skill (`/annotate-paper <PMID>`) that automates benchmark gold
standard entry creation using PubMed MCP + Playwright figure extraction + Claude multimodal analysis.
**Rationale:** Scaling from 12 to 24-30 papers manually is slow and inconsistent. The skill ensures
every entry follows the same gene inclusion criteria (from BENCHMARK_EXPANSION_PLAN.md) and produces
verbatim source quotes. User reviews the entry before it's appended to gold_standard.json.
**Workflow:** metadata/OA check (4 parallel MCP calls) → full text → Playwright figure screenshots
→ Claude reads figures → gene inclusion decision → classify type → user review → append.
**Files:** `.claude/commands/annotate-paper.md`, `python/scripts/extract_pmc_figures.js`

### Playwright figure extraction: element-level screenshots, not full-page
**Decision:** Use a Node.js Playwright script that navigates to PMC, finds `<figure>` elements,
and screenshots each individually — rather than Playwright CLI `--full-page` screenshots.
**Rationale:** PMC articles can be 30+ printed pages. Full-page screenshots are too large and
low-resolution for figure details (oncoprint gene labels, volcano plot dots). Element-level
screenshots capture each figure at native resolution.
**Lazy-loading fix:** PMC uses `loading="lazy"` on images. Script removes this attribute, copies
`data-src` → `src`, and waits for `naturalWidth > 0` (browser image decode complete) with 8s timeout.
**Files:** `python/scripts/extract_pmc_figures.js`

### Benchmark expansion workflow: create-then-validate
**Decision:** Michal creates ALL gold standard entries (using `/annotate-paper`), Suski validates
and corrects them. Her corrections serve as the independent assessment for Cohen's κ.
**Rationale:** Creating gold standards from scratch requires reading full PMC text — easier for
the tool builder who knows the gene inclusion criteria. Validation/correction is faster for the
domain expert and still provides the inter-rater reliability metric needed for SoftwareX.
**Previous plan:** Suski creates gold standards for ~half the new papers independently.

### BENCHMARK_EXPANSION_PLAN.md PMCID error caught
**Finding:** PMC2848885 was listed as the PMCID for PMID 18650507 (SEARCH simvastatin study).
It actually maps to PMID 20083201. The SEARCH study is paywalled NEJM with no PMC deposit.
Replaced with CPIC guideline PMID 35152405 (PMC9035072, 3 genes: SLCO1B1, ABCG2, CYP2C9).
**Action:** Updated gold_standard.json with correct replacement paper. Notes field documents
the PMCID error for audit trail.

---

## 2026-03-03 — Figure Analysis: Precision Anchor Effect (Benchmark Finding)

### Figure analysis improves precision, not just recall

**Finding:** In the controlled 36-run figure-on vs figure-off benchmark, the primary measurable
effect of `ENABLE_FIGURE_ANALYSIS` is **precision improvement and extraction stability**, not
recall uplift as originally hypothesised.

**Key result:** PMID 20129251 (Verhaak 2010 GBM): F1-on=1.000 vs F1-off=0.167, ΔF1=+0.833.
Figure_ON extracted exactly 4 gold-standard genes (Jaccard=1.0 across 3 runs). Figure_OFF
extracted 44 genes in union (Jaccard=0.091) — 40 false positives, stochastically variable.

**Mechanism:** Figures in comprehensive genomics papers (subtype classification diagrams,
oncoprints) prominently display only the primary driver/finding genes. Figure analysis extracts
these as high-confidence seed candidates. Via `ENABLE_DETERMINISTIC_CANDIDATES`, these seeds
anchor Stage 3 LLM text extraction — preventing the model from enumerating the hundreds of
genes mentioned incidentally in a comprehensive paper's methods, background, and pathway discussion.
Figures encode the authors' own editorial prioritization of their findings, and the pipeline
inherits that editorial judgment.

**Where the effect is absent:**
- Cancer genomics papers where primary genes are unambiguously named in prose (TCGA ovarian,
  TCGA breast): ΔF1=0 — text extraction is already sufficient.
- GWAS papers (Manhattan plots have no gene labels): ΔF1=0 — control verified.

**Implication for SoftwareX paper:** Figure analysis is most valuable for:
1. Subtype-classification / integrated-genomics papers (GBM, pan-cancer) — figures are the
   editorial summary of primary findings
2. RNA-seq / transcriptomics papers where DEGs appear as labeled volcano plot points, not prose
It is least impactful on GWAS and text-first driver-mutation papers.

**Distinction from P2-A single-run benchmark (2026-02-26):** P2-A found 166 figure-only genes
across 4 papers using single runs. The 3-run controlled design reveals those are stochastic
single-run findings that don't replicate. The stable, multi-run contribution of figure analysis
is the precision/repeatability improvement, not additive unique gene discovery.

**Files:** `python/data/benchmark/benchmark_figure_comparison.csv`, `AUDIT.md §Figure-On vs
Figure-Off Controlled F1 Benchmark`

---

## 2026-02-28 — Post-FDA Audit Wave 1

### Display-layer confidence badge rename (HIGH → CORROBORATED)
**Decision:** Rename the confidence badge from HIGH to CORROBORATED in the UI display only.
The CSV pipeline continues to output `HIGH`. A `normalizeConfLevel()` adapter in `Results.tsx`
bridges the gap.
**Rationale:** Changing the pipeline output would break all existing CSV files users have saved.
The rename is cosmetic — it clarifies that "HIGH" means multi-source corroboration, not clinical
validation. The translation belongs at the UI boundary, not in the data layer.
**Files:** `Results.tsx` (`normalizeConfLevel`, `CONFIDENCE_STYLES`, `CONFIDENCE_TOOLTIPS`)

### Figure-derived genes require caption grounding, not blind pass-through
**Decision:** `llm_figure` genes in the grounding check must match at least one figure
caption/label text before being accepted. Previously they bypassed all grounding checks.
**Rationale:** Figure analysis extracts genes from rasterized images via Gemini — these are
more hallucination-prone than text extraction. A lightweight caption/label check provides
a safety floor without requiring the full prose-matching pipeline (which would be structurally
wrong for image-derived genes).
**Files:** `gemini_extractor.py:1361–1385`

---

## 2026-02-24 — Bootstrapped from AUDIT.md

### Hybrid NER + LLM architecture
**Decision:** Use PubTator3 (NER, high precision) as seed + Gemini Flash (LLM, high recall) for extraction.
**Rationale:** Neither alone is sufficient. PubTator misses context and relationships. LLM alone hallucinates.
Combining gives precision floor + recall ceiling.
**Files:** `pubtator_tool.py`, `gemini_extractor.py`, `pipeline_orchestrator.py`

### Desktop-first, no server
**Decision:** Ship as Electron app, users bring their own Gemini API key. No backend infrastructure.
**Rationale:** Privacy (data never leaves local machine), zero cost to user, no auth/payments complexity.
**Tradeoff:** Users must manage their own API key; no usage analytics.

### OA-only paper access
**Decision:** Fetch full text only from PMC Entrez and Europe PMC (open-access). No paywall bypass.
**Rationale:** Legal clarity, reliability, simplicity. Playwright/publisher-specific scrapers were dead code
and a maintenance burden (removed in F5 fix).
**Implication:** ~40–60% of PubMed papers skipped due to paywall; mitigated by overfetch factor (4x).

### Local HGNC database bundled
**Decision:** Ship `hgnc_genes.json` (44,933 genes, 6.6 MB) inside the app.
**Rationale:** Offline validation, no API dependency for core gene checking, fast lookups.
**Maintenance:** Must regenerate if HGNC data becomes stale (update `gene_validator.py` accordingly).

### Two-stage Gemini pipeline
**Decision:** Stage 1 = Flash on abstract (fast discovery), Stage 2 = Flash on full text (detailed extraction).
**Rationale:** Abstracts are cheap to screen; full-text tokens are expensive. Avoids wasting quota on
papers that won't yield results.

### Multiprocessing worker pool
**Decision:** 2–4 persistent worker processes for parallel paper analysis (not per-paper spawning).
**Rationale:** Avoids spawn overhead on each paper. Workers stay alive across papers in a run.
**Config:** `AI_WORKER_POOL_SIZE=2` default; `AI_PER_PAPER_TIMEOUT_SECONDS=600`.

### Secrets via environment variables only
**Decision:** `GEMINI_API_KEY` and `ENTREZ_EMAIL` passed as env vars to spawned Python process.
**Rationale:** CLI args appear in `ps aux` output on multi-user systems. Env vars are scoped to process.

### Deterministic candidate seeding + strict gate
**Decision:** `ENABLE_DETERMINISTIC_CANDIDATES=True`, `FINAL_VALIDATION_MIN_CONFIDENCE=0.7`
**Rationale:** Reduces LLM hallucination. Genes not found in fetched paper text are dropped
(grounding check). Confidence gate ensures only validated genes reach CSV output.

### iCite primary + Semantic Scholar fallback for citation ranking
**Decision:** Fetch citation counts from iCite first; fall back to Semantic Scholar on failure.
**Rationale:** iCite is NIH-maintained and stable. Semantic Scholar has rate limits (0.2s delay, 5s backoff
on 429). Dual-sourcing ensures ranking works even if one API is down (C1 from AUDIT).

### Abstract screening moved from pipeline to UI (2026-03-02)
**Decision:** Abstract screening no longer filters papers inside the pipeline. Instead, the TypeScript
gene-relevance scorer (`geneRelevanceScorer.ts`) runs in the Electron renderer during the paper
selection modal (TopicResultsModal). Low-relevance papers are hidden by default with a "Show all"
toggle. The pipeline trusts the user's final selection — no silent post-submission filtering.
**Rationale:** The screener was silently dropping papers the user had explicitly selected, which is
bad UX for genomics researchers who hand-pick papers for analysis. Moving screening to the UI gives
users transparent control: they see relevance badges, can override the filter, and the pipeline
respects their choices.
**Implementation:**
- `geneRelevanceScorer.ts`: TypeScript port of Python screener (keyword scoring + gene regex + molecular-context gate)
- `TopicResultsModal.tsx`: fetches abstracts via `pubmed:fetch-abstracts` IPC, scores each paper, auto-selects high/medium, hides low/none
- `ipc-handlers.ts`: new `pubmed:fetch-abstracts` endpoint (PubMed efetch XML API, batched 200)
- `pipeline_orchestrator.py`: screening is now a pass-through (forensic logging preserved for debug artifacts)
- `run_pipeline.py`: `--skip-abstract-screening` flag removed (no longer needed)
**Previous state:** `abstract_screener.py` used weighted keyword scoring (threshold ≥ 5) inside the pipeline.
The Python scorer and its tests are retained for reference/benchmarking but no longer gate papers.

### Molecular-context precision gate (2026-03-02)
**Decision:** Added `MOLECULAR_CONTEXT_TERMS` to `abstract_screener.py` — papers with gene-like
symbols (IL6, CRP, BNP) but no unambiguously molecular terms (mutation, variant, sequencing, gwas,
etc.) receive a score penalty (`gene_count + 3`).
**Rationale:** Clinical outcome papers mention biomarker abbreviations that match gene symbol patterns
but discuss lab test values, not molecular genetics. The penalty prevents these from scoring above
the relevance threshold. Calibrated: 5/5 molecular genetics papers unaffected, 10/10 irrelevant
papers correctly rejected.
**Files:** `abstract_screener.py`, `test_abstract_screener.py` (2 new test cases)

### AUDIT.md as quality source of truth
**Decision:** All pipeline bugs, fixes, and known tradeoffs are documented in `AUDIT.md`.
**Protocol:** Update `AUDIT.md` synchronously whenever pipeline modules change. Never let it drift.

---

## 2026-02-23 — Trust-gap hardening sessions (C7–C21)

### Prompt-based disambiguation over static blocklists for clinical-vs-gene abbreviations
**Decision:** Do NOT maintain a static list of clinical abbreviations to block (ESR, AST, CRP, etc.).
Instead, use a Stage 1 LLM prompt clause that asks the model to distinguish clinical measurement
context from molecular genetics context by reading the sentence.
**Rationale:** A blocklist derived from one paper's false positives blocks correct extractions in
other paper types (ESR1 in breast cancer, KLK3/PSA in prostate cancer, ACE in pharmacogenomics,
GOT1/AST in liver genetics). This was formally identified by an FDA auditor reviewing the initial implementation.
**Tradeoff:** The LLM clause is stochastic — not 100% reliable across runs. The corroboration gate
provides a hard backstop: when the LLM correctly refuses to extract a clinical biomarker, the gene
falls to `deterministic_lexicon`-only and the corroboration gate drops it.
**Files:** `gemini_extractor.py` Stage 1 prompt (commit `c0bcca26`), `gene_validator.py`

### Per-source evidence gate thresholds
**Decision:** LLM-sourced rows pass the evidence gate with min=0 (LLM translation is inherent evidence).
Deterministic-only rows require min=1 (symbol matching needs textual corroboration).
**Rationale:** Treating all rows identically caused valid LLM extractions to be dropped when
backfill also failed (gene mentioned by natural language name, no literal symbol in text).
**Files:** `gemini_extractor.py` `_apply_evidence_gate()`, `config.py`

---

## 2026-02-25 — Gemini usage bar: live state vs IPC round-trip

### Compute live UI values from React state, not IPC
**Decision:** When a value already exists in React state (e.g. `stats.gemini_api_calls` updated on
each `PROGRESS` event), compute the display value directly from that state rather than making an
IPC round-trip to the main process to re-read from the electron-store.
**Rationale:** IPC is asynchronous — the renderer invokes the handler, waits for the main process
to respond, and the result only arrives after the next render cycle. Calling IPC on every progress
tick introduces per-tick lag and race conditions. React state is synchronous within the renderer
and reflects PROGRESS events immediately.
**Pattern:**
```tsx
// BAD — IPC round-trip per tick, laggy
useEffect(() => { refreshUsageFromStore() }, [stats.gemini_api_calls])

// GOOD — direct React state, instant
const displayUsed = (persistedBaseline?.used ?? 0) + (isRunning ? (stats.gemini_api_calls ?? 0) : 0)
```
**Rule:** Use IPC (electron-store reads) only for: (1) initial load on mount, (2) after run completion
to sync the persisted total. Use colocated React state for all live display during a run.
**Files:** `src/renderer/pages/Pipeline.tsx`, `src/main/usage-store.ts`, `src/main/python-bridge.ts`

---

## 2026-02-25 — Citation encoding sprint (C22)

### Symmetric encoding normalization before citation matching
**Decision:** When comparing LLM citations against paper text, normalize BOTH strings with the same
function before any character-level matching. Never normalize only one side.
**Rationale:** Encoding artifacts (Unicode slash variants, LaTeX commands, ASCII mu prefix) can
appear in either the paper text (PDF encoding) OR the LLM output (training data transcription).
Normalizing only citations leaves the paper-text variant unmatched; normalizing only paper text
leaves the LLM-output variant unmatched. Both sides must be brought to the same canonical form.
**Implementation:** `_normalize_unicode_slashes()` in `gene_validator.py` — covers 4 slash variants,
LaTeX Greek commands (`\upmu`, `\alpha`, etc.), ASCII `mu ` prefix regex, U+00B5 unification.
Applied at the top of `_citation_exists_in_paper()` before any matching step.
**Files:** `gene_validator.py` (commit `50144109`, `055a84e4`, `e336893c`)

### Stage 3 CRITICAL INSTRUCTIONS: accumulation over replacement
**Decision:** Stage 3 prompt instructions in `gemini_extractor.py` are additive — each new
constraint appended without removing previous ones. Currently 9 instructions covering verbatim
quoting, unit copying, ellipsis prohibition, table-cell avoidance, gene-named requirements,
adjacency constraints, and independent row filling.
**Rationale:** Each instruction targets a specific observed failure mode. Removing any one can
reintroduce its failure mode. However, more instructions increase prompt length and potential
for instruction-interaction conflicts.
**Known risk:** At high instruction count, prompt engineering yields diminishing returns and
a post-extraction validation schema becomes more reliable. Monitor instruction count across sessions.
**Files:** `gemini_extractor.py` Stage 3 prompt block (lines ~967–981)

---

## 2026-02-28 — Genomics correctness cluster (#12, #13)

### Biotype filtering: soft gate, not hard drop
**Decision:** Non-protein-coding genes (pseudogenes, lncRNAs, miRNAs) get confidence reduced to 0.5
(below the 0.7 strict gate) rather than being hard-dropped from the pipeline.
**Rationale:** With strict gate ON (default): non-coding genes are filtered out automatically.
With strict gate OFF: non-coding genes appear with `non_coding:{locus_type}` annotation in
`validation_source`. Users studying lncRNAs can set `VALIDATE_PROTEIN_CODING_ONLY=false`.
**Tradeoff:** Soft gating adds complexity vs. hard drops, but preserves optionality for
non-coding RNA researchers. The HGNC database has 25,638 non-protein-coding entries (57%)
that were previously accepted without annotation.
**Files:** `config.py`, `gene_validator.py`

### Mouse symbol flag is informational, not blocking
**Decision:** Title-case symbols (`Brca1`, `Tp53`) that resolve to human HGNC genes are flagged
with `potential_murine_symbol` in `validation_source` but not penalized in confidence.
**Rationale:** A lowercase-initial symbol may be a legitimate human gene written in mouse
convention by the paper authors. Blocking it would create false negatives. The flag lets
downstream consumers (researchers, reviewers) investigate.
**Files:** `gene_validator.py`

### Stage 1 prompt: human protein-coding focus
**Decision:** Added two sentences to Stage 1 (abstract gene discovery) prompt: focus on human
protein-coding genes, exclude model organism genes unless mapped to human orthologs, include
non-coding RNA only if primary finding.
**Rationale:** Deliberately concise (2 sentences) per memory-decisions.md principle that "at high
instruction count, prompt engineering yields diminishing returns." The validator-side biotype
filter provides the hard backstop.
**Files:** `gemini_extractor.py` Stage 1 prompt
