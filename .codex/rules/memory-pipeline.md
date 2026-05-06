# memory-pipeline.md — Pipeline Technical Reference

> Codex migration note (2026-04-25): this file is the active pipeline memory for Codex sessions.
> Older wording copied from `archive/claude/` may describe Claude-era history; keep historical entries intact
> unless they are active instructions that should point at `AGENTS.md` or `.codex/`.

> Deep domain reference. Read before modifying any pipeline module.
> Medical accuracy implications are marked ⚕. Audit-tracked items marked 🔍.

---

## Architecture Overview

```
UI: `paper_selection` → `oa_filter`
                         ↓
Pipeline: `paper_reading` → `candidate_discovery` → `detail_extraction` → `validation` → `output_writing`
```

Two precision layers:
- **PubTator** (`candidate_discovery`): high precision / lower recall — forms the safety floor
- **Per-paper Gemini calls**: high recall / lower precision — extend coverage and add relationships
- **Gene Validation** (`validation`): final safety gate before any result reaches the user

Gemini structured outputs are centralized in `pipeline/modules/paper_analysis/schemas.py`.
Abstract, full-text, and figure candidate discovery share the same candidate association
schema; detail extraction builds a dynamic Pydantic schema from the user columns.

**UI-side screening:** Gene relevance scoring runs in the Electron renderer (`geneRelevanceScorer.ts`)
during paper selection. Users see relevance badges; low-relevance papers hidden by default with
"Show all" toggle. Pipeline trusts user's selection — no silent filtering.

---

## `paper_selection` — PubMed Search (`pubmed_data_collector.py`)

**What it does:** Queries NCBI Entrez for papers matching the user's query or PMID list. Ranks results by
citation count using iCite (primary) and Semantic Scholar (fallback). Returns top-N most-cited records.

**Inputs:** query string | list of PMIDs | author name
**Outputs:** list of normalised records (PMID, title, authors, abstract, journal, DOI, year, citation_count)

**Key filters applied here:**
- Publication type exclusion: removes reviews, editorials, guidelines, case reports (toggleable)
- Open-access filter (`ENABLE_OA_FILTER`): restricts to PMC full-text papers
- Year range filter (optional)

**Failure modes:**
- Entrez API rate limit → NCBI requires `ENTREZ_EMAIL`; without it requests may be throttled silently
- Malformed query → returns empty results with no error surfaced to user
- iCite unavailable → falls back to Semantic Scholar; if both fail, results are unranked (no error raised)

⚕ **Medical accuracy implication:** The paper set selected here determines everything downstream.
Ranking by citation count biases toward established findings over emerging ones — this is appropriate for
a literature-synthesis tool but means very recent discoveries in rare diseases may be ranked low.
Overfetch factor (4x target count) mitigates but does not eliminate this.

🔍 **Audit notes:** C1 (iCite primary, Semantic Scholar fallback), F4 (Semantic Scholar rate limiting fixed)

---

## `paper_selection` — Gene Relevance Scoring (UI-side, `geneRelevanceScorer.ts`)

> **Changed 2026-03-02:** `paper_selection` relevance scoring moved from Python pipeline gating to TypeScript UI.
> The Python `abstract_screener.py` module is retained for reference/benchmarking but no longer gates papers in the pipeline.

**What it does:** Free, API-free keyword scoring in the Electron renderer. Runs during the paper
selection modal (TopicResultsModal) after fetching abstracts via `pubmed:fetch-abstracts` IPC.
Returns `{ score, tier, geneSymbols, topKeywords, hasMolecularContext }`.

**Inputs:** abstract text + title (fetched via PubMed efetch XML API)
**Outputs:** relevance tier (high/medium/low/none) + score breakdown

**Scoring system (same logic as Python screener):**
- Positive (high weight): mutation +3, variant +3, snp +3, gene expression +2, genotype +2, CRISPR, GWAS...
- Positive (low weight): biomarker +1, therapy +1, treatment +1...
- Negative: systematic review −5, meta-analysis −5, psychological −3, quality of life −2, policy −2...
- Gene symbol regex: matches known gene patterns (BRCA1, TP53, IL6) with false-positive filter
- **Molecular-context precision gate:** papers with gene-like symbols but no molecular terms
  (mutation, variant, sequencing, etc.) receive a penalty to avoid clinical biomarker false positives

**Tier mapping:** high (≥10), medium (≥5), low (1–4), none (≤0)

**UI behavior:**
- High/medium papers auto-selected; low/none hidden by default
- "Show all (N hidden)" toggle reveals hidden papers with dimmed styling + amber badge
- High-relevance papers get green "Gene content" badge with DNA icon
- Sort dropdown includes "Gene Relevance" option

**Pipeline behavior (pass-through):**
- `pipeline_orchestrator.py` still runs scoring for forensic logging (`ScreeningDecision` records)
- All papers proceed regardless of score — `papers_screened_rejected` is always 0
- Debug artifacts (`drop_debug_{hash}.json`) still contain screening decisions

**Key advantage over previous approach:** Users see the relevance assessment BEFORE submitting papers.
No silent post-selection filtering. Researchers who know a paper is relevant can override the scorer.

🔍 **Audit notes:** F2 (gene symbol blind spot fixed), molecular-context gate (2026-03-02)

---

## `paper_reading` — Full Text Fetch (`full_text_fetcher.py`)

**What it does:** Retrieves structured full-text for OA papers via PMC Entrez JATS XML (preferred)
or Europe PMC fullTextXML (fallback). Parsed XML goes through a `pubmed_parser`
adapter for body paragraphs and figure metadata, with ResearchShop's parser as
fallback. Also extracts figure metadata for multimodal Gemini analysis.

**Inputs:** PMID list
**Outputs:** per-paper dict with sections (abstract, intro, methods, results, discussion, conclusion),
            figure captions + image URLs, raw text

**Strategy chain:**
1. PMC Entrez `efetch` → structured JATS XML (preferred, section-aware)
2. Europe PMC fullTextXML → alternative OA endpoint
3. `pubmed_parser` adapter → standard paragraph + figure-caption parsing; current parser remains fallback
3. Supplementary file extraction (tables, data files — max 3 files, 200 KB each)

**Failure modes:**
- PMC JATS not available for paper → tries Europe PMC; if no OA full text is fetched, the run emits metadata-only rows
- Section parsing failure → returns raw concatenated text, losing structural signals
- Context window exceeded → text is truncated (preserves abstract > intro > results > discussion)
- Greek letter destruction (pre-W1): α/β/γ were stripped as non-ASCII; now transliterated

⚕ **Medical accuracy implication:** Gene variants are frequently described using Greek letters (α-globin,
β-thalassemia). Destroying these creates incorrect variant strings. W1 fix is critical for haematology
and protein biology papers. Verify this fix is intact before any text processing changes.

**OA-only by design:** No paywall bypass. ~40–60% of PubMed papers are behind paywalls and will
not receive automated extraction. This is a deliberate design choice (legal clarity + reliability),
not a gap to be filled with browser automation.

🔍 **Audit notes:** F5 (Playwright dead code removed), W1 (Greek letter transliteration fixed)

---

## `candidate_discovery` — PubTator NER (`pubtator_tool.py`)

**What it does:** Submits PMIDs to NCBI PubTator3 API for Named Entity Recognition. Returns
high-precision gene symbols and variant text extracted by a dedicated biomedical NER model.
Results are used as seeds for Gemini extraction (not standalone output).

**Inputs:** PMID list (batched, up to 10 per request)
**Outputs:** per-paper `HybridExtractionResult` with `pubtator_genes` and `pubtator_variants`

**Role in hybrid architecture:** PubTator provides the precision floor. Genes it finds are almost
certainly real (biomedical NER trained on annotated literature). LLM is then asked to find
additional genes and add contextual information PubTator cannot provide.

**Failure modes:**
- Batch silent loss (W10): parse errors on individual papers in a batch are silently skipped;
  affected PMIDs produce no PubTator results but pipeline continues — no error raised
- PubTator API outage → pipeline continues with Gemini-only extraction (lower precision)
- Rare/novel genes: PubTator may miss gene symbols not present in its training data;
  this is a known limitation of NER approaches in general

⚕ **Medical accuracy implication:** PubTator is the most reliable signal in the pipeline. If a gene
appears in PubTator output, treat it with high confidence. If it appears only in Gemini output,
it needs grounding check + confidence validation before being trusted.
Disabling PubTator (`ENABLE_PUBTATOR_EXTRACTION=False`) significantly degrades precision.

🔍 **Audit notes:** W10 (batch silent loss — accepted, low impact; rare parse errors)

---

## `candidate_discovery` And `detail_extraction` — Per-Paper Analysis Package (`pipeline/modules/paper_analysis/`)

**What it does:** Per-paper candidate discovery, Gemini extraction, grounding, validation, evidence backfill, and metadata annotation.
- `candidate_discovery`: mandatory full-text Gemini gene discovery, deterministic scans, PubTator merge, and optional abstract/figure/recall passes
- `detail_extraction`: full-text structured extraction with user-defined schema columns

**Architecture:**
- `PaperAnalysisPipeline` class: instantiated per paper by multiprocessing worker
- `pipeline/modules/gemini_extractor.py` is only a compatibility shim exporting legacy aliases to `PaperAnalysisPipeline`
- Inputs: full text + abstract + PubTator seeds + figure metadata + user column schema
- JSON schema prompting: Gemini is given the user's column definitions with BRCA1/TP53 examples

**Key safeguards (do not remove or weaken):**
- **Deterministic candidate seeding** (`ENABLE_DETERMINISTIC_CANDIDATES`): soft gate using PubTator
  results to steer LLM toward known genes, reducing hallucination surface
- **Grounding check** (`ENABLE_GROUNDING_CHECK`): drops any gene not found as text in the fetched
  paper. Uses canonical symbol + all HGNC aliases + raw LLM labels (e.g., "BNP" for NPPB).
  This is the primary hallucination filter. Do not check only the canonical symbol — raw labels are essential.
- **Strict validation gate** (`ENABLE_STRICT_VALIDATION_GATE`): drops genes with confidence < 0.7
- **Evidence backfill**: requires citations + text snippets for extracted claims
- **Disambiguation clause** in the candidate-discovery prompt: instructs LLM not to extract clinical lab test
  abbreviations (ESR mm/h, AST U/L, CRP mg/L) as genes. Works with corroboration gate (see C18/C21).

**Detail-extraction critical instructions (prompt-internal; historically called Stage 3 — do not remove any):**
These instructions in `pipeline/modules/paper_analysis/prompts.py` are accumulated fixes for specific failure modes:
1. Independent row filling per gene (do not leave rows empty because another gene was filled)
2. Verbatim numbers and units — no unit conversion, rounding, or substitution
3. No ellipsis in citations (`...`, `[...]`) — quote only the specific clause, or leave empty
4. PROSE CITATIONS ONLY — no raw table cells, table rows, or number sequences
5. GENE-NAMED CITATIONS — at least one sentence naming the gene/alias; AT MOST ONE adjacent sentence from same paragraph if primary sentence lacks gene name; no reaching into Methods or definitions blocks
6. Separate citation fields from content fields
7. No placeholder text — empty string only
8. Gene/variant name format constraints
9. Do NOT repeat same sentence across variant rows of the same gene

**Failure modes:**
- Hallucination: LLM generates plausible-sounding gene symbols not in the paper.
  Grounding check catches most; confidence gate catches more; some may still pass.
- Clinical-vs-molecular ambiguity: ESR, AST, CRP etc. appear as both lab tests and gene symbols.
  Disambiguation clause is soft (stochastic compliance) — corroboration gate provides hard backstop.
- Table-only papers: LLM correctly leaves citation fields empty when findings are in tables not prose.
  This is correct behaviour, not a bug — but results in zero grounded citations for that gene.
- Citation cross-contamination: LLM synthesises a non-verbatim Key Finding, can't find a matching
  sentence, cites the nearest statistical sentence (which may belong to a different gene).
- W14 (schema examples): BRCA1/TP53 as column examples could bias extraction toward well-known genes.
  Low risk, documented, but worth monitoring in rare disease use cases.
- Context truncation: papers exceeding 1M tokens are truncated, losing some content.
  Truncation order: abstract preserved first, then intro, results, discussion, methods last.
- Streaming JSON failure: partial responses on network issues; retry logic handles most cases (F1)
- Thinking mode: Gemini preview models have thinking enabled by default — set `thinking_budget=0` on
  ALL GenerateContentConfig calls. Without it, 12k-token detail-extraction prompts hang for >600s (C20).

⚕ **Medical accuracy implication:** `detail_extraction` produces the most output but also the most risk.
The three safeguards above (grounding, confidence gate, deterministic seeding) are not optional —
they exist specifically to prevent false gene associations from reaching the CSV output.
Any change to prompt structure must be evaluated for hallucination rate impact.
The 0.7 confidence threshold was set deliberately; lowering it increases recall but also
increases false positives — document the reasoning if it changes.

🔍 **Audit notes:** F1 (retry response corruption fixed), W2 (fallback text fixed), W14 (schema bias — monitored),
C17 (grounding check using raw labels), C18 (disambiguation clause), C19 (citation validator fixed),
C20 (thinking mode disabled), C21 (disambiguation × corroboration confirmed), C22 (detail-extraction instructions hardened)

---

## `validation` — Gene Validation (`gene_validator.py`, ~940 lines)

**What it does:** Multi-source validation of extracted gene symbols and variant strings.
Validates against local HGNC snapshot first, then remote HGNC REST API, then MyGene.info.
Adds confidence scores, validation source, and suggestions for near-misses.

**Validation sources (priority order):**
1. Local HGNC JSON (44,943 genes — fast, offline, no API call)
2. HGNC REST API — authoritative gene nomenclature
3. MyGene.info — comprehensive gene/alias database
4. Fuzzy matching — suggests similar valid symbols for review

**Key functions:**
- `resolve_gene_symbol()`: handles aliases and previous symbols (e.g., MYH9 prev symbol: MYH-9)
- `get_gene_biotype()`: returns HGNC `locus_type` for a resolved symbol
- `validate_citations()`: dense word matching to verify AI-cited passages exist in paper text
- `validate_extracted_genes()`: adds validation columns + `Gene Biotype` to result DataFrame

**Biotype handling:**
- ~~Biotype filtering removed 2026-04-08~~ — all valid HGNC genes pass at equal confidence.
  `Gene Biotype` column is still populated from `get_gene_biotype()` for informational display.
- Murine-convention symbols (Title case: `Brca1`) are flagged `potential_murine_symbol` but not penalized.

**Variant pattern coverage (12+ HGVS patterns):**
amino acid substitution, coding variant, genomic variant, frameshift, splice site, indel,
deletion, duplication, insertion, copy number, complex/fusion

**Citation validation** (`validate_citations`, `_citation_exists_in_paper`):
Dense sequence matching (difflib.SequenceMatcher, threshold 0.85) checks that LLM-extracted
citation text exists verbatim in the paper. Applied to all `{Field} Citation` columns.
- Numerical consistency gate: all numbers in the citation must exist in the matched paragraph
- Gene context gate: gene symbol or alias must appear within ±1500 chars of the citation match
- Encoding normalization: `_normalize_unicode_slashes()` applied symmetrically to BOTH citation
  and paper text before matching — handles U+2044 slash variants, LaTeX `\upmu/\mu/\alpha` etc.,
  ASCII `mu g/l` prefix, and U+00B5 → μ unification
- **Always normalize both sides** — normalizing only the citation fails when the paper PDF contains
  the Unicode artifact (the LLM may produce the correct character while the PDF has the variant)

**Failure modes:**
- W12: variant patterns are incomplete — complex structural variants, multi-exon deletions, CNV
  notation variations may not be caught. Known limitation; does not block pipeline.
- Stale local HGNC snapshot: genes approved after the snapshot date won't validate locally;
  remote API fallback handles this but adds latency.
- `memory-profile.md` records the snapshot as 44,943 genes — if regenerating, update that figure.
- Citation validation always returns False/0.0 silently if `validate_citations()` is called with
  a row dict (non-string values cause TypeError in re.search, swallowed by inner try/except).
  Fixed in C19 — now uses explicit column pairing against string-only citation columns.

⚕ **Medical accuracy implication:** This is the final safety gate. The confidence threshold
(`FINAL_VALIDATION_MIN_CONFIDENCE=0.7`) determines what reaches the CSV.
- Valid gene + valid variant → confidence 1.0
- Valid gene alone → confidence 0.7
- Fuzzy match / alias resolution → confidence < 0.7 → filtered out
Changing this threshold is a medical accuracy decision that requires benchmark evaluation first.

🔍 **Audit notes:** F3 (HGNC database bundled), W3 (token estimation corrected), W12 (variant patterns — accepted gap),
C19 (citation validator silent TypeError fixed), C22 (encoding normalization, gene context window ±500→±1500)

---

## `output_writing` — Orchestration And Output Writing (`pipeline_orchestrator.py`, 883 lines)

**What it does:** Coordinates all domains, manages multiprocessing worker pool, aggregates results,
deduplicates, ranks by citation count, and writes final CSV.

**Worker pool:** 2–4 persistent processes (configurable via `AI_WORKER_POOL_SIZE`).
Each worker creates a fresh `PaperAnalysisPipeline` instance per paper.
Per-paper timeout: 600 seconds (`AI_PER_PAPER_TIMEOUT_SECONDS`).

**Deduplication:** `groupby(gene + pmid)` then `first()` strategy.
W6: this collapses distinct findings from the same paper about the same gene into one row.
Acceptable tradeoff — prevents duplicate rows — but means some variant detail may be lost.

**Candidate widening (query-mode only):** Query-mode runs pull up to
`PUBMED_RELEVANT_COUNT=200` candidates from PubMed before citation ranking trims to the
user's requested top-N. User-curated PMID lists are taken 1:1 — no widening. There is no
"4× overfetch factor" — that claim appeared in older docs but the symbol was orphaned and
has been removed (see `docs/audit/final-audit.md` F1).

**Citation ranking:** Final CSV is sorted by citation count descending.
High-citation papers appear first — appropriate for literature synthesis, but researchers
studying emerging/rare findings should be aware of this ordering.

**Failure modes:**
- W13: `papers_analyzed` stat counts only papers that produced non-empty results;
  papers that failed extraction are undercounted. Fixed in UI display but metric is misleading.
- Division by zero on empty screening results (F6 — fixed).

⚕ **Medical accuracy implication:** The final CSV is a tool for researchers, not a clinical product.
However, false gene associations in this output could propagate into downstream analysis.
The pipeline must never present unvalidated extraction as ground truth.
Consider adding a confidence column to the CSV (already present in validation output)
and documenting in the paper that results should be manually reviewed for clinical use.

---

## Domain Data Flow

```
UI:      PubMed search → efetch abstracts → geneRelevanceScorer → user selects papers
`paper_selection` → [{pmid, title, abstract, authors, citation_count, ...}]  (user-selected papers)
`oa_filter` → OA-only PMIDs when the filter is enabled; non-OA papers degrade or are excluded depending on entry path
`paper_reading` → [{...record, full_text: {sections}, figures: [...]}]
`candidate_discovery` → [{...record, pubtator_genes: [...], pubtator_variants: [...], candidate_meta: {...}}]
`detail_extraction` → [HybridExtractionResult(rows=DataFrame, pubtator_genes=[...])]
`validation` → DataFrame with validation columns and gate metadata added
`output_writing` → deduplicated, citation-ranked artifact bundle. Primary CSV/JSON/Excel `Results` contain only requested user fields plus fixed researcher-facing provenance fields; diagnostics stay in metadata/debug artifacts.
```

## Configuration Quick Reference

| Flag | Default | Impact if disabled |
|---|---|---|
| `ENABLE_OA_FILTER` | True | Paywall papers included; full text unavailable |
| `ENABLE_ABSTRACT_SCREENING` | True | Pipeline pass-through (forensic logging only); scoring moved to UI |
| `ENABLE_PUBTATOR_EXTRACTION` | True | Precision floor removed; hallucination risk up |
| `ENABLE_GROUNDING_CHECK` | True | Hallucinated genes may pass to output |
| `ENABLE_DETERMINISTIC_CANDIDATES` | True | LLM has less constraint; recall up, precision down |
| `ENABLE_STRICT_VALIDATION_GATE` | True | Low-confidence genes reach CSV |
| `ENABLE_FIGURE_ANALYSIS` | False | Enable for figure-heavy papers; otherwise figure-only genes may be missed |
| `FINAL_VALIDATION_MIN_CONFIDENCE` | 0.7 | Medical accuracy decision — benchmark before changing |
| ~~`VALIDATE_PROTEIN_CODING_ONLY`~~ | ~~Removed~~ | Removed 2026-04-08 — all HGNC genes pass equally |
