# Elicit Research Analysis — ResearchShop Competitive Intelligence

> 12 Elicit blog articles analyzed against ResearchShop Disease2Gene architecture.
> Each file covers: article summary, technical insights, honest comparison, implications for RS, and implications for **Glyph**.

---

## Files

| # | File | Article | Key Finding |
|---|------|---------|-------------|
| 1 | [01_system2_learning.md](01_system2_learning.md) | Against RL: The Case for System 2 Learning | RS's 7-stage validated pipeline is already a practical System 2 architecture — frame it that way in the paper |
| 2 | [02_auto_evaluation.md](02_auto_evaluation.md) | Trust at Scale: Auto-evaluation | RS's deterministic validation (HGNC, grounding) is stronger than LLM-eval for gene accuracy, but free-text fields are unprotected |
| 3 | [03_semantic_search.md](03_semantic_search.md) | From grep to SPLADE | PubMed delegation is right for SoftwareX; highest-ROI improvement is HGNC-alias query expansion |
| 4 | [04_search_vs_vectordb.md](04_search_vs_vectordb.md) | Build a Search Engine, Not a Vector DB | RS has no search quality evaluation — biggest engineering gap |
| 5 | [05_strict_screening.md](05_strict_screening.md) | Introducing Strict Screening | User-defined inclusion/exclusion criteria are Elicit's biggest systematic-review advantage over RS |
| 6 | [06_keyword_search.md](06_keyword_search.md) | Introducing Keyword Search | LLM-assisted query construction with HGNC aliases is the single highest-ROI search improvement RS could add |
| 7 | [07_research_agents.md](07_research_agents.md) | New in Elicit: Research Agents | Add agent UX (iterative refinement, clarification) without abandoning RS's deterministic pipeline |
| 8 | [08_clinical_trials.md](08_clinical_trials.md) | Introducing Clinical Trials | ClinicalTrials.gov integration is highest-value near-term extension, especially for pharmacogenomics (F1=0.000) |
| 9 | [09_systematic_review_eval.md](09_systematic_review_eval.md) | How We Evaluated Elicit Systematic Review | **RS's 12-paper benchmark is underpowered for SoftwareX — needs 30-50 papers + external validation** |
| 10 | [10_reports_eval.md](10_reports_eval.md) | How We Evaluated Elicit Reports | Transparent methodology and academic-only sources are the most valued features — RS already has both |
| 11 | [11_notebooks.md](11_notebooks.md) | Introducing Notebooks | RS's batch pipeline model is the biggest UX gap vs. Elicit's interactive workspace |
| 12 | [12_factored_verification.md](12_factored_verification.md) | Factored Verification | RS's filter-and-drop is more conservative than Elicit's verify-and-revise — avoids 37% hallucination increase from unconditional self-revision |

---

## Cross-Cutting Themes

### Where RS Does Better Than Elicit

1. **Domain specificity** — HGNC (44,943 genes), PubTator3 NER, HGVS variant patterns give RS structural knowledge Elicit's generic LLM cannot replicate
2. **Hallucination control** — Grounding check + deterministic seeding + confidence gate is more conservative than Elicit's factored verification; filter-and-drop avoids the 37% hallucination increase from unconditional self-revision
3. **Reproducibility** — Multi-run repeatability measurement and controlled ablation (36-run figure experiment) that Elicit does not report
4. **Privacy** — Desktop-first, no server, zero data leaves the user's machine
5. **Cost** — Free, no subscription, users bring their own API key
6. **Structured output** — Schema-driven CSV with typed gene/variant/citation columns vs. Elicit's prose reports

### Where Elicit Does Better Than RS

1. **Evaluation infrastructure** — Meta-evals, gold standards (hundreds of verified answers), 17 external PhD evaluators. RS has 12 papers and no external validation
2. **Search quality** — SPLADE + keyword + semantic hybrid vs. RS's pure PubMed Entrez delegation. No search eval pipeline in RS
3. **Scale** — 138M+ papers, ClinicalTrials.gov, web sources. RS limited to PubMed OA papers
4. **UX / workspace model** — Notebooks, iterative chat, multi-query aggregation. RS is a single-shot batch pipeline
5. **Screening expressivity** — Elicit's strict criteria let users define arbitrary inclusion/exclusion logic. RS gene-relevance is hardcoded
6. **Benchmark size** — Elicit benchmarked 58 systematic reviews for screening, ~128 gold standard answers for extraction. RS: 12 papers

### Immediate Actionable Improvements for RS (pre-SoftwareX)

| Priority | Improvement | Effort |
|----------|-------------|--------|
| 🔴 High | Expand benchmark to 20-30 papers with external validation | High |
| 🔴 High | Add smoke tests that assert >0 citations validate on known-good input | Low |
| 🟡 Medium | LLM-assisted PubMed query construction using existing Gemini key + HGNC aliases | Medium |
| 🟡 Medium | Claim-level verification for free-text Key Findings column | Medium |
| 🟢 Low | Cross-run CSV aggregation UI (notebook-style result exploration) | Medium |

---

## Project Glyph — Vision Summary

> *Glyph: a repo-like structure for every paper, used in a graph RAG to solve the unread papers problem in genomics.*

### The Problem Glyph Solves

Genomics researchers are deep specialists. A cardiologist studying LMNA variants doesn't read papers on yeast membrane biology — even though the yeast literature may contain the mechanism explanation that unlocks their clinical puzzle. The knowledge exists; the connections are never made.

Elicit helps researchers find and screen papers they *know* they want. Glyph would help researchers find papers they *don't know* they need.

### The Architecture

Each paper becomes a structured repository:
```
paper/{pmid}/
├── metadata.json       # PMID, title, authors, year, citation count
├── full_text.md        # cleaned prose, section-tagged
├── genes.csv           # extracted genes with confidence, biotype, variant
├── variants.csv        # HGVS-normalized variants with evidence citations
├── figures/            # extracted figure captions + gene labels
├── citations.csv       # key claims with supporting text
├── mesh_terms.csv      # MeSH concepts for semantic bridging
└── graph_edges.json    # explicit gene→function, gene→disease, gene→pathway edges
```

This is the natural output of the RS pipeline — the CSV files RS already produces, enriched and persisted per-paper rather than discarded after each run.

### The Graph RAG Layer

Nodes: papers, genes, variants, pathways, diseases, phenotypes
Edges: co-mention, citation, shared gene, pathway membership, variant→disease

A researcher asks: *"What mechanisms cause LMNA-linked dilated cardiomyopathy?"*

Graph RAG traverses:
1. Start at LMNA → find all papers in the graph mentioning LMNA
2. Expand to mechanistic terms in those papers (nuclear lamina, chromatin organization, mechanotransduction)
3. Find papers sharing those mechanisms that *don't* mention LMNA — these are the cross-domain discoveries
4. Rank by graph centrality × confidence × novelty (not in the researcher's existing citation network)

### What Each Elicit Article Contributes to Glyph

| Article | Glyph Insight |
|---------|---------------|
| System 2 Learning | Graph RAG is System 2 reasoning — explicit, auditable, transparent world model |
| Auto-evaluation | Eval infrastructure must be built into the graph from day 1; node-level confidence scores |
| Semantic Search | Structured graph queries are fundamentally more powerful than embedding search for constraint-rich genomics |
| Search vs Vector DB | Build the graph, not just embeddings — structure enables reproducible traversals |
| Strict Screening | Graph edges have typed confidence; traversal criteria replace screening criteria |
| Keyword Search | HGNC aliases + MeSH synonyms embedded in graph edges solve the synonym problem structurally |
| Research Agents | Agents traverse the graph; paper-as-repo gives agents persistent grounding Elicit's sessions lack |
| Clinical Trials | Trials are first-class nodes; NCT IDs link trial arms to gene targets to outcome papers |
| Systematic Review Eval | Recall across the full graph (not just searched papers) is the right metric for Glyph |
| Reports Eval | Glyph reports trace provenance through graph paths, not just citations — fully auditable |
| Notebooks | Each graph traversal session is a notebook; persist queries and results as graph annotations |
| Factored Verification | Each graph edge is a verified claim — factored verification is the edge-creation protocol |

### Why Glyph Beats Both Elicit and RS for Cross-Domain Discovery

- **RS** extracts structured data per paper but discards the relationships between papers
- **Elicit** finds papers matching a query but doesn't reason about cross-domain mechanisms
- **Glyph** persists relationships as first-class graph data, enabling queries like:
  - *"Which genes in cardiomyopathy papers share pathways with genes in yeast aging papers?"*
  - *"What variants in condition X were first described in model organism research from 1990-2005?"*
  - *"Which unpublished (preprint) mechanisms in neuroscience have structural analogs in the cancer literature?"*

The unread paper problem is not a search problem. It's a **representation** problem. Glyph solves it by making the knowledge structure explicit and traversable.
