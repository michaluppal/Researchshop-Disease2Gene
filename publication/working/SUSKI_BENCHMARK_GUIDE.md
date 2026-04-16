# Benchmark Collaboration Guide — Zofia Suski

> **Who is this for:** This document is written specifically for Zofia Suski, who is joining as a
> domain expert collaborator. No prior knowledge of this project is assumed. Everything you need
> is explained from scratch.

---

## 1 · What ResearchShop Does (Plain Language)

ResearchShop is a desktop application that automates the extraction of gene and variant information
from published biomedical papers. A researcher provides a PubMed query (or a list of paper IDs),
the tool fetches the full texts, and produces a structured CSV table of:

- Which genes were identified in each paper
- Which variants were reported for each gene
- Key findings (user-defined: e.g. "role in disease", "expression change", "drug response")
- Citations (verbatim quotes from the paper supporting each finding)

The tool is aimed at geneticists and bioinformaticians who need to synthesize gene/variant data
from tens or hundreds of papers — work that currently takes days to do manually.

**Extraction pipeline summary:**
1. PubMed search → fetches paper abstracts and full texts
2. PubTator3 (biomedical NER model) identifies gene mentions with high precision
3. Google Gemini LLM expands coverage, adding context and user-defined fields
4. HGNC gene database validates all extracted symbols
5. Genes below a confidence threshold (0.7) are filtered out before output

---

## 2 · What Is the Benchmark?

To know how well the tool works, we need to measure it against papers where we already know
the correct answer — the "gold standard."

**The benchmark works like this:**
1. We selected 12 published molecular genetics papers across 5 research types
2. For each paper, a human expert created a list of the **primary genes** the paper reports as
   its main findings (e.g. "TCF7L2 is associated with T2D risk")
3. We ran the pipeline on all 12 papers, 3 runs each (the LLM is stochastic — results vary
   slightly between runs)
4. We compared pipeline output to the gold standard using **Precision, Recall, and F1 score**:
   - **Precision** = of genes the pipeline found, what fraction are actually in the gold standard?
   - **Recall** = of genes in the gold standard, what fraction did the pipeline find?
   - **F1** = harmonic mean of precision and recall (the headline number)

**Current results (12 papers, 3 runs each, full LLM pipeline):**

| Paper type | Mean F1 | Interpretation |
|---|---|---|
| Cancer genomics | 0.668 | Good — TCGA driver genes reliably extracted |
| GWAS | 0.611 | Good — top loci named in Results are found |
| RNA-seq | 0.600 | Good — major DEGs captured |
| Rare disease | 0.167 | Poor — exome papers are harder (few genes, paywall issues) |
| Pharmacogenomics | 0.000 | Not yet measured with LLM active |

**Why this benchmark is important for the paper:**
The SoftwareX journal requires that software papers demonstrate their tool works. F1 numbers are
the main quantitative evidence. A reviewer will ask "how well does this actually work?" — the
benchmark is the answer.

**Why we need to expand it:**
The current 12-paper benchmark is considered underpowered for a published evaluation. For
SoftwareX submission, we need **20-30 papers**, and at least some of them should be verified
by an independent expert (you), not just by Michal.

---

## 3 · Your Role

You have **three tasks**, ordered by priority:

### Task A — Gold Standard Verification (highest priority)
**What:** Check that the existing gene lists for 8 papers are biologically correct.
**Why it matters:** If our "correct answer" is wrong, every F1 number we report is wrong.
These gene lists were created by Michal from paper abstracts and full texts — a biology expert
should confirm them.
**Time estimate:** ~30–45 minutes total (3–5 minutes per paper).

### Task B — New Paper Gold Standards (high priority)
**What:** For 8–12 new papers (chosen together), read each paper's abstract and identify the
primary genes reported as findings. This becomes the new gold standard for those papers.
**Why it matters:** Expanding from 12 to 20-30 papers requires new gold standards.
Your expertise ensures the gene lists are biologically correct from the start.
**Time estimate:** ~5 minutes per paper. Papers are pre-selected to be open-access.

### Task C — Inter-Rater Reliability (required for paper submission)
**What:** For exactly 3 papers, independently write your own gene list *before* seeing the
pipeline output. Then we compare your list to the pipeline's output AND to the existing gold
standard.
**Why it matters:** Scientific journals require a measure of how reproducible the gold standard
is. This is Cohen's κ (kappa) — a statistic that says "two independent experts agreed X% of
the time beyond chance." We need this number.
**Time estimate:** ~15–20 minutes (3 papers, 5–7 minutes each, done without looking at the
pipeline output).

---

## 4 · Task A — Detailed Instructions: Gold Standard Verification

For each of the 8 papers below, you will read the abstract (and skim the Results if needed)
and answer: **Are the genes in the "Expected genes" list the right primary findings?**

For each paper, provide:
1. ✅ Confirm / ❌ Correct / ⚠️ Partial — your verdict
2. If ❌ or ⚠️: your corrected gene list with a brief justification
3. Any genes that should be added (important findings we missed)
4. Any genes that should be removed (not a primary finding in this paper)

**How to access the papers:** All are open-access. Click the PubMed link or search the PMID
at https://pubmed.ncbi.nlm.nih.gov/{PMID}. The full text is on PMC.

---

### Paper 1 — T2D GWAS (PMID: 17463248)
**Title:** A genome-wide association study of type 2 diabetes in Finns detects multiple susceptibility variants
**PubMed:** https://pubmed.ncbi.nlm.nih.gov/17463248/
**Type:** GWAS
**Expected genes:** TCF7L2, SLC30A8, HHEX, CDKAL1, IGF2BP2, CDKN2A, CDKN2B, FTO, PPARG, KCNJ11
**Source quote:** "confirm that variants near TCF7L2, SLC30A8, HHEX, FTO, PPARG, and KCNJ11 are associated with T2D risk and contribute to the identification of T2D-associated variants near the genes IGF2BP2 and CDKAL1 and the region of CDKN2A and CDKN2B"

**Your verdict:** ___
**Notes:** ___

---

### Paper 2 — Schizophrenia GWAS (PMID: 21926974)
**Title:** Genome-wide association study identifies five new schizophrenia loci
**PubMed:** https://pubmed.ncbi.nlm.nih.gov/21926974/
**Type:** GWAS
**Expected genes:** MIR137, TCF4, CACNA1C, ANK3, ITIH3, ITIH4, NRGN
**Source quote:** "strongest new finding at rs1625579 (MIR137)... TCF4... CACNA1C, ANK3, ITIH3-ITIH4 in combined analysis... NRGN at 11q24.2"

**Your verdict:** ___
**Notes:** ___

---

### Paper 3 — Crohn's / WTCCC GWAS (PMID: 17554300)
**Title:** Genome-wide association study of 14,000 cases of seven common diseases
**PubMed:** https://pubmed.ncbi.nlm.nih.gov/17554300/
**Type:** GWAS
**Expected genes (Crohn's disease findings only):** NOD2, ATG16L1, IL23R, IRGM, MST1, PTPN2, NKX2-3
**Note:** This paper covers 7 diseases. The gold standard intentionally covers only Crohn's disease — the other disease gene findings are not included.
**Source quote:** "NOD2 (P=9.4×10⁻¹²), ATG16L1 (P=7.1×10⁻¹⁴), IL23R, IRGM, MST1, PTPN2, NKX2-3 — all Crohn's disease associations named in Results"

**Your verdict:** ___
**Notes:** ___

---

### Paper 4 — TCGA Ovarian (PMID: 21720365)
**Title:** Integrated genomic analyses of ovarian carcinoma
**PubMed:** https://pubmed.ncbi.nlm.nih.gov/21720365/
**Type:** Cancer genomics
**Expected genes:** TP53, NF1, BRCA1, BRCA2, RB1, CDK12, CCNE1
**Source quote:** "TP53 mutations in almost all tumours (96%); low prevalence but statistically recurrent somatic mutations in nine further genes including NF1, BRCA1, BRCA2, RB1 and CDK12. CCNE1 aberrations impact survival."

**Your verdict:** ___
**Notes:** ___

---

### Paper 5 — TCGA Breast Cancer (PMID: 23000897)
**Title:** Comprehensive molecular portraits of human breast tumours
**PubMed:** https://pubmed.ncbi.nlm.nih.gov/23000897/
**Type:** Cancer genomics
**Expected genes:** TP53, PIK3CA, GATA3, MAP3K1, CDH1, PTEN
**Source quote:** "Somatic mutations in only three genes (TP53, PIK3CA and GATA3) occurred at >10% incidence across all breast cancers. MAP3K1 enriched in luminal A, CDH1 in lobular (30/36), PTEN in basal-like module."

**Your verdict:** ___
**Notes:** ___

---

### Paper 6 — Warfarin Pharmacogenomics (PMID: 19228618)
**Title:** Estimation of the warfarin dose with clinical and pharmacogenetic data
**PubMed:** https://pubmed.ncbi.nlm.nih.gov/19228618/
**Type:** Pharmacogenomics
**Expected genes:** VKORC1, CYP2C9
**Source quote:** "variations in two genes — CYP2C9 and VKORC1 — contribute significantly to the variability among patients in dose requirements for warfarin"
**Note:** CYP4F2 and GGCX are mentioned as minor contributors — the question is whether they belong in the primary gene list.

**Your verdict:** ___
**Notes:** ___

---

### Paper 7 — GBM Subtypes (PMID: 20129251)
**Title:** Integrated genomic analysis identifies clinically relevant subtypes of glioblastoma characterized by abnormalities in PDGFRA, IDH1, EGFR, and NF1
**PubMed:** https://pubmed.ncbi.nlm.nih.gov/20129251/
**Type:** RNA-seq / integrated genomics
**Expected genes:** EGFR, NF1, PDGFRA, IDH1
**Source quote:** "Aberrations and gene expression of EGFR, NF1, and PDGFRA/IDH1 each define the Classical, Mesenchymal, and Proneural subtypes, respectively"

**Your verdict:** ___
**Notes:** ___

---

### Paper 8 — Miller Syndrome Exome (PMID: 19915526)
**Title:** Exome sequencing identifies the cause of a mendelian disorder
**PubMed:** https://pubmed.ncbi.nlm.nih.gov/19915526/
**Type:** Rare disease
**Expected genes:** DHODH
**Source quote:** "identified a single candidate gene, DHODH, which encodes a key enzyme in the pyrimidine de novo biosynthesis pathway"
**Note:** This paper reports only ONE gene — but the exome analysis examined 4 affected individuals. Is DHODH the complete correct answer, or should other candidate genes from the paper's analysis be included?

**Your verdict:** ___
**Notes:** ___

---

## 5 · Task C — Inter-Rater Reliability (3 Papers)

For these 3 papers, please do the following **without looking at Task A's expected gene list above**:

1. Read the abstract. Skim the Results section.
2. Write down: **which genes does this paper identify as its primary findings?**
3. Apply these criteria for inclusion:
   - The gene is **explicitly named** (not just implied) in the paper
   - The gene is associated with a **main finding** (not just a passing mention)
   - The paper reports a **direct molecular genetics finding** for this gene (association, mutation, expression change, variant effect, or pharmacogenetic consequence)
   - Do **not** include: clinical biomarker abbreviations used as lab values (e.g., CRP 12 mg/L, ESR 45 mm/h), model organism genes (Brca1 mouse notation), control genes, reference genes

**Papers for inter-rater reliability (submit your list before looking at Task A answers):**

**Paper IR-1:** PMID 17463248 (T2D GWAS, Scott et al. 2007)
**Paper IR-2:** PMID 21720365 (TCGA Ovarian, Cancer Genome Atlas 2011)
**Paper IR-3:** PMID 20129251 (GBM subtypes, Verhaak et al. 2010)

For each, submit: your gene list + a 1-2 sentence note on what criteria you used.

---

## 6 · Task B — New Paper Gold Standards

We will select 8–12 new papers together. Once selected, for each paper you will:

1. Read the abstract (and Results if needed — typically 5 minutes)
2. Submit a list of **primary finding genes** with the same criteria as Task C
3. Include a brief source quote from the paper that supports each gene's inclusion

**Criteria we use to select papers for the benchmark:**
- Open-access (full text available on PubMed Central / PMC)
- Molecular genetics paper (not epidemiology, not pure clinical outcome study)
- Clear gene-level findings explicitly named in abstract or Results
- Diverse coverage: rare disease, pharmacogenomics, RNA-seq, GWAS, cancer genomics

**Candidate categories we still need more of:**
- Rare disease: more exome/panel sequencing papers
- Pharmacogenomics: more drug-gene interaction papers beyond warfarin/codeine
- RNA-seq: more differential expression studies
- Multi-ethnic GWAS: studies from non-European populations

---

## 7 · How to Submit Your Answers

Please fill in this document directly, or copy the relevant sections into an email/Google Doc.
For each task:

**Task A format (per paper):**
```
Paper N — [Title]
Verdict: ✅ Confirm / ❌ Correct / ⚠️ Partial
Corrected gene list (if ❌ or ⚠️): [genes]
Genes to add: [if any]
Genes to remove: [if any]
Notes: [brief justification]
```

**Task B/C format (per paper):**
```
PMID: [PMID]
My gene list: [comma-separated]
Source: [brief quote from paper that supports the inclusion]
Notes: [any uncertainty or edge cases]
```

---

## 8 · Questions?

Contact Michal for:
- Access to full texts if PMC link doesn't work
- Clarification on any paper
- Technical questions about the pipeline
- Which 8-12 papers to use for Task B

The most important thing is that your gene lists reflect **your independent biological judgment**
based on the papers, not an attempt to guess what the pipeline would find.
