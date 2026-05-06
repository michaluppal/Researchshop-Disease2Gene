/**
 * Gene relevance scorer for abstract screening in the UI.
 *
 * TypeScript port of the Python abstract_screener.has_genetic_content() logic.
 * Scores paper abstracts for gene/variant content using keyword matching,
 * gene symbol regex patterns, and a molecular-context precision gate.
 *
 * Used in TopicResultsModal to rank papers and label weak gene-content signals.
 */

export type RelevanceTier = 'high' | 'medium' | 'low' | 'none'

export interface RelevanceResult {
  score: number
  tier: RelevanceTier
  geneSymbols: string[]
  topKeywords: string[]
  hasMolecularContext: boolean
}

// Positive signals — weighted by relevance to molecular genetics
const GENETIC_KEYWORDS: [string, number][] = [
  ['mutation', 3], ['variant', 3], ['polymorphism', 3],
  ['gene expression', 2], ['genotype', 2], ['allele', 2],
  ['snp', 3], ['deletion', 2], ['amplification', 2],
  ['methylation', 2], ['rna', 1], ['protein expression', 1],
  ['molecular', 1], ['genetic', 1], ['genomic', 2],
  ['sequencing', 2], ['exon', 2], ['intron', 1],
  ['transcription', 1], ['translation', 1], ['mrna', 2],
  ['somatic', 2], ['germline', 2], ['inheritance', 1],
  ['chromosomal', 2], ['karyotype', 2], ['copy number', 2],
  ['fusion', 2], ['translocation', 2], ['inversion', 1],
  ['crispr', 3], ['gene editing', 3], ['epigenetic', 2],
  ['histone', 2], ['promoter', 1], ['enhancer', 1],
  ['lncrna', 2], ['mirna', 2], ['sirna', 2], ['ncrna', 2],
  ['gwas', 3], ['whole genome', 2], ['exome', 3],
  ['proteomics', 2], ['phosphorylation', 1], ['ubiquitination', 1],
  ['cytokine', 2], ['interleukin', 2], ['chemokine', 2],
  ['interferon', 2], ['receptor', 1], ['signaling pathway', 2],
  ['kinase', 1], ['pathway', 1], ['biomarker', 2],
  ['dysregulation', 2], ['overexpressed', 2], ['knockdown', 2],
  ['knockout', 2], ['transgenic', 2], ['phenotype', 1],
]

// Negative signals — red flags for non-genetic papers
const NEGATIVE_KEYWORDS = [
  'systematic review', 'meta-analysis', 'literature review',
  'overview', 'commentary', 'perspective', 'editorial',
  'rehabilitation', 'psychological', 'quality of life',
  'screening program', 'public health', 'policy',
  'economic burden', 'cost-effectiveness', 'health care costs',
  'nursing', 'palliative care', 'end of life',
  'patient education', 'communication', 'decision making',
  'disparities', 'access to care', 'health insurance',
]

// Disease-gene language bonus phrases
const DISEASE_GENE_PHRASES = [
  'associated with', 'linked to', 'mutations in',
  'variants in', 'polymorphisms in', 'alterations in',
  'overexpression of', 'downregulation of', 'loss of',
]

// Terms that appear almost exclusively in molecular biology contexts
const MOLECULAR_CONTEXT_TERMS = [
  'mutation', 'variant', 'polymorphism', 'allele', 'genotype', 'haplotype',
  'gene expression', 'overexpression', 'overexpressed', 'downregulation',
  'upregulation', 'knockdown', 'knockout', 'transgenic',
  'sequencing', 'exome', 'gwas', 'snp', 'whole genome',
  'methylation', 'epigenetic', 'histone',
  'somatic', 'germline',
  'mrna', 'sirna', 'mirna', 'lncrna', 'ncrna',
  'translocation', 'chromosomal', 'karyotype', 'copy number',
  'exon', 'intron', 'promoter', 'enhancer',
  'crispr', 'gene editing',
  'proteomics', 'transcriptome',
  'locus', 'loci',
  'deletion', 'amplification',
]

// Known gene symbols (alpha-only, no digits) — high-frequency cancer/immune genes
const KNOWN_ALPHA_GENES = new Set([
  'TNF', 'EGFR', 'PTEN', 'MYC', 'KRAS', 'NRAS', 'BRAF', 'STAT', 'MAPK',
  'MTOR', 'VEGF', 'VEGFA', 'NOTCH', 'ERBB', 'FGFR', 'PDGF', 'PDGFRA',
  'PDGFRB', 'AKT', 'PIK3CA', 'RB1', 'CDKN', 'CDK', 'MDM', 'SMAD', 'TGFB',
  'NFKB', 'BCL', 'BAX', 'FAS', 'CASP', 'JAK', 'CTLA', 'IKZF', 'ARID',
  'KMT', 'IDH', 'FLT', 'KIT', 'RET', 'MET', 'ALK', 'ROS', 'ABL', 'SRC',
  'RAF', 'MEK', 'ERK', 'JNK', 'WNT', 'APC', 'AXIN', 'PARP', 'ATM', 'ATR',
  'CHEK', 'RAD', 'XRCC', 'MLH', 'MSH', 'PMS', 'HLA', 'IFNG', 'IFNA',
  'CSF', 'CXCL', 'CCL', 'CCR', 'CXCR', 'TLR', 'NLRP', 'HMGB', 'SOD',
  'GPX', 'CAT', 'HIF', 'EPAS', 'VHL', 'NRF', 'KEAP', 'GATA', 'RUNX',
  'ETV', 'FOXP', 'RORC', 'TBET', 'EOMES', 'IRF', 'BATF', 'BCL6', 'PRDM',
  'CTCF', 'DNMT', 'TET', 'HDAC', 'SIRT', 'EZH', 'SUZ', 'BMI', 'RING',
  'PRC', 'SWI', 'SNF', 'BRD', 'MLL', 'DOT', 'NSD', 'SETD', 'KDM', 'LSD',
  'JMJD', 'PHF', 'TRIM', 'RNF', 'UBE', 'USP', 'CUL', 'SKP', 'FBXW',
  'BTRC', 'VCP', 'HSP', 'HSPA', 'HSPB', 'GRP', 'BIP',
])

// False positive gene-like patterns to filter out
const GENE_FALSE_POSITIVES = new Set([
  'HIV1', 'HIV2', 'COVID19', 'H1N1', 'H5N1', 'SARS', 'MERS',
  'TABLE1', 'TABLE2', 'TABLE3', 'FIGURE1', 'FIGURE2', 'FIGURE3',
  'GROUP1', 'GROUP2', 'STUDY1', 'STUDY2', 'PHASE1', 'PHASE2', 'PHASE3',
  'TYPE1', 'TYPE2', 'GRADE1', 'GRADE2', 'GRADE3', 'STAGE1', 'STAGE2',
])

// Gene symbol regex: uppercase letters + digits (BRCA1, TP53, IL6)
const GENE_WITH_DIGITS = /\b[A-Z]{2,6}[0-9]{1,3}\b/g
// Known alpha-only gene pattern (built from KNOWN_ALPHA_GENES)
const KNOWN_ALPHA_PATTERN = new RegExp(
  `\\b(?:${Array.from(KNOWN_ALPHA_GENES).join('|')})\\b`, 'g'
)

// Variant nomenclature patterns
const VARIANT_PATTERNS = [
  /[cp]\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}/g,  // p.Val600Glu
  /[cp]\.\d+[ACGT]>[ACGT]/g,                // c.123A>G
  /\brs\d{5,}/g,                             // rs123456
  /\b[A-Z]\d{3,4}[A-Z]\b/g,                 // L858R, T790M
  /del[A-Z]?\d+/g,                           // deletion
  /ins[A-Z]?\d+/g,                           // insertion
]

function getTier(score: number): RelevanceTier {
  if (score >= 10) return 'high'
  if (score >= 5) return 'medium'
  if (score >= 1) return 'low'
  return 'none'
}

export function scoreGeneRelevance(abstract: string, title: string): RelevanceResult {
  if (!abstract || abstract.length < 100) {
    return { score: 0, tier: 'none', geneSymbols: [], topKeywords: [], hasMolecularContext: false }
  }

  const combined = `${title} ${abstract}`.toLowerCase()
  const rawText = `${title} ${abstract}`

  let score = 0
  const positiveMatches: string[] = []
  const negativeMatches: string[] = []

  // Positive keywords
  for (const [keyword, weight] of GENETIC_KEYWORDS) {
    if (combined.includes(keyword)) {
      score += weight
      positiveMatches.push(keyword)
    }
  }

  // Negative keywords
  for (const keyword of NEGATIVE_KEYWORDS) {
    if (combined.includes(keyword)) {
      score -= 5
      negativeMatches.push(keyword)
    }
  }

  // Gene symbol patterns
  const geneDigits = rawText.match(GENE_WITH_DIGITS) || []
  const geneAlpha = rawText.match(KNOWN_ALPHA_PATTERN) || []
  const allGenes = [...geneDigits, ...geneAlpha]
  const filteredGenes = allGenes.filter(g => !GENE_FALSE_POSITIVES.has(g))
  const uniqueGenes = Array.from(new Set(filteredGenes))
  const geneCount = uniqueGenes.length
  score += geneCount * 2

  // Variant nomenclature
  let variantCount = 0
  for (const pattern of VARIANT_PATTERNS) {
    pattern.lastIndex = 0 // Reset global regex
    const matches = abstract.match(pattern) || []
    variantCount += matches.length
  }
  score += variantCount * 3

  // Disease-gene phrase bonus
  for (const phrase of DISEASE_GENE_PHRASES) {
    if (combined.includes(phrase)) {
      score += 1
    }
  }

  // Molecular-context precision gate
  const hasMolecularContext = MOLECULAR_CONTEXT_TERMS.some(term => combined.includes(term))
  if (geneCount > 0 && !hasMolecularContext) {
    score -= geneCount + 3 // Halve gene contribution + flat penalty
  }

  return {
    score,
    tier: getTier(score),
    geneSymbols: uniqueGenes.slice(0, 10),
    topKeywords: positiveMatches.slice(0, 5),
    hasMolecularContext,
  }
}
