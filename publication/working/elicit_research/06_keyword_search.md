# Introducing Keyword Search — Elicit Research Analysis

## Article Summary

This product announcement by Hamsa Pillai (Elicit Product Manager, Oct 2025) introduces keyword search for Elicit's Systematic Review workflow. The feature takes a plain-language research question and automatically builds a structured Boolean keyword query, which users can then refine iteratively. Searches run over PubMed, ClinicalTrials.gov, and Elicit's own 138M+ paper bank, with results guaranteed to exactly match what the respective source databases would return. The generated search string is included in the Methods section of synthesized reports for reproducibility. The article positions this as complementary to their existing semantic search -- planned future work includes using semantic search results to refine keyword searches, filters, combining multiple searches, and AI-suggested query improvements.

## Key Technical Insights

- **LLM-generated Boolean queries from natural language**: Users type a plain-language question ("Do GLP-1/GIP agonists like tirzepatide reduce cardiovascular risk in patients with obesity?"), and Elicit automatically produces a structured keyword query with Boolean operators, synonyms, and MeSH-compatible terms.
- **Source-faithful execution**: Queries are executed against the actual PubMed and ClinicalTrials.gov APIs, guaranteeing that results match what users would get searching those databases directly. This is critical for systematic review reproducibility.
- **Iterative refinement**: Users can adjust the generated query, compare search history, and iterate until satisfied. The query is a starting point, not a final answer.
- **Methods section integration**: The exact search string is included in generated reports, enabling third-party replication -- a PRISMA requirement.
- **Hybrid future**: The roadmap explicitly combines semantic and keyword search -- using semantic results to refine keyword queries, and using keyword queries to validate semantic retrieval. This is the "build search, not a vector DB" philosophy in practice.
- **Multi-source search**: A single interface searches PubMed, ClinicalTrials.gov, and Elicit's corpus, with source filtering. Users can restrict to PubMed-only for reproducibility.
- **Planned features**: semantic-keyword cross-refinement, result filtering, multi-search combination, AI query analysis and improvement suggestions.

## How Elicit Approaches This Problem

Elicit layers keyword search on top of their existing semantic search infrastructure as a complementary modality:

1. **Natural language input** -- user types a research question
2. **LLM query construction** -- Gemini/GPT converts the question into a Boolean query with synonym expansion, MeSH terms, and logical operators
3. **Source-routed execution** -- the query is sent to the actual PubMed/ClinicalTrials.gov APIs, not to Elicit's own index
4. **Result deduplication** -- results from keyword search are combined with semantic search results within the same review
5. **Audit trail** -- the exact query string is preserved in the methodology section

This is a sophisticated approach that gives researchers the best of both worlds: the reproducibility and transparency of keyword search with the ease-of-use of semantic search. The key insight is that they are treating keyword search and semantic search as complementary, not competing -- each catches papers the other misses.

## How ResearchShop Approaches This Problem

RS uses PubMed's Entrez API as its sole search mechanism, with a simpler query construction model:

- **Stage 1 (`pubmed_data_collector.py`)**: Accepts three input modes: free-text query, PMID list, or author name. Free-text queries are sent directly to PubMed's Entrez esearch endpoint, which applies PubMed's own automatic term mapping (ATM) and MeSH expansion.
- **No LLM query construction**: Users write their own queries or rely on PubMed's built-in query processing. There is no intermediate step where an LLM converts natural language to a structured Boolean query.
- **Query filters**: Publication type exclusion (reviews, editorials, etc.), OA filter, year range -- these are applied as PubMed query parameters, not as post-retrieval filters.
- **UI query builder (`QueryBuilder.tsx`)**: The UI provides a form for query construction, but it assembles PubMed query syntax from form fields rather than generating queries from natural language.
- **No ClinicalTrials.gov**: RS searches PubMed only.
- **No query audit trail**: The search query is not included in the output CSV or any report. There is no record of what query produced the results, beyond what the user remembers.

## Where We Do Better

- **Direct PubMed API fidelity**: RS queries PubMed directly with no intermediate translation layer. There is zero risk of an LLM misinterpreting the research question and generating a flawed Boolean query. PubMed's automatic term mapping is well-characterized and deterministic.
- **Domain-specific filters**: RS includes publication type exclusion (removing reviews, editorials, case reports) and OA filtering as built-in query parameters. These are biomedical-specific filters that Elicit treats as generic.
- **PMID list input**: Researchers who already know their papers can bypass search entirely and provide PMIDs directly. This is common in biomedical workflows where a lab maintains curated paper lists. Elicit requires going through their search interface.
- **No API cost for search**: RS's PubMed queries are free. Elicit's LLM-assisted query construction consumes tokens.
- **Query-mode widening as recall safety margin**: Pulling up to `PUBMED_RELEVANT_COUNT=200` candidates in query mode before citation-ranking down to the user's top-N gives a safety margin against poor PubMed top-N ordering. Crude compared to Elicit's hybrid search, but free.

## Where Elicit Does Better

- **LLM-assisted query construction is a major usability advantage**: Converting "Do GLP-1 agonists reduce cardiovascular risk in obese patients?" into a proper Boolean query with synonyms (semaglutide, liraglutide, exenatide, tirzepatide), MeSH terms, and logical operators is exactly the tedious work that blocks researchers from writing good queries. RS offers no help here.
- **Multi-source search**: PubMed + ClinicalTrials.gov + Elicit's corpus in one interface. RS is PubMed-only, missing clinical trial registries and non-PubMed-indexed literature entirely.
- **Query iteration with history**: Users can refine queries, compare result sets, and roll back to previous versions. RS has no query history or comparison capability.
- **Methods section reproducibility**: Including the exact search string in the generated report satisfies PRISMA systematic review requirements. RS provides no search methodology documentation in its output.
- **Semantic + keyword hybrid roadmap**: The planned integration of semantic search results to refine keyword queries is a powerful feedback loop. RS has no semantic search capability at all.
- **Query analysis and improvement suggestions**: The planned feature where AI analyzes query results and suggests refinements would close the gap between novice and expert searchers. RS leaves query quality entirely to the user.

## Implications for ResearchShop

1. **LLM-assisted PubMed query construction is the single highest-ROI feature RS could add**: Using the user's existing Gemini API key to convert a plain-language disease/gene question into an optimized PubMed query (with MeSH terms, gene aliases from the local HGNC database, variant nomenclature patterns) would dramatically improve search recall. This requires no infrastructure -- it is a prompt engineering task that runs client-side before the Entrez API call.

2. **Gene alias expansion from local HGNC is a unique advantage RS could exploit**: RS has 44,943 HGNC gene records with aliases locally. When a user searches for "BRCA1 breast cancer," RS could automatically expand to include all HGNC-registered aliases (BRCA1, RNF53, FANCS, PPP1R53) in the PubMed query. Elicit's generic LLM might know these aliases from training data, but RS has an authoritative local source. This is a concrete differentiation opportunity.

3. **Query audit trail is missing and matters**: The output CSV should include metadata about the search query, date, number of results, and filter settings. Without this, RS results are not reproducible by a third party. This is a simple fix with high impact for the SoftwareX paper's credibility.

4. **ClinicalTrials.gov integration would be valuable**: Many pharmacogenomics papers reference clinical trials. Adding ClinicalTrials.gov as a searchable source (its API is free and well-documented) would close a gap for pharmacogenomics and drug-response use cases.

5. **Query history and comparison**: Even without LLM query construction, allowing users to save, compare, and refine queries would improve the search experience. This is a UI feature, not a pipeline change.

## Implications for Glyph

Elicit's keyword search announcement reveals the tension between reproducible search (keyword) and comprehensive search (semantic) -- a tension Glyph must resolve at a deeper level.

- **Query as a first-class object in the paper repo**: In Glyph's paper-as-repo model, the queries that led to discovering a paper should be part of the repo metadata. When a paper is added to the graph, recording how it was found (keyword query, citation follow, gene co-occurrence, semantic similarity to another paper) creates provenance edges that help researchers understand why the system surfaced it. Elicit's Methods section integration is a simple version of this.

- **Gene-aware query expansion is a graph operation**: Elicit uses LLM to expand "GLP-1 agonists" into a list of specific drugs. In Glyph, this expansion would be a graph traversal: the gene/drug node connects to alias nodes, pathway nodes, and target nodes, and the expanded query is derived from the graph structure rather than from LLM world knowledge. This is more reliable (authoritative sources, not training data) and more transparent (the expansion path is inspectable).

- **Multi-modal search unification**: Elicit plans to combine keyword and semantic search. Glyph would add a third modality: graph-based retrieval (papers connected through shared entities). The query "papers studying genes in the PI3K/AKT pathway in melanoma" is naturally expressed as: find pathway node PI3K/AKT, traverse to gene nodes, traverse to paper nodes, filter by disease context melanoma. No embedding or keyword expansion needed -- the graph encodes the relationships directly.

- **The "unread papers" problem is a query formulation problem**: Researchers miss cross-domain papers because they do not know what to search for. Elicit helps by expanding known queries. Glyph could go further by generating queries the researcher never thought to ask -- traversing the graph from a researcher's known papers, finding underexplored edges, and proposing searches that would fill structural holes in their knowledge graph. This is proactive discovery, not reactive search.

- **Reproducibility through graph provenance**: Elicit includes search strings in reports for reproducibility. Glyph could provide deeper reproducibility: not just "here is the query" but "here is the graph path that led from your known paper to this discovery, through these intermediate nodes, with these connection strengths." This makes cross-domain discoveries auditable and defensible.

## Key Takeaways

- **LLM-assisted PubMed query construction using the existing Gemini key is the highest-ROI search improvement RS could implement** -- it requires no infrastructure, just a prompt that generates optimized PubMed Boolean syntax from a natural-language question.
- **Local HGNC gene alias expansion is a unique differentiator RS should exploit in query construction** -- 44,943 genes with authoritative aliases provide better expansion than LLM world knowledge for gene-specific queries.
- **Search query audit trail in the CSV output is a critical gap for SoftwareX credibility** -- a simple metadata addition that addresses reproducibility concerns.
- **Glyph's graph structure enables a query modality that neither keyword nor semantic search can replicate** -- graph traversal from known entities to related papers through typed, weighted edges.
- **Proactive query generation from graph structure** (suggesting searches the researcher did not think to run) is Glyph's most differentiated capability for solving the "unread papers" problem.
