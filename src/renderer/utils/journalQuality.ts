/**
 * Journal quality scoring backed by Scimago Journal Rank (SJR) data.
 *
 * Lookup chain: ISSN (exact) → normalized journal name → Unranked fallback.
 * Data source: scimagojr.com (2024), built via scripts/build-sjr-lookup.js.
 * ~49K ISSN entries, ~30K name entries covering all ranked journals worldwide.
 */

import sjrData from '../data/sjr-lookup.json'

type SjrLookup = { byIssn: Record<string, string>; byName: Record<string, string> }
const { byIssn, byName } = sjrData as SjrLookup

const Q_SCORES: Record<string, number> = { Q1: 100, Q2: 75, Q3: 50, Q4: 35 }
const UNRANKED_SCORE = 30

function normalizeJournalName(name: string): string {
  return name.toLowerCase().replace(/^the\s+/i, '').replace(/[^\w\s]/g, '').trim()
}

export function getJournalQuality(journalName: string, issn?: string): number {
  if (issn) {
    const q = byIssn[issn]
    if (q) return Q_SCORES[q] ?? UNRANKED_SCORE
  }
  if (journalName) {
    const q = byName[normalizeJournalName(journalName)]
    if (q) return Q_SCORES[q] ?? UNRANKED_SCORE
  }
  return UNRANKED_SCORE
}

export function getQuartile(journalName: string, issn?: string): string {
  if (issn) {
    const q = byIssn[issn]
    if (q) return q
  }
  if (journalName) {
    const q = byName[normalizeJournalName(journalName)]
    if (q) return q
  }
  return 'Unranked'
}

export function calculateCompositeScore(citationCount: number, journalQuality: number): number {
  const normalizedCitations = Math.min((citationCount / 200) * 100, 100)
  const compositeScore = (normalizedCitations * 0.6) + (journalQuality * 0.4)
  return Math.round(compositeScore)
}

export function getScoreBreakdown(citationCount: number, journalQuality: number, issn?: string, journalName?: string) {
  const normalizedCitations = Math.min((citationCount / 200) * 100, 100)
  const citationComponent = Math.round(normalizedCitations * 0.6)
  const journalComponent = Math.round(journalQuality * 0.4)
  const quartile = getQuartile(journalName || '', issn)
  return {
    composite: citationComponent + journalComponent,
    citationCount,
    normalizedCitations: Math.round(normalizedCitations),
    citationComponent,
    journalQuality,
    journalComponent,
    tier: quartile,
  }
}
