import { useState, useEffect, useMemo, useRef } from 'react'
import {
  X,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  AlertTriangle,
  Loader2,
  ArrowUpDown,
  Dna,
  ChevronDown,
  ChevronUp,
  FlaskConical,
  CircleMinus,
  Lock,
  LockOpen,
} from 'lucide-react'
import { getJournalQuality, getScoreBreakdown, getQuartile } from '../utils/journalQuality'
import type { RelevanceResult } from '../utils/geneRelevanceScorer'
import {
  calculateGeneticsSignal,
  calculateRecommendationScore,
  compareRecommendedPapers,
  RECOMMENDATION_WEIGHTS,
  type PaperSortMode,
} from '../../shared/paperRecommendation'

interface PaperItem {
  title?: string
  pmid?: string
  doi?: string
  pmc?: string
  issn?: string
  url: string
  journal?: string
  authors?: string[]
  citationCount?: number
  compositeScore?: number
  recommendationScore?: number
  geneticsScore?: number
  pubYear?: string
  abstract?: string
  relevance?: RelevanceResult
  publicationTypes?: string[]
  searchRank?: number
}

interface TopicResultsModalProps {
  isOpen: boolean
  onClose: () => void
  query: string
  onSelectPapers: (papers: PaperItem[]) => void
}

const PAGE_SIZE = 20

export default function TopicResultsModal({
  isOpen,
  onClose,
  query,
  onSelectPapers,
}: TopicResultsModalProps) {
  const [allPmids, setAllPmids] = useState<string[]>([])
  const [rankedPapersByPmid, setRankedPapersByPmid] = useState<Record<string, PaperItem>>({})
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sortMode, setSortMode] = useState<PaperSortMode>('recommended')
  const [expandedScore, setExpandedScore] = useState<string | null>(null)
  const [tooMany, setTooMany] = useState(false)
  const [rankingWarning, setRankingWarning] = useState<string | null>(null)
  const [expandedAbstract, setExpandedAbstract] = useState<string | null>(null)
  const rankedSearchRequestId = useRef(0)

  // Initial search
  useEffect(() => {
    const requestId = rankedSearchRequestId.current + 1
    rankedSearchRequestId.current = requestId

    if (!isOpen || !query) {
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    setTooMany(false)
    setTotalCount(0)
    setAllPmids([])
    setRankedPapersByPmid({})
    setSelected(new Set())
    setPage(0)
    setRankingWarning(null)
    setExpandedScore(null)
    setExpandedAbstract(null)

    window.api.pubmed
      .searchRanked(query)
      .then((result) => {
        if (rankedSearchRequestId.current !== requestId) return
        if (result.error) {
          setError(result.error)
          return
        }
        setTotalCount(result.count)
        if (result.count > 500) {
          setTooMany(true)
          return
        }
        const rankedPapers = result.papers || {}
        setRankedPapersByPmid(rankedPapers)
        setRankingWarning(result.rankingWarning || null)
        setAllPmids(result.pmids)
        const autoSelected = new Set<string>()
        result.pmids.slice(0, PAGE_SIZE).forEach((pmid) => {
          const paper = rankedPapers[pmid]
          if (paper?.relevance && (paper.relevance.tier === 'high' || paper.relevance.tier === 'medium')) {
            autoSelected.add(pmid)
          }
        })
        setSelected(autoSelected)
      })
      .catch((err) => {
        if (rankedSearchRequestId.current === requestId) setError(String(err))
      })
      .finally(() => {
        if (rankedSearchRequestId.current === requestId) setLoading(false)
      })

    return () => {
      if (rankedSearchRequestId.current === requestId) {
        rankedSearchRequestId.current += 1
      }
    }
  }, [isOpen, query])

  const orderedPapers = useMemo(() => {
    const rankedPapers = allPmids.map((pmid, index) => (
      rankedPapersByPmid[pmid] || {
        pmid,
        title: 'Title unavailable',
        url: `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`,
        journal: 'Unknown Journal',
        authors: [],
        citationCount: 0,
        compositeScore: 0,
        recommendationScore: 0,
        geneticsScore: 0,
        pubYear: '',
        abstract: '',
        publicationTypes: [],
        searchRank: index,
      }
    ))
    return rankedPapers
      .sort((a, b) => compareRecommendedPapers(a, b, sortMode))
  }, [allPmids, rankedPapersByPmid, sortMode])

  useEffect(() => {
    setPage(0)
  }, [sortMode])

  const visiblePapers = useMemo(() => {
    const start = page * PAGE_SIZE
    return orderedPapers.slice(start, start + PAGE_SIZE)
  }, [orderedPapers, page])

  const totalPages = Math.ceil(allPmids.length / PAGE_SIZE)

  const toggleSelect = (pmid: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(pmid)) next.delete(pmid)
      else next.add(pmid)
      return next
    })
  }

  const toggleAll = () => {
    const pagePmids = visiblePapers.map((p) => p.pmid!).filter(Boolean)
    const allSelected = pagePmids.every((id) => selected.has(id))
    setSelected((prev) => {
      const next = new Set(prev)
      if (allSelected) {
        pagePmids.forEach((id) => next.delete(id))
      } else {
        pagePmids.forEach((id) => next.add(id))
      }
      return next
    })
  }

  const handleAdd = () => {
    // Preserve full ranked metadata for selected papers, including off-page selections.
    const selectedPapers = Array.from(selected).map((pmid) => (
      rankedPapersByPmid[pmid] ||
      orderedPapers.find((p) => p.pmid === pmid) ||
      { pmid, url: `https://pubmed.ncbi.nlm.nih.gov/${pmid}/` }
    ))
    onSelectPapers(selectedPapers)
    onClose()
  }

  if (!isOpen) return null

  const getScoreBadgeColor = (score?: number) => {
    if (!score) return 'bg-slate-100 text-slate-600'
    if (score >= 70) return 'bg-emerald-100 text-emerald-700'
    if (score >= 40) return 'bg-amber-100 text-amber-700'
    return 'bg-slate-100 text-slate-600'
  }

  const getRelevanceBadge = (relevance?: RelevanceResult) => {
    if (!relevance) return null
    if (relevance.tier === 'high') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-xs font-semibold border border-emerald-200">
          <Dna className="w-3.5 h-3.5" />
          Gene content
        </span>
      )
    }
    if (relevance.tier === 'medium') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 text-xs font-medium border border-blue-200">
          <FlaskConical className="w-3 h-3" />
          Moderate relevance
        </span>
      )
    }
    if (relevance.tier === 'low' || relevance.tier === 'none') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 text-xs font-medium border border-amber-200">
          <CircleMinus className="w-3 h-3" />
          Low relevance
        </span>
      )
    }
    return null
  }

  const isLowRelevance = (paper: PaperItem) =>
    paper.relevance && (paper.relevance.tier === 'low' || paper.relevance.tier === 'none')

  const getLowRelevanceReason = (paper: PaperItem): string => {
    const types = paper.publicationTypes || []
    if (types.some(t => ['Review', 'Meta-Analysis', 'Systematic Review'].includes(t))) return 'Review article'
    if (!paper.relevance) return 'Not scored'
    const { score, hasMolecularContext, geneSymbols } = paper.relevance
    if (score <= 0 && geneSymbols.length === 0) return 'No molecular gene content'
    if (!hasMolecularContext && geneSymbols.length === 0) return 'No gene symbols detected'
    if (!hasMolecularContext) return 'No molecular context'
    return 'Low gene signal'
  }

  const currentPagePmids = new Set(visiblePapers.map(p => p.pmid).filter(Boolean) as string[])
  const offPageSelected = Array.from(selected).filter(pmid => !currentPagePmids.has(pmid)).length

  return (
    <div className="fixed inset-0 z-50 bg-slate-50 flex flex-col">
      {/* Ranking warning banner */}
      {rankingWarning && (
        <div className="flex-shrink-0 bg-amber-50 border-b border-amber-200 px-6 py-2 flex items-center justify-between">
          <p className="text-sm text-amber-800">
            {rankingWarning}
          </p>
          <button
            onClick={() => setRankingWarning(null)}
            className="ml-4 text-amber-600 hover:text-amber-800 text-xs underline flex-shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}
      {/* Sticky header */}
      <div className="flex-shrink-0 bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Topic Search Results</h2>
            <p className="text-sm text-slate-500 mt-0.5">
              {totalCount.toLocaleString()} papers found for &ldquo;{query}&rdquo;
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={toggleAll}
              className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900 transition-colors"
            >
              <div className={`w-4 h-4 rounded flex-shrink-0 flex items-center justify-center transition-colors ${
                visiblePapers.length > 0 && visiblePapers.every((p) => p.pmid && selected.has(p.pmid))
                  ? 'bg-brand-600 text-white'
                  : 'border-2 border-slate-300 hover:border-brand-400'
              }`}>
                {visiblePapers.length > 0 && visiblePapers.every((p) => p.pmid && selected.has(p.pmid)) && (
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>
              Select All
            </button>
          </div>
          <div className="flex items-center gap-2">
            <ArrowUpDown className="w-4 h-4 text-slate-400" />
            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as PaperSortMode)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
            >
              <option value="recommended">Recommended</option>
              <option value="recent">Most Recent</option>
              <option value="citations">Most Cited</option>
              <option value="pubmed">PubMed Order</option>
            </select>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 text-brand-600 animate-spin" />
            <span className="ml-2 text-sm text-slate-500">Searching and ranking PubMed...</span>
          </div>
        )}

        {tooMany && (
          <div className="flex items-center gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200 mt-4">
            <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-amber-800">
                Too many results ({totalCount.toLocaleString()})
              </p>
              <p className="text-sm text-amber-600 mt-0.5">
                Please refine your query to fewer than 500 papers.
              </p>
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-3 p-4 rounded-xl bg-red-50 border border-red-200 mt-4">
            <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {!loading && !tooMany && visiblePapers.length > 0 && (
          <div className="space-y-3">
            {visiblePapers.map((paper) => {
              const isSelected = paper.pmid ? selected.has(paper.pmid) : false
              const journalScore = paper.journal ? getJournalQuality(paper.journal, paper.issn) : null
              const quartile = paper.journal ? getQuartile(paper.journal, paper.issn) : 'Unranked'
              const lowRelevance = isLowRelevance(paper)
              return (
                <div
                  key={paper.pmid}
                  className={`w-full text-left rounded-xl border transition-all ${
                    isSelected
                      ? 'border-brand-300 bg-brand-50/50 shadow-sm ring-1 ring-brand-200'
                      : lowRelevance
                        ? 'border-amber-200 bg-white hover:border-amber-300 hover:shadow-sm'
                        : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
                  }`}
                >
                  <button
                    onClick={() => paper.pmid && toggleSelect(paper.pmid)}
                    className="w-full text-left p-4"
                  >
                  <div className="flex items-start gap-3">
                    <div className={`w-5 h-5 mt-0.5 flex-shrink-0 rounded ${isSelected ? 'bg-brand-600 text-white' : lowRelevance ? 'border-2 border-amber-300' : 'border-2 border-slate-300 hover:border-brand-400'} flex items-center justify-center transition-colors`}>
                      {isSelected && (
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      {/* Title — prominent */}
                      <p className="text-[15px] font-bold text-slate-900 mb-1.5 leading-snug line-clamp-2">
                        {paper.title || 'Untitled'}
                      </p>

                      {/* Authors — muted */}
                      {paper.authors && paper.authors.length > 0 && (
                        <p className="text-xs text-slate-400 mb-1">
                          {paper.authors.slice(0, 4).join(', ')}
                          {paper.authors.length > 4 && ` et al.`}
                        </p>
                      )}

                      {/* Journal + year — italic journal */}
                      <div className="flex items-center gap-2 mb-2">
                        {paper.journal && (
                          <span className="text-xs text-slate-500 italic">{paper.journal}</span>
                        )}
                        {paper.pubYear && (
                          <span className="text-xs text-slate-400">{paper.pubYear}</span>
                        )}
                        {journalScore !== null && quartile !== 'Unranked' && (
                          <span
                            className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                              quartile === 'Q1'
                                ? 'bg-emerald-100 text-emerald-700'
                                : quartile === 'Q2'
                                  ? 'bg-amber-100 text-amber-700'
                                  : 'bg-slate-100 text-slate-500'
                            }`}
                          >
                            {quartile}
                          </span>
                        )}
                      </div>

                      {/* Abstract preview — always visible, 2-line clamp */}
                      {paper.abstract && (
                        <p className="text-xs text-slate-500 line-clamp-2 mb-2 leading-relaxed">
                          {paper.abstract}
                        </p>
                      )}

                      {/* Badges row */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="inline-flex items-center px-2 py-0.5 rounded bg-slate-100 text-slate-500 text-xs font-mono">
                          PMID: {paper.pmid}
                        </span>
                        {paper.citationCount !== undefined && paper.citationCount > 0 && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs font-medium">
                            {paper.citationCount} citations
                          </span>
                        )}
                        {/* Publication type warning */}
                        {(() => {
                          const reviewType = (paper.publicationTypes || []).find(t =>
                            ['Review', 'Meta-Analysis', 'Systematic Review', 'Editorial', 'Comment', 'Letter'].includes(t)
                          )
                          if (!reviewType) return null
                          return (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-50 text-red-600 text-xs font-medium border border-red-200">
                              <AlertTriangle className="w-3 h-3" /> {reviewType}
                            </span>
                          )
                        })()}
                        {/* Full text availability */}
                        {paper.pmc
                          ? <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium border border-emerald-200">
                              <LockOpen className="w-3 h-3" /> Full text
                            </span>
                          : <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 text-xs font-medium border border-amber-200">
                              <Lock className="w-3 h-3" /> Abstract only
                            </span>
                        }
                        {getRelevanceBadge(paper.relevance)}
                      </div>

                      {/* Gene symbols + keywords */}
                      {paper.relevance && paper.relevance.geneSymbols.length > 0 && (
                        <p className="text-xs text-slate-400 mt-1.5">
                          <span className="font-medium text-slate-500">Genes: </span>
                          {paper.relevance.geneSymbols.slice(0, 6).join(' · ')}
                        </p>
                      )}
                      {paper.relevance && paper.relevance.topKeywords.length > 0 && (
                        <p className="text-xs text-slate-400">
                          <span className="font-medium text-slate-500">Keywords: </span>
                          {paper.relevance.topKeywords.join(', ')}
                        </p>
                      )}
                      {/* Low-relevance reason */}
                      {lowRelevance && (
                        <p className="text-xs text-amber-500 mt-1 italic">{getLowRelevanceReason(paper)}</p>
                      )}

                      {/* Action row */}
                      <div className="flex items-center gap-3 mt-2 flex-wrap">
                        <span
                          role="link"
                          tabIndex={0}
                          onClick={(e) => {
                            e.stopPropagation()
                            window.api.shell.openExternal(paper.url)
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.stopPropagation()
                              window.api.shell.openExternal(paper.url)
                            }
                          }}
                          className="inline-flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 cursor-pointer"
                        >
                          <ExternalLink className="w-3 h-3" />
                          View on PubMed
                        </span>
                        {paper.doi && (
                          <span
                            role="link"
                            tabIndex={0}
                            onClick={(e) => {
                              e.stopPropagation()
                              window.api.shell.openExternal(`https://doi.org/${paper.doi}`)
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.stopPropagation()
                                window.api.shell.openExternal(`https://doi.org/${paper.doi}`)
                              }
                            }}
                            className="inline-flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 cursor-pointer"
                          >
                            <ExternalLink className="w-3 h-3" />
                            DOI
                          </span>
                        )}
                        {paper.abstract && (
                          <span
                            onClick={(e) => {
                              e.stopPropagation()
                              setExpandedAbstract(expandedAbstract === paper.pmid ? null : (paper.pmid || null))
                            }}
                            className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 cursor-pointer"
                          >
                            {expandedAbstract === paper.pmid ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                            Full abstract
                          </span>
                        )}
                        {paper.recommendationScore !== undefined && (
                          <span
                            onClick={(e) => {
                              e.stopPropagation()
                              setExpandedScore(expandedScore === paper.pmid ? null : (paper.pmid || null))
                            }}
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium cursor-pointer hover:ring-2 hover:ring-offset-1 hover:ring-brand-300 transition-all ${getScoreBadgeColor(paper.recommendationScore)}`}
                          >
                            Recommended: {paper.recommendationScore}
                          </span>
                        )}
                      </div>

                    </div>
                  </div>
                  </button>
                  {/* Expandable panels — outside button to avoid nesting interactive elements */}
                  {expandedScore === paper.pmid && paper.citationCount !== undefined && (() => {
                    const journalQuality = paper.journal ? getJournalQuality(paper.journal, paper.issn) : 30
                    const bd = getScoreBreakdown(paper.citationCount!, journalQuality, paper.issn, paper.journal)
                    const geneticsScore = paper.geneticsScore ?? calculateGeneticsSignal(paper.relevance)
                    const impactScore = paper.compositeScore ?? bd.composite
                    const geneticsComponent = Math.round(geneticsScore * RECOMMENDATION_WEIGHTS.genetics)
                    const impactComponent = Math.round(impactScore * RECOMMENDATION_WEIGHTS.impact)
                    return (
                      <div className="mx-4 mb-3 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                        <p className="font-semibold text-slate-700 mb-2">Recommendation Score</p>
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Genetics signal (65%)</span>
                            <span className="font-mono text-emerald-600 font-medium">{geneticsComponent}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Gene relevance score</span>
                            <span className="font-mono text-slate-700">{paper.relevance?.score ?? 0}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Gene relevance tier</span>
                            <span className="font-medium text-slate-700">{paper.relevance?.tier ?? 'unscored'}</span>
                          </div>
                          <div className="border-t border-slate-200 my-1" />
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Impact signal (35%)</span>
                            <span className="font-mono text-blue-600 font-medium">{impactComponent}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Citations</span>
                            <span className="font-mono text-slate-700">{bd.citationCount}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Normalized citations (0-100)</span>
                            <span className="font-mono text-slate-700">{bd.normalizedCitations}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Citation share of impact score</span>
                            <span className="font-mono text-slate-700">{bd.citationComponent}</span>
                          </div>
                          <div className="border-t border-slate-200 my-1" />
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Journal</span>
                            <span className="text-slate-700">{paper.journal || 'Unranked / unknown'}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Journal tier</span>
                            <span className={`font-medium ${bd.tier === 'Q1' ? 'text-emerald-600' : bd.tier === 'Q2' ? 'text-blue-600' : bd.tier === 'Q3' ? 'text-amber-600' : 'text-slate-500'}`}>{bd.tier} ({bd.journalQuality}/100)</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Journal share of impact score</span>
                            <span className="font-mono text-slate-700">{bd.journalComponent}</span>
                          </div>
                          <div className="border-t border-slate-200 my-1" />
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-slate-700">Recommendation Score</span>
                            <span className="font-mono font-bold text-slate-900">{paper.recommendationScore}</span>
                          </div>
                        </div>
                      </div>
                    )
                  })()}
                  {expandedAbstract === paper.pmid && paper.abstract && (
                    <div className="mx-4 mb-3 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs leading-relaxed text-slate-600 max-h-48 overflow-y-auto">
                      <p className="font-semibold text-slate-700 mb-1.5">Abstract</p>
                      <p className="whitespace-pre-wrap">{paper.abstract}</p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Pagination */}
        {!tooMany && totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-6">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-2 rounded-lg hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              let pageNum: number
              if (totalPages <= 7) {
                pageNum = i
              } else if (page < 3) {
                pageNum = i
              } else if (page > totalPages - 4) {
                pageNum = totalPages - 7 + i
              } else {
                pageNum = page - 3 + i
              }
              return (
                <button
                  key={pageNum}
                  onClick={() => setPage(pageNum)}
                  className={`w-8 h-8 rounded-lg text-sm font-medium transition-colors ${
                    page === pageNum
                      ? 'bg-brand-600 text-white'
                      : 'hover:bg-slate-100 text-slate-600'
                  }`}
                >
                  {pageNum + 1}
                </button>
              )
            })}
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="p-2 rounded-lg hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Sticky footer */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-3 border-t border-slate-200 bg-white">
        <div className="flex items-center gap-3">
          <span className={`inline-flex items-center gap-1.5 text-sm font-semibold ${selected.size > 0 ? 'text-brand-700' : 'text-slate-400'}`}>
            <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${selected.size > 0 ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-400'}`}>
              {selected.size}
            </span>
            paper{selected.size !== 1 ? 's' : ''} selected
            {offPageSelected > 0 && (
              <span className="text-xs font-normal text-slate-400 ml-1">(+{offPageSelected} on other pages)</span>
            )}
          </span>
          {allPmids.length > 0 && (
            <span className="text-xs text-slate-400">
              of {allPmids.length} total
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-700 rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={selected.size === 0}
            className="px-5 py-2 text-sm font-semibold text-white bg-brand-600 rounded-lg hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            Add {selected.size} Paper{selected.size !== 1 ? 's' : ''}
          </button>
        </div>
      </div>
    </div>
  )
}
