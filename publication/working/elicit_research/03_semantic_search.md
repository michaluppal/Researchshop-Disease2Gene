# From grep to SPLADE: A Journey Through Semantic Search -- Elicit Research Analysis

**Source:** Elicit Blog, June 13, 2024 (Adrian "Panda" Smith, Infrastructure Engineer)
**Tags:** Engineering

## Article Summary

This article traces the evolution of search from string matching (grep) through full-text search (Postgres, Elasticsearch) to semantic search (embeddings, LLM-based) and identifies a critical problem: standard semantic search is unsuitable for systematic literature review because it is non-deterministic and opaque. Elicit's solution is SPLADE (Sparse Lexical and Expansion model), which uses language model knowledge to expand queries with related terms, then feeds the expanded query into a traditional full-text search engine.

The key insight is that academic literature search has stricter requirements than web search: researchers conducting systematic reviews must explain how they found their papers, demonstrate comprehensiveness (no important papers missed), and enable reproducibility by others. Dense vector search fails all three requirements -- the same query can produce different results between runs, the ranking is a black box, and there is no way to audit what was matched and why.

SPLADE sits in a productive middle ground: it uses the semantic knowledge of language models (the latent space that understands "dandelion" is related to "flower") to enrich queries, but produces a sparse, interpretable representation that feeds into deterministic full-text search. The expanded query terms are human-readable and auditable. Custom SPLADE models can be trained on domain-specific corpora (biomedicine, law, athletics).

The article also describes Automated Comprehensive Search (ACS), credited to Undermind: use semantic search to rank papers by relevance, then have an LLM read them in that order, modeling the relevance decay curve to probabilistically guarantee comprehensive coverage. This is slower and more expensive but avoids search bias entirely.

## Key Technical Insights

- **Naive embedding averaging fails for natural language.** "Chocolate is tastier than liver" and "liver is tastier than chocolate" would have identical embeddings under word-level averaging. Sequence-aware LLM embeddings are necessary.
- **Dense vector search is non-deterministic** in practice due to approximate nearest neighbor algorithms and floating-point nondeterminism. The same query can produce different results between runs, which is unacceptable for systematic reviews.
- **Dense vector search is a black box.** Even ML researchers consider embedding-based ranking a "gray box" -- we know it works but cannot explain why a specific paper was ranked higher than another.
- **SPLADE preserves determinism.** For a given SPLADE model, the expanded query is deterministic, and full-text search over that expansion is deterministic. Changing the model changes results, but within a model version, results are reproducible.
- **SPLADE preserves transparency.** The expanded terms are "conceptually very similar to human-readable search terms" and can be viewed and audited by users.
- **Domain-specific SPLADE models** can be fine-tuned to understand jargon within specific fields -- biomedicine, law, athletics -- improving expansion quality beyond a general-purpose model.
- **Automated Comprehensive Search (ACS)** represents the frontier: have an LLM read and judge every paper, using semantic search only for initial ordering. The relevance decay curve provides a probabilistic completeness guarantee. Not reproducible in the traditional sense, but exhaustiveness partially compensates.
- **Manual query expansion is established practice** in systematic reviews -- researchers manually create huge fanouts of search terms. SPLADE automates this existing practice rather than replacing it with something alien.

## How Elicit Approaches This Problem

Elicit's search strategy has three tiers:

1. **SPLADE** as the primary search method -- deterministic, transparent, semantically enriched, domain-trainable. This is their current production approach.
2. **Query expansion** as a conceptual predecessor -- using a general LLM to generate search term variations, which is slower but transparent. SPLADE is essentially a more efficient version of this.
3. **Automated Comprehensive Search (ACS)** as a forward-looking approach -- LLM-as-reader over the entire corpus, with probabilistic completeness guarantees. Slow and expensive today, expected to become practical as costs decrease.

Elicit operates over a massive corpus (scientific literature broadly), so search quality is existential for them. They have invested in custom infrastructure (SPLADE model training, full-text search indexing) to serve this need.

## How ResearchShop Approaches This Problem

RS takes a fundamentally different approach to search because it operates in a different context:

- **Stage 1 (PubMed Search, `pubmed_data_collector.py`):** Delegates search entirely to NCBI Entrez, which uses PubMed's own full-text search with MeSH term expansion. RS does not implement its own search -- it uses PubMed's established, reproducible query language (which systematic reviewers already know and trust).
- **Citation-count ranking via iCite/Semantic Scholar:** Instead of semantic relevance ranking, RS ranks results by citation count. This biases toward established findings (deliberate design choice for a literature-synthesis tool) and is fully transparent and reproducible.
- **Gene relevance scoring (UI-side, `geneRelevanceScorer.ts`):** A keyword-weighted scorer that identifies gene-rich papers using domain-specific terms (mutation, variant, SNP, CRISPR, GWAS) and gene symbol regex patterns. This is essentially manual query expansion encoded as scoring rules -- deterministic, transparent, and auditable.
- **Overfetch factor (4x):** Analyzes 4x the requested papers to compensate for paywall losses and low-yield papers. This is a crude but effective comprehensiveness strategy.
- **Publication type exclusion:** Removes reviews, editorials, guidelines, case reports -- a form of structured filtering that PubMed's query language natively supports.
- **OA filter:** Restricts to PMC-available full-text papers, which is a pragmatic constraint (legal, reliable) that also serves as a reproducibility guarantee -- the same papers will be available to anyone running the same query.

## Where We Do Better

- **Leveraging established infrastructure.** By using PubMed's Entrez API directly, RS inherits decades of MeSH term curation, medical subject heading expansion, and established systematic review methodology. Biomedical researchers already know how to construct PubMed queries that are reproducible and auditable. RS does not need to build or maintain a search index.
- **Citation-count ranking is transparent and domain-appropriate.** A researcher can immediately understand why Paper A is ranked above Paper B: it has more citations. This is more interpretable than any embedding-based ranking, including SPLADE. For a gene/variant extraction tool focused on established literature, citation ranking is a defensible default.
- **Zero search infrastructure cost.** RS has no search index to maintain, no SPLADE model to train, no embedding storage to manage. PubMed is a free, authoritative, well-maintained index. This aligns with RS's desktop-first, no-server architecture.
- **Domain-specific relevance scoring is more precise than general semantic search for our use case.** The `geneRelevanceScorer.ts` explicitly checks for molecular genetics terms and gene symbol patterns. It knows that "mutation" + "BRCA1" is high-relevance while "CRP mg/L" is not, because it has domain-specific rules. A general semantic search would need to learn this distinction from training data.

## Where Elicit Does Better

- **Semantic understanding of search intent.** A researcher searching for "papers about how exercise affects cardiovascular health in elderly populations" would get poor results from a keyword-based PubMed query but excellent results from SPLADE-expanded semantic search. RS depends on users being skilled PubMed query builders.
- **Cross-domain search capability.** SPLADE can find papers that are semantically related even when they use different terminology. A paper about "motor neuron disease" would be found by a search for "ALS" through semantic expansion. PubMed's MeSH terms partially handle this, but SPLADE is more flexible.
- **Search over their own corpus.** Elicit indexes and searches over a curated collection of papers, enabling search features (library, alerts, reports) that go beyond PubMed's query interface. RS is limited to what PubMed's API returns.
- **The ACS vision.** Automated Comprehensive Search -- having an LLM read and judge every candidate paper -- would guarantee comprehensiveness in a way that keyword or SPLADE search cannot. RS's overfetch factor (4x) is a heuristic approximation of this; Elicit is building toward the real thing.
- **User experience for non-expert searchers.** Elicit's semantic search works for users who do not know PubMed query syntax. RS requires either a well-formed query string or a list of PMIDs, which assumes a level of PubMed literacy that many researchers -- especially those outside biomedicine -- may not have.
- **Reproducible semantic search.** SPLADE gives Elicit the benefits of semantic search (understanding concepts, not just words) while maintaining reproducibility. RS gets reproducibility from PubMed but misses the semantic enrichment.

## Implications for ResearchShop

1. **Consider adding LLM-assisted query construction.** RS currently passes the user's query string directly to PubMed Entrez. A lightweight query expansion step -- using Gemini to suggest additional MeSH terms, gene aliases, and disease synonyms before submitting to PubMed -- would improve recall without sacrificing the reproducibility of PubMed search. The expanded query could be shown to the user for approval (transparent, like SPLADE).

2. **Gene alias expansion is a specific instance of query expansion.** When a user searches for "BRCA1 breast cancer," RS could automatically expand to include BRCA1's known aliases (RNF53, IRIS, PSCP, BRCAI, BRCC1, FANCS, PPP1R53) from the local HGNC database. This is deterministic, domain-specific query expansion that directly improves recall for gene-centric searches.

3. **The ACS concept maps to RS's overfetch strategy.** RS already overfetches 4x and then filters. A more sophisticated version would: overfetch broadly, use the gene relevance scorer to rank all candidates, and use the relevance decay curve (as Undermind does) to determine when sufficient coverage has been achieved. This would replace the fixed 4x factor with an adaptive one.

4. **PubMed search is the right default for SoftwareX.** For a tool targeting biomedical researchers submitting to a methods journal, PubMed-native search is a strength. Reviewers will recognize and trust PubMed queries. However, the paper should acknowledge the limitation: RS depends on PubMed's search quality and cannot find papers that PubMed's index does not surface.

5. **Document the search reproducibility guarantee.** Elicit explicitly calls out reproducibility as a requirement for systematic review. RS provides this through PubMed's deterministic API, but the SoftwareX paper should state it explicitly: given the same query and date range, RS produces identical paper sets (modulo PubMed index updates).

## Implications for Glyph

This article reveals that search is the critical infrastructure challenge for Glyph, and the choices made here will determine whether cross-domain discovery actually works.

**Keyword search will not find cross-domain connections.** Glyph's central promise is discovering that Gene X studied in cardiology is relevant to a neurological condition. A keyword search for "Gene X neurology" only works if you already know to search for it. The value of Glyph is in connections the researcher does not know to look for. This requires semantic search, graph traversal, or both.

**SPLADE-like approaches for structured graph queries.** Glyph's knowledge graph would contain nodes (papers, genes, variants, pathways, diseases) and edges (mentions, validates, contradicts, extends). Searching this graph requires a query language that understands biology: a search for "genes involved in inflammatory signaling" should traverse pathway edges, not just match the phrase. A domain-specific SPLADE model trained on biomedical literature could expand graph queries with biologically meaningful terms.

**The paper-as-repo enables structured search that dense vectors cannot.** If each paper is a repo with structured CSV data (genes, variants, expression levels, p-values), Glyph can run structured queries that are impossible with embedding search: "Find papers where TP53 has a loss-of-function variant AND the sample size exceeds 100 AND the tissue is liver." This is SQL-like querying over structured extraction results -- deterministic, transparent, and reproducible. Dense vector search cannot express these constraints.

**ACS applied to graph completion.** Undermind's approach of having an LLM read papers in relevance order until the decay curve flattens could be adapted for Glyph: given a partially constructed knowledge graph, have an LLM read candidate papers and determine whether they add new edges or confirm existing ones. Stop when the rate of new graph connections drops below a threshold. This would provide a probabilistic completeness guarantee for the knowledge graph -- a critical property for cross-domain discovery.

**The reproducibility requirement is even higher for Glyph.** If Glyph alerts a researcher to a cross-domain connection, the researcher must be able to trace that alert back to specific papers, specific extracted entities, and specific graph edges. The entire discovery chain must be auditable. SPLADE's transparency principle (human-readable expanded terms) should extend to Glyph's connection explanations: "Paper A mentions TP53 L194R (extracted from Results section, paragraph 3) and Paper B mentions the same variant (extracted from Table 2, column 4) in the context of a different disease." This is only possible with structured extraction (paper-as-repo), not with dense embeddings.

**Hybrid search for the Glyph graph.** The optimal search architecture for Glyph is likely a combination: (1) structured queries over extracted entities (SQL-like, deterministic), (2) SPLADE-style semantic expansion for natural-language queries, (3) graph traversal for multi-hop connections, and (4) ACS-style comprehensiveness guarantees for critical searches. No single method suffices for the range of queries Glyph needs to support.

## Key Takeaways

- RS's decision to delegate search to PubMed Entrez is the right default for a SoftwareX tool: it is reproducible, transparent, free, and familiar to the target audience. But it limits RS to PubMed's search capabilities and requires users to be skilled query builders.
- The highest-impact search improvement for RS is gene alias expansion using the local HGNC database -- a deterministic, domain-specific query enrichment that directly improves recall for gene-centric searches.
- Elicit's SPLADE approach solves the reproducibility-vs-semantics tradeoff that RS has not yet addressed. For Glyph, this tradeoff becomes existential: cross-domain discovery requires semantic understanding, but researchers must trust and audit the connections.
- The paper-as-repo concept enables structured search that is fundamentally more powerful than any embedding-based approach for specific, constraint-rich queries. This is a key differentiator for Glyph over general-purpose literature tools.
- Automated Comprehensive Search (ACS) is the most relevant concept for Glyph's mission: guaranteeing that the knowledge graph has not missed important connections requires reading the literature exhaustively, not just searching it cleverly.
