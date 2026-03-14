# Benchmark Expansion Plan — 12 → 24 Papers

**Current state:** 12 papers, 5 types. Underpowered for journal submission.
**Target:** 24 papers (12 new), covering gaps in type distribution and disease area diversity.
**Owner:** Michal selects + verifies OA status; Suski provides gold standards for new papers.

---

## Gap Analysis (Current 12 Papers)

| Type | Current count | Target | Gap |
|---|---|---|---|
| cancer_genomics | 3 | 5–6 | +2–3 |
| gwas | 3 | 5–6 | +2–3 |
| rare_disease | 2 (1 paywalled) | 4–5 | +3 (all OA) |
| pharmacogenomics | 2 | 4 | +2 |
| rna_seq | 2 | 4–5 | +2–3 |

**Other weaknesses in current set:**
- All 3 GWAS papers are European-cohort only → need ≥1 multi-ethnic or non-European GWAS
- No RNA-seq paper with a pure differential expression design (COVID paper is transcriptomic profiling; GBM paper is integrated genomics)
- No pharmacogenomics paper covering a drug class beyond anticoagulants/opioids
- Pan-cancer paper (24132290) has 127 significantly mutated genes — gold standard covers only top 15, which is a defensible but debatable choice

---

## Candidate Papers to Add

All candidates below are selected for:
✓ Open-access (PMC full text available)
✓ Clear primary gene findings named in abstract
✓ Landmark/well-cited papers (pipeline most likely to have the paper in its training data)
✓ Type diversity

---

### RARE DISEASE (need +3 papers)

**RD-1 | Kabuki syndrome — MLL2/KMT2D (PMID: 20711175)**
- Ng et al. 2010, Nature Genetics
- First exome sequencing study to identify cause of Kabuki syndrome
- Primary gene: KMT2D (formerly MLL2)
- Abstract-stated finding: "mutations in MLL2 as the major cause of Kabuki syndrome"
- PMC: PMC3020211 — OA confirmed
- *Rationale:* Clean 1-gene result; landmark exome paper; direct parallel to Miller syndrome

**RD-2 | Intellectual disability — de novo point mutations (PMID: 22495306)**
- de Ligt et al. 2012, NEJM
- Exome sequencing in 100 patients with severe intellectual disability
- Primary genes: DYRK1A, GRIN2B, HDAC4, SYNGAP1, MED13L (and others named in Results)
- *Rationale:* Multi-gene rare disease paper; tests whether pipeline handles "many genes, one disease" correctly
- *Need to verify:* OA status on PMC — check before adding

**RD-3 | Noonan syndrome gene panel — RASopathies (PMID: 18851527)**
- Tartaglia et al. 2011 or similar RASopathy panel paper
- Primary genes: PTPN11, SOS1, RAF1, KRAS, NRAS, BRAF
- *Rationale:* Multi-gene panel (pathway-level); tests pharmacogenomics-adjacent rare disease
- *Need to identify:* Best OA landmark paper for RASopathy gene panel

**RD-4 | BRCA1/BRCA2 hereditary breast cancer (well-known)**
- Any landmark BRCA1/BRCA2 functional analysis or pathogenic variant study
- Must be OA — original cloning papers are not
- *Rationale:* BRCA1/BRCA2 are the most-studied disease genes; pipeline should score 1.0 here

---

### GWAS (need +2–3 papers)

**GW-1 | BMI/Obesity GWAS — FTO, MC4R (PMID: 18454148)**
- Loos et al. 2008, Nature Genetics — large-scale obesity GWAS
- Primary genes: MC4R (FTO already in T2D paper)
- PMC: need to verify OA status
- *Rationale:* Adds obesity/metabolic disease diversity; MC4R is a clean, well-known GWAS hit

**GW-2 | Coronary artery disease GWAS (PMID: 21378990)**
- Schunkert et al. 2011, Nature Genetics — CARDIoGRAM consortium
- Primary loci: SORT1, LDLR, APOE-APOC region, and others
- *Rationale:* High-impact cardiovascular GWAS; adds non-metabolic disease type

**GW-3 | Multi-ethnic GWAS — blood pressure (PMID: 21909115 or similar)**
- International Consortium for Blood Pressure GWAS
- Primary genes: CACNA1D, CYP17A1, PLCD3, others
- *Rationale:* Addresses the European-cohort bias in current GWAS papers; tests whether pipeline handles multi-ancestry loci

---

### PHARMACOGENOMICS (need +2 papers)

**PGx-1 | Simvastatin myopathy — SLCO1B1 (PMID: 18650507)**
- SEARCH Collaborative Group 2008, NEJM
- Primary gene: SLCO1B1 (rs4149056 variant → 16.9-fold increased myopathy risk)
- PMC: PMC2848885 — OA confirmed
- Abstract quote: "a common variant in the gene SLCO1B1 was strongly associated with an increased risk of simvastatin-induced myopathy"
- *Rationale:* Clean 1-gene result; high-impact PGx; statins are most-prescribed drug class

**PGx-2 | Clopidogrel and CYP2C19 (PMID: 19106084)**
- Mega et al. 2009, NEJM — TRITON-TIMI 38 substudy
- Primary gene: CYP2C19
- PMC: PMC2715610 — OA confirmed
- Abstract quote: "carriers of a reduced-function CYP2C19 allele had significantly lower levels of the active metabolite of clopidogrel, diminished platelet inhibition, and a higher rate of adverse cardiovascular events"
- *Rationale:* Classic PGx paper; antiplatelet therapy; different drug class from warfarin/codeine

---

### RNA-SEQ (need +2–3 papers)

**RNA-1 | Differential gene expression in ALS — TDP-43 target genes (PMID: 24700422)**
- Tollervey et al. or similar TDP-43 RNA-seq paper
- *Need to identify best OA paper*
- *Rationale:* Neurodegenerative disease RNA-seq; pure DEG design

**RNA-2 | Transcriptomics in sepsis — immune gene expression (PMID: 26432509 or similar)**
- Large-scale RNA-seq study identifying immune gene signatures in sepsis
- *Need to identify:* Validated landmark OA paper
- *Rationale:* Adds infectious disease / immunology perspective

**RNA-3 | TCGA LUAD — lung adenocarcinoma transcriptomics (PMID: 25079552)**
- Cancer Genome Atlas Research Network 2014, Nature
- Primary genes: STK11, KEAP1, NF1, RBM10, SETD2 (mutational), plus EGFR, KRAS (established)
- PMC: PMC4231481 — OA confirmed
- *Rationale:* Strong OA paper; adds lung cancer; pure somatic mutation + expression design

---

## Gold Standard Criteria (for all new papers)

A gene belongs in `expected_genes` if ALL of the following are true:

1. **Named explicitly** — the paper uses the official gene symbol (HGNC) or a clearly mapped name
   (e.g. "vitamin K epoxide reductase" → VKORC1 is acceptable; "metabolism genes" is not)

2. **Primary finding** — the gene is a main result, not incidental background
   - In Results/Abstract, not only in Introduction or Discussion
   - Associated with a statistically significant result OR explicitly called a "finding" by the authors

3. **Molecular genetics context** — the paper reports a specific molecular finding:
   - GWAS: significant association (p < 5×10⁻⁸ is standard)
   - Rare disease: identified as causative/likely pathogenic variant
   - RNA-seq: differentially expressed (FDR < 0.05 typical)
   - Pharmacogenomics: variant affecting drug metabolism/response
   - Cancer genomics: significantly mutated gene (q < 0.1 typical)

4. **Human gene** — murine genes acceptable only if the paper is explicitly about a human
   ortholog and maps it correctly

**Do NOT include:**
- Genes only mentioned as prior knowledge ("BRCA1 has been shown to...")
- Pathway members not directly tested
- Genes in supplementary tables but not discussed in main text
- Clinical biomarker abbreviations (CRP, ESR, AST as lab measurements)

---

## Division of Work

| Paper | Who confirms OA? | Who creates gold standard? | Suski verification? |
|---|---|---|---|
| Current 12 | Michal (done) | Michal (done) | Yes — Task A |
| RD-1 (Kabuki) | Michal | Michal draft | Suski confirm |
| RD-2 (ID exome) | Michal | Suski | Suski primary |
| RD-3 (RASopathies) | Michal | Suski | Suski primary |
| GW-1 (BMI) | Michal | Michal draft | Suski confirm |
| GW-2 (CAD) | Michal | Michal draft | Suski confirm |
| GW-3 (BP multi-ethnic) | Michal | Suski | Suski primary |
| PGx-1 (SLCO1B1) | Michal | Michal draft | Suski confirm |
| PGx-2 (CYP2C19) | Michal | Michal draft | Suski confirm |
| RNA-1 (ALS) | Michal | Suski | Suski primary |
| RNA-2 (Sepsis) | Michal | Suski | Suski primary |
| RNA-3 (LUAD) | Michal | Michal draft | Suski confirm |

**Suski primary** = Suski provides the initial gene list (Michal verifies from paper text)
**Suski confirm** = Michal provides draft, Suski validates or corrects

---

## Timeline

| Step | Owner | When |
|---|---|---|
| Verify OA status for all 12 candidates | Michal | Before sending to Suski |
| Send `SUSKI_BENCHMARK_GUIDE.md` | Michal | Week 1 |
| Suski: Task A (gold standard verification, 8 papers) | Suski | Week 1–2 |
| Suski: Task C (inter-rater reliability, 3 papers) | Suski | Week 1–2 |
| Add verified candidates to `gold_standard.json` | Michal | Week 2 |
| Suski: Task B (new paper gold standards) | Suski | Week 2–3 |
| Run pipeline on all 24 papers (3 runs each) | Michal | Week 3 |
| Update AUDIT.md + paper with new F1 numbers | Michal | Week 3–4 |
| Compute Cohen's κ and add to paper | Michal | Week 4 |

---

## What the Paper Says (Expected Output)

After completing this expansion, the paper will report:

> "The benchmark dataset comprises 24 open-access papers spanning five molecular genetics
> research types: cancer genomics (N=6), GWAS (N=6), rare disease (N=5), RNA-seq (N=5), and
> pharmacogenomics (N=4). Gold standard gene lists were independently curated by two researchers
> (inter-rater Cohen's κ = [value] on 3 papers), with discrepancies resolved by consensus."
