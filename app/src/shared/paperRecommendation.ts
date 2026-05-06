import type { RelevanceResult } from './geneRelevanceScorer'

export type PaperSortMode = 'recommended' | 'recent' | 'citations' | 'pubmed'

export interface RecommendablePaper {
  citationCount?: number
  compositeScore?: number
  recommendationScore?: number
  geneticsScore?: number
  pubYear?: string
  relevance?: RelevanceResult
  searchRank?: number
}

export const GENETICS_SIGNAL_CAP = 20
export const RECOMMENDATION_WEIGHTS = {
  genetics: 0.65,
  impact: 0.35,
} as const

export function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)))
}

export function calculateGeneticsSignal(relevance?: RelevanceResult): number {
  if (!relevance) return 0
  return clampScore((Math.max(relevance.score, 0) / GENETICS_SIGNAL_CAP) * 100)
}

export function calculateRecommendationScore(geneticsScore: number, impactScore: number): number {
  return clampScore(
    geneticsScore * RECOMMENDATION_WEIGHTS.genetics +
    impactScore * RECOMMENDATION_WEIGHTS.impact
  )
}

function compareNumbersDesc(a = 0, b = 0): number {
  return b - a
}

export function compareByPubMedOrder(a: RecommendablePaper, b: RecommendablePaper): number {
  return (a.searchRank ?? Number.MAX_SAFE_INTEGER) - (b.searchRank ?? Number.MAX_SAFE_INTEGER)
}

export function compareRecommendedPapers(
  a: RecommendablePaper,
  b: RecommendablePaper,
  sortMode: PaperSortMode
): number {
  if (sortMode === 'recent') {
    return (
      (b.pubYear || '').localeCompare(a.pubYear || '') ||
      compareNumbersDesc(a.recommendationScore, b.recommendationScore) ||
      compareByPubMedOrder(a, b)
    )
  }
  if (sortMode === 'citations') {
    return (
      compareNumbersDesc(a.citationCount, b.citationCount) ||
      compareNumbersDesc(a.recommendationScore, b.recommendationScore) ||
      compareByPubMedOrder(a, b)
    )
  }
  if (sortMode === 'recommended') {
    return (
      compareNumbersDesc(a.recommendationScore, b.recommendationScore) ||
      compareNumbersDesc(a.relevance?.score, b.relevance?.score) ||
      compareNumbersDesc(a.compositeScore, b.compositeScore) ||
      compareByPubMedOrder(a, b)
    )
  }
  return compareByPubMedOrder(a, b)
}
