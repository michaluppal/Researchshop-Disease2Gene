# Introducing Strict Screening and 80-Paper Reports — Elicit Research Analysis

## Article Summary

This product announcement by Hamsa Pillai (Elicit Product Manager, Dec 2025) introduces two features for Elicit's Systematic Review workflow: strict screening criteria and expanded 80-paper reports. Strict screening allows researchers to mark inclusion/exclusion criteria as "strict," causing papers that fail those criteria to be automatically excluded (with manual override available). Papers with ambiguous assessments ("Maybe") are included by default to avoid missing relevant work. The 80-paper report expansion doubles the previous 40-paper limit for the synthesis report generated at the end of a systematic review. Both features are targeted at Pro, Teams, and Enterprise users.

## Key Technical Insights

- **Strict criteria = hard gates with override**: Papers failing any strict criterion are automatically excluded, but researchers can manually override. This balances automation with expert judgment.
- **Default inclusion for ambiguity**: "Maybe" assessments default to inclusion, not exclusion. This is a recall-preserving design choice -- Elicit would rather show a borderline paper than silently drop it.
- **Transparent exclusion reasoning**: Excluded papers appear at the bottom of results with labels showing which strict criteria caused their exclusion. The screening decision is auditable.
- **Screening spans abstract and full-text**: Strict criteria apply across both abstract screening and full-text screening stages, maintaining consistency.
- **80-paper synthesis limit**: Even with automation, there is a practical ceiling on how many papers an LLM can synthesize into a coherent report. The doubling from 40 to 80 suggests they hit quality limits and found ways to extend them (likely through better context management or multi-pass synthesis).
- **Methodology documentation**: The screening criteria become part of the systematic review methodology, making the review defensible and reproducible.

## How Elicit Approaches This Problem

Elicit's screening is LLM-driven: the model evaluates each paper against user-defined criteria and produces Yes/No/Maybe assessments per criterion. The "strict" toggle converts soft assessments into hard gates. This is a column-based approach -- each criterion is a column, and the screening decision is the conjunction of all strict columns. The system is designed for systematic review methodology compliance (PRISMA, Cochrane), where explicit inclusion/exclusion criteria and documented screening decisions are required for publication.

Key design choices:
- Criteria are user-defined in natural language, assessed by LLM
- Strict criteria create automatic exclusion (hard gate)
- Non-strict criteria are informational (soft signal)
- Manual override preserves researcher authority
- Exclusion reasoning is visible and documented

## How ResearchShop Approaches This Problem

RS has undergone a significant evolution in its screening approach:

- **Previous approach (pre-2026-03-02)**: Python `abstract_screener.py` ran inside the pipeline with a weighted keyword scoring system (threshold >= 5). This silently dropped papers the user had selected -- a fundamental UX problem for researchers who hand-pick papers.

- **Current approach**: Screening was moved from the pipeline to the UI (`geneRelevanceScorer.ts` in `TopicResultsModal.tsx`). The TypeScript scorer uses keyword weights, gene symbol regex, variant pattern detection, and a molecular-context precision gate. Papers are tiered (high/medium/low/none) and displayed with relevance badges. High/medium papers are auto-selected; low/none are hidden behind a "Show all" toggle. The pipeline trusts the user's final selection -- no post-submission filtering.

- **Pipeline pass-through**: The Python screener still runs inside `pipeline_orchestrator.py` for forensic logging (screening decisions appear in debug artifacts), but it no longer gates papers. `papers_screened_rejected` is always 0.

- **No user-defined criteria**: RS screening is hardcoded to gene-relevance heuristics. Users cannot define custom inclusion/exclusion criteria. The scoring dimensions (molecular keywords, gene symbols, variant patterns) are baked into the code.

## Where We Do Better

- **Domain precision**: RS's screening is purpose-built for molecular genetics content detection. The molecular-context precision gate (distinguishing CRP-as-lab-value from CRP-as-gene) is a solved problem in RS that Elicit's generic LLM-based criterion assessment may not handle as well for biomedical queries.
- **No LLM cost for screening**: RS screening runs locally in TypeScript with zero API calls. Elicit's LLM-based criterion assessment costs tokens for every paper evaluated against every criterion. For large paper sets, this adds up.
- **Transparent scoring**: RS shows the exact score components (keywords matched, gene symbols found, molecular context detected). Elicit shows Yes/No/Maybe, which is simpler but less inspectable.
- **User authority preserved**: RS's migration to UI-side screening explicitly solved the "silent dropping" problem. Users see all papers and make the final call. Elicit achieves this with manual override, but the default is automated exclusion.

## Where Elicit Does Better

- **User-defined criteria**: This is Elicit's decisive advantage. Researchers define inclusion/exclusion criteria in natural language ("RCT only," "human subjects only," "published after 2015"). RS's criteria are hardcoded to molecular genetics relevance -- there is no way for a user to add "must be a prospective cohort study" as a screening criterion.
- **Multi-criterion conjunction**: Elicit supports multiple independent criteria, each toggleable as strict or soft. RS has a single composite score. A researcher doing a systematic review of pharmacogenomics RCTs cannot express "must discuss gene variants AND must be an RCT AND must report clinical outcomes" in RS.
- **Systematic review methodology compliance**: Elicit's strict screening produces PRISMA-compatible audit trails. The documented criteria, per-paper assessments, and exclusion reasons form a defensible methodology section. RS has no equivalent -- its screening is a UX convenience, not a methodological tool.
- **Full-text screening**: Elicit applies criteria to full-text content, not just abstracts. RS scores only abstracts (and titles), missing papers where gene content appears only in the body.
- **Ambiguity handling**: Elicit's "Maybe defaults to inclusion" is a principled recall-preserving design. RS's tiering (high/medium/low/none) is more granular but the thresholds are calibrated empirically rather than derived from a screening methodology.
- **Report synthesis at scale**: Elicit generates structured synthesis reports from up to 80 papers. RS outputs a CSV of extracted data -- useful, but no synthesis.

## Implications for ResearchShop

1. **User-defined screening criteria would be high-value**: Even without LLM-based assessment, allowing users to define simple criteria (publication type, year range, study design keywords) as hard filters would move RS closer to systematic review utility. Some of this already exists as search filters (publication type exclusion, year range) but they are not framed as screening criteria with audit trails.

2. **The PRISMA gap matters for the SoftwareX paper**: If RS is positioned as a research tool, reviewers will ask about systematic review methodology support. The current answer is "we do gene-relevance scoring in the UI" -- this is weaker than "researchers define inclusion/exclusion criteria with documented screening decisions." The SoftwareX paper should either position RS as an extraction tool (not a systematic review tool) or address this gap.

3. **Screening audit trail is missing**: Elicit documents which criteria excluded which papers. RS's forensic logging (drop_debug artifacts) captures screening decisions but only as developer debug output, not as researcher-facing methodology documentation.

4. **The "Maybe defaults to inclusion" principle is worth adopting**: RS's molecular-context gate penalizes ambiguous papers. A safer approach for gene extraction would be to include borderline papers and flag them, letting the extraction pipeline's downstream validation (grounding check, confidence gate) handle the quality control. This aligns with the existing architectural principle that false negatives at screening are unrecoverable.

5. **Synthesis reports are a natural extension**: RS outputs structured CSV data. Generating a narrative synthesis report from that CSV (using the user's Gemini key) would be a valuable addition that leverages existing infrastructure.

## Implications for Glyph

Elicit's strict screening model reveals an important tension for Glyph: structured discovery requires principled inclusion/exclusion, but cross-domain discovery requires maximizing inclusion.

- **Glyph should invert the screening paradigm**: In systematic reviews, screening narrows a broad search to a precise set. Glyph's "unread papers" problem is the opposite -- researchers have already narrowed too much (to their own field), and Glyph needs to widen their view. Glyph's screening should be expansive by default, surfacing papers that a researcher would normally exclude but that share molecular or pathway-level connections.

- **Multi-criterion scoring as connection strength**: Elicit's per-criterion assessment model could be adapted for Glyph's graph edges. Instead of "Does this paper meet criterion X? Yes/No/Maybe," the question becomes "How strongly does paper A connect to paper B on dimension X?" Dimensions could be shared genes, shared pathways, shared methods, shared phenotypes. Each dimension is an edge type in the graph with a strength score.

- **Strict criteria for noise control**: While Glyph should be expansive, it still needs noise control. Elicit's strict/soft distinction maps well: certain connection types (shared gene symbol) could be "strict" requirements for an edge to exist, while others (semantic similarity of abstracts) could be soft signals that modulate edge weight. Without some strictness, the graph becomes fully connected and useless.

- **The 80-paper limit is a context window problem**: Elicit's doubling from 40 to 80 papers per report reflects LLM context constraints. Glyph's graph RAG approach could transcend this by pre-computing structured summaries per paper (the repo's markdown + CSV) and only loading relevant subsets into context for any given query. The graph determines what to load; the repo structure determines how compactly it can be represented.

- **Audit trails for discovered connections**: If Glyph surfaces a cross-domain connection, researchers will need to evaluate whether it is real. Elicit's screening transparency (showing which criteria were met/failed) is a model for Glyph's connection explanations: "Paper A connects to Paper B because: shared gene BRCA1 (strict match), similar pathway disruption (semantic similarity 0.87), different tissue context (novel connection signal)."

## Key Takeaways

- **User-defined screening criteria are Elicit's biggest feature advantage over RS for systematic review use cases** -- RS's hardcoded gene-relevance scoring cannot express arbitrary inclusion/exclusion logic.
- **The PRISMA methodology gap should inform how the SoftwareX paper positions RS** -- as a gene extraction tool, not a systematic review tool, unless screening audit trails are added.
- **"Maybe defaults to inclusion" aligns with RS's existing design principle** that false negatives at screening are unrecoverable -- this validates the decision to move screening to the UI and let users override.
- **Glyph should treat screening as connection strength assessment rather than inclusion/exclusion** -- repurposing the multi-criterion model for graph edge typing and weighting.
- **Synthesis reports from extracted CSV data** would be a natural, low-cost addition to RS using the user's existing Gemini API key.
