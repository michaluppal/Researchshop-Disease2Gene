# PubMed Query Results Presentation — How It Works

> Codex migration note (2026-04-25): this is the active PubMed results-flow reference for
> Codex sessions. Historical Claude-era wording should be left intact unless it is active guidance.

> Written 2026-03-15. Covers the full flow from query submission to pipeline handoff.
> Files: `QueryBuilder.tsx`, `TopicResultsModal.tsx`, `geneRelevanceScorer.ts`, `journalQuality.ts`, `ipc-handlers.ts`

---

## 1. Query construction (`QueryBuilder.tsx`)

The user builds a query using condition rows (term + field + Boolean operator) or raw PubMed syntax. As the user types, a debounced count fetch (`pubmed:count` → NCBI esearch `count` endpoint) shows the live result count alongside the form — this is purely informational so the user can refine before opening the modal.

When "Preview Papers" is clicked, `TopicResultsModal` opens with the constructed query string.

---

## 2. Initial search — PMID retrieval (`TopicResultsModal.tsx` lines 73–99)

The modal immediately fires `window.api.pubmed.search(query)`, which calls the `pubmed:search` IPC handler. That handler:
- Calls NCBI esearch with `usehistory=n&retmax=500` — fetches up to 500 PMIDs
- Returns `{ count, pmids }` — `count` is the *total* PubMed hit count; `pmids` is the list actually fetched

**Hard limit:** If `count > 500`, the modal shows a "too many results" warning and stops. The user must narrow their query. This is intentional — processing 500+ papers in the UI would be unresponsive, and queries that broad usually indicate the search terms are too vague to be useful for gene extraction.

**What's in the PMID list:** The PubMed API returns PMIDs in its own relevance order ("best match") by default. This order is preserved as the `relevance` sort mode.

---

## 3. Page fetch — three parallel calls (`fetchPage`, lines 102–170)

Results are displayed 20 at a time (`PAGE_SIZE = 20`). When a page loads, three API calls fire in parallel via `Promise.all`:

### a) `pubmed:fetchDetails` — paper metadata
Calls NCBI esummary API for the page's 20 PMIDs. For each paper, the handler extracts:
- `title`, `journal`, `authors` (first 3), `pubYear`, `doi`, `pmc`, `url`
- `publicationTypes` — array from the `pubtype` field (e.g. `["Journal Article"]`, `["Review", "Journal Article"]`)
- `pmc` presence → used as **OA proxy**. If a PMC ID exists, the paper has a PMC record and full text is likely available. This is reliable because the search itself filtered for open-access papers via `"loattrfull text"[sb]` (applied in `pubmed_data_collector.py`). Papers with PMC IDs get a green "Full text" badge; others get amber "Abstract only".

### b) `citations:fetch` — citation counts
Calls iCite (NIH) for citation counts. iCite is the primary source; if it fails, falls back to Semantic Scholar. Citation counts are used in the composite impact score.

### c) `pubmed:fetchAbstracts` — abstract text
Calls NCBI efetch XML API (`rettype=abstract&retmode=xml`), parses `<AbstractText>` elements. Abstracts are needed for gene relevance scoring. If this call fails, the modal shows a warning banner and disables filtering (shows all papers) — users can still select papers, just without relevance badges.

---

## 4. Per-paper processing (lines 127–149)

For each of the 20 papers, four values are computed locally (no additional API calls):

### Journal quality score (`journalQuality.ts`)
A hardcoded three-tier system:
- **Tier 1 (score 100):** ~25 top journals — Nature, Science, Cell, NEJM, Lancet, JAMA, Nature Genetics, etc.
- **Tier 2 (score 80):** ~30 journals — PLOS Genetics, Genome Research, Bioinformatics, BMJ, etc.
- **Tier 3 (score 60):** ~20 journals — Frontiers, PLOS ONE, Scientific Reports, etc.
- **Unranked (score 40):** everything else
- **Fuzzy override:** if journal name contains 'nature'/'cell'/'science' → 80; 'lancet'/'jama'/'nejm' → 90

Displayed as Q1/Q2/Q3 badge next to the journal name.

### Composite impact score (`calculateCompositeScore`)
```
normalized_citations = min(citationCount / 500 × 100, 100)
composite = (normalized_citations × 0.6) + (journalQuality × 0.4)
```
Normalized against 500 citations as the ceiling — papers with 500+ citations all score 100 on the citation component. Displayed as "Impact: N" badge; clicking it opens a breakdown panel.

**Intent:** This gives an orderable signal for "which papers are most established/influential" without requiring the user to know citation counts. A paper in Nature with 50 citations scores higher than a paper in a minor journal with 50 citations.

### Gene relevance score (`geneRelevanceScorer.ts`)
Runs fully client-side on the abstract + title text. Implements the same weighted keyword algorithm as the Python `abstract_screener.py`:

- **Positive high weight (+3):** mutation, variant, snp, gwas, sequencing, gene expression, genotype, CRISPR, rare disease, exome, genome-wide, ...
- **Positive low weight (+1):** biomarker, therapy, treatment, pathway, ...
- **Negative weight:** systematic review (−5), meta-analysis (−5), psychological (−3), quality of life (−2), policy (−2), ...
- **Gene symbol detection:** regex `[A-Z]{2,6}[0-9]{1,3}` + a `KNOWN_ALPHA_GENES` set (TP53, BRCA1, KRAS, IL6, etc.)
- **Molecular-context precision gate:** if gene symbols found but no molecular terms (mutation, variant, sequencing, gwas, ...) → penalty of `-(geneCount + 3)`. This prevents clinical papers mentioning IL-6 or CRP as lab values from scoring as gene-relevant.

Tier thresholds: **high** ≥10, **medium** ≥5, **low** 1–4, **none** ≤0.

Returns `{ score, tier, geneSymbols, topKeywords, hasMolecularContext }`.

---

## 5. Filtering — default hide low-relevance (lines 192–200)

```typescript
const visiblePapers = showAll ? sortedPapers
  : sortedPapers.filter(p => !p.relevance || p.relevance.tier === 'high' || p.relevance.tier === 'medium')
```

**Intent:** Most searches return some papers that mention a disease name but contain no molecular genetics content (clinical outcome studies, reviews, RCTs). These would waste the user's extraction quota. They're hidden by default but not removed — the "Show all (N hidden)" toggle reveals them, dimmed at 60% opacity, so a researcher who specifically wants one of them can still add it.

If abstract fetching failed entirely, `showAll` is forced to `true` — don't hide papers when you can't actually evaluate them.

---

## 6. Auto-selection on page 1 (lines 153–162)

On the **first** page load only, papers with tier = `high` or `medium` are automatically pre-selected. The intent is to reduce friction for the common case: run a focused query, see the top 20 papers, most relevant ones already checked, glance through and click "Add".

Auto-selection does **not** happen on subsequent pages — the user has explicitly navigated there and should consciously choose those papers.

---

## 7. Sorting (lines 179–190)

Four sort modes via dropdown:
- **Best Match** (`relevance`) — preserves NCBI's own relevance ordering (the order PMIDs came back from esearch)
- **Most Recent** (`recent`) — descending by `pubYear`
- **By Impact** (`impact`) — descending by `compositeScore` (citations + journal tier) — **default**
- **Gene Relevance** (`gene-relevance`) — descending by `relevance.score`

Default is "By Impact" because for literature synthesis, established highly-cited papers in top journals are the most trusted starting point. Researchers studying emerging/rare findings should switch to "Most Recent" or "Gene Relevance".

---

## 8. Card rendering — what each element communicates

Each paper card shows (top to bottom):

| Element | Source | Intent |
|---|---|---|
| **Title** (2-line clamp) | esummary | Primary identification |
| **Authors** (first 4, et al.) | esummary | Secondary identification |
| **Journal + year + Q1/Q2/Q3 badge** | esummary + journalQuality | Venue credibility at a glance |
| **Abstract preview** (2 lines) | efetch XML | Let user see content without clicking |
| **PMID badge** | esummary | Permanent identifier |
| **N citations badge** | iCite | Raw citation number |
| **Review / Meta-Analysis / Editorial badge** (red) | esummary `pubtype` | Warn: pipeline extracts poorly from reviews — they describe other papers' findings, not molecular data |
| **Full text / Abstract only badge** | `pmc` field presence | Warn if only abstract available — extraction quality degrades |
| **Gene content / Moderate relevance / Low relevance badge** | geneRelevanceScorer | Pipeline extraction confidence prediction |
| **Genes: BRCA1 · TP53 · ...** | geneRelevanceScorer | Which specific genes the scorer detected |
| **Keywords: mutation, variant, ...** | geneRelevanceScorer | Why the score is high |
| **Low-relevance reason** (amber italic) | derived from relevance + publicationTypes | Why a paper is hidden by default |
| **View on PubMed** link | esummary url | Open paper page in browser |
| **DOI** link | esummary doi | Open publisher page in browser |
| **Full abstract** toggle | efetch XML | Read complete abstract inline |
| **Impact: N** badge (clickable) | compositeScore | Opens breakdown panel showing the math |

Low-relevance papers (when shown) are rendered at 60% opacity with a lighter checkbox border — visually subordinate but still selectable.

---

## 9. Cross-page selection tracking (lines 293–294)

```typescript
const currentPagePmids = new Set(visiblePapers.map(p => p.pmid).filter(Boolean))
const offPageSelected = Array.from(selected).filter(pmid => !currentPagePmids.has(pmid)).length
```

The `selected` Set persists across page navigation. The footer shows "(+N on other pages)" when papers on other pages are selected, so the user never loses track of their full selection.

---

## 10. Handoff to pipeline (lines 227–239, `handleAdd`)

When "Add N Papers" is clicked:
- Collects `PaperItem` objects for all selected PMIDs that are on the current page (have full metadata)
- For any selected PMID *not* on the current page, creates a minimal `{ pmid, url }` object — the pipeline only needs the PMID
- Calls `onSelectPapers(selectedPapers)` → bubbles up to `QueryBuilder.tsx` → stored in `topicPapers` state
- The pipeline receives only the PMID list — none of the UI-computed scores (relevance, compositeScore, journalQuality) travel to Python. The pipeline is agnostic to selection rationale.

---

## What the pipeline does NOT know

The pipeline receives a flat PMID list. It doesn't know:
- Why a paper was selected (user override vs auto-select)
- The paper's gene relevance score
- Whether it's a review article
- Whether it has full text in PMC

The OA filter runs again independently inside `pubmed_data_collector.py` at pipeline start — it re-checks PMC availability and degrades gracefully to abstract-only for papers where full text retrieval fails.

---

## Known limitations / things to be aware of

- **`pmc` as OA proxy is imperfect**: A PMC ID means the paper is *indexed* in PMC but not necessarily that full text is available via the API. Some PMC papers are embargoed or publisher-deposited without full text. The pipeline will degrade to abstract-only when fetch fails.
- **Citation counts from iCite have a lag**: iCite processes citation data monthly. Very recent papers may show 0 citations even if already well-cited in preprint form.
- **Journal tier list is static**: The hardcoded list in `journalQuality.ts` needs manual maintenance. Journals not on the list get the unranked default (40). Field-specific high-impact journals (e.g. *Human Mutation*, *American Journal of Human Genetics*) may be undertired.
- **Gene symbol regex produces false positives**: The pattern `[A-Z]{2,6}[0-9]{1,3}` matches things like "COVID19", "PCR12", "IgG4". The molecular-context gate partially mitigates this but doesn't eliminate it.
- **Sorting is per-page only**: The sort operates on the 20 papers fetched for the current page. "By Impact" on page 2 shows the 20 papers of page 2 sorted by impact — it does not globally re-rank all 500 papers. Global re-ranking would require fetching all metadata upfront, which is too slow.
- **500-paper cap**: The esearch `retmax=500` cap means very broad queries simply can't be processed in the modal. This is a deliberate UX constraint, not a technical limitation.
