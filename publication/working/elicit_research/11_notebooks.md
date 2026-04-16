# Introducing Notebooks: A New Way to Analyze Papers in Elicit — Elicit Research Analysis

## Article Summary

This March 2024 blog post by Andreas Stuhlmuller (Cofounder and CEO of Elicit) announces Notebooks, a new interface that allows researchers to combine papers from multiple searches, chat with them, create summaries, and conduct systematic literature searches on a single page. The post is brief (1 minute read) and product-focused rather than technical, describing four key workflows: combining papers across queries and sources (including user uploads), chatting with selected papers (comparing, follow-ups, multi-paper exploration), creating flexible summaries of chosen papers, and systematic literature search with filters and columns. The framing connects to Elicit's "core bets" philosophy of making research "unbounded" — enabling continuous finding, digging, comparing, and expanding knowledge.

## Key Technical Insights

- **Multi-query composition:** Users can enter multiple queries on a single page and combine papers across all queries. This is a significant departure from single-query research tools.
- **Source mixing:** Papers from search results can be combined with user uploads, enabling hybrid workflows where researchers bring known papers alongside discovery.
- **Conversational paper interaction:** Users select specific papers to chat with, enabling targeted comparison and follow-up questions across a chosen subset.
- **Flexible summaries:** Users generate concise paragraph summaries of selected papers — on demand, as many as needed.
- **Systematic search integration:** Filters and columns support methodical narrowing, with the ability to delete irrelevant papers. This suggests a structured data extraction layer (columns) operating alongside the conversational interface.
- **Unbounded research:** The design philosophy is continuous, iterative exploration rather than one-shot queries. Papers, queries, and analysis accumulate on a single page.

## How Elicit Approaches This Problem

Elicit Notebooks represent a shift from tool-as-query-answerer to tool-as-workspace. The notebook metaphor borrows from computational notebooks (Jupyter, Colab) where analysis accumulates in a persistent, editable document. Key design choices:

1. **Aggregation over isolation:** Papers from different searches and uploads coexist, enabling cross-query analysis that single-search tools cannot support.
2. **Selective interaction:** Users choose which papers to chat with or summarize, maintaining researcher agency over what gets analyzed.
3. **Structured + unstructured in one view:** Columns and filters (structured) sit alongside chat and summaries (unstructured), acknowledging that research requires both modes.
4. **Persistence:** The notebook is a persistent workspace, not a disposable query result. This enables multi-session research workflows.

## How ResearchShop Approaches This Problem

RS operates as a batch pipeline, not a workspace. The current workflow is:

1. User submits a PubMed query or PMID list.
2. Gene relevance scoring runs in the UI (TopicResultsModal) — users see badges, select papers.
3. Selected papers enter the pipeline: full-text fetch, PubTator NER, Gemini extraction, gene validation, CSV output.
4. Results are displayed in a table view (Results.tsx) with confidence badges, metadata, and export to CSV.

There is no persistent workspace, no cross-query accumulation, no conversational interface, and no ability to incrementally add papers after a pipeline run. Each run is independent. The closest RS comes to the Notebooks concept is:

- **Schema-driven extraction columns:** Users define custom columns for Gemini extraction, similar to Elicit's column-based systematic search.
- **User paper selection:** The gene relevance scoring UI lets users override automated scoring, selecting which papers enter the pipeline.
- **Job history:** better-sqlite3 stores past job results locally, but there is no mechanism to combine results across jobs.

## Where We Do Better

- **Extraction depth:** RS extracts structured gene/variant data with multi-layer validation (HGNC, grounding check, biotype filtering, HGVS patterns). Elicit Notebooks extract general-purpose column data without domain-specific validation.
- **Data quality guarantees:** RS provides confidence scores, validation sources, and citation cross-referencing for every extracted datum. Notebooks provide summaries and chat responses without comparable verification infrastructure.
- **Offline and privacy:** RS runs locally. Notebooks require cloud processing and Elicit account. For sensitive clinical data or pre-publication research, local processing is a meaningful advantage.
- **Open-source reproducibility:** RS pipeline is fully open-source and reproducible. Elicit Notebooks are a proprietary SaaS product.
- **Domain precision:** For the specific task of gene/variant extraction from biomedical literature, RS's domain-specialized pipeline will outperform a general-purpose notebook interface every time.

## Where Elicit Does Better

- **Iterative exploration:** Notebooks support continuous, non-linear research workflows. RS is a one-shot batch pipeline — submit papers, wait, get CSV. There is no way to ask follow-up questions, compare specific papers, or incrementally refine the analysis.
- **Multi-query aggregation:** Researchers rarely have a single query that captures everything they need. Notebooks let users combine results from multiple searches. RS requires users to pre-specify their PMID list or query upfront.
- **Conversational interface:** The ability to chat with papers — asking comparison questions, follow-ups, and exploratory queries — is a fundamentally different interaction model than structured extraction. RS offers no conversational layer.
- **User uploads:** Researchers often have key papers already identified. Elicit lets users upload PDFs and combine them with search results. RS accepts PMIDs only — there is no PDF upload path.
- **Summary generation:** RS produces structured data but no narrative summaries. Researchers must interpret the CSV themselves. Notebooks generate paragraph summaries on demand.
- **Lower barrier to entry:** Notebooks require no technical setup. RS requires Electron installation, Python venv, and a Gemini API key.

## Implications for ResearchShop

1. **Cross-run result aggregation is a significant UX gap.** RS stores job history in SQLite but provides no way to combine results across runs. A simple "merge results" feature — combining CSVs from multiple pipeline runs with deduplication — would address the most basic version of cross-query aggregation.
2. **PDF upload would expand the addressable use case.** Many researchers have papers they have already identified. Adding a PDF upload path (bypassing PubMed search, feeding directly into full-text fetch) would make RS useful for researchers who start with a literature collection rather than a search query.
3. **Post-extraction querying is the workspace gap.** After RS produces a CSV, the interaction ends. A lightweight post-extraction interface — even just filtering, sorting, and grouping the results table — would move RS toward a workspace model without requiring a full conversational AI layer.
4. **Schema-driven columns are RS's notebook equivalent.** RS already lets users define custom extraction columns. This should be emphasized as a key feature in the SoftwareX paper — it is the structured counterpart to Elicit's conversational flexibility.
5. **The conversational layer is out of scope for SoftwareX but relevant for the roadmap.** A chat-with-papers feature is architecturally feasible (Gemini can answer questions given full-text context) but would be a major scope expansion. Park it as a post-publication feature.

## Implications for Glyph

Elicit Notebooks represent a step toward the workspace model that Glyph envisions, but they stop at the UI layer. Glyph's paper-as-repo architecture would go deeper.

- **Paper repos are persistent, structured notebooks.** Where Elicit Notebooks accumulate papers on a page, Glyph would give each paper its own structured repo (md text, charts, CSV). A Glyph "notebook" would be a view over a subgraph of paper repos — persistent, queryable, and composable without re-processing.
- **Cross-query aggregation as graph traversal.** Elicit combines papers from multiple searches on a page. Glyph would combine papers through graph connections — shared genes, shared pathways, shared methods. This is a fundamentally richer aggregation model: papers are connected by meaning, not just by co-occurrence in a search result.
- **Chat-with-papers as graph RAG.** When an Elicit user chats with selected papers, the system concatenates their text and queries the LLM. Glyph's graph RAG would enable the same interaction but with structural awareness: "What do these papers say about BRCA1?" would be answered not just from paper text but from the gene node's connections to variant nodes, phenotype nodes, and pathway nodes across the entire graph.
- **The "unread papers" problem is a multi-query problem.** Researchers miss cross-domain connections because they do not formulate the right query. Elicit Notebooks let users enter multiple queries, but the user must still know what to ask. Glyph's graph would proactively surface connections: "You are studying BRCA1 in breast cancer. This cardiology paper discusses BRCA1 in cardiac fibrosis — a connection found in 3 other papers in your graph." This is the shift from user-driven multi-query to system-driven cross-domain discovery.
- **Summaries as composable graph artifacts.** Elicit generates summaries as text blobs. Glyph would generate summaries as structured artifacts: each claim linked to source nodes, each gene mention linked to the gene's graph node, each statistical finding linked to the study's methodology node. Summaries become queryable, updatable, and composable rather than static text.

## Key Takeaways

- **The workspace model (persistent, iterative, multi-query) is the direction research tools are moving** — RS's batch pipeline model is functional but will feel increasingly dated as researchers expect interactive exploration.
- **Cross-run aggregation is the lowest-hanging fruit** — combining CSVs from multiple RS pipeline runs with deduplication would address the most basic gap without architectural changes.
- **PDF upload is a high-value, medium-effort feature** — it expands RS's addressable use case to researchers who start with a paper collection rather than a search query.
- **RS's schema-driven extraction columns are the structural equivalent of Elicit's notebook columns** — this feature should be prominently positioned in the SoftwareX paper as enabling systematic, customizable analysis.
- **Glyph's paper-as-repo model is the natural evolution of the notebook concept** — where notebooks accumulate papers on a page, paper repos accumulate structured knowledge in a graph, enabling cross-domain discovery that no multi-query interface can match.
