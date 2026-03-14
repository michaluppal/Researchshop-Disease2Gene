# How We Evaluated Elicit Reports — Elicit Research Analysis

## Article Summary

This March 2025 blog post by Etienne Fortier-Dubois (Eval Specialist at Elicit) describes the methodology and results of a comparative evaluation of Elicit Reports against competing "deep research" tools. Elicit Reports are fully-automated research overviews inspired by systematic reviews. The evaluation recruited 17 professional researchers (PhD holders, not active Elicit users) across disciplines including neuroscience, speech therapy, economics, organizational psychology, ecology, and engineering. Evaluators compared Elicit against ChatGPT Deep Research (o3-mini-high), Perplexity Deep Research, Google Gemini Advanced 1.5 Pro with Deep Research, Undermind, and Ai2 Scholar QA. Tools like GPT-4o, Claude 3.5 Sonnet, Perplexity Pro, Consensus, and Scite were excluded after early evaluations showed they did not meet researcher needs. The evaluation covered overall quality (0-10 scale), time savings, main answer quality (accuracy, usefulness, research question fit), and accuracy/citation support of the top 5 claims per report. In total, 29 Elicit reports and 120 competitor reports were evaluated. Elicit scored highest on overall quality and time savings (all comparisons statistically significant via Wilcoxon signed-ranks test). Main answer quality differences were small and often not statistically significant, especially vs. ChatGPT Deep Research. Citation support scores were surprisingly similar across tools, though evaluators qualitatively praised Elicit's inline passage-level citations. Elicit's key qualitative advantages: academic-only sources (no blog posts or news), specific passage citations, transparent/modifiable methods, and better structured tables. Competitors were praised for background sections, paper range, conversational follow-up, limitations discussion, and literature landscape exploration features.

## Key Technical Insights

- **Evaluation scale:** 17 evaluators, 149 total reports (29 Elicit + 120 competitor), ~25-30 evaluations per competitor. Modest sample sizes acknowledged.
- **Statistical method:** Wilcoxon signed-ranks test on paired comparisons (same research question across tools).
- **Overall quality:** Elicit scored highest; four reports received 10/10. Statistically significant vs. all competitors.
- **Time savings:** Median reported (not mean, due to skew from 0-960 hour range). All comparisons favored Elicit, statistically robust.
- **Main answer quality:** Elicit highest but differences small and generally not significant, especially vs. ChatGPT Deep Research.
- **Claim accuracy and citation support:** Several tools performed statistically equivalently. Evaluators may have treated whole-paper references as sufficient citation support, undermining Elicit's inline-passage advantage in quantitative scoring.
- **Academic source quality:** Evaluators consistently noted Elicit avoids non-scholarly content (news, blogs, SEO content farms), unlike competitors.
- **Transparency:** Elicit exposes its search, screening, and extraction steps. Users can add papers, override screening, modify extraction questions, and regenerate reports.
- **Tables:** Elicit generates structured data tables (e.g., 40-row comparison tables) that evaluators found highly valuable for systematic review work.
- **Limitations acknowledged:** Paid evaluators (potential bias), repeated evaluators across rounds (saw improvement), modest sample sizes.
- **Under the hood:** Elicit Reports use Elicit Systematic Reviews — separate search, screening, extraction, and report-writing steps.

## How Elicit Approaches This Problem

Elicit Reports is a cloud SaaS product that automates the systematic review workflow: search, screening, extraction, and report generation. The system draws exclusively from academic literature (no web sources), provides inline passage-level citations, and exposes its methodology transparently so users can understand and modify the search, screening, and extraction steps. The product is built on top of Elicit Systematic Reviews, meaning it has a formal pipeline of discrete steps (analogous to our own staged pipeline) rather than a monolithic LLM query. Users can add their own PDFs, override screening decisions, and customize extraction questions. Reports include structured comparison tables — a feature evaluators found particularly valuable for research synthesis.

## How ResearchShop Approaches This Problem

RS does not produce narrative reports or literature overviews. Instead, it produces structured CSV output of gene/variant data extracted from papers. The pipeline shares the same multi-stage architecture philosophy (PubMed search, gene relevance scoring, full-text fetch, PubTator NER, Gemini extraction, gene validation, CSV output) but targets a narrower and deeper problem: structured biomedical data extraction rather than general research synthesis.

Key parallels:
- **Academic-only sources:** RS uses PubMed/PMC exclusively — inherently academic. No web sources.
- **Transparent methodology:** RS exposes pipeline stages via PROGRESS events in the UI, and the entire pipeline is open-source. Users see gene relevance badges before submission.
- **User override of screening:** RS moved abstract screening to a transparent UI layer where users see relevance scoring and can override it (2026-03-02 decision). This directly mirrors Elicit's praised approach.
- **Structured table output:** RS outputs structured CSV tables with validated gene/variant data — comparable to the 40-row comparison tables evaluators praised in Elicit Reports.
- **Citation support:** RS implements citation cross-referencing (SequenceMatcher >= 0.85, numerical consistency gate, gene context gate) to verify that LLM-extracted claims exist verbatim in the source paper.

## Where We Do Better

- **Domain depth over breadth:** RS goes far deeper on gene/variant extraction than any general-purpose research tool. Multi-layer validation (HGNC database of 44,943 genes, grounding check, biotype filtering, HGVS variant pattern matching) provides scientific rigor that a general report tool cannot match.
- **Hallucination control specificity:** RS has domain-specific hallucination controls (deterministic candidate seeding from PubTator, grounding check requiring gene symbols to appear in paper text, confidence gating at 0.7). These are more targeted than general-purpose report verification.
- **Citation verification rigor:** RS verifies citations at the character level (SequenceMatcher >= 0.85 threshold + numerical consistency + gene context within 1500 chars), whereas Elicit's evaluators considered whole-paper references as sufficient citation support.
- **Privacy and cost:** RS is fully local, open-source, no subscription. Users bring their own Gemini API key. No data leaves the local machine. Elicit Reports requires a paid subscription and cloud processing.
- **Reproducibility:** RS is deterministic enough to benchmark (12 papers x 3 runs, 36-run figure analysis experiment). Open-source pipeline means results can be independently reproduced.

## Where Elicit Does Better

- **Breadth of output:** Elicit produces narrative research overviews with thematic analysis, background sections, and synthesis across findings. RS produces raw structured data only — no narrative, no thematic synthesis, no discussion of limitations or research gaps.
- **Cross-domain applicability:** Elicit works across any research domain (neuroscience, economics, engineering, speech therapy). RS is narrowly scoped to biomedical gene/variant extraction.
- **Iterative research workflow:** Elicit supports conversational follow-up, adding papers from multiple queries, chatting with papers, and regenerating reports. RS is a batch pipeline: submit papers, get CSV.
- **Professional evaluation infrastructure:** Elicit has invested in formal evaluation methodology (17 PhD evaluators, paired statistical testing, multi-tool comparison). RS has a benchmark suite but no external human evaluation against competitors.
- **Report writing automation:** Elicit saves researchers time on the synthesis and writing step, which is typically the most time-consuming part of a systematic review. RS saves time on data extraction but leaves synthesis entirely to the researcher.
- **Scale and polish:** Elicit is a mature SaaS product with 200k+ monthly active users. RS is an open-source desktop app targeting a SoftwareX paper.

## Implications for ResearchShop

1. **User-facing methodology transparency is a competitive differentiator.** Elicit's evaluators praised the ability to see and modify the search/screening/extraction process. RS already does this (PROGRESS events, gene relevance badges, open-source pipeline) but should highlight it more prominently in the SoftwareX paper and UI.
2. **Structured tables are highly valued.** The 40-row comparison table was singled out as a major time-saver. RS already outputs structured CSV, but could improve the in-app table viewing experience (the Results.tsx component) to make the data more immediately useful.
3. **Citation passage-level specificity matters qualitatively even when not captured quantitatively.** Evaluators praised Elicit's inline citations in qualitative feedback even though quantitative scores did not differentiate. RS's citation cross-referencing with SequenceMatcher is technically more rigorous — this should be emphasized in the paper as a verification mechanism, not just a display feature.
4. **Narrative synthesis is the gap.** RS stops at structured data. A future version could generate a summary paragraph per disease-gene association, using the validated CSV as the evidence base. This would move RS closer to Elicit's report-level output while maintaining the structured data backbone.
5. **External evaluation is expected.** For the SoftwareX paper, RS should consider recruiting domain experts to evaluate output quality against manual extraction, similar to Elicit's methodology.

## Implications for Glyph

Elicit Reports demonstrate that researchers value structured, transparent, citation-supported synthesis across papers — exactly what Glyph aims to provide at a deeper structural level.

- **Paper-as-repo enables better reports:** Elicit Reports are generated from a pipeline (search, screen, extract, write). Glyph's paper-as-repo structure (md text + charts + CSV) would make each paper a pre-processed, structured input to synthesis. Instead of running extraction at report-generation time, Glyph could compose reports from pre-existing structured representations — faster, more cacheable, and with richer cross-paper connections.
- **Graph RAG solves the "range of papers" limitation.** Evaluators noted competitors sometimes found a wider range of papers. Glyph's graph structure would enable discovery of related papers through structural connections (shared genes, methods, datasets) rather than just keyword search — potentially surfacing papers that no text-based search would find.
- **Cross-domain discovery is Glyph's unique value.** Elicit works within a single research question. Glyph's graph RAG across paper repos could identify cross-domain connections (a gene pathway discovered in oncology that is relevant to a rare neurological disorder) that no single-query report tool would surface. This is the "unread papers" problem in action: the oncologist never reads the neurology paper, but Glyph's graph connects them.
- **Structured data tables as graph nodes.** The comparison tables evaluators loved in Elicit are static artifacts. In Glyph, each row of a comparison table would be a graph node with typed edges to the source paper, gene, variant, and phenotype nodes. This makes tables queryable, composable, and automatically updated as new papers enter the graph.
- **Transparent methodology as graph provenance.** Elicit's transparency advantage could be amplified in Glyph by making every claim traceable through the graph: claim node -> extraction node -> paper section node -> paper repo. Provenance is structural, not just a displayed method section.

## Key Takeaways

- **Transparent, modifiable methodology and academic-only sources are the features researchers value most** — RS already has both (open-source pipeline, PubMed/PMC only, user-visible gene relevance scoring) and should emphasize them in the SoftwareX paper.
- **Citation specificity matters more qualitatively than quantitatively** — RS's character-level citation verification (SequenceMatcher >= 0.85) is technically ahead of what evaluators could even measure in this study, and should be positioned as a verification mechanism, not just UX.
- **The gap between structured data and narrative synthesis is the biggest product distance between RS and Elicit** — bridging this gap (even partially, with per-gene summary paragraphs) would significantly increase RS's value to researchers.
- **External human evaluation is the gold standard for credibility** — the SoftwareX paper should include domain expert assessment of RS output quality, not just automated benchmarks.
- **Elicit's pipeline-under-the-hood architecture validates RS's multi-stage approach** — both tools decompose the research workflow into discrete, inspectable steps rather than treating it as a monolithic LLM query.
