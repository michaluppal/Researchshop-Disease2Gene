# Trust at Scale: Auto-Evaluation for High-Stakes LLM Accuracy -- Elicit Research Analysis

**Source:** Elicit Blog, July 23, 2024 (Etienne Fortier-Dubois, Eval Specialist)
**Tags:** Engineering, Machine Learning

## Article Summary

This article describes Elicit's approach to evaluating LLM outputs at scale in a high-stakes domain (scientific literature review). The core problem: LLMs are unreliable, but requiring human verification of every output negates the scaling benefits of AI. Elicit needs "scalable and trustable evaluation" -- a system that lets users trust outputs without double-checking each one.

The article frames evaluation along three dimensions: **scale** (speed, cost, ease of running), **trust** (accuracy, alignment with task goals), and **flexibility** (adaptability to custom tasks). It argues that no single traditional method satisfies all three: manual evaluation is trustable but not scalable; crowdsourcing is semi-scalable but low-trust for specialized domains; standard benchmarks (SQuAD, QuAC) are scalable and trustable but inflexible; custom benchmarks and unit tests are somewhat flexible but limited by what can be tested in code.

Elicit's solution is LLM-based auto-evaluation, made trustworthy through two mechanisms:

1. **Meta-evals**: Humans evaluate the evaluator. Score a sample of LLM-judged outputs manually, compute human-machine agreement, iterate on the evaluator prompt/model until agreement is satisfactory. Takes less than a day of work but converts an untrusted auto-eval into a calibrated pipeline.

2. **Gold standards**: Manually verified correct answers for specific extraction tasks (e.g., "what intervention was used in this ashwagandha study?"). Instead of asking the LLM "is this accurate?" (unmoored), ask "does this answer match the gold standard?" (grounded comparison). This leverages the insight that validating a hypothesis is easier for LLMs than generating correct answers from scratch.

The article candidly discusses practical challenges: evaluator model choice (cross-provider evaluation avoids self-preference bias), meta-eval stability (changing the evaluator model requires re-doing the meta-eval), gold standard creation and maintenance (extremely time-consuming for complex scientific papers), fuzzy comparison stringency calibration, and binary vs. multi-level scoring tradeoffs.

## Key Technical Insights

- **Validation is easier than generation.** Asking an LLM "does answer A match answer B?" is substantially more reliable than asking "is answer A correct?" This asymmetry is the foundation of their approach and mirrors a fundamental principle in computational complexity.
- **Cross-provider evaluation reduces self-preference bias.** Elicit found that evaluating an OpenAI model with an Anthropic model (or vice versa) produces more trustworthy results than same-provider evaluation. There is published evidence that LLMs favor their own generations.
- **Meta-eval stickiness.** Once a meta-eval is calibrated for a specific evaluator model and prompt, changing either requires re-calibrating. This makes evaluation design choices "sticky" -- Elicit still uses older GPT-4 versions for extraction evaluation because the meta-eval was calibrated against them.
- **Gold standards are not always golden.** Creating ground truth for complex scientific extraction is error-prone. Elicit spent "considerable time" fixing mistakes in their own gold standards.
- **Scoring granularity tradeoff.** They use binary (true/false), ternary (true/partial/false), and X/5 scoring depending on the task. Simpler scoring is easier to meta-eval; finer-grained scoring captures nuance (distinguishing minor vs. major hallucinations).
- **Eval difficulty calibration.** An eval that is too easy or too hard provides no signal. Best practice: use real failure cases from production as eval data. But improving models may make existing evals too easy over time, requiring redesign.
- **Custom evaluator models** (e.g., from Atla) can be trained specifically for evaluation tasks, reaching higher trust at the cost of flexibility. Elicit has not needed this yet but considers it promising.

## How Elicit Approaches This Problem

Elicit's evaluation stack has multiple layers:

1. **In-house manual eval** for new features -- high trust, low scale
2. **LLM-based auto-eval with meta-evaluation** for ongoing quality monitoring -- high scale, medium-high trust, high flexibility
3. **Gold-standard-grounded auto-eval** for data extraction accuracy -- high scale, high trust, medium flexibility
4. **A dataset of hundreds of verified answers** across predefined columns (Intervention, Region, etc.) for diverse papers
5. **Cross-provider LLM evaluation** to mitigate self-preference bias
6. **Iterative prompt engineering** with chain-of-thought and evidence-before-scoring patterns

Their main accuracy metric is the agreement rate between Elicit's extraction outputs and gold standard answers, as judged by the auto-evaluator.

## How ResearchShop Approaches This Problem

RS has a fundamentally different evaluation architecture -- layered deterministic validation rather than LLM-based auto-evaluation:

- **Benchmark infrastructure** (`benchmark_runner.py`, `benchmark_analysis.py`): 12 papers across 5 disease types, 3 runs each (36 total), with gold standard gene sets in `gold_standard.json`. Computes precision, recall, F1, and Jaccard similarity per paper and per type. Wilson confidence intervals on all metrics.
- **Gold standard creation**: Manually curated expected gene lists per paper, categorized by paper type (cancer_genomics, gwas, rare_disease, rna_seq, pharmacogenomics). The `has_figure_genes` field enables controlled figure-analysis benchmarking.
- **Deterministic validation layers** instead of LLM-based eval:
  - Grounding check: gene must appear as text in the paper (canonical symbol, HGNC aliases, or raw LLM labels)
  - HGNC validation: gene must exist in the 44,943-gene database (local) or remote API
  - Confidence scoring: valid gene + valid variant = 1.0; valid gene alone = 0.7; fuzzy match < 0.7 (filtered)
  - Citation validation: SequenceMatcher (0.85 threshold) with numerical consistency gate and gene context gate
  - Biotype filtering: non-protein-coding genes get confidence capped at 0.5
- **Repeatability analysis** (`repeatability_check.py`): measures Jaccard similarity across runs to detect stochastic instability. Perfect Jaccard = 1.0 for deterministic components; LLM components show measurable variance.
- **Multi-run averaging**: citation scores are averaged across 3 runs to account for stochastic LLM compliance (documented: scores fluctuate 0/8 to 8/8 on the same paper).

## Where We Do Better

- **Deterministic validation does not require meta-evaluation.** RS's grounding check, HGNC validation, and biotype filtering are correct by construction -- they check against authoritative databases, not against LLM judgment. There is no "does the evaluator agree with humans?" question because the evaluator is a database lookup.
- **Domain-specific gold standards with biological grounding.** RS's gold standards are gene symbol lists validated against HGNC, not free-text answers that require fuzzy LLM comparison. "Is BRCA1 in the output?" is a deterministic check. "Does 'Ashwagandha extract (Shoden beads) delivering 21 mg' match 'Ashwagandha extract Withanolide glycosides: 21mg daily'?" requires an LLM judge.
- **Multi-run stability measurement.** The Jaccard similarity metric across 3 runs per paper directly measures what Elicit's meta-eval can only indirectly assess: how stable are the outputs? RS can quantify that deterministic components produce Jaccard = 1.0 while LLM components show measurable variance.
- **Layered validation prevents error propagation.** A hallucinated gene must pass grounding check AND HGNC validation AND confidence gate AND biotype filter. Each layer is independently verifiable. In Elicit's approach, a single LLM evaluator makes the entire trust/no-trust decision.
- **Transparent failure modes.** RS can identify exactly why an extraction failed: ungrounded (gene not in text), unvalidated (not in HGNC), low-confidence, non-coding biotype, failed citation match. Elicit's LLM evaluator produces a binary or ternary score with less diagnostic specificity.

## Where Elicit Does Better

- **General-purpose flexibility.** Elicit's auto-eval framework works for any extraction task -- intervention, region, sample size, study design -- without task-specific validation logic. RS's validation stack is deeply specialized for gene/variant extraction. Adding a new extraction target (e.g., drug interactions, protein structures) would require building new validation layers from scratch.
- **Fuzzy comparison for free-text outputs.** Many valuable scientific extraction tasks produce free-text answers where exact matching is impossible. "What is the main finding of this paper?" has no deterministic gold standard. Elicit's LLM-based comparison handles this naturally. RS cannot evaluate free-text fields like Key Findings or citation text with the same rigor it applies to gene symbols.
- **Scale of evaluation data.** Elicit has "hundreds of verified answers" across many column types and paper types. RS has 12 papers with gene-level gold standards. Elicit's evaluation dataset is broader, even if RS's is deeper within its domain.
- **Continuous evaluation pipeline.** Elicit runs auto-evals whenever they change models or prompts, getting immediate accuracy feedback. RS's benchmark runs require manual invocation and take significant time (12 papers x 3 runs with LLM calls).
- **Systematic meta-evaluation methodology.** The practice of measuring human-machine agreement on evaluation scores is a rigorous calibration step. RS's citation validation, for example, was silently returning False/0.0 for months due to a TypeError (C19) -- a meta-eval would have caught this immediately.
- **Hallucination-specific scoring.** Elicit distinguishes minor hallucination (does not change meaning) from major hallucination (misleading). RS's grounding check is binary: the gene is in the paper text or it is not. There is no nuance for partial hallucinations (e.g., correct gene, wrong variant for that gene in that paper).

## Implications for ResearchShop

1. **Add an auto-eval layer for free-text fields.** RS extracts Key Findings, citations, and other prose fields via the Gemini prompt, but validates only the gene symbols and variant strings deterministically. An LLM-based auto-eval (with gold standard comparison) for Key Findings accuracy would catch cases where the LLM produces plausible but incorrect findings. This is especially relevant given the citation cross-contamination failure mode documented in C22.

2. **Implement continuous benchmarking.** Currently, benchmarks are run manually during development sessions. A CI-triggered benchmark on a small representative subset (3-4 papers, 1 run each) would catch regressions immediately when prompts or configurations change. Elicit's model of "run eval after every change" is more robust than RS's "run benchmark when someone remembers."

3. **Build a meta-eval for citation validation.** The C19 silent TypeError (citation validation returning False/0.0 for months) demonstrates exactly the failure mode that meta-evaluation prevents. A small set of known-good citations (verified to exist in specific papers) should be checked periodically to confirm the validator is functioning. The AUDIT.md already recommends this ("add a smoke test that asserts at least one citation validates True on known-good input").

4. **Consider cross-model evaluation for the Gemini extraction stage.** RS currently uses Gemini for both extraction and (implicitly, through prompt design) self-evaluation within the extraction prompt. Using a different model (Claude, GPT-4) to evaluate Gemini's extraction quality could reveal systematic biases. This is low priority given the deterministic validation layers, but worth exploring for the free-text fields.

5. **Expand gold standard coverage.** 12 papers across 5 types is a reasonable start, but coverage is thin in pharmacogenomics (CYP2C9/VKORC1 papers with F1=0.0) and rare disease. Adding 5-10 more papers with verified gene lists, especially in under-performing categories, would significantly improve benchmark reliability.

## Implications for Glyph

Elicit's evaluation framework reveals a fundamental challenge that Glyph must solve at a much larger scale: how do you trust automatically generated knowledge at the scale of millions of papers?

**Quality assurance for the paper-as-repo pipeline.** Every Glyph repo would contain extracted entities (genes, variants, pathways), structured summaries, and relationship annotations. If each repo is generated by an LLM pipeline similar to RS's current one, then each repo needs quality assessment. Elicit's auto-eval approach -- LLM comparison against gold standards -- could be adapted: maintain a set of gold-standard repos (perfectly annotated papers) and periodically evaluate the pipeline's output against them.

**Trust propagation in graph RAG.** When Glyph connects Paper A to Paper B through a shared gene, the trustworthiness of that connection depends on the extraction quality of both papers. A graph RAG system needs to propagate confidence scores through edges: if Gene X was extracted from Paper A with 0.95 confidence and from Paper B with 0.6 confidence, the connection strength should reflect the weaker link. Elicit's multi-level scoring (binary, ternary, 5-point) provides a model for grading connection quality.

**The meta-eval principle scales to graph correctness.** Just as Elicit meta-evaluates individual extraction accuracy, Glyph would need to meta-evaluate graph-level properties: Are the connections between papers biologically meaningful? Do cross-domain links represent genuine biological relationships or spurious co-occurrences of common gene names? Human expert evaluation of a sample of graph connections, used to calibrate an automated graph quality scorer, is the natural extension of Elicit's meta-eval to a knowledge graph context.

**Solving the "unread papers" problem requires trusted automation.** The entire premise of Glyph -- that researchers miss cross-domain knowledge because they cannot read everything -- assumes that the automated extraction is trustworthy enough to act on. If a Glyph alert says "Paper X in cardiology describes the same gene variant you are studying in neurology," the researcher must trust that claim enough to read Paper X. This is Elicit's "scaling trust" problem applied to discovery: the trust threshold for "read this paper" is lower than "include this finding in your analysis," but it is still nonzero. Glyph needs a calibrated confidence score for each cross-domain connection, and the methodology for calibrating it is exactly what Elicit describes.

**Gold standards for cross-domain discovery.** The hardest evaluation problem for Glyph would be: "Did the system correctly identify a novel cross-domain connection?" There is no pre-existing gold standard for undiscovered connections. However, retrospective gold standards can be constructed: take a known cross-domain finding (e.g., the connection between PCSK9 in cholesterol and its role in liver cancer), remove one of the key papers from the graph, and test whether the system rediscovers the connection from the remaining papers. This is a natural extension of Elicit's gold-standard methodology to graph-level evaluation.

## Key Takeaways

- RS's deterministic validation layers (grounding check, HGNC, biotype filtering) are stronger than LLM-based auto-eval for gene/variant accuracy because they are correct by construction. But RS lacks evaluation infrastructure for free-text fields (Key Findings, citations), where Elicit's approach would add value.
- The C19 silent TypeError (citation validator broken for months) is the canonical example of why meta-evaluation matters. RS should implement automated smoke tests for all validation components.
- Elicit's "validation is easier than generation" principle directly applies to RS: the deterministic pipeline gates are already exploiting this asymmetry, but the free-text extraction stages are not.
- Expanding gold standard coverage from 12 to 20+ papers, with special attention to under-performing categories, is the highest-ROI evaluation investment RS can make before SoftwareX submission.
- For Glyph, the critical unsolved evaluation problem is trust propagation through a knowledge graph -- how confident are multi-hop connections? Elicit's meta-eval methodology provides the calibration framework, but the graph-level application requires novel approaches.
