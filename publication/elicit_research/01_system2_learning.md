# Against RL: The Case for System 2 Learning -- Elicit Research Analysis

**Source:** Elicit Blog, January 30, 2025 (Andreas Stuhlmuller, Cofounder & CEO)
**Tags:** Engineering, Machine Learning

## Article Summary

Elicit's CEO argues that reinforcement learning (RL), despite its current momentum with DeepSeek R1, OpenAI o1/o3, is fundamentally the wrong paradigm for building safe superintelligent systems. The core thesis: RL is "System 1 learning" -- fast, intuitive gradient updates where the relationship between each datapoint and the weight update is fixed and simple. What we actually need is "System 2 learning" -- training mechanisms that deliberately reflect on what kinds of belief updates are licensed by data.

The article traces inference-time progress (next-token prediction to chain-of-thought to distillation) and observes that training-time learning has changed far less fundamentally. RL fails in three specific ways: (1) data inefficiency -- extracting too little signal from each datapoint, which matters when you cannot perfectly simulate your environment, (2) opacity -- RL pushes away from transparency, with R1 exhibiting poor readability and language mixing, and potentially inventing inscrutable internal languages, and (3) misalignment -- blind search over model space leads to reward hacking and alignment faking.

Stuhlmuller proposes that System 2 learning will require rethinking how we train, deploy, and use LLMs -- potentially zooming out from "what is the language model learning" to "what is the system containing the language model learning." The system can learn even if component models are static. This connects to agent architectures and scaffolding that structure deliberate reasoning around fixed model components.

## Key Technical Insights

- Current RL for LLMs is closer to REINFORCE than AlphaZero -- extremely basic. AlphaZero compressed millions of long-term rollouts into each gradient step; current LLM RL does tiny local tweaks.
- The R1 paper explicitly acknowledges that pure RL training (R1-Zero) produces poor readability and language mixing -- transparency degrades as optimization pressure increases.
- The "Move 37" analogy: we have not yet seen true LLM creativity that surprises us by being fundamentally different from human approaches. o1/o3/R1 bring us closer but are not there yet.
- Karpathy's observation that RL optimization could invent its own inscrutable language that is more efficient for problem-solving but completely opaque to humans.
- Roger Grosse's diagram mapping the path from compression/imitation to reasoning/planning -- the question is whether we can reach the bottom-right (reasoning) without passing through the top-right (strong selection/evolution via RL).
- The system-level learning insight: a system can learn even if its component models are static, through agent architectures and scaffolding. This is a near-term practical path.
- Transparency of world models makes System 2 learning easier; opaque matrix representations make it harder.

## How Elicit Approaches This Problem

Elicit positions itself as building a "System 2 learner for scientific reasoning and high-stakes decision-making." Their practical approach appears to be:

- Using LLMs as static components within structured reasoning systems (agent architectures)
- Investing in transparent, inspectable intermediate steps rather than end-to-end RL optimization
- The system learns through scaffolding improvements, evaluation pipelines (see their auto-eval article), and structured reasoning chains -- not through gradient updates on the end task
- Their emphasis on "scaling trust" (from the auto-eval article) is essentially a System 2 approach: deliberate, explicit reasoning about whether outputs are correct, rather than fast pattern matching

## How ResearchShop Approaches This Problem

ResearchShop's pipeline is, architecturally, already a System 2 reasoning system -- though we have not framed it that way. The 7-stage pipeline is a structured reasoning chain where each stage performs deliberate, inspectable processing:

- **Deterministic candidate seeding** (`ENABLE_DETERMINISTIC_CANDIDATES`): PubTator NER genes are fed as soft constraints to the LLM, steering it toward known entities. This is explicitly "the system constraining the model" rather than training the model to be better.
- **Grounding check** (`ENABLE_GROUNDING_CHECK`): a hard rule that rejects any gene not found in the paper text. This is a transparent, inspectable validation step -- pure System 2 reasoning applied post-hoc to LLM output.
- **Multi-layer validation**: HGNC local database (44,943 genes), remote API fallback, MyGene.info -- three independent knowledge sources that the system consults deliberately, not through learned intuition.
- **Confidence gate** (0.7 threshold): an explicit decision boundary with documented medical reasoning, not a learned threshold.
- **Citation cross-referencing**: the system checks whether LLM-claimed citations actually exist in the paper text using SequenceMatcher (0.85 threshold). This is deliberate verification, not pattern matching.
- **The hybrid NER+LLM architecture itself**: PubTator (precision floor) + Gemini (recall ceiling) is a system-level design where neither component was trained for this specific task, but the system architecture produces reliable results through structured composition.

The pipeline orchestrator (`pipeline_orchestrator.py`) is essentially the "scaffolding" Stuhlmuller describes -- it coordinates static model components into a deliberate reasoning process.

## Where We Do Better

- **Concrete System 2 implementation in a domain**: While Elicit discusses System 2 learning as an aspiration, RS has a working 7-stage pipeline where every stage is inspectable and every decision is auditable. The drop-debug artifacts, AUDIT.md tracking, and confidence annotations are practical System 2 transparency.
- **Explicit hallucination controls**: Our grounding check, deterministic seeding, and strict validation gate are exactly the kind of "deliberate reflection on what belief updates are licensed by the data" that Stuhlmuller calls for. When the LLM says "gene X is in this paper," the system deliberately checks whether that claim is grounded.
- **Domain-specific knowledge integration**: The local HGNC database, biotype filtering, variant pattern matching (12+ HGVS patterns), and PubTator NER are structured knowledge that the system consults explicitly -- not learned representations buried in weights.
- **Reproducibility**: Deterministic pipeline stages (PubTator, HGNC validation, grounding check) produce identical results across runs. The stochastic component (Gemini) is constrained by deterministic gates. This is more aligned with System 2 principles than end-to-end optimization.

## Where Elicit Does Better

- **Strategic framing**: Elicit has articulated a clear research philosophy connecting their product decisions to fundamental AI safety and capability concerns. RS has not framed its architecture in these terms, despite having made many of the same design choices.
- **Scale and generality**: Elicit operates across all of scientific literature with general-purpose extraction and summarization. RS is deeply specialized in gene/variant extraction. Elicit's System 2 approach must generalize across domains; RS benefits from domain specificity but cannot claim general reasoning capability.
- **Research community engagement**: By publishing this kind of thinking, Elicit attracts researchers and engineers who think about these problems at a foundational level. RS operates as an applied tool without contributing to the broader discourse on safe AI architectures.
- **Component model flexibility**: Elicit likely swaps models (OpenAI, Anthropic) based on task performance. RS is currently coupled to Gemini Flash, which limits its ability to benefit from model diversity in the "static components, dynamic system" paradigm.

## Implications for ResearchShop

1. **Frame the pipeline as a System 2 architecture in the SoftwareX paper.** The 7-stage pipeline with explicit validation gates, grounding checks, and multi-source corroboration is a concrete implementation of the "system learns even if component models are static" principle. This framing would resonate with reviewers who follow the AI safety and reliability literature.

2. **Make the scaffold the product, not the model.** RS already does this -- the value is in the pipeline orchestration, not in Gemini Flash specifically. But the architecture should be explicitly model-agnostic. If Gemini is replaced by Claude or GPT-4, the pipeline's correctness guarantees (grounding, HGNC validation, confidence gating) remain intact. Document this property.

3. **Consider adding a "reasoning trace" output.** Stuhlmuller emphasizes transparency. RS already has drop-debug artifacts and forensic logging, but these are developer-facing. A user-facing reasoning trace (why was this gene included? what evidence supported it? what was rejected?) would align with System 2 principles and differentiate from black-box competitors.

4. **Evaluate whether any pipeline decisions could benefit from learned components.** The strict 0.7 confidence threshold, the SequenceMatcher 0.85 citation threshold, and the biotype filtering rules are all hand-tuned. These are good System 2 defaults, but a System 2 learner would eventually reason about whether these thresholds are appropriate for a given paper type. This is a research direction, not an immediate change.

## Implications for Glyph

The System 2 learning framework is deeply relevant to Glyph's mission of solving the "unread papers" problem.

**Paper-as-repo as a transparent world model.** Stuhlmuller argues that transparent world models make System 2 learning easier. A Glyph repo -- containing structured markdown, charts, and CSV files for each paper -- is exactly a transparent, inspectable world model of that paper's knowledge. Unlike embedding a paper into a dense vector (System 1 representation), a Glyph repo preserves the structure, the evidence, and the reasoning chain. When the graph RAG system connects two papers, the connection is inspectable: you can see which gene in Paper A shares a pathway with which variant in Paper B.

**Graph RAG as System 2 reasoning over literature.** The cross-domain discovery that Glyph aims for -- finding that a gene studied in cardiology has implications for a rare neurological condition -- requires exactly the kind of deliberate, multi-step reasoning that Stuhlmuller describes. An RL-trained system might learn these connections as implicit patterns in weights, but a System 2 approach would: (1) identify the gene in both contexts, (2) check whether the biological mechanism is plausible, (3) find intermediate evidence linking the two, and (4) present the reasoning chain transparently. Graph RAG over structured paper repos enables this.

**The "unread papers" problem is a data efficiency problem.** Stuhlmuller's point about RL being data-inefficient resonates directly: researchers specialize narrowly because they cannot extract enough signal from papers outside their domain quickly enough. Glyph's structured extraction (genes, variants, pathways, experimental results) is a form of maximizing signal extraction per paper -- converting a 12-page PDF into a compact, queryable knowledge node. This is the data efficiency that System 2 learning demands.

**Cross-domain connections require explicit reasoning, not pattern matching.** A researcher in oncology will not recognize that a rare disease paper describes a gene relevant to their drug target unless something deliberately reasons about the connection. Dense semantic search might rank the papers as similar, but it cannot explain why. Glyph's graph structure, with explicit gene-to-gene, variant-to-pathway, and paper-to-paper edges, enables System 2 discovery: transparent, reproducible, and auditable connections.

## Key Takeaways

- RS's 7-stage pipeline with explicit validation gates is already a practical System 2 architecture -- this should be articulated clearly in the SoftwareX paper as a design philosophy, not just an implementation detail.
- The "system learns even if component models are static" principle validates RS's approach of composing PubTator + Gemini + HGNC validation into a pipeline that is more reliable than any single component.
- Elicit's strategic framing is more mature than RS's; we have the architecture but lack the narrative. The SoftwareX paper is the opportunity to articulate it.
- Glyph's paper-as-repo concept is a natural instantiation of "transparent world models" -- the foundational requirement for System 2 learning over scientific literature.
- The biggest gap identified by this article is not in RS's current pipeline but in its learning capability: RS does not yet improve from its own outputs. A System 2 learner for gene extraction would reason about why certain papers produce low F1 scores and adjust its approach -- this is a research frontier for Glyph.
