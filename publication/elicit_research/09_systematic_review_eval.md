# How We Evaluated Elicit Systematic Review — Elicit Research Analysis

## Article Summary

Published March 18, 2025 by Etienne Fortier-Dubois (Eval Specialist), this post details Elicit's evaluation methodology and results for their Systematic Review product. The evaluation covers two dimensions: screening performance (whether the system correctly includes/excludes papers) and extraction performance (whether data extracted from papers is accurate). Screening was evaluated against 58 published systematic reviews, achieving 93.6% recall (96.4% with correctly specified criteria) and 62.8% specificity. Extraction was evaluated both internally (LLM-based auto-evaluation against 128 gold-standard answers, 94% accuracy) and externally by two independent organizations: VDI/VDE (German consulting firm, 99.4% accuracy on 550 papers) and CSIRO (Australia's national science agency, near-zero false negatives, sometimes outperforming human extractors). The post positions Elicit as "the most rigorous AI systematic review tool available."

## Key Technical Insights

- **Screening evaluation methodology:**
  - 58 published systematic reviews used as ground truth
  - Research questions extracted from each review and used as Elicit queries
  - "Relevant papers" = papers screened into the published reviews (extracted via LLM from review text)
  - "Irrelevant papers" = papers found by submitting the same queries to Consensus (academic semantic search), minus any that seemed relevant per LLM judgment
  - Recall: 93.6% (96.4% after adjusting for criteria specification errors)
  - Specificity: 62.8%
  - Priority given to recall over specificity -- excluding relevant papers biases review results

- **Extraction evaluation methodology:**
  - Internal: LLM-as-judge comparing Elicit extraction against 128 gold-standard answers on predefined columns
  - LLM evaluation has 89% agreement with manual verification (previously validated)
  - Key insight: providing BOTH a gold standard AND the full paper text to the LLM judge is more trustworthy than either alone
  - Result: 94% accuracy on internal evaluation

- **External validation:**
  - VDI/VDE: 99.4% accuracy scaling a review from 50 to 550 papers, 11x throughput improvement
  - CSIRO: near-zero false negatives; sometimes outperformed human extractors on detail/specificity; compared favorably to raw GPT-4-Turbo implementations

- **LLM-as-judge with dual reference:** The evaluation gives the judge model both the gold standard answer and the source paper text, finding this combined reference more reliable than either alone. This addresses the problem of gold standards being incomplete or ambiguous.

- **Recall > specificity trade-off:** Elicit explicitly optimizes for recall in screening, accepting a 37.2% false positive rate. This is the correct choice for systematic reviews where missed papers introduce bias, but false inclusions only add manual review burden.

## How Elicit Approaches This Problem

Elicit's evaluation strategy has three layers: (1) internal automated evaluation using LLM-as-judge with dual-reference gold standards, (2) external independent evaluations by credible third parties (VDI/VDE, CSIRO), and (3) planned professional replication of published reviews. Their screening evaluation uses real published systematic reviews as ground truth, which is methodologically sound -- these represent expert human decisions on inclusion/exclusion. For extraction, they use a 128-item gold-standard dataset with predefined columns (participant count, study design, etc.). The 94-99% accuracy range is reported across multiple independent evaluations, giving it reasonable credibility.

Elicit's product philosophy is visible in the metrics they emphasize: recall over specificity for screening (minimizing missed papers), and accuracy for extraction (minimizing incorrect data). They acknowledge that users can override screening decisions, which mitigates the specificity gap.

## How ResearchShop Approaches This Problem

RS has a formal benchmark infrastructure, though with different scope and methodology:

- **Benchmark dataset:** 12 papers across 5 types (cancer_genomics, gwas, rare_disease, rna_seq, pharmacogenomics) with a gold-standard gene set (`gold_standard.json`)
- **Multi-run evaluation:** 3 runs per paper to measure repeatability (Jaccard similarity across runs)
- **Precision/Recall/F1:** Computed per paper and per type against gold-standard gene lists
- **Wilson confidence intervals** on P/R/F1 (added in wave 1 remediation)
- **Figure analysis controlled experiment:** 36-run (3 runs x 6 papers x 2 conditions) figure-on vs figure-off benchmark
- **Citation validation:** Spot-checked manually (5/5 citations verified verbatim on T2D GWAS) plus automated citation validator accuracy measurement (19/20 = 95% on T2D GWAS, 12/18 = 67% on Miller syndrome)

RS does not have an equivalent to Elicit's screening evaluation (RS's screening moved to the UI and is pass-through in the pipeline). RS also does not have external independent evaluations -- the benchmark is entirely internal.

Key RS benchmark results:
- cancer_genomics mean F1=0.668
- gwas mean F1=0.611
- rare_disease F1=0.167 (limited by OA availability)
- rna_seq, pharmacogenomics: TBD/low
- PubTator-baseline Jaccard=1.0 (perfectly deterministic)

## Where We Do Better

- **Repeatability measurement.** RS measures run-to-run Jaccard similarity, revealing stochastic LLM variance. Elicit's evaluation does not report repeatability -- they measure accuracy but not whether the same query produces the same results twice. RS's finding that citation coverage varies 0/8-8/8 across identical runs on the same paper is a critical insight about LLM-based extraction that Elicit's evaluation framework would miss.
- **Domain-specific evaluation rigor.** RS's gold standard is a curated gene list per paper -- a hard, verifiable ground truth. A gene is either in the paper or not; it either resolves to a valid HGNC symbol or not. Elicit's gold standard consists of 128 answers to general extraction questions, which are more subjective (what counts as "accurate" for a study design classification is fuzzier than whether BRCA1 was extracted from a cancer genomics paper).
- **Controlled experiments.** RS's 36-run figure-on vs figure-off experiment isolates the causal contribution of a single pipeline feature. Elicit's evaluations measure overall system performance but do not report controlled ablation studies of individual components.
- **Honest reporting of weaknesses.** RS's benchmark openly reports F1=0.000 for pharmacogenomics and F1=0.167 for rare disease. The AUDIT.md system tracks every known limitation. Elicit's blog post presents only the favorable headline numbers (94-99% accuracy) without reporting failure modes or weak categories.
- **Multi-layer validation pipeline.** RS does not just extract and check accuracy -- it validates extracted entities against HGNC (44,943 genes), checks HGVS variant patterns, applies grounding checks against source text, and applies a strict confidence gate. This is a fundamentally different quality assurance approach than post-hoc accuracy measurement.

## Where Elicit Does Better

- **Scale of evaluation.** 58 systematic reviews for screening evaluation and 128 gold-standard extraction items vastly exceed RS's 12-paper benchmark. RS's evaluation is statistically underpowered -- 12 papers across 5 types means 2-4 papers per type, which is too few for reliable F1 estimates (hence the wide Wilson CIs).
- **External independent validation.** VDI/VDE and CSIRO are credible third parties with no financial relationship to Elicit. RS has no external validation -- the benchmark was designed and run internally. For a SoftwareX paper, this is a significant gap.
- **Real-world systematic review ground truth.** Using 58 published systematic reviews as ground truth is methodologically elegant -- these represent thousands of expert screening decisions. RS's gold standard was manually curated by the development team, which introduces potential curator bias.
- **Screening evaluation exists.** Elicit evaluates screening (recall + specificity) as a distinct capability. RS moved screening to the UI and does not formally evaluate its gene-relevance scoring accuracy against a ground truth.
- **LLM-as-judge methodology.** Elicit validated that LLM-based evaluation has 89% agreement with manual verification, then used it at scale. RS relies on manual spot-checks for citation validation and does not use automated evaluation for extraction quality. Elicit's approach scales; RS's does not.
- **Headline numbers are stronger.** 94-99% extraction accuracy is substantially higher than RS's cancer_genomics F1=0.668 or gwas F1=0.611. The tasks are not directly comparable (general extraction vs. gene-specific extraction), but from a publication and marketing perspective, Elicit's numbers are more compelling.

## Implications for ResearchShop

1. **Scale up the benchmark urgently.** 12 papers is insufficient for a SoftwareX publication. The minimum credible benchmark should be 30-50 papers across all 5 types (6-10 per type). This would narrow the Wilson CIs and provide statistically meaningful per-type F1 scores.
2. **Seek external validation.** Before SoftwareX submission, RS should provide the tool to 2-3 independent research groups (bioinformatics labs, genomics centers) and have them evaluate extraction accuracy against their own gold standards. Even one external validation study would significantly strengthen the paper.
3. **Adopt LLM-as-judge for extraction evaluation.** Elicit's finding that LLM evaluation + gold standard + source text has 89% agreement with human judgment is directly applicable. RS could use this approach to evaluate extraction quality at scale, replacing manual spot-checks. The methodology: give a judge model the paper, the gold-standard gene list, and RS's extracted gene list, and ask it to evaluate precision/recall with explanations.
4. **Evaluate the gene-relevance scorer.** RS moved screening to the UI but does not formally evaluate the scorer's accuracy. Following Elicit's methodology: compile a set of known gene-relevant and gene-irrelevant papers, run the scorer, and measure recall/specificity. The molecular-context precision gate was calibrated on 15 papers -- this should be expanded to 50+.
5. **Report repeatability as a first-class metric.** RS already measures Jaccard across runs. This should be prominently reported in the SoftwareX paper as a differentiator -- it addresses a real limitation of LLM-based systems that Elicit's evaluation framework ignores.
6. **Acknowledge the accuracy gap honestly.** RS's F1 scores are lower than Elicit's extraction accuracy. The SoftwareX paper should frame this correctly: RS performs a harder, more specific task (gene/variant extraction with validation) vs. Elicit's general extraction. RS should also report accuracy on validated genes specifically (genes that pass the 0.7 confidence gate), which will be higher than the overall F1.

## Implications for Glyph

Elicit's evaluation methodology reveals important design principles for Glyph's quality assurance:

- **Evaluation must be built into the graph from day one.** Elicit's 89% LLM-human agreement on extraction evaluation could be applied continuously within Glyph. Every time a paper repo is created and gene/variant CSVs are generated, an automated evaluation agent could score the extraction quality and store the confidence as metadata on the graph edges. Low-confidence extractions would be flagged for human review. This creates a self-auditing knowledge graph.
- **Published systematic reviews as graph validation.** Elicit's use of 58 published systematic reviews as screening ground truth points to a powerful Glyph validation strategy. Existing systematic reviews and meta-analyses in genomics (e.g., large GWAS meta-analyses) contain expert-curated gene lists. Glyph could automatically compare its graph's gene-disease associations against these published reviews, measuring graph completeness and accuracy. Discrepancies would identify either gaps in Glyph's coverage or potential novel findings.
- **Cross-domain accuracy varies.** Elicit achieves 94-99% on general extraction but RS achieves 0.17-0.67 F1 on specialized gene extraction. This suggests that Glyph's extraction quality will vary significantly by domain and paper type. The graph should store per-extraction confidence scores and per-domain accuracy estimates, so downstream consumers (both humans and RAG queries) can weight evidence appropriately. A gene association from a cancer genomics paper (higher baseline accuracy) should carry more weight than one from a rare disease paper (lower baseline accuracy).
- **The "unread papers" problem requires recall-first design.** Elicit explicitly optimizes for recall over specificity in screening. Glyph should adopt the same philosophy for graph construction: it is better to include a marginally relevant paper (adding a low-confidence edge to the graph) than to exclude it entirely. False positives in the graph can be corrected later; false negatives are invisible. For cross-domain discovery, the cost of missing a paper that connects oncology to rare disease is far higher than the cost of including a paper that turns out to be irrelevant.
- **Repeatability as graph edge metadata.** RS's Jaccard stability measurement (1.0 for PubTator, variable for LLM) maps directly to graph reliability. Glyph edges derived from deterministic sources (PubTator NER, HGNC validation) should be marked as high-stability. Edges derived from LLM extraction should carry a repeatability score based on multi-run consistency. Graph RAG queries could then prefer high-stability paths for factual queries and accept lower-stability paths for exploratory/discovery queries.

## Key Takeaways

- RS's 12-paper benchmark is statistically underpowered for a SoftwareX publication. Scaling to 30-50 papers across all 5 types, ideally with at least one external validation study, is the most important pre-submission task.
- Elicit's LLM-as-judge evaluation methodology (dual-reference: gold standard + source text, 89% human agreement) should be adopted by RS for scalable extraction evaluation.
- RS's repeatability measurement (Jaccard across runs) and controlled ablation studies (figure-on vs figure-off) are genuine methodological differentiators that Elicit does not report. These should be prominently featured in the SoftwareX paper.
- The accuracy gap between Elicit (94-99%) and RS (0.17-0.67 F1) reflects task difficulty, not system quality -- but the SoftwareX paper must frame this comparison carefully and report post-validation accuracy as a separate metric.
- For Glyph, the key lesson is that evaluation infrastructure must be built into the graph from inception, with per-edge confidence scores, domain-specific accuracy estimates, and automated comparison against published systematic reviews.
