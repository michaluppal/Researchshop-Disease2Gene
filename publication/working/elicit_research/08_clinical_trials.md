# Introducing Clinical Trials — Elicit Research Analysis

## Article Summary

Published July 23, 2025 by Jungwon Byun (Cofounder & COO), this post announces Elicit's integration of ClinicalTrials.gov data -- 545,000 trials searchable via natural language queries. New trial registrations are instantly available. The feature allows users to search trials without boolean query construction, systematically screen studies based on trial protocol information, extract custom data across all trials into structured summary tables, extract derived insights (e.g., "clinical significance assessment of primary endpoint results"), view full study details inline, and access meticulous citations. Early use cases include benchmarking trial designs/endpoints, analyzing safety signals and subgroup data, understanding asset histories, informing launch/commercial strategy, tracking competitor progress, and due diligence. Clinical Trials are available to all paying Elicit users within Research Reports and Systematic Reviews.

## Key Technical Insights

- **Natural language to trial parameters:** Elicit converts free-text queries into structured ClinicalTrials.gov search parameters, handling concept expansion (relevant keywords even if not explicitly specified). This is a semantic search layer over a structured database -- similar to text-to-SQL but for trial registry filters.
- **Custom extraction across trials:** Users can define arbitrary extraction columns, and the system populates them across all matched trials. This includes both factual extraction (endpoints, sample sizes) and derived insights (clinical significance assessments).
- **Inline full-study view:** Users can view the entire trial record without navigating away from the Elicit interface, reducing context-switching.
- **Citation granularity:** Every extracted data point is backed by citations to specific sections of the trial record, maintaining Elicit's evidence-grounding philosophy.
- **Screening on trial protocol:** Users can filter studies based on any information in the trial protocol and registration, not just title/abstract -- this is full-document screening on structured clinical data.
- **Instant new trial availability:** New ClinicalTrials.gov registrations are indexed immediately, suggesting a real-time or near-real-time ingestion pipeline.

## How Elicit Approaches This Problem

Elicit treats clinical trials as a first-class data source alongside academic papers. Their approach layers semantic search and LLM-powered extraction over the structured ClinicalTrials.gov database. Users interact through natural language queries that get translated into appropriate trial parameters. The extraction engine can pull both factual fields and synthesized insights, and everything is citation-grounded. The output is flexible -- structured tables or descriptive reports. Elicit positions this as part of a broader evidence ecosystem that includes papers, trials, and (planned) regulatory documents.

## How ResearchShop Approaches This Problem

RS does not currently integrate clinical trial data. The pipeline is paper-centric: PubMed search returns academic publications, full text is fetched from PMC, and the extraction pipeline operates on paper prose and figures. Clinical trial data enters RS only indirectly -- when a paper describes trial results in its text, those results may be extracted as gene/variant associations. RS has no equivalent of querying ClinicalTrials.gov directly, screening trial protocols, or extracting structured trial metadata (endpoints, phases, sample sizes).

RS's PubMed search stage (`pubmed_data_collector.py`) uses NCBI Entrez, which searches the same NCBI ecosystem that hosts ClinicalTrials.gov, but RS only queries the PubMed literature database. The pipeline's schema-driven extraction (users define custom columns) is architecturally similar to Elicit's custom extraction -- both let users specify what to extract. But RS applies this to paper text, while Elicit applies it to trial records.

## Where We Do Better

- **Gene/variant extraction depth.** When RS does encounter a clinical trial described in a paper, its hybrid NER+LLM pipeline extracts gene symbols, variants (12+ HGVS patterns), and validates them against HGNC. Elicit's clinical trial extraction is general-purpose -- it can extract "endpoints" or "sample sizes" but lacks RS's specialized biomedical entity recognition and validation.
- **Hallucination control on extracted entities.** RS's grounding check, deterministic candidate seeding, and strict validation gate ensure that extracted gene names actually appear in the source text and resolve to valid HGNC symbols. Elicit's extraction is citation-grounded but does not have an equivalent multi-source validation layer for biomedical entities.
- **Privacy.** RS processes everything locally. For pharmaceutical companies running competitive trial analyses (one of Elicit's listed use cases), sending proprietary analysis queries through a cloud service may raise concerns. RS's local-first architecture avoids this.
- **Schema-driven extraction with domain validation.** RS's custom columns are not just LLM-populated text fields -- the pipeline validates extracted values against known databases (HGNC for genes, HGVS patterns for variants). Elicit's custom extraction appears to be pure LLM completion without domain-specific validation.

## Where Elicit Does Better

- **Clinical trial data access is the fundamental gap.** RS has zero clinical trial integration. Elicit provides searchable, extractable access to 545,000 trials with real-time updates. For pharmacogenomics researchers -- a core RS use case -- this is a significant capability gap.
- **Natural language query translation.** Elicit's conversion of free-text queries to structured trial parameters is a sophisticated NLU capability. RS's PubMed search uses Entrez query syntax, which is powerful but requires users to understand PubMed query conventions. RS does have natural language query support, but it is limited to PubMed's own query expansion.
- **Derived insights.** Elicit's ability to extract synthesized judgments ("clinical significance assessment of primary endpoint results") goes beyond factual extraction into analytical territory. RS extracts factual gene/variant associations but does not synthesize higher-order clinical assessments.
- **Multi-source evidence synthesis.** Elicit can combine trial data with paper data in the same analysis session. RS cannot cross-reference trial metadata with paper-extracted gene data.
- **Screening on structured data.** Elicit's trial screening operates on structured protocol fields (phase, condition, intervention, endpoints). RS's screening operates on unstructured text (abstracts and titles), which is noisier.

## Implications for ResearchShop

1. **ClinicalTrials.gov integration is the highest-value near-term extension for pharmacogenomics.** RS's pharmacogenomics benchmark (CYP2C9, VKORC1, CYP2D6) showed F1=0.000 on PubTator-baseline -- these genes require LLM extraction from paper text. Adding ClinicalTrials.gov as a supplementary source would provide structured data about which genes are studied in which trial contexts, which could seed extraction or validate LLM output.
2. **Trial-paper cross-referencing.** Many clinical trials are linked to publications via NCT identifiers. RS could add an enrichment step: for each extracted paper, check if it references a registered trial, and pull structured trial metadata (phase, endpoints, conditions) as additional context for extraction. This is lower-effort than building a full trial search engine.
3. **Natural language query improvement.** RS should study Elicit's query translation approach. The current PubMed Entrez query works but requires user sophistication. A lightweight NLU layer that converts natural language disease/gene queries into optimized PubMed search strings would improve accessibility.
4. **Structured data extraction.** Elicit's ability to extract from structured trial records is a different problem than extracting from unstructured paper text. RS should not try to replicate Elicit's trial extraction engine -- instead, it should focus on what structured trial data can enhance the gene extraction pipeline (e.g., using trial endpoints to disambiguate clinical-vs-molecular gene contexts).

## Implications for Glyph

Clinical trials are a critical missing data type for cross-domain genomics discovery. Glyph implications:

- **Paper-as-repo should include linked trial data.** When a Glyph paper repo is created, it should automatically link to any associated clinical trials (via NCT identifiers in the paper text or PubMed linkout records). The repo would contain the paper's md text, extracted gene/variant CSVs, AND a trials/ subdirectory with structured trial metadata. This creates a richer node in the knowledge graph.
- **Trials as first-class graph nodes.** In Glyph's graph RAG, clinical trials should be nodes alongside papers, connected by shared genes, conditions, interventions, and investigators. A query like "which genes are being targeted in Phase III trials for condition X" would traverse trial nodes, while "what do the published results show for those genes" would traverse paper nodes. The graph enables multi-source reasoning that neither RS nor Elicit currently supports.
- **Solving the pharmacogenomics blind spot.** RS's benchmark shows pharmacogenomics as the weakest category (F1=0.000 on PubTator-baseline). Glyph's integration of trial data would directly address this: CYP2D6 drug-gene interactions are extensively documented in trial registrations, even when the associated publications focus on clinical outcomes rather than molecular mechanisms. The graph would connect clinical trial gene targets to paper-extracted gene associations.
- **Real-time trial monitoring as graph updates.** Elicit's instant availability of new trial registrations maps to Glyph's concept of a living knowledge graph. New trial registrations that mention genes already in the graph would automatically create new edges, alerting researchers to new pharmacogenomics relationships before any paper is published.
- **Cross-domain discovery via trial-paper bridges.** A rare disease researcher might never search ClinicalTrials.gov for oncology trials, but Glyph's graph would surface that the same gene variant implicated in their rare disease is being targeted in a Phase II cancer trial. This is precisely the "unread papers" (and unread trials) problem Glyph aims to solve.

## Key Takeaways

- ClinicalTrials.gov integration is the single most impactful data source RS could add, particularly for the pharmacogenomics use case where paper-only extraction underperforms.
- RS should not build a general trial search engine -- instead, it should add trial-paper cross-referencing (NCT ID linkage) and use structured trial metadata to enrich the gene extraction pipeline.
- Elicit's natural language-to-structured-query translation is a UX pattern RS should study for improving PubMed search accessibility.
- For Glyph, clinical trials must be first-class graph nodes alongside papers, enabling the cross-domain discovery (paper <-> trial <-> gene) that neither tool currently supports.
- The pharmacogenomics benchmark gap (F1=0.000) is partly a data source problem, not just an extraction problem -- trial data would directly address it.
