# Build a Search Engine, Not a Vector DB — Elicit Research Analysis

## Article Summary

This engineering blog post by Adrian "Panda" Smith (Elicit Infrastructure Engineer, Dec 2023) argues against the common pattern of treating vector databases as "memory" for LLMs. The core thesis: if you want to build a good RAG-based tool, first build a good search engine. Smith draws on experience building Stripe's AI docs product to make the case that naive embed-and-retrieve approaches hit a dead end because vector search, like all search, returns irrelevant or missing documents -- and LLMs are misled by irrelevant context. The article advocates for hybrid search (keyword + embedding), LLM-assisted query construction, and LLM-based re-ranking as the modern search stack, noting that Elicit uses Vespa for this purpose. The post concludes with a sobering reminder that evaluation infrastructure is just as critical as the search pipeline itself.

## Key Technical Insights

- **Vector search is not magic memory** -- it is a particular kind of search with the same failure modes as keyword search (false positives, false negatives), just along different axes
- **Irrelevant documents in context actively mislead LLMs** -- the article cites research (arxiv 2302.00093) showing that retrieved noise degrades LLM performance, not just wastes tokens
- **Hybrid search (keyword + embedding) outperforms either alone** -- Google has done this since BERT; Elicit uses Vespa to combine both modalities
- **LLM-assisted query construction** is low-hanging fruit -- models can add date filters, expand synonyms, and restructure queries in ways that previously required specialized expertise
- **LLM-based re-ranking** can beat all but the best purpose-built ranking models (citing arxiv 2311.07994), and is dramatically cheaper to build
- **Evaluation is the hard part** -- building the search engine is only half the work; you need monitoring infrastructure to answer: when is search appropriate, what content are you locating, and how well does it rank
- **Elicit's stack: Vespa** -- hybrid keyword + vector search engine

## How Elicit Approaches This Problem

Elicit treats search as a first-class engineering problem, not a side effect of having embeddings. Their infrastructure uses Vespa for hybrid search combining traditional keyword matching (later enhanced with SPLADE, per their separate semantic search post) with embedding-based retrieval. They layer LLM-assisted query construction on top -- visible in their keyword search product where a plain-language question is automatically converted into a structured Boolean query. Re-ranking is LLM-powered. They search across 138M+ papers and index PubMed, ClinicalTrials.gov, and their own paper bank. Their approach is cloud-hosted with substantial infrastructure investment.

## How ResearchShop Approaches This Problem

ResearchShop takes a fundamentally different approach to search, delegating it entirely to PubMed's Entrez API rather than building a custom search engine:

- **Stage 1 (`pubmed_data_collector.py`)**: Queries are sent directly to NCBI Entrez, relying on PubMed's own indexing, MeSH term expansion, and relevance algorithms. No custom embedding or hybrid retrieval.
- **Ranking**: iCite citation counts (primary) with Semantic Scholar fallback. This is a citation-based ranking, not a relevance-based ranking -- papers are sorted by how well-cited they are, not how well they match the query semantically.
- **Gene relevance scoring (`geneRelevanceScorer.ts`)**: A lightweight keyword + regex scorer in the UI that acts as a post-search filter, not a search engine. It scores abstracts for gene-related content after PubMed returns results.
- **Overfetch factor (4x)**: Compensates for the imprecision of using PubMed directly -- fetch 4x more papers than needed, then filter down.
- **No embedding, no vector DB, no hybrid search**: The entire search layer is PubMed-as-a-service.

## Where We Do Better

- **Domain specialization**: By delegating to PubMed, RS inherits decades of biomedical indexing expertise (MeSH controlled vocabulary, automated term mapping) that a general-purpose vector DB could not replicate. PubMed's search is purpose-built for biomedical literature.
- **Zero infrastructure cost**: No Vespa cluster, no embedding generation pipeline, no index maintenance. PubMed handles all of this. For a desktop app with no server, this is an existential advantage.
- **Reproducibility**: PubMed queries are deterministic and reproducible (same query, same PMID set). Embedding-based search has non-trivial reproducibility challenges (model updates, index rebuilds, score drift).
- **Transparency**: Users can take the exact same query and run it on pubmed.ncbi.nlm.nih.gov to verify results. No black-box retrieval.

## Where Elicit Does Better

- **Recall on cross-domain queries**: Embedding search finds semantically related papers that keyword search misses entirely. A query about "protein misfolding diseases" would find papers about specific prion diseases even if they never use the term "misfolding." RS is limited to PubMed's term expansion, which is good but not semantic.
- **Query construction quality**: Elicit's LLM-assisted query builder converts natural language to structured Boolean queries with synonym expansion. RS users must either write their own PubMed queries or rely on PubMed's automated term mapping, which is competent but not LLM-augmented.
- **Re-ranking by relevance**: Elicit re-ranks by semantic relevance to the query. RS ranks by citation count, which is a popularity signal, not a relevance signal. A highly cited paper about a tangential topic will outrank a lesser-cited paper that perfectly answers the question.
- **Scale**: 138M+ papers across multiple sources vs. PubMed-only (approximately 36M records). RS misses preprints, non-PubMed-indexed venues, and clinical trial registries at the search level.
- **Evaluation infrastructure**: Smith emphasizes that Elicit invests heavily in search evaluation. RS has no search quality evaluation -- there is no measurement of whether PubMed returns the right papers for a given gene-disease query.

## Implications for ResearchShop

1. **Search quality is an unexamined assumption**: RS assumes PubMed returns the right papers and compensates with overfetching. Smith's article suggests this is exactly the mistake that leads to poor downstream results. Silent false negatives at the search stage are the hardest failures to detect.

2. **Citation ranking is not relevance ranking**: Sorting by citation count is appropriate for "what are the landmark papers" but poor for "what papers contain gene X findings." A relevance-aware re-ranking step -- even a lightweight LLM-based one using abstracts -- would improve the quality of papers entering the extraction pipeline.

3. **LLM query expansion is low-hanging fruit**: Using Gemini to expand a user's query into a better PubMed search string (adding MeSH terms, gene aliases, variant nomenclature) would improve recall without requiring any search infrastructure. This could be done client-side with the user's existing API key.

4. **Evaluation gap**: RS has benchmarks for extraction quality (F1 per paper type) but none for search quality. Adding a search-level evaluation -- "for disease X, do we find the known gene-association papers?" -- would close a blind spot.

5. **The overfetch-then-filter pattern validates Smith's thesis**: The 4x overfetch factor is an implicit admission that search quality is insufficient. Improving search would reduce wasted API calls on papers that get filtered out.

## Implications for Glyph

Smith's core insight -- that search quality determines everything downstream -- is foundational for Glyph. A paper-as-repo graph RAG system lives or dies on retrieval quality.

- **Hybrid search is non-negotiable for Glyph**: The "unread papers" problem is fundamentally a search problem. A genomics researcher studying BRCA1 resistance mechanisms needs to find a materials science paper about protein conformational changes -- this requires semantic search, not keyword matching. Glyph's graph RAG must combine structured queries (gene symbols, pathways, variants) with embedding-based semantic retrieval across the paper graph.

- **The graph IS the search engine**: Smith argues for building search, not a vector DB. Glyph's paper-as-repo structure creates a third modality beyond keyword and embedding: graph traversal. Citation networks, shared gene mentions, pathway co-occurrence, and method similarity create typed edges that enable retrieval impossible with flat search. A query like "papers that study the same gene as PMID X but in a different tissue" is a graph query, not a search query.

- **Cross-domain discovery requires multi-hop retrieval**: The biggest value proposition of Glyph -- finding connections between seemingly unrelated genomics research -- requires retrieval that follows edges across domains. Paper A mentions gene X; gene X appears in pathway Y; pathway Y is disrupted in disease Z studied in paper B. This is neither keyword search nor embedding similarity -- it is structured graph traversal with semantic re-ranking at each hop.

- **Evaluation is harder for cross-domain discovery**: Smith's warning about evaluation infrastructure is amplified for Glyph. "Did we find the right paper?" is straightforward for single-query search. "Did we find a novel cross-domain connection?" has no ground truth. Glyph will need to develop evaluation methods that go beyond retrieval metrics -- perhaps measuring whether surfaced connections lead to testable hypotheses.

- **Per-paper structured repos enable better indexing**: If every paper is decomposed into markdown sections, extracted CSV data, and chart metadata, each component can be independently indexed and searched. A variant table from one paper can be directly matched against a gene list from another -- something that flat full-text embedding cannot do.

## Key Takeaways

- **Search quality is the unexamined assumption in RS** -- the pipeline invests heavily in extraction validation but treats search as "PubMed handles it." Smith's article suggests this is the single highest-leverage improvement available.
- **LLM-assisted query expansion for PubMed** would improve recall without requiring search infrastructure -- this is feasible today within the RS desktop architecture using the user's existing Gemini key.
- **Citation-count ranking is a popularity proxy, not a relevance signal** -- adding a lightweight relevance re-ranking step (even keyword-based, using the user's disease query against abstracts) would improve paper selection quality.
- **Glyph's core value proposition is graph-structured search** -- the article validates that pure embedding retrieval is insufficient, and Glyph's paper-as-repo + typed-edge graph offers a retrieval modality that neither Elicit's hybrid search nor RS's PubMed delegation can match.
- **Evaluation infrastructure for search quality is absent in RS** and would be essential for both RS improvements and Glyph development.
