import { describe, expect, it } from 'vitest'
import {
  calculateGeneticsSignal,
  calculateRecommendationScore,
  compareRecommendedPapers,
  type RecommendablePaper,
} from '../paperRecommendation'

describe('paper recommendation scoring', () => {
  it('weights genetics above impact for the recommended score', () => {
    const highGenetics = calculateGeneticsSignal({
      score: 20,
      tier: 'high',
      geneSymbols: ['IFNG'],
      topKeywords: ['interferon'],
      hasMolecularContext: true,
    })
    const noGenetics = calculateGeneticsSignal({
      score: 0,
      tier: 'none',
      geneSymbols: [],
      topKeywords: [],
      hasMolecularContext: false,
    })

    expect(calculateRecommendationScore(highGenetics, 30)).toBeGreaterThan(
      calculateRecommendationScore(noGenetics, 100)
    )
  })

  it('sorts the complete result set before pagination can slice it', () => {
    const papers: RecommendablePaper[] = [
      { recommendationScore: 20, searchRank: 0 },
      { recommendationScore: 95, searchRank: 24 },
      { recommendationScore: 80, searchRank: 3 },
    ]

    const sorted = [...papers].sort((a, b) => compareRecommendedPapers(a, b, 'recommended'))

    expect(sorted.map((paper) => paper.searchRank)).toEqual([24, 3, 0])
  })

  it('keeps PubMed order as an explicit stable sort option', () => {
    const papers: RecommendablePaper[] = [
      { recommendationScore: 95, searchRank: 3 },
      { recommendationScore: 20, searchRank: 0 },
    ]

    const sorted = [...papers].sort((a, b) => compareRecommendedPapers(a, b, 'pubmed'))

    expect(sorted.map((paper) => paper.searchRank)).toEqual([0, 3])
  })
})
