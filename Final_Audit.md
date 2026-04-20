# Final Audit

> Findings discovered while tracing the pipeline end-to-end, co-documented with the project owner.
> Each entry: **what we expected → what we found → why it matters → suggested action.**
> Newest at the top. Append-only.

---

## Findings Index

Quick scan. Each row links to the full entry below.

| # | Finding | Severity | Area |
|---|---|---|---|
| [F10](#f10--post-validation-silent-failures-citation-false-negatives-fuzzy-match-drops-opaque-evidence-thresholds) | Post-validation silent failures — citation false negatives, fuzzy-match drops, opaque evidence thresholds | Trust erosion / UX opacity | Step 4 — post-validation |
| [F9](#f9--corroboration-gate-cant-distinguish-table-only-genes-from-biomarker-abbreviations) | Corroboration gate can't distinguish table-only genes from biomarker abbreviations | Potential false drops on table-heavy papers | Step 2 — corroboration gate |
| [F8](#f8--grounding-check-silent-failure-modes-truncation-interaction-and-fuzzy-pattern-blind-spots) | Grounding check silent failure modes — truncation interaction and fuzzy pattern blind spots | Potential false drops | Step 1.6 — grounding check |
| [F7](#f7--batched-detail-extraction-has-known-artefacts-offer-per-gene--context-caching-as-a-user-option) | Batched detail extraction has known artefacts — offer per-gene + context caching as a user option | Architectural / quality evolution | Stage 5 — Gemini detail extraction |
| [F6](#f6--greek-letter-transliteration-is-asymmetric-between-body-and-abstract) | Greek letter transliteration is asymmetric between body and abstract | Potential silent drops | Full-text fetch / grounding check |
| [F5](#f5--pubtator-response-has-more-annotation-types-than-we-consume) | PubTator response has more annotation types than we consume | Untapped resource | Stage 4 — PubTator NER |
| [F4](#f4--redundant-fetches-across-the-uipipeline-boundary) | Redundant fetches across the UI/pipeline boundary | Efficiency | UI ↔ pipeline handoff |
| [F3](#f3--doi-and-pmc-id-inputs-are-silently-dropped-from-user-defined-lists) | DOI and PMC ID inputs are silently dropped from user-defined lists | Silent data loss / UX bug | `SmartInput.tsx` entry |
| [F2](#f2--all-papers-are-oa-is-not-actually-enforced-on-all-entry-paths) | "All papers are OA" is not actually enforced on all entry paths | Architectural invariant violation | Specific-PMIDs entry |
| [F1](#f1--the-4-overfetch-factor-does-not-exist-in-code) | The "4× overfetch factor" does not exist in code | Documentation inaccuracy | Config + paper draft |

**Legend:** *Severity is how the finding could hurt users or correctness, not how urgent
it is to fix.* A "documentation inaccuracy" can be higher-priority than an "efficiency"
finding if the publication deadline is imminent.

---

## F10 — Post-validation silent failures: citation false negatives, fuzzy-match drops, opaque evidence thresholds

**Date:** 2026-04-19
**Source:** Tracing Step 4 (`_run_post_validation`) in Section 15 of
`pipeline-understanding.md`.
**Severity:** Mixed. Three distinct silent failure modes in the final three gates.
One is a trust-erosion bug (F10a), one is a known-accepted trade-off worth
documenting (F10b), one is a UX/debuggability issue (F10c).

### Context — what post-validation does

Three checks run in sequence on the detail-extracted DataFrame:

1. **Strict validation gate** — drop if `validation_confidence < 0.7`
2. **Citation validation** — annotate every `{col, col Citation}` pair with
   validity, confidence, details. Doesn't drop.
3. **Evidence gate** — drop if non-empty cells below per-source threshold

Each has a specific silent failure mode worth documenting separately.

### F10a — Citation validator false negatives on formatting drift

**What we expected:** a citation that's a verbatim quote from the paper is marked
`citation_valid=True`.

**What we found:** [`_citation_exists_in_paper`](pipeline/modules/gene_validator.py) uses
`difflib.SequenceMatcher` with a **hardcoded ratio threshold of 0.85** to verify that
the LLM-extracted citation text appears in the paper. On papers with any of the
following, the matcher returns < 0.85 and the citation is flagged invalid **even
when the quote is genuinely in the paper**:

- **Soft hyphens and line-break hyphenation.** PMC XML sometimes preserves
  word-break hyphens (`suscep-\ntibility`) that the LLM correctly quotes without the
  hyphen (`susceptibility`). Character-level diff pushes ratio below 0.85.
- **Figure-caption drift.** Figure captions in JATS XML have whitespace-normalised
  rendering that differs subtly from how the LLM quotes the same caption.
- **Em-dash / en-dash reconciliation.** Greek transliteration in the body (Section 4.4)
  handles some Unicode glyphs but not all; the LLM sometimes normalises en-dashes in
  its quote that remain unnormalised in the body (or vice versa).
- **Typesetting artefacts from old PDF-derived XML.** Ligatures (`fi`, `fl`),
  mid-sentence spaces, and publisher-specific entity encoding.

**Why it matters:** `citation_valid=False` shows up in the final CSV — an operator
reviewing the output sees "this citation is not backed" and loses trust in the
extraction, even when the extraction is correct. The evidence gate doesn't drop the
row for this (it counts cell populate-ness, not citation validity), but the UX
degradation is real.

**Why this is particularly painful:** the C19 fix (logged in `memory-decisions.md`)
addressed citation validation *crashing silently* (every row tagged "No validation
performed" because of a TypeError). The fix made validation run — but made the 0.85
threshold's false-negative rate visible to users, who hadn't seen it before because
it was hidden behind the crash.

**Suggested action:**
- [ ] **Preprocess both sides before SequenceMatcher.** Collapse whitespace aggressively
      (including soft hyphens and line-break hyphenation), unify dashes, strip
      common typesetting artefacts. The encoding-normalisation pass in `_normalize_unicode_slashes`
      (C22) is a template for this — extend it to include these new cases.
- [ ] **Consider lowering the threshold to 0.80** and re-characterising on the benchmark
      set. Trade-off: might accept more false positives (fuzzy matches where the quote
      isn't actually in the paper). Worth measuring the precision/recall shift.
- [ ] **Expose the threshold as a config flag** (`CITATION_SIMILARITY_MIN_RATIO`), so
      future tuning doesn't require code edits.
- [ ] **Better `citation_details` messaging** — currently says "not found in paper,"
      which implies the quote is absent. A message like "matched at 0.82 ratio, below
      0.85 threshold — likely formatting drift" would let operators distinguish a real
      false-quote from a near-miss.

### F10b — Strict gate drops mouse-convention symbols and fuzzy resolutions (accepted trade-off — document explicitly)

**What we expected:** the strict validation gate at 0.7 confidence is a medical-accuracy
threshold that drops low-confidence matches.

**What we found:** the gate silently drops two categories of legitimate extractions:

1. **Mouse-convention symbols mapped to human genes.** When a paper uses title-case
   mouse convention (`Brca1`) to refer to the human gene (common in comparative
   genomics and cross-species studies), `gene_validator.resolve_gene_symbol` flags
   `potential_murine_symbol` in `validation_source` and returns confidence 0.5.
   The 0.7 strict gate drops these. Documented in `memory-decisions.md` 2026-02-28 as
   "Mouse symbol flag is informational, not blocking" — but the strict gate *is*
   blocking on it.
2. **Fuzzy-matched aliases.** A paper using an old / non-canonical alias that only
   resolves via fuzzy matching (`MYH-9` for `MYH9`, older literature) can return at
   0.5–0.6. Dropped.

**Why this is not a bug:** CLAUDE.md explicitly marks `FINAL_VALIDATION_MIN_CONFIDENCE=0.7`
as a medical-accuracy decision, not a performance knob. The trade-off is
intentionally biased toward precision over recall.

**Why it's worth flagging:** the trade-off isn't documented in the operator-facing
output. An operator looking at the CSV sees "47 genes extracted," has no idea that 3
legitimate mouse-convention mentions and 2 alias-fuzzy-matches were dropped at this
gate. For mouse-model papers and cross-species reviews, this could be a meaningful
blind spot.

**Suggested action:**
- [ ] **Surface strict-gate drops to the operator.** Add a "Dropped by strict
      validation" section to the metadata CSV or a UI banner on the results page
      listing the dropped genes with their confidence and `validation_source` tags.
      The data is already in `self.strict_gate_drops` — it just doesn't reach the UI.
- [ ] **Reconsider the mouse-symbol path.** The explicit `potential_murine_symbol`
      flag is informational by design, but it *interacts* with the strict gate to
      produce an unintentional drop. Either: (a) bump confidence for mouse-convention
      resolutions that clearly map to a valid human HGNC symbol, or (b) carve out
      a secondary CSV section for "flagged for review" genes that didn't make the
      strict cutoff but aren't outright hallucinations.

### F10c — Evidence gate's per-tier thresholds are not user-visible

**What we expected:** a row is either sufficient or insufficient.

**What we found:** whether a row with 0 non-empty cells survives depends entirely on
its `sources` set, which the operator never sees. Specifically:

- A row with `{llm_text}` source and 0 cells survives (`min_cells = 0`).
- A row with `{deterministic_lexicon}` source and 0 cells drops (`min_cells = 1`).
- A row with `{pubtator}` source and 0 cells drops (`min_cells = 1` via mixed default).

The operator looking at `drop_debug_{hash}.json` sees
`{reason: "insufficient_user_evidence", source_tier: "deterministic", evidence_cells: 0, min_required: 1}`
— but only if they know to look, and even then the logic isn't obvious.

**Why it matters:** debuggability. When an operator asks "why did TP53 not reach my
CSV?" and the answer is "because it was only found by the deterministic scanner, and
the evidence gate requires 1 non-empty cell for non-LLM sources, and the detail call
didn't produce any user-column content for it," that's a non-obvious chain of events.
Researchers investigating false negatives for the SoftwareX paper would hit this wall.

**Why it's design-intentional:** the per-tier thresholds encode a real trust model
(the LLM's act of naming a gene is evidence; a lexicon match alone isn't). But the
model is invisible to the user.

**Suggested action:**
- [ ] **UI surfacing of drop reasons.** Results page could expose a "Why are some
      genes missing?" affordance that summarises drops by gate (grounding,
      corroboration, strict, evidence) with counts and a representative example
      each.
- [ ] **Document the per-tier logic in the user-facing README or a Help tooltip.**
      Currently it's buried in `gemini_extractor.py` with a code comment.
- [ ] **Consider making at least one tier threshold user-configurable.** Precision
      users (clinical, publication) might want `EVIDENCE_MIN_NONEMPTY_CELLS_LLM_TEXT=1`
      to require at least some content extraction per LLM-surfaced gene; recall users
      (exploratory review) might want `EVIDENCE_MIN_NONEMPTY_CELLS_DETERMINISTIC=0`
      to include table-only genes that F9 already flagged.

### Cross-references

- **F10a** compounds with **F6** (Greek-letter asymmetry): both are encoding-drift
  failures at different layers. Fixing them together (a unified, symmetric
  normalisation pipeline that runs on both sides of every comparison) would close
  multiple paths at once.
- **F10c** overlaps with **F9** (table-only genes): both would benefit from making
  per-tier logic user-visible so researchers can opt into different trust models
  per use case.

---

## F9 — Corroboration gate can't distinguish table-only genes from biomarker abbreviations

**Date:** 2026-04-19
**Source:** Tracing Step 2's corroboration gate in Section 13 of
`pipeline-understanding.md`.
**Severity:** Collateral damage on a specific paper class — table-heavy Results-only
gene reporting. Real but bounded.

### What we expected

The corroboration gate exists to filter clinical-biomarker abbreviations that the
deterministic scanner catches but the LLM correctly refuses to extract (per the C18
disambiguation clause, confirmed in C21). A candidate tagged only with
`deterministic_lexicon` source and no variant → dropped as uncorroborated.

### What we found

The gate cannot distinguish two semantically opposite cases that produce the same
`sources` set:

| Case | Why it happens | What should happen |
|---|---|---|
| **(a) Biomarker false positive.** `ESR1` appears in a clinical paper discussing "ESR 78 mm/h" lab values. LLM correctly identifies this as a lab value and refuses extraction. Deterministic scanner picks it up because the literal token `ESR1` is somewhere in the text. | LLM disambiguation clause working as intended | Drop ✅ |
| **(b) Real table-only gene.** A gene panel paper mentions `NUDT15` only in a Results table with no accompanying prose discussion. The LLM, which typically skips table-heavy prose, misses it. Deterministic scanner picks it up from the table token. | LLM skipped the table (known Gemini behaviour on structured data) | Keep ❌ **dropped anyway** |

Both produce `sources == {deterministic_lexicon}` and `variant == ""`. The gate treats
them identically.

### Why it matters

Pharmacogenomics guideline papers, gene-panel cancer papers, and certain CPIC-style
drug-gene tables routinely report gene findings in structured tables without prose
elaboration. Examples from the project benchmark:

- **PMID 35152405** (CPIC guideline for statins — SLCO1B1/ABCG2/CYP2C9). Several dose-
  adjustment guideline genes appear only in Table 2 with no surrounding prose.
- **Pan-cancer oncoprint papers.** Commonly a supplementary table of "genes with
  significant mutations" that the prose summarises only generically ("the top 30
  drivers").

On these papers, the gate silently drops real genes. The operator sees "47 → 43
after corroboration gate" with no indication whether the 4 drops were false positives
(the gate's intent) or false negatives (table-only genes).

### Why it's not easy to fix

The trade-off is structural:

- **Tighten the gate** (e.g., require 2+ sources for *all* candidates) → drops more
  real genes on every paper, not fewer.
- **Loosen the gate** (e.g., allow deterministic-only to pass) → reintroduces
  biomarker false positives. This was the whole reason C9/C18/C14 were added.
- **Context-aware distinction** — detect whether the deterministic-only token is in a
  table-cell context or a prose-sentence context. The JATS parser currently concatenates
  table text into the body stream without structural markers (Section 6), so there's
  no "in a table" signal at this stage.

### Suggested action

Not a single-fix issue. Consider in order of increasing ambition:

- [ ] **Immediate:** log dropped candidates with enough context (surrounding snippet
      from paper text) that the operator can spot false negatives in `drop_debug_{hash}.json`.
      Current drop record has `{gene, variant, reason, confidence}` — adding a
      snippet would make post-hoc review tractable.
- [ ] **Medium:** preserve table-vs-prose provenance in the JATS parser (Section 6).
      Annotate each text span with a source-element tag (`<body>`, `<table-wrap>`,
      `<caption>`). Then add a `table_context` signal to deterministic-scan output.
      Genes only found in tables could be given a different source tag
      (`deterministic_lexicon_table`) that's allowed to pass when accompanied by a
      concurrent PubTator hit, even without LLM backing.
- [ ] **Ambitious:** per the F7 architectural discussion — per-gene detail extraction
      with context caching would let the LLM be prompted specifically about a
      table-token gene with a focused "is this a real gene mention?" check. This is
      the "use the LLM as a tie-breaker" path and it would naturally subsume this
      gate's job.
- [ ] Verify on the benchmark: run PMID 35152405 and a pan-cancer paper from the
      gold-standard set. If `rejected_uncorroborated_deterministic` drops contain any
      entries that match the gold standard, this finding is confirmed reproducible.

### Cross-reference

F9 is a sibling to **F5** (PubTator unused annotations). If PubTator's `Disease` or
`Chemical` annotations were consumed (F5's suggestion), a candidate appearing in a
table adjacent to a PubTator-tagged disease mention could be given a soft corroboration
boost. Solving F5 would weaken F9's sharp edge.

---

## F8 — Grounding check silent failure modes: truncation interaction and fuzzy pattern blind spots

**Date:** 2026-04-19
**Source:** Tracing Step 1.6 (`_run_grounding_check`) in Section 12 of
`pipeline-understanding.md`.
**Severity:** Mixed. Three sub-findings — one structural bug, one narrow matching gap,
one design choice worth documenting explicitly.

### Context — what the grounding check is

Step 1.6 of the Gemini extractor drops candidates whose gene / alias / raw-label
doesn't appear in the paper text. Primary hallucination filter. See Section 12 of
`docs/pipeline-understanding.md` for mechanics.

### F8a — Truncation × grounding interaction (structural)

**What we expected:** candidates found in the abstract would be grounded against text
that includes the abstract.

**What we found:** if `_validate_and_prepare_paper_text`
([`gemini_extractor.py:2068`](pipeline/modules/gemini_extractor.py:2068)) truncates the
paper (Section 9.1) — dropping Methods, Supplementary, Discussion, Conclusion, or
Introduction to fit the 80% context threshold — the grounding check then runs against
the **truncated** `self.paper_text`.

Consequence: a gene that is:
- Found by the abstract pass (`source: llm_abstract`), because it appears in the
  abstract, AND
- Mentioned in the paper *only in a section that was truncated* (e.g., Methods or
  Supplementary),

…will be dropped by the grounding check, because the terms don't appear in the retained
body. The abstract block is preserved in JATS parsing, so the gene might still match
there — but if the raw label differs between abstract wording and the abstract's JATS
rendition, it can silently fail.

**Why it's real but rare:** most meaningful gene mentions appear in results or
discussion sections, and both are preserved unless the paper is extraordinarily long.
The bite case is supplementary-heavy papers (gene panels, genome-wide association
studies), where key gene lists sometimes live only in the supp.

**Suggested action:**
- [ ] During grounding, also search the *original* untruncated text (the PMC-returned
      body + abstract, stored before truncation) as a secondary pass. Keep the primary
      search on the truncated text to avoid rehydrating dropped sections into later
      evidence snippets.
- [ ] Failing that: log a warning when a candidate is dropped that *would* have
      matched in an untruncated search, so the operator at least knows truncation is
      biting.

### F8b — Fuzzy pattern blind spot

**What we expected:** the fuzzy pattern in
[`_find_evidence_snippet`](pipeline/modules/gemini_extractor.py:246) tolerates common
gene-symbol punctuation variants (`IL-6`, `IL_6`, `IL 6`, `IL/6`).

**What we found:** the fuzzy separator class is hardcoded to `[\s\-_\/]*`. It
**doesn't** cover:

- Parentheses: `IL(6)`, a formatting quirk in some typeset papers
- Periods: `IL.6`, rare but seen in bibliographic abbreviations
- Em-dash / en-dash: `IL—6`, `IL–6`, common in older typeset PDFs where OCR or
  publisher conversion maps hyphens to dashes
- Non-breaking hyphen (U+2011): visually identical to `-` but not matched

**Why it matters:** after Greek transliteration and ASCII coercion (Section 4.4, F6),
Greek letters are gone, but Unicode dashes in the body **survive** the cleaning step
because they're already ASCII-range (actually, the em-dash `—` is U+2014 and *is*
stripped by the cleaner — but en-dash `–` U+2013 and hyphen-minus `-` have different
behaviour across different cleaning paths). A gene symbol joined by an em-dash in the
source survives as joined by a space after cleaning, which the fuzzy pattern *does*
match. But en-dash `–` is U+2013, above the ASCII range, and gets stripped to a space
in `_clean_and_validate_content`. So dashes are largely fine — the real blind spot is
parentheses and periods in abbreviation conventions.

**Suggested action:**
- [ ] Extend the fuzzy separator class to `[\s\-_\/\.\(\)]*`. Low-risk change; the
      strict pattern still requires word boundaries, so we can't accidentally match
      across unrelated words.
- [ ] Add a test case: `IL(6)`, `IL.6`, `il 6` — should all ground against canonical
      `IL6`.

### F8c — No variant verification (design choice, documented for clarity)

**What we found:** the grounding check verifies the gene's presence in paper text,
but **not the variant's**. A row with `gene=BRCA1, variant=rs80357906` passes
grounding if `BRCA1` appears anywhere, regardless of whether `rs80357906` actually
exists in the paper.

**Why this is intentional:** variant verification is handled later by the citation
validator in `gene_validator.validate_citations` and by the evidence gate's per-source
thresholds (`_apply_evidence_gate`). Grounding's narrow job is "is this gene
hallucinated?"; variant realism is a separate concern.

**Why it's worth documenting:** the function's name (`_run_grounding_check`) suggests
it does full verification. Future contributors touching this code might assume
variants are checked here and skip adding variant-specific validation elsewhere.
A one-line comment would prevent that.

**Suggested action:**
- [ ] Add a docstring clarification: *"Grounding checks gene presence only. Variant
      presence is validated by the citation gate and evidence gate downstream."*
- [ ] No code change required — the separation of concerns is defensible.

### Cross-reference

F8 overlaps with **F6** (Greek letter asymmetry) on one surface: the grounding check is
where F6's asymmetry materialises into silent drops. F6 is the root cause (abstract
preserves Greek, body transliterates); F8a/b are the grounding-check-specific
consequences. Keep both entries; they live at different layers.

---

## F7 — Batched detail extraction has known artefacts — offer per-gene + context caching as a user option

**Date:** 2026-04-19
**Source:** Architectural discussion after tracing Sections 8–9 of `pipeline-understanding.md`.
**Severity:** Evolution opportunity. Current pipeline works; known failure modes in
`AUDIT.md` (C22 sprint) can be reduced or eliminated by a structural change.

### What the pipeline does today

**One** Gemini call fills in the user's column schema for **all** candidate gene–variant
pairs on a paper. The prompt contains:

- The accumulated candidate list as JSON (`[{gene_name, variant_name}, ...]`)
- The full paper text (post-truncation)
- The 9 accumulated CRITICAL INSTRUCTIONS in `_DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS`
- Per-column descriptions + per-column citation-field asks

Gemini returns an array of rows. One API call per paper, regardless of how many genes
were found. See [`gemini_extractor.py:1169`](pipeline/modules/gemini_extractor.py:1169).

### Known failure modes that stem from batching

Documented in the C22 citation sprint ([`docs/AUDIT.md`](docs/AUDIT.md), 2026-02-25):

1. **Citation cross-contamination.** Gemini summarises Gene A's Key Finding in
   non-verbatim form, can't find a matching sentence, and cites the nearest statistical
   sentence — which sometimes belongs to Gene B. Patched with "GENE-NAMED CITATIONS"
   instruction and widened ±1500-char gene-context window in `_citation_exists_in_paper`,
   but not eliminated structurally.
2. **Row cross-repetition.** Gemini copies the same Key Finding across multiple variant
   rows of the same gene (or between genes discussed adjacently). Motivated
   instructions #1 ("Each gene is INDEPENDENT") and #9 ("Do NOT repeat same sentence
   across variant rows").
3. **Attention split.** A paper with 30 candidate genes forces Gemini to extract 30 sets
   of column values in a single response. Attention-per-gene degrades as the candidate
   count rises.
4. **Stochastic citation compliance (L16).** Per-paper citation coverage fluctuates 0/8
   to 8/8 across runs — the batched call sometimes complies with the quoting
   instructions, sometimes doesn't. Per-gene calls would average this out across 20
   independent decisions rather than amplifying through a single coupled decision.

Several of the 9 CRITICAL INSTRUCTIONS in the Stage 3 prompt exist **solely** because of
batching. Per-gene calls would make those instructions unnecessary and reduce
prompt-length drift over time.

### Why this is a user decision, not an architectural one

The two designs have opposite cost/quality curves:

| Dimension | Batched (current) | Per-gene (proposed) | Per-gene + context caching (hybrid) |
|---|---|---|---|
| Calls per paper (20 genes) | 1 | 20 | 20 (but cached paper text) |
| Input tokens per paper (~50k paper) | ~50k | ~1,000k | ~50k + ~20×small prompt ≈ ~70k |
| Free-tier rate impact (15 RPM) | Minor | **Severe** — ~0.75 papers/min | Moderate |
| Citation cross-contamination | Real, partially patched | Structurally impossible | Structurally impossible |
| Cross-gene context | Preserved | Lost | Lost |
| Attention per gene | Degrades with N | Full | Full |
| Prompt complexity | Heavy (9 instructions) | Minimal | Minimal |
| Failure isolation | Batch-level | Per-gene | Per-gene |

For a home/academic user running the free Gemini tier, per-gene without caching is
prohibitively expensive and hits the 15 RPM wall quickly. For a user running with a paid
API key on clinical / publication-grade extraction, per-gene (ideally hybrid) is
worth the trade.

**Therefore: neither design is universally superior. Make it a user-facing setting.**

### Proposed implementation

**Settings UI addition** — extend the existing Performance section in
[`Settings.tsx`](app/src/renderer/pages/Settings.tsx) where `parallelAnalysis` already
lives. Three-way choice:

```
Extraction mode
  ○ Economy — one detail call per paper (default, free-tier friendly)
  ○ Precision — one detail call per gene (best quality, ~15–20× more API calls)
  ○ Hybrid — one detail call per gene with context caching (best quality, moderate cost, requires paid tier)
```

**Threading the setting through the stack** — same pattern as `parallelAnalysis`
(see `memory-sessions.md` 2026-04-07):

1. `settings-store.ts` — add `extractionMode: "economy" | "precision" | "hybrid"`.
2. `preload/index.ts` — expose via `window.api.settings`.
3. `useSettings.ts` — React hook.
4. `python-bridge.ts` — pass as env var `EXTRACTION_MODE`.
5. `config.py` — read at module load.
6. `gemini_extractor.py` — branch in `extract_gene_info()`:
   - Economy: existing batched call (unchanged).
   - Precision: loop over `self.associations`, one call per gene with the paper text
     re-sent each time. Collect results into the same output DataFrame structure.
   - Hybrid: on first gene, call Gemini `CachedContent.create()` with the paper text
     + CRITICAL INSTRUCTIONS ([docs](https://ai.google.dev/gemini-api/docs/caching)).
     Subsequent per-gene calls reference the `cached_content` ID. TTL scoped to the
     worker's paper (few minutes — well under the 5-minute min).
7. **Merge the results identically downstream** — the detail-extraction output has the
   same shape regardless of mode, so grounding check, corroboration gate, evidence
   gate, and CSV writer are unchanged.

### What changes and what doesn't

**Changes:** `extract_gene_info()` branches. The 9 CRITICAL INSTRUCTIONS could be
trimmed in precision/hybrid mode — instructions #1, #3, #9 (the row-repetition ones)
become no-ops per-gene. But keep them in economy mode unchanged.

**Does not change:** candidate discovery (Steps 0.5, 1, 1b, 1.1, 1.25, 1.5), grounding
check, corroboration gate, evidence gate, validation, CSV output. Those all consume
`self.associations` and the resulting rows — mode-agnostic.

### Risks and caveats

- **Cached-context TTL and eviction.** Gemini context caching has a minimum 5-minute
  TTL. If a paper's extraction finishes in under 5 minutes (likely), the cache is paid-
  for even after we're done. On a many-paper run this averages out; on a 1-paper run
  it's wasted cost. Mitigation: documentation, not code.
- **Parallelism interaction.** `parallelAnalysis` (Codex-era feature, already shipped)
  parallelises *papers*. Per-gene mode could also parallelise *genes within a paper*,
  but 15 RPM rate limits on free tier would make this counterproductive. Scope this
  as a future enhancement.
- **Output row count.** Economy mode sometimes collapses multiple variant rows of the
  same gene into one row when Gemini lazy-fills across rows. Per-gene mode will emit
  strictly one row per `(gene, variant)` pair. This is *better* behaviour but would be
  a visible diff in benchmark outputs — flag in `AUDIT.md` when the mode is introduced.
- **Cache security.** Cached content is scoped to the API key. Users with multiple keys
  (research lab sharing) would get separate caches. Not a security issue, just a
  cost-sharing nuance.

### Suggested action

- [ ] Land in two phases to de-risk:
  - **Phase 1:** Ship *precision* mode (per-gene, no caching). Simplest diff. Validates
    the branching logic in `extract_gene_info` and the settings plumbing.
  - **Phase 2:** Ship *hybrid* (per-gene with context caching). Layered on top of the
    Phase 1 branching.
- [ ] Before shipping: run both modes on the benchmark set (`pipeline/data/benchmark/`)
      and compute F1 / citation coverage / Cohen's κ. This is the argument for F7 in
      the SoftwareX paper ("user-selectable extraction modes with characterised
      precision/cost trade-off"). A real table comparing the three modes would be a
      publication-worthy figure.
- [ ] Trim redundant CRITICAL INSTRUCTIONS in precision/hybrid mode. Specifically
      instructions #1, #9 (row-independence, row-repetition) can be removed — keep
      the disambiguation clause, verbatim numbers, gene-named citations.
- [ ] Add a user warning in the UI when the selected mode + API key combination is
      likely to hit rate limits (e.g., precision mode + free-tier Gemini + >5 papers).

---

## F6 — Greek letter transliteration is asymmetric between body and abstract

**Date:** 2026-04-19
**Source:** Tracing how paper text reaches Gemini at the abstract pass (Section 8).
**Severity:** Potential silent extraction loss at the grounding check. Needs empirical
verification — not yet confirmed as reproducible in a real run.

### What we expected

The W1 fix in `AUDIT.md` made Greek letters work correctly in paper text by transliterating
them (`α → alpha`, `β → beta`, `μ → mu`) before downstream stages see the content. This is
medical-accuracy-critical — haematology papers discuss α-globin, β-thalassemia, γ-heavy
chain constantly.

The implicit assumption: **every copy of a paper's text seen by Gemini is cleaned the
same way.**

### What we found

The cleaning is applied in exactly one place —
[`full_text_fetcher._clean_and_validate_content`](pipeline/modules/full_text_fetcher.py:676)
— which only runs on the paper **body text** path (PMC JATS XML / Europe PMC). It does
**not** run on abstracts.

The abstract that Gemini sees in Step 0.5 (abstract pass) comes from a different source:
`paper_details[pmid]["abstract"]`, populated by
[`pubmed_data_collector.fetch_paper_details`](pipeline/modules/pubmed_data_collector.py:249)
from the Medline `AB` field. That path never calls `_clean_and_validate_content` and has
no Greek-letter transliteration of its own.

So for the same paper, within the same run, Gemini sees:

| Surface | Greek letters |
|---|---|
| Abstract (Step 0.5) | **Raw** — `α-globin`, `β-thalassemia`, `μg` |
| Body text (Step 1 / 1b / 1.25) | **Transliterated** — `alpha-globin`, `beta-thalassemia`, `mug` |

### Why it matters

The LLM itself is robust to this — Gemini treats `α-globin` and `alpha-globin` as
semantically equivalent, and the final gene symbol `HBA1` is emitted either way. So the
**discovery** side is probably fine.

The risk is in the **grounding check**
([`gemini_extractor.py:1447`](pipeline/modules/gemini_extractor.py:1447) — the primary
hallucination filter documented in `memory-pipeline.md` §Stage 5). Per that doc:

> *Uses canonical symbol + all HGNC aliases + raw LLM labels (e.g., "BNP" for NPPB).*
> *Do not check only the canonical symbol — raw labels are essential.*

If Gemini picks up `HBA1` from the abstract and emits the raw label `α-globin` (because
that's what the abstract said), the grounding check then searches the **body text**,
which has been transliterated to `alpha-globin`. The search for `α-globin` in
`alpha-globin`-cleaned text can fail — silently dropping a correctly-extracted gene.

This is the exact failure mode the grounding check was designed to catch for hallucinated
genes, misfiring on real ones because of text-normalisation drift between two code paths.

### Why it's marked "unconfirmed"

Two mitigations that may absorb most real-world occurrences:

1. **Gemini normalises in its output.** When the abstract says `α-globin`, Gemini often
   returns raw_label as `HBA1` (already canonical) rather than the Greek form — so there's
   no Greek mismatch to fail against.
2. **HGNC aliases are checked too.** The grounding check walks all aliases for `HBA1`
   (`HBA-A1`, `HBH`, etc.). At least one of those is usually ASCII-safe and will match.

So the failure mode is likely rare but real — and it's the kind of rare-but-real failure
that bites haematology papers specifically, which is exactly the population W1 was
supposed to protect.

### Suggested action

- [ ] **Verify with a known-good paper.** Pick a haematology paper with α-globin /
      β-thalassemia in the abstract (PMID 28077840 or similar). Run it through the
      pipeline with debug logging on `self.dropped_candidates`. Check whether any
      legitimately-extracted gene was dropped by the grounding check for reasons that
      trace back to Greek-letter mismatch.
- [ ] **If confirmed, apply `_clean_and_validate_content` to abstracts too** — either in
      `fetch_paper_details` or at the `_prepare_paper_inputs` boundary. Symmetry between
      the two text surfaces is the correct fix; trying to handle it inside the grounding
      check would be more complex and more fragile.
- [ ] **If unconfirmed after realistic testing**, document the asymmetry in
      `memory-pipeline.md` as a known limitation rather than a bug, so future Claude
      sessions don't have to rediscover this trail.
- [ ] Separate, smaller todo: step 3 of the cleaning (`[^\x00-\x7F\t\n]+`) strips *any*
      non-ASCII — not just Greek. German umlauts in author names (if they appear in the
      body text as cited reference), non-Latin transliteration, emoji. Usually fine,
      worth noting because it's aggressive.

---

## F5 — PubTator response has more annotation types than we consume

**Date:** 2026-04-19
**Source:** Reading `_parse_document` in `pubtator_tool.py` while tracing Stage 4.
**Severity:** Untapped resource, not a bug. Flag for future feature work.

### What we expected

For each batch of PMIDs, PubTator3 returns a BioC JSON document per paper. Our parser
walks the `passages[].annotations[]` list and keeps what's relevant.

### What we found

PubTator3 annotates multiple entity types per document:
`Gene`, `DNAMutation`, `ProteinMutation`, `SNP`, `Chemical`, `Disease`, `Species`,
`CellLine`, and a few minor types. Our parser
([`pubtator_tool.py:243–293`](pipeline/modules/pubtator_tool.py:243)) keeps only:

```python
if ann_type == "gene":                          # → PubTatorGene
elif ann_type in ("variant", "snp", "mutation"): # → PubTatorVariant
# everything else: silently discarded
```

We're paying the full API cost (one batched call fetches all types), NCBI serialises the
whole document, and the parser drops `Chemical`, `Disease`, `Species`, `CellLine` on the
floor.

### Why it matters

This is not a correctness bug — the pipeline's output is gene-and-variant-centric and
rightly so. But the discarded annotations are structured, high-precision, and directly
relevant to extraction quality in several ways:

1. **Pharmacogenomics extraction quality.** Papers like the CPIC guideline PMID 35152405
   (SLCO1B1 / CYP2C9 / ABCG2 for statins) need drug ↔ gene linkage. PubTator's `Chemical`
   annotations would tell us "simvastatin," "rosuvastatin," "warfarin" appear in the text
   — priceless context for the Gemini prompt and for validation.
2. **Gene-disease association context.** `Disease` annotations identify the clinical
   phenotype the gene is being discussed in. Could feed the "Condition" column in the
   extraction schema with zero extra tokens.
3. **Species filter.** `Species` annotations let us distinguish "this gene is discussed in
   the context of mouse studies" vs. "human patient cohort." Currently the pipeline relies
   on HGNC validation to flag mouse-convention symbols *after* extraction (see
   `memory-decisions.md` 2026-02-28 "Mouse symbol flag is informational"). Upstream
   `Species` context would be cheaper and more reliable.
4. **Free data.** The annotations are already in the response body. Adding parsers for
   them is a dozen lines and zero additional API calls.

### Suggested action

Not urgent. Noted here so it's not rediscovered later:

- [ ] Extend `_parse_document` to also collect `PubTatorChemical`, `PubTatorDisease`,
      `PubTatorSpecies` dataclasses (same pattern as `PubTatorGene`).
- [ ] Thread them through `HybridExtractionResult` alongside the existing gene/variant
      lists.
- [ ] Optional downstream uses to evaluate:
      - Feed `Disease` and `Chemical` names into the Gemini Stage 3 prompt as context
        anchors for the "Condition" and "Drug" columns (if user schema has them).
      - Use `Species` annotations as a soft signal in gene validation (e.g., if a paper's
        `Species` list is `Mus musculus` only, raise murine-symbol confidence lower).
      - Expose as optional columns in the CSV for researchers who want them.
- [ ] Cheap to add; ship only when there's a concrete consumer for it — don't add data
      to the pipeline that nothing reads.

---

## F4 — Redundant fetches across the UI/pipeline boundary

**Date:** 2026-04-19
**Source:** End-to-end per-PMID fetch inventory (Section 5 of `pipeline-understanding.md`).
**Severity:** Efficiency bug. Wastes API quota, slows pipeline start, risks NCBI rate limits
on large batches.

### What we expected

When the user is browsing papers in `TopicResultsModal`, the UI already fetches metadata,
abstracts, and citation counts for every paper on the current page. A sensible system would
pass that data forward when the user clicks **Run**, so the pipeline can start with what
the UI already paid for.

### What we found

**Nothing is handed forward.** Only PMIDs cross the UI → pipeline boundary (see Section 1
of `pipeline-understanding.md`). The pipeline re-fetches everything from scratch, often
from *different* endpoints of the *same* service. For a paper the user just looked at, the
pipeline hits:

| Data | UI already fetched via | Pipeline re-fetches via | Format change |
|---|---|---|---|
| PubMed metadata (title, journal, authors, year, DOI, PMC) | NCBI `esummary.fcgi` (JSON) | NCBI `efetch.fcgi?rettype=medline` (Medline text) | JSON → Medline text |
| Abstract | NCBI `efetch.fcgi?rettype=abstract&retmode=xml` (XML) | Extracted from the same Medline response above | XML → text |
| Citation count | NIH iCite `/api/pubs` (JSON) | NIH iCite `/api/pubs` (JSON) — lazy, only when ranking or fallback | **Same endpoint, same format, same service** |

Three separate parsers handle what is essentially the same bibliographic record. The second
iCite call is especially wasteful — identical URL, identical params, identical response,
fetched again because the pipeline has no channel to receive the UI's copy.

### Concrete cost per run

For a **10-PMID user-curated run** (a typical "I want to extract genes from these papers"
workflow):

- UI fetches during selection: **3 calls** (esummary, efetch-abstracts, iCite — all batched)
- Pipeline re-fetches on start: **2 calls** for the same data (efetch Medline, iCite). Plus
  8 that genuinely couldn't have been prefetched (PMC XML, supplementary, figures, PubTator).

For a **100-PMID run** the redundant calls stay at 2 (both batched), but each one now covers
100 PMIDs — so the real cost is "~5 seconds of cold-start latency" and "2× the NCBI quota
burn on metadata."

For NCBI's default rate limit of 3 req/sec (no API key), this doesn't throttle. With the
`ENTREZ_API_KEY` ceiling of 10 req/sec, still fine. But the same pattern applied to every
pipeline stage is cumulative — the pipeline currently starts with an unnecessary round-trip
to a service it will hit many more times.

### Why it matters

1. **Fast-run degradation.** Every UX that encourages "quick re-runs" (re-queue a paper,
   retry failed extractions, compare runs) pays the redundant cost each time.
2. **Free-tier user impact.** Users without an `ENTREZ_API_KEY` are capped at 3 req/sec.
   The redundant metadata fetch is one of those three slots, during the critical
   pipeline-start moment where responsiveness matters most.
3. **Hidden inconsistency risk.** The UI's esummary JSON and the pipeline's Medline text
   return overlapping but **not identical** field sets (e.g. esummary's `pubtype` array vs.
   Medline's `PT` field; esummary's truncated `authors[0..3]` vs. Medline's full `AU` list).
   Any code that *thinks* it's comparing "the same paper as the UI showed" against what
   the pipeline processed has to reconcile two formats.
4. **Contradicts F3's fix path.** If we want to implement DOI → PMID resolution (F3),
   doing it in the UI now and passing the resolved PMID forward is cheaper than making the
   pipeline do it too.

### Suggested action

Two reasonable strategies — pick one, don't half-do it:

- **(A) Forward the UI's data.** Extend the `startPipeline(args)` IPC contract
  ([`python-bridge.ts:64`](app/src/main/python-bridge.ts:64)) to accept a pre-fetched
  metadata bundle (`{ [pmid]: { title, journal, doi, pmc, citations } }`), serialise it to
  a temp file, pass the path via env var, and let the pipeline consume it in place of the
  esummary/iCite refetches. Bonus: lets the pipeline skip the metadata fetch entirely when
  the UI provided everything.
  - Pro: one-off metadata fetch per paper per session, cleanest.
  - Con: requires adding a data channel; must handle stale data if user waits a long time
    between selecting and running (realistically not a concern — titles/authors don't change).

- **(B) Accept the redundancy, but only within the pipeline.** Pick one endpoint in the
  pipeline and stick with it. Currently the pipeline uses Medline text (#4) to get metadata
  and also reads abstract from PMC JATS XML (#5). Simpler: use efetch-XML like the UI
  does, parse once, use everywhere. Eliminates the Medline parser and one redundancy inside
  the pipeline, even if UI and pipeline still both hit NCBI.
  - Pro: much smaller change; no new IPC plumbing.
  - Con: doesn't remove the UI → pipeline duplicate, only the pipeline-internal one.

- [ ] Decide which (A or B) matches the project's priorities.
- [ ] If (A): add a small invalidation rule — if the PMID bundle is older than, say,
      24 hours, refetch. Cheap safety net.
- [ ] Either way: the second iCite call inside the pipeline (#10 in Section 5.2) is the
      single clearest win. UI has already fetched this for every paper on screen. Even
      without full bundle-forwarding, a `citationCounts` map in `startPipeline` args
      would eliminate one entire fetch stage.

---

## F3 — DOI and PMC ID inputs are silently dropped from user-defined lists

**Date:** 2026-04-19
**Source:** Walking through a realistic paste-box input end-to-end.
**Severity:** Silent data loss at an entry boundary. UX correctness bug.

### What we expected

The "Specific Papers" paste box
([`SmartInput.tsx`](app/src/renderer/components/SmartInput.tsx)) explicitly advertises
support for four identifier formats in its placeholder text:

> *"Paste PMIDs, DOIs, PMC IDs, or PubMed URLs"*

…with examples including `DOI: 10.1234/example`. The parser recognises all four types and
the validated-papers UI displays them all. A user has every reason to expect all four to
reach the pipeline.

### What we found

Only PMID-classified entries reach the pipeline. The drop happens in two places:

1. [`SmartInput.tsx:184`](app/src/renderer/components/SmartInput.tsx:184) —
   `useValid()` returns only `papers.filter(p => p.pmid)`.
2. [`QueryBuilder.tsx:164`](app/src/renderer/pages/QueryBuilder.tsx:164) —
   `specificPapers.map(p => p.pmid).filter(Boolean)` strips again.

No reverse lookup is attempted. DOI → PMID and PMC → PMID conversions both exist as trivial
NCBI API calls (`esearch?term={doi}[AID]` and `elink` respectively) but neither is wired in.

Concrete trace with `PMC9035072` and `10.1038/nature12373` pasted:
- Parser tags them `pmc` and `doi` — correctly identified.
- `fetchDetails` is only called for `pmid`-typed entries, so no metadata lookup happens.
- The UI's validated-papers list shows both (with URLs to PMC/doi.org), implying they're accepted.
- On **"Use these"**, both are silently dropped because they lack `.pmid`.
- The pipeline never sees them.

### Why it matters

1. **UI/behaviour mismatch.** The placeholder says the input accepts DOIs and PMC IDs. The
   code parses them. The validated-papers panel displays them. They appear to be selected.
   They aren't processed. This is the worst-case UX outcome: the system looks like it's
   working and silently fails.
2. **DOIs are how researchers cite papers.** A biomedical researcher building a list from
   a published reference section will most naturally paste DOIs. This path is probably used
   more than raw PMIDs.
3. **Compounds with F2.** Even if a user works around this by pasting only PMIDs, they can
   still feed paywalled PMIDs unchecked (F2). Entry-path validation across the specific-
   papers flow is generally under-enforced.

### Suggested action

- [ ] Implement reverse lookup in `SmartInput.validate()`:
  - DOI → PMID via NCBI esearch `term={doi}[AID]` (single-call, fast, already rate-limited
    on the main process side)
  - PMC ID → PMID via NCBI esummary on `db=pmc` or elink
  - If lookup fails (paper not in PubMed), surface it in the existing `invalid` list with a
    clear reason ("DOI not found in PubMed" / "PMC not indexed in PubMed").
- [ ] Alternatively — and more honestly in the short term — **strip DOI/PMC from the
      placeholder text and parser** until the backend supports them. Better to refuse input
      than accept-and-drop.
- [ ] After fixing, verify `useValid()` and `QueryBuilder`'s merge both consume all items,
      not just those with a `.pmid` field.

---

## F2 — "All papers are OA" is not actually enforced on all entry paths

**Date:** 2026-04-19
**Source:** Tracing paper selection paths vs. the OA filter.
**Severity:** Architectural invariant violation. Silently degrades extraction quality.

### What we expected (and what the code assumes)

The project principle — repeated in code, docs, and the SoftwareX paper — is that the pipeline
is **OA-only**: every paper reaching full-text extraction has freely available full text.
The pipeline's architecture depends on this:

- [`pipeline/modules/full_text_fetcher.py:1–14`](pipeline/modules/full_text_fetcher.py) opens
  with an explicit guarantee:
  > *"Since the PubMed search step filters to open-access papers only (ENABLE_OA_FILTER=True),
  > every PMID that reaches this module is guaranteed to have free full text."*

  On the strength of that guarantee, Playwright, Trafilatura, paywall detection, and
  publisher-specific scrapers were all removed as "unreachable dead code" (F5 in `AUDIT.md`).

### What we found

The guarantee holds for **two of three** entry paths. The third silently bypasses it.

| Entry path | OA filter applied? | Where |
|---|---|---|
| Topic search (query) | ✅ Yes | `search_pubmed()` appends `"loattrfull text"[sb]` ([`pubmed_data_collector.py:169–182`](pipeline/modules/pubmed_data_collector.py:169)) |
| Author search | ✅ Yes | `search_pubmed_by_author()` delegates to `search_pubmed()` ([`pubmed_data_collector.py:244`](pipeline/modules/pubmed_data_collector.py:244)) |
| **Specific PMIDs (paste box)** | ❌ **No** | [`SmartInput.tsx`](app/src/renderer/components/SmartInput.tsx) calls `pubmed:fetchDetails` but never gates on the `pmc` field; the PMIDs flow straight to `mandatory_pmids` ([`pipeline_orchestrator.py:685`](pipeline/modules/pipeline_orchestrator.py:685)) and are explicitly exempt from filtering |

A user pasting a paywalled PMID (e.g. NEJM, old papers pre-PMC deposit) gets that paper
accepted into the run with no warning. When it reaches `full_text_fetcher`:

- Both OA endpoints (PMC efetch, Europe PMC) return nothing
- The fetcher returns an empty `ContentExtractionResult` with
  `extraction_method="no_oa_full_text"` ([`full_text_fetcher.py:934–945`](pipeline/modules/full_text_fetcher.py:934))
- A `logger.warning` is emitted — not surfaced in the UI's main log stream
- The paper contributes empty content to downstream stages; the user sees a "fetch failed"
  count but not *why*

### Why it matters

1. **The architectural claim underpinning Playwright removal is false.** F5 in AUDIT.md
   justified deleting the paywall-handling code because "the OA filter upstream makes this
   unreachable." That filter doesn't cover the specific-PMIDs path, so the code was reachable
   — the removal happens to be OK only because the failure mode is "silently produce nothing"
   rather than "crash."
2. **Silent quality degradation.** A researcher pasting a list of key papers for a review
   may have no idea that some of them were dropped to abstract-only. This is exactly the
   "silent failure at screening" failure mode flagged as unacceptable in `CLAUDE.md`.
3. **The UI signal already exists but isn't enforced.** `TopicResultsModal` uses the `pmc`
   field as an OA proxy for badge colour — the same check could gate `SmartInput`.
4. **Existing precedent confirms the problem.** The benchmark gold standard notes PMID
   21076407 as "paywalled → 0 genes extracted" (memory-sessions.md). That paper is in the
   benchmark precisely because someone pasted its PMID without the OA gate stopping it.

### Suggested action

- [ ] Decide the enforcement point. Options:
  - **UI gate (preferred):** `SmartInput.tsx` rejects pasted PMIDs where `fetchDetails`
    returns no `pmc` field, with a clear "not open-access" error. Mirrors the topic-search
    badge logic.
  - **Pipeline gate:** `pipeline_orchestrator.py` filters `specific_pmids` by `pmc`
    presence after `fetch_paper_details`. Less friendly — user only learns mid-run.
  - **Both:** UI prevents the common case, pipeline as defence-in-depth.
- [ ] Decide whether author search should use a stricter OA check too (currently relies on
      `[Author]` + `loattrfull text[sb]`, which is correct but worth re-confirming).
- [ ] If the rejection is a hard "no," the orchestrator/full-text fetcher should also
      explicitly surface `no_oa_full_text` papers to the UI (not just a warning) so the user
      knows which papers contributed nothing.
- [ ] Revise `full_text_fetcher.py`'s opening comment — the guarantee claim is currently
      wrong and future contributors will rely on it.

---

## F1 — The "4× overfetch factor" does not exist in code

**Date:** 2026-04-19
**Source:** Tracing the handoff from user paper selection → `pipeline_orchestrator.run_pipeline()`.
**Severity:** Documentation inaccuracy. No runtime impact. Affects publication correctness.

### What we expected

Documentation in multiple places claims the pipeline applies a 4× overfetch factor — "if the
user asks for 10 papers, 40 are analysed" — to compensate for paywalled papers and failed
extractions.

References asserting this:
- [`.claude/rules/memory-decisions.md:164`](.claude/rules/memory-decisions.md:164) —
  "mitigated by overfetch factor (4x)"
- [`docs/pipeline-internals.md:369`](docs/pipeline-internals.md:369) —
  "`ANALYSIS_OVERFETCH_FACTOR=4` … fetches and analyzes 40 candidates"
- [`docs/pipeline-internals.md:1122`](docs/pipeline-internals.md:1122) — config table
- [`docs/reports/pipeline-report.tex:319`](docs/reports/pipeline-report.tex:319)
- [`publication/sections/02_description.tex:14`](publication/sections/02_description.tex:14) —
  "an overfetch factor of 4× ensures sufficient open-access papers reach extraction"
- [`publication/working/MEETING_NOTES_2026-03-09.md:219`](publication/working/MEETING_NOTES_2026-03-09.md:219)
- Several Elicit-research notes in `publication/working/elicit_research/`

### What we found

- `ANALYSIS_OVERFETCH_FACTOR = 4` is defined in
  [`pipeline/modules/config.py:158`](pipeline/modules/config.py:158), but
  **not referenced anywhere else in the codebase** (grep confirmed: single occurrence).
- The only candidate-widening mechanism that actually runs is
  `PUBMED_RELEVANT_COUNT = 200` in
  [`pipeline_orchestrator.py:710`](pipeline/modules/pipeline_orchestrator.py:710),
  which pulls up to 200 candidates from PubMed — **independent of `top_n`, not a multiplier**.
  It only fires when the user provides a search query.
- For a user-curated PMID list,
  [`pipeline_orchestrator.py:685`](pipeline/modules/pipeline_orchestrator.py:685) treats
  every `specific_pmid` as `mandatory_pmids`. All are included, none are added. 1:1.

### Why it matters

1. **Publication accuracy.** `02_description.tex` makes a claim about system behaviour that
   the system does not implement. Reviewers running the code would find this out.
2. **Design rationale drift.** The memory-decisions entry frames overfetching as a deliberate
   mitigation for OA paywalls (~40–60% of PubMed). If the team ever *needs* that mitigation,
   they'd assume it's already in place — and it isn't.
3. **Conceptually incoherent for curated lists.** Overfetching a hand-picked list would defeat
   the point of user curation. The code correctly does not do this; the docs confusingly imply
   it would.

### Suggested action

- [ ] Decide: implement the overfetch, or remove the claim.
  - If implementing: only applies to query-mode runs; `specific_pmids` must remain 1:1.
  - If removing: it's likely the right call — `PUBMED_RELEVANT_COUNT=200` already gives a
    substantial candidate pool on query-mode, and PMID-mode should trust the user.
- [ ] Update `publication/sections/02_description.tex` before submission.
- [ ] Remove/correct references in `memory-decisions.md`, `docs/pipeline-internals.md`,
      `docs/reports/pipeline-report.tex`, `publication/working/*`.
- [ ] Either delete `ANALYSIS_OVERFETCH_FACTOR` from `config.py` or wire it up — don't leave
      orphaned config.
