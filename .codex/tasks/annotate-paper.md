# Annotate Paper Recipe

Use this to create a two-tier benchmark `gold_standard.json` entry for a PMID.

## Goal

Build:

- `expected_genes`: genes the paper is about, usually key findings in abstract/results.
- `expected_genes_comprehensive`: all genes with molecular findings in the main text, with multi-source evidence and name variants.

If no PMID is provided, stop and ask for one.

## Data Gathering

Collect these sources where available:

- PubMed metadata: title, abstract, MeSH terms.
- ID conversion: PMCID.
- Copyright/OA status.
- PubMed Gene related IDs.
- PubTator3 NER via `pipeline/scripts/pubtator_lookup.py`.
- Full text for OA PMC articles.
- Figures and captions if extraction tooling is available.

Stop if no PMCID is found or the article is not OA. If PubTator or figure extraction fails, warn and continue with the remaining sources.

## Full-Text Analysis

Read full text and identify all gene mentions by section:

- exact text form, including symbols, aliases, full names, and protein names
- section: abstract, introduction, results, discussion, figures
- molecular evidence: p-values, variants, fold changes, odds ratios, or comparable findings

Track:

- Primary candidates: genes in the abstract as findings with molecular evidence in results.
- Comprehensive candidates: genes named in main text with molecular context.
- Excluded genes: methods-only mentions, prior-work references, or clinical abbreviations without gene context.

Resolve full names and aliases through `GeneValidator` before adding symbols.

## Source Synthesis

For each unique HGNC symbol, record:

- Sources: PubTator, PubMed Gene, Codex full-text analysis, abstract, figures, MeSH.
- As-appears forms from every source.
- Sections and molecular evidence.
- Tier classification.

Primary genes must be findings the paper is about. Comprehensive genes can include all molecular-context mentions.

## Review Format

Present the proposed JSON entry plus:

- Primary genes as a flat list.
- Comprehensive gene table with symbol, as-appears forms, sources, sections, evidence, and tier.
- Cross-reference summary grouped by number of sources.
- Excluded genes with reasons.

Do not append to `pipeline/data/benchmark/gold_standard.json` until the user explicitly approves.

After approval, append the entry, validate JSON with Node or Python, and report the new paper count.
