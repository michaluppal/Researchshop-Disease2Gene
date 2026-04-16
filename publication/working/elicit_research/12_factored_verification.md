# Factored Verification: Detecting and Reducing Hallucinations in Frontier Models Using AI Supervision — Elicit Research Analysis

## Article Summary

This October 2023 blog post by Charlie George (Machine Learning Engineer at Elicit) describes a hallucination reduction technique called "factored verification." The core idea: instead of verifying an entire LLM-generated summary at once, decompose it into individual claims and verify each claim separately against the source text. When false claims are identified, they are concatenated with the model's reasoning into a "factored critique," which is then used to prompt the model to revise its summary. Critically, if no errors are found, the summary is left unchanged — avoiding the known problem of models "correcting" true statements during self-revision.

The work is framed as an application of factored cognition (from Ought, Elicit's predecessor organization) to in-context hallucination reduction, distinguishing it from Meta's concurrent chain-of-verification work which targets out-of-context hallucination. The paper was published at an IJCNLP workshop and is available as an arXiv preprint (2310.10627).

Key empirical findings:
- Factored verification achieves SOTA on the summarization section of HaluEval, beating chain-of-thought prompting.
- Average hallucinations per multi-paper summary: ChatGPT (16k) = 0.62, GPT-4 = 0.84, Claude 2 = 1.55.
- Naive self-correction (GPT-4 generates critique then revises) increases hallucinations by 37%.
- Factored critiques reduce hallucinations by ~35%: ChatGPT to 0.49, GPT-4 to 0.46, Claude 2 to 0.95.
- Human validators initially missed over half of true hallucinations, only finding them after inspecting model reasoning.
- GPT-4 overestimates hallucinations by ~50%.
- Stronger models (GPT-4) are better at generating critiques; weaker models (ChatGPT) can generate and revise summaries.

## Key Technical Insights

- **Decomposition is key:** Verifying a single claim is easier for both models and humans than checking an entire summary. This is the fundamental insight that makes factored verification work.
- **Factored critiques preserve correctness:** By only revising when errors are found, the method avoids the self-correction failure mode where models "fix" correct statements. This is a crucial design choice — unconditional self-revision is net negative (37% increase in hallucinations).
- **Weak-supervising-strong is feasible:** Weaker models can generate summaries; stronger models verify. This asymmetry means the expensive verification model is used sparingly (per-claim checks) while the cheaper model handles the bulk work.
- **Hallucination rates vary by model:** Claude 2 hallucinated 2.5x more than ChatGPT in multi-paper summarization. Model choice for generation matters independently of verification strategy.
- **Human oversight is insufficient alone:** Humans missed >50% of hallucinations without model-assisted reasoning traces. This is a strong argument for automated verification in any research tool.
- **GPT-4 over-flags by ~50%:** The verification model has its own false positive rate. This means factored verification can cause unnecessary revisions — a precision-recall tradeoff in the verification step itself.
- **In-context vs. out-of-context hallucination:** This work specifically targets in-context hallucination (claims that contradict the source text), not out-of-context hallucination (claims that are factually wrong but not contradicted by the source). The distinction matters for research tools where the source text is the ground truth.
- **Safety framing:** The authors position this as evidence that scalable AI oversight is becoming feasible, noting that human feedback does not scale and can induce unintended negative effects in frontier models.

## How Elicit Approaches This Problem

Elicit's factored verification pipeline:

1. **Generate:** LLM produces a summary from source papers.
2. **Decompose:** Summary is broken into individual claims/sentences.
3. **Verify:** Each claim is checked against the source text by a (potentially stronger) model, which produces reasoning about whether the claim is supported.
4. **Critique:** False claims and their associated reasoning are concatenated into a factored critique.
5. **Revise:** The original model is asked to revise its summary using the critique. Only called when errors are found.
6. **Output:** Revised summary (or original if no errors found).

This is a post-generation verification and revision loop. The key architectural choice is that verification is per-claim, not per-summary, and revision is conditional, not unconditional.

## How ResearchShop Approaches This Problem

RS does not use post-generation revision. Instead, it implements a multi-layer pre-output verification pipeline that is structurally analogous to factored verification but operates through different mechanisms:

1. **Deterministic candidate seeding** (`ENABLE_DETERMINISTIC_CANDIDATES`): PubTator NER results constrain the LLM's extraction space before generation. This is a pre-generation hallucination reduction strategy — rather than verifying and revising LLM output, RS narrows the input to reduce hallucination surface area.

2. **Grounding check** (`ENABLE_GROUNDING_CHECK`): Every gene symbol extracted by the LLM must appear as text in the fetched paper (checking canonical symbol, all HGNC aliases, and raw LLM labels). This is the closest analog to Elicit's per-claim verification — each extracted gene is individually checked against the source. The difference: RS drops ungrounded genes rather than asking the LLM to revise.

3. **Strict validation gate** (`ENABLE_STRICT_VALIDATION_GATE`): Genes with confidence < 0.7 are filtered from the output. This is a hard threshold rather than a revision prompt.

4. **Citation cross-referencing** (`validate_citations` in `gene_validator.py`): Each LLM-extracted citation is verified against the paper text using SequenceMatcher (threshold >= 0.85), with additional numerical consistency and gene context gates. This is per-claim verification applied specifically to citation fidelity.

5. **HGNC validation** (`gene_validator.py`): Every extracted gene symbol is validated against the local HGNC database (44,943 genes) and remote APIs. This is a factual verification step — checking whether the gene exists as a real entity, not just whether it appears in the paper.

6. **Biotype filtering**: Non-protein-coding genes get confidence capped at 0.5, below the strict gate. This is a domain-specific verification that has no analog in general-purpose factored verification.

The key architectural difference: RS uses **filter-and-drop** rather than **verify-and-revise**. False extractions are removed, not corrected. This is more conservative (higher precision, potentially lower recall) but avoids the risk of revision introducing new errors.

## Where We Do Better

- **Domain-specific verification is more precise.** RS verifies genes against HGNC (an authoritative nomenclature database), not against the source text alone. A gene symbol that appears in the paper but is not a real HGNC gene will be caught by RS but would pass Elicit's factored verification (which only checks source text support).
- **Multi-layer verification catches different failure modes.** RS applies 5+ independent verification checks (grounding, HGNC, biotype, confidence, citation). Elicit applies one (per-claim source text verification) with optional revision. RS's approach has more redundancy.
- **Pre-generation constraint is more efficient than post-generation revision.** Deterministic candidate seeding prevents hallucinations from being generated at all, rather than generating them and then catching/revising them. This saves LLM calls and avoids the revision error risk.
- **Filter-and-drop avoids revision-induced errors.** Elicit's revision step could introduce new hallucinations (GPT-4 over-flags by 50%, meaning some revisions are unnecessary). RS's drop strategy has no revision step — false extractions are simply removed.
- **Citation verification is more rigorous.** RS uses character-level SequenceMatcher (>= 0.85) with numerical consistency and gene context gates. Elicit's claim verification checks whether a claim is "supported" by the source, which is a softer standard.
- **Deterministic benchmarking.** RS can measure verification effectiveness (12 papers x 3 runs, Jaccard stability metrics). Elicit's 35% hallucination reduction is measured on a different corpus and task.

## Where Elicit Does Better

- **Revision preserves recall.** RS drops unverified extractions, losing any true positive that fails verification. Elicit's revision approach attempts to correct false claims while preserving the underlying true information. For recall-sensitive tasks, revision is preferable to dropping.
- **General applicability.** Factored verification works on any LLM summarization task across any domain. RS's verification is purpose-built for gene/variant extraction and does not generalize.
- **Published, peer-reviewed methodology.** Elicit's factored verification is an arXiv preprint published at an IJCNLP workshop with quantified results on HaluEval. RS's verification pipeline is documented in AUDIT.md but has not been formally published or externally benchmarked against competing methods.
- **Handling of nuanced claims.** Factored verification can evaluate soft claims ("studies suggest...") and narrative synthesis. RS's verification is binary: the gene is real or it is not, the citation matches or it does not. Complex biomedical claims about gene function, disease association strength, or mechanistic pathways are not verified at the claim level.
- **Scalable oversight framing.** Elicit's approach explicitly addresses the scalability problem: human oversight does not scale, weaker models can supervise stronger ones. RS relies on deterministic databases (HGNC) and heuristic checks, which scale perfectly but cannot evaluate novel claims.
- **Human-in-the-loop insight.** The finding that humans missed >50% of hallucinations without model reasoning traces is a powerful argument for automated verification. RS has not measured human detection rates for its output errors.

## Implications for ResearchShop

1. **Consider adding a claim-level verification step for Key Findings.** RS extracts a "Key Finding" column per gene, which is a free-text claim. Currently this claim is not verified against the source text beyond citation matching. A lightweight factored verification step — asking the LLM "Does the source text support this specific claim about this gene?" — could catch synthesized or exaggerated findings without a full revision loop.

2. **The revision-vs-drop tradeoff should be documented in the SoftwareX paper.** RS's filter-and-drop approach is more conservative than Elicit's verify-and-revise. This is the right choice for medical accuracy (false positives are worse than false negatives in gene association data), but the tradeoff should be explicitly stated and justified.

3. **Conditional revision could improve citation quality.** RS's citation stochasticity problem (0/8 to 8/8 variance across runs) suggests that some citations fail extraction rather than verification. A revision step specifically for citation fields — "This citation field is empty; based on the source text, what passage supports this finding?" — could improve citation recall without introducing gene-level hallucination risk.

4. **The 50% human miss rate validates automated verification.** For the SoftwareX paper, this Elicit finding supports RS's architectural decision to invest heavily in automated verification rather than relying on researcher review of raw LLM output.

5. **Per-claim decomposition maps to RS's per-gene architecture.** RS already verifies per-gene (not per-paper), which is structurally analogous to Elicit's per-claim verification. This parallel should be drawn in the paper.

## Implications for Glyph

Factored verification's core insight — decompose, verify individually, revise conditionally — maps directly onto Glyph's paper-as-repo architecture and has profound implications for building a trustworthy knowledge graph.

- **Claim nodes as the unit of verification.** In Glyph's graph, each paper repo would decompose its content into individual claim nodes (analogous to Elicit's claim decomposition). Each claim node would carry a verification status: verified against source text, verified against external database, unverified, or contradicted. The graph would encode not just knowledge but the epistemic status of that knowledge.

- **Cross-paper factored verification.** Elicit verifies claims against their source paper. Glyph could verify claims against the entire graph: "This paper claims BRCA1 is associated with cardiac fibrosis. Do other papers in the graph support or contradict this?" This is factored verification at graph scale — using the accumulated knowledge of thousands of papers to verify individual claims. A single-paper LLM could not do this, but a graph RAG system can.

- **Weak-supervising-strong as graph consensus.** Elicit uses a stronger model to verify a weaker model's output. Glyph could use graph consensus to verify individual paper claims: if 15 papers in the graph agree that TP53 is a tumor suppressor and one paper claims it is an oncogene, the graph structure itself provides the supervisory signal. This is a form of factored verification where the "verifier" is the knowledge graph rather than a single LLM call.

- **Revision as graph update.** Elicit revises a summary based on a factored critique. Glyph could revise claim nodes based on new evidence: when a new paper enters the graph that contradicts an existing claim, the claim node's verification status updates, and downstream summaries that depend on it are flagged for regeneration. This is continuous, incremental factored verification rather than one-shot revision.

- **Solving the "unread papers" problem through verified connections.** The real danger of unread papers is not just missing information — it is acting on unverified assumptions. Glyph's graph with per-claim verification status would let researchers see exactly which claims in their subfield have cross-paper support and which are single-source assertions. A genomics researcher studying a rare disease gene would immediately see whether the claimed disease association is supported by 1 paper or 50, and whether any papers contradict it. This is the factored verification insight applied to the knowledge discovery problem: decompose literature into claims, verify each against the graph, and surface the epistemic structure to the researcher.

## Key Takeaways

- **Factored verification (decompose into claims, verify individually, revise conditionally) reduces hallucinations by ~35%** — RS achieves a structurally analogous result through per-gene grounding checks and multi-layer validation, but with a filter-and-drop strategy rather than verify-and-revise.
- **Unconditional self-revision increases hallucinations by 37%** — this validates RS's decision not to ask the LLM to "fix" its own extractions. The grounding check drops rather than revises, avoiding this failure mode.
- **Humans miss >50% of hallucinations without model reasoning traces** — this is strong justification for RS's automated verification pipeline and should be cited in the SoftwareX paper to motivate the multi-layer validation architecture.
- **The revision-vs-drop tradeoff is the key architectural divergence** — RS trades recall for precision (drop unverified), Elicit trades precision risk for recall preservation (revise and keep). For medical gene association data, RS's conservative approach is defensible.
- **Claim-level verification for Key Findings is the most actionable improvement** — RS currently does not verify free-text claims about gene function. A lightweight factored verification step for the Key Finding column would close the most significant gap with Elicit's approach.
