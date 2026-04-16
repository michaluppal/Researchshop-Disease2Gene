# New in Elicit: Research Agents — Elicit Research Analysis

## Article Summary

Published December 9, 2025, this blog post announces Elicit's beta launch of an agentic research platform. The system introduces "Research Agents" that decompose a user's research prompt into a systematic program, execute it across multiple source types (not just academic papers), and produce structured outputs with citations. Four new workflows are offered: competitive landscapes, research landscapes, clinical trial analyses, and topic exploration. The agent begins each session with clarifying questions, then iteratively searches, evaluates, and synthesizes information. Users can chat with the agent to refine outputs, request new analyses, or reshape deliverables within the same session. The feature is available to Pro, Teams, and Enterprise users.

## Key Technical Insights

- **Prompt decomposition into programs:** The agent does not simply search-and-summarize. It breaks the user's prompt into a structured plan (a "systematic program") before executing, which is a form of task planning similar to chain-of-thought or plan-then-execute architectures.
- **Multi-source flexibility:** The agent searches beyond academic publications -- clinical trial databases, regulatory filings, press releases, product labels, and the broader web. This is a significant departure from Elicit's paper-only origins.
- **Clarifying questions before execution:** The agent asks the user about source priorities, output structure, and scope boundaries before starting work. This upfront disambiguation reduces wasted computation and misaligned outputs.
- **Iterative refinement:** Users can follow up, modify existing output, or spin up new analyses within the same session. This maps to a conversational research workflow rather than a batch query-response model.
- **Flexible output formats:** Structured comparison tables, narrative summaries, or multiple artifacts simultaneously. Output format is user-selected, not fixed.
- **Transparency maintained:** The agent shows which sources it consults and how it builds toward the deliverable, preserving Elicit's core value of systematicity.
- **Extended thinking process:** The agent uses an "extended thinking" process during execution -- likely an inference-time compute strategy (similar to o1/o3-style reasoning or long chain-of-thought).

## How Elicit Approaches This Problem

Elicit treats research as an interactive, iterative conversation between a human and an AI agent. The agent is a generalist -- it can handle competitive landscapes, clinical trial analysis, or open-ended topic exploration. It operates on a cloud platform with access to Elicit's 138M+ paper index plus the broader web, regulatory databases, and clinical trial registries. The workflow is: user prompt -> agent clarification -> systematic plan -> multi-source execution -> structured output -> iterative refinement via chat. The agent is source-agnostic and output-flexible.

## How ResearchShop Approaches This Problem

ResearchShop takes the opposite architectural stance: a domain-specific, deterministic pipeline rather than a general-purpose agent. The system is specialized for gene/variant extraction from biomedical literature, with a fixed 7-stage pipeline (PubMed search, gene relevance scoring, full-text fetch, PubTator NER, Gemini extraction, gene validation, CSV output). There is no agent loop or iterative refinement -- the pipeline runs end-to-end with predefined stages. Users configure the pipeline upfront (query, columns, API key) and receive a structured CSV. The pipeline is not conversational; it is batch-oriented. Source flexibility is intentionally limited to PubMed/PMC open-access papers only. The hybrid NER+LLM architecture (PubTator precision floor + Gemini recall ceiling) is a domain-specific design that has no equivalent in Elicit's general-purpose agent.

## Where We Do Better

- **Domain-specific precision:** RS's hybrid architecture (PubTator NER + Gemini + HGNC validation + grounding check) produces higher-precision gene/variant extractions than a general-purpose agent could. The 0.7 confidence gate, deterministic candidate seeding, and biotype filtering are biomedical-specific safeguards that a generalist agent would not implement.
- **Reproducibility and auditability:** The fixed pipeline produces deterministic, benchmarkable output. RS has a formal benchmark infrastructure (12 papers x 5 types x 3 runs, 36-run figure analysis experiment) with measured F1 scores. Elicit's agent, being iterative and conversational, produces outputs that are harder to reproduce exactly.
- **No cloud dependency:** RS runs entirely locally. No data leaves the user's machine (beyond API calls to Gemini/NCBI). For genomics researchers working with sensitive variant data, this is a meaningful advantage. Elicit requires uploading research context to their servers.
- **Cost transparency:** Users bring their own Gemini API key and see exact usage (the Gemini usage bar). Elicit's agent workflows consume opaque credits on a paid plan.
- **Multi-layer validation:** RS does not trust LLM output. Every extracted gene is validated against HGNC (44,943 genes), grounded against the source text, checked for HGVS variant patterns, and confidence-gated. Elicit's citations are grounded but there is no equivalent biomedical validation layer.

## Where Elicit Does Better

- **Iterative refinement:** The agent's ability to take follow-up questions and reshape output within the same session is a fundamental UX advantage. RS's batch pipeline requires re-running the entire pipeline to adjust results.
- **Source diversity:** Elicit's agent can pull from clinical trials, regulatory documents, press releases, and the web. RS is limited to PubMed/PMC open-access papers -- roughly 40-60% of the literature.
- **Output flexibility:** Elicit produces tables, narratives, or multi-artifact deliverables on demand. RS produces a fixed CSV with user-defined columns.
- **Scope:** Elicit handles any research question across any domain. RS handles exactly one task: gene/variant extraction from biomedical literature.
- **Clarification before execution:** Elicit's agent asks disambiguation questions upfront, reducing the chance of wasted work. RS relies on the user to configure the pipeline correctly before launch.
- **Scale:** Elicit indexes 138M+ papers. RS searches PubMed per-query with no persistent index.

## Implications for ResearchShop

1. **Consider a post-pipeline chat layer.** The single most compelling feature of Elicit's agent is iterative refinement. RS could add a lightweight chat interface after pipeline completion that lets users ask questions about their CSV results, request re-extraction of specific papers, or adjust column definitions without re-running the full pipeline. This does not require abandoning the deterministic pipeline -- it layers a conversational interface on top.
2. **Upfront clarification step.** RS could benefit from a pre-pipeline configuration wizard that asks clarifying questions (like Elicit's agent does) -- e.g., "Are you looking for protein-coding genes only?", "Should I include genes from figures?", "What confidence threshold do you want?" This would reduce the number of users who run the pipeline with default settings and then discover they wanted different parameters.
3. **Multi-source expansion (carefully).** Elicit's extension to clinical trials and regulatory documents is noteworthy. RS could add ClinicalTrials.gov as a supplementary data source for pharmacogenomics use cases, without abandoning the PubMed-first architecture.
4. **Do not chase generality.** Elicit's agent is a generalist. RS's strength is domain-specific precision. The lesson is not "become an agent" but rather "add agent-like UX features (iteration, clarification) while preserving the deterministic, validated pipeline underneath."

## Implications for Glyph

Elicit's agent architecture is a preview of what Glyph needs to be -- but Glyph should go further. Key connections:

- **Paper-as-repo enables agent grounding.** Elicit's agent searches across sources and synthesizes, but its grounding is per-query and ephemeral. Glyph's paper-as-repo structure (md text, charts, CSV files) would give an agent persistent, pre-indexed, structured representations of every paper. An agent querying Glyph would not need to re-fetch and re-parse papers on every query -- it would navigate a pre-built knowledge graph.
- **Graph RAG solves the cross-domain discovery problem Elicit's agent cannot.** Elicit's agent is powerful within a single session, but it starts from scratch each time. Glyph's graph RAG would maintain persistent connections between papers -- gene X mentioned in paper A (oncology) is the same gene discussed in paper B (pharmacogenomics) and paper C (rare disease). The agent would traverse these connections, not just search for them. This is the "unread papers" problem: a GWAS researcher does not read pharmacogenomics papers, but Glyph's graph would surface that the same variant is discussed in both fields.
- **Iterative refinement within a persistent knowledge structure.** Elicit's chat-based iteration is session-scoped. Glyph could offer iteration over a persistent, evolving knowledge graph -- each query enriches the graph, and subsequent queries benefit from prior exploration. A researcher's second question about BRCA1 variants would already have the context of their first question.
- **Structured repo format enables deterministic validation.** Elicit's agent produces outputs that are hard to validate systematically. Glyph's paper repos (with CSV files of extracted gene/variant data) would allow RS-style validation (HGNC, grounding checks) to be applied to the entire knowledge graph, not just individual pipeline runs.

## Key Takeaways

- Elicit's shift to agentic workflows signals that the market expects iterative, conversational research tools -- but RS should add agent-like UX features (iteration, clarification) without abandoning its validated pipeline architecture.
- Source diversity (clinical trials, regulatory docs, web) is becoming table stakes. RS should plan for ClinicalTrials.gov integration as a near-term extension.
- The clarifying-questions-before-execution pattern is a low-cost, high-value UX improvement RS should adopt in a pre-pipeline configuration step.
- RS's domain-specific precision (hybrid NER+LLM, HGNC validation, grounding checks) is a durable advantage that general-purpose agents cannot replicate without equivalent domain infrastructure.
- Glyph's paper-as-repo + graph RAG architecture would provide the persistent, structured, cross-domain knowledge layer that Elicit's ephemeral agent sessions lack.
