const TIER_1_JOURNALS = [
  'Nature', 'Science', 'Cell', 'The New England Journal of Medicine', 'NEJM',
  'The Lancet', 'Lancet', 'JAMA', 'Journal of the American Medical Association',
  'Nature Medicine', 'Nature Biotechnology', 'Cell Stem Cell', 'Nature Genetics', 'Nature Immunology',
]

const TIER_2_JOURNALS = [
  'British Medical Journal', 'BMJ', 'PLOS Medicine', 'Annals of Internal Medicine',
  'Circulation', 'Journal of Clinical Oncology', 'JCO', 'Immunity', 'Cancer Cell', 'Neuron',
  'Cell Metabolism', 'Molecular Cell', 'The Lancet Oncology', 'The Lancet Neurology',
  'Nature Reviews', 'Blood', 'Gastroenterology', 'Hepatology',
  'Journal of Experimental Medicine', 'Proceedings of the National Academy of Sciences', 'PNAS',
]

const TIER_3_JOURNALS = [
  'PLOS ONE', 'Scientific Reports', 'Journal of Biological Chemistry', 'Biochemistry',
  'Clinical Infectious Diseases', 'The American Journal of Pathology',
  'Molecular Biology and Evolution', 'Genome Research', 'Diabetes',
  'The Journal of Infectious Diseases', 'Pediatrics', 'Archives of Internal Medicine',
  'European Heart Journal', 'Journal of the National Cancer Institute',
  'American Journal of Respiratory and Critical Care Medicine', 'Biomaterials', 'Nucleic Acids Research',
]

const DEFAULT_SCORE = 40

function normalizeJournalName(name: string): string {
  return name.toLowerCase().replace(/^the\s+/i, '').replace(/[^\w\s]/g, '').trim()
}

export function getJournalQuality(journalName: string): number {
  if (!journalName) return DEFAULT_SCORE
  const normalized = normalizeJournalName(journalName)
  if (TIER_1_JOURNALS.some(j => normalizeJournalName(j) === normalized)) return 100
  if (TIER_2_JOURNALS.some(j => normalizeJournalName(j) === normalized)) return 80
  if (TIER_3_JOURNALS.some(j => normalizeJournalName(j) === normalized)) return 60
  if (normalized.includes('nature') || normalized.includes('cell') || normalized.includes('science')) return 80
  if (normalized.includes('lancet') || normalized.includes('jama') || normalized.includes('nejm')) return 90
  return DEFAULT_SCORE
}

export function calculateCompositeScore(citationCount: number, journalQuality: number): number {
  const normalizedCitations = Math.min((citationCount / 500) * 100, 100)
  const compositeScore = (normalizedCitations * 0.6) + (journalQuality * 0.4)
  return Math.round(compositeScore)
}

export function getScoreBreakdown(citationCount: number, journalQuality: number) {
  const normalizedCitations = Math.min((citationCount / 500) * 100, 100)
  const citationComponent = Math.round(normalizedCitations * 0.6)
  const journalComponent = Math.round(journalQuality * 0.4)
  const tier = journalQuality >= 100 ? 'Tier 1' : journalQuality >= 80 ? 'Tier 2' : journalQuality >= 60 ? 'Tier 3' : 'Unranked'
  return {
    composite: citationComponent + journalComponent,
    citationCount,
    normalizedCitations: Math.round(normalizedCitations),
    citationComponent,
    journalQuality,
    journalComponent,
    tier,
  }
}
