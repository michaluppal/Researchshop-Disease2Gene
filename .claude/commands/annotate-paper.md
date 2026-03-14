---
allowed-tools: mcp__plugin_pubmed_PubMed__get_article_metadata, mcp__plugin_pubmed_PubMed__convert_article_ids, mcp__plugin_pubmed_PubMed__get_full_text_article, mcp__plugin_pubmed_PubMed__get_copyright_status, mcp__plugin_pubmed_PubMed__find_related_articles, Bash(node *), Bash(mkdir *), Bash(ls *), Bash(rm /tmp/annotate-paper/*), Bash(cd python *), Bash(source *), Bash(python3 *), Bash(python/.*), Read, Write, Edit
description: Create a two-tier gold_standard.json entry for a PMID. Usage /annotate-paper <PMID>
---

## Context

- Current gold standard: !`grep '"pmid"' python/data/benchmark/gold_standard.json`
- Paper count: !`grep -c '"pmid"' python/data/benchmark/gold_standard.json`

## Your task

Create a two-tier benchmark gold standard entry for PMID **$ARGUMENTS**.

**Two tiers:**
- **Primary** (`expected_genes`): genes the paper is ABOUT — key findings in abstract/results
- **Comprehensive** (`expected_genes_comprehensive`): ALL genes with molecular findings in main text, with multi-source evidence and name variants

If `$ARGUMENTS` is empty, print usage and stop:
> Usage: `/annotate-paper <PMID>` — e.g. `/annotate-paper 17463248`

If the PMID already exists in gold_standard.json (shown in Context above), warn the user and ask whether to continue or stop.

---

### Step 1 — Parallel data gathering (5 sources)

Run these **in parallel**:

1. `get_article_metadata` with pmids `["$ARGUMENTS"]` → title, abstract, MeSH terms
2. `convert_article_ids` with ids `["$ARGUMENTS"]` → PMCID
3. `get_copyright_status` with pmids `["$ARGUMENTS"]` → OA check
4. `find_related_articles` with pmids `["$ARGUMENTS"]` and `link_type: "pubmed_gene"` → NCBI Gene IDs
5. PubTator3 independent NER:
```bash
cd python && source .venv/bin/activate && python3 scripts/pubtator_lookup.py $ARGUMENTS
```

**Stop if:** No PMCID found or not OA.

Record from PubTator: each gene's `symbol`, `as_appears` (text forms), `ncbi_gene_id`.

If PubTator fails, WARN and continue — it's one of three sources.

---

### Step 2 — Full text + figures (parallel)

Run these **in parallel**:

1. `get_full_text_article` with the PMCID from Step 1
2. Figure extraction:
```bash
mkdir -p /tmp/annotate-paper/$ARGUMENTS
node python/scripts/extract_pmc_figures.js <PMCID> /tmp/annotate-paper/$ARGUMENTS
```

If figures are produced:
- `ls /tmp/annotate-paper/$ARGUMENTS/`
- Read each `figure_NN.png` with the Read tool
- Read each `figure_NN_caption.txt`
- Identify gene names in figure labels, axes, legends, heatmaps, oncoprints, volcano plots

If figures fail: set `has_figure_genes` to `null`, continue.

---

### Step 3 — Claude full text analysis

Read the full text and identify **ALL** gene mentions by section, noting:
- The exact text form each gene appears as (symbol, full name, alias, protein name)
- Which section (abstract, introduction, results, discussion)
- The molecular evidence (p-value, variant, fold change, OR)

Track separately:
- **Primary candidates**: genes in Abstract as findings + molecular evidence in Results
- **Comprehensive candidates**: ALL genes named in main text with molecular context (including intro/discussion if they have results in the paper)
- **Excluded**: genes only in Methods, only as prior work references, clinical lab abbreviations

For genes found by full name only (not HGNC symbol), resolve to symbol:
```bash
cd python && source .venv/bin/activate && python3 -c "
from modules.gene_validator import GeneValidator
v = GeneValidator()
symbol, source = v.resolve_gene_symbol('<FULL_NAME_OR_ALIAS>')
print(f'{symbol} ({source})')
"
```

---

### Step 4 — Resolve pubmed_gene IDs

For each NCBI Gene ID from `find_related_articles(pubmed_gene)`:
```bash
cd python && source .venv/bin/activate && python3 -c "
from modules.pubtator_tool import NCBIGeneTool
t = NCBIGeneTool()
m = t.get_gene_metadata('<GENE_ID>')
print(f'{m.symbol} | {m.full_name} | aliases: {m.aliases}')
"
```

If there are many IDs, batch them in a single Python call.

---

### Step 5 — Cross-reference synthesis

Build a unified gene table. For each unique HGNC symbol across ALL sources:

1. **Sources**: which found it? Tag each:
   - `PT` = PubTator3 NER
   - `PG` = pubmed_gene (NCBI curated)
   - `FT` = Claude full text analysis
   - `AB` = Claude found in abstract specifically
   - `FIG` = Claude found in figures
   - `MESH` = appears in MeSH terms

2. **As appears**: merge text forms from PubTator (`as_appears`) + Claude analysis. Include ALL name variants: symbols, aliases, full names, protein names.

3. **Sections**: abstract, results, discussion, figures

4. **Evidence**: molecular finding with statistical measure

5. **Classify tier**:
   - **PRIMARY**: in abstract as a finding AND has molecular evidence in results section
   - **COMPREHENSIVE**: named in main text with molecular context, from any source
   - Genes in 3+ sources → very high confidence
   - Genes in 1 source only → flag for user review

---

### Step 6 — Classify paper type

- `gwas` — genome-wide association study, SNP associations
- `cancer_genomics` — somatic mutations, significantly mutated genes
- `rare_disease` — exome/genome sequencing, Mendelian inheritance
- `rna_seq` — differential expression, transcriptomics
- `pharmacogenomics` — drug-gene interactions, pharmacokinetic variants

---

### Step 7 — Present for user review

Compose the entry in this exact JSON format:
```json
{
  "pmid": "<PMID>",
  "type": "<type>",
  "title": "<title from metadata>",
  "expected_genes": ["GENE1", "GENE2"],
  "expected_genes_comprehensive": [
    {
      "symbol": "GENE1",
      "as_appears": ["GENE1", "Gene One Protein", "G1P"],
      "sources": ["pubtator", "pubmed_gene", "fulltext", "abstract"],
      "section": "abstract,results,discussion",
      "evidence": "p=1.2e-9, OR=4.5"
    }
  ],
  "gold_standard_source": "<verbatim quotes from abstract/results proving primary genes>",
  "pmcid": "<PMCID>",
  "oa_confirmed": true,
  "has_figure_genes": <true|false|null>,
  "notes": "<caveats, scoping decisions>"
}
```

Present to the user:

**1. Primary genes** (flat list — what the paper is ABOUT)

**2. Comprehensive gene table:**

| Symbol | As Appears | Sources | Sections | Evidence | Tier |
|--------|-----------|---------|----------|----------|------|

Legend: PT=PubTator, PG=pubmed_gene, FT=fulltext, AB=abstract, FIG=figures, MESH=MeSH

**3. Cross-reference summary:**
- Genes in 3+ sources: [list]
- Genes in 2 sources: [list]
- Single-source genes (review carefully): [list]

**4. Excluded genes with reasons**

Then ask: **"Does this look correct? Reply 'yes' to append to gold_standard.json, or describe changes."**

Do NOT proceed to Step 8 until the user explicitly approves.

---

### Step 8 — Append to gold_standard.json (only after user approval)

1. Read `python/data/benchmark/gold_standard.json`
2. Append the new entry to the `papers` array
3. Write the updated file
4. Validate JSON:
```bash
node -e "JSON.parse(require('fs').readFileSync('python/data/benchmark/gold_standard.json','utf8')); console.log('JSON valid ✅')"
```
5. Report: "Entry appended. Gold standard now has N papers."

---

### Cleanup

```bash
rm -rf /tmp/annotate-paper/$ARGUMENTS
```
