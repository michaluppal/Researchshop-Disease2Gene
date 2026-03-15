import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  X,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  AlertTriangle,
  Loader2,
  CheckSquare,
  Square,
  ArrowUpDown,
  Eye,
  EyeOff,
  Dna,
  ChevronDown,
  ChevronUp,
  FlaskConical,
  CircleMinus,
  Lock,
  LockOpen,
} from 'lucide-react'
import { getJournalQuality, calculateCompositeScore, getScoreBreakdown } from '../utils/journalQuality'
import { scoreGeneRelevance, type RelevanceResult } from '../utils/geneRelevanceScorer'

interface PaperItem {
  title?: string
  pmid?: string
  doi?: string
  pmc?: string
  url: string
  journal?: string
  authors?: string[]
  citationCount?: number
  compositeScore?: number
  pubYear?: string
  abstract?: string
  relevance?: RelevanceResult
  publicationTypes?: string[]
}

interface TopicResultsModalProps {
  isOpen: boolean
  onClose: () => void
  query: string
  onSelectPapers: (papers: PaperItem[]) => void
}

type SortMode = 'relevance' | 'recent' | 'impact' | 'gene-relevance'
const PAGE_SIZE = 20

export default function TopicResultsModal({
  isOpen,
  onClose,
  query,
  onSelectPapers,
}: TopicResultsModalProps) {
  const [allPmids, setAllPmids] = useState<string[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(0)
  const [papers, setPapers] = useState<PaperItem[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [pageLoading, setPageLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sortMode, setSortMode] = useState<SortMode>('impact')
  const [expandedScore, setExpandedScore] = useState<string | null>(null)
  const [tooMany, setTooMany] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [abstractFetchError, setAbstractFetchError] = useState<string | null>(null)
  const [expandedAbstract, setExpandedAbstract] = useState<string | null>(null)

  // Initial search
  useEffect(() => {
    if (!isOpen || !query) return
    setLoading(true)
    setError(null)
    setTooMany(false)
    setPapers([])
    setSelected(new Set())
    setPage(0)
    setShowAll(false)

    window.api.pubmed
      .search(query)
      .then((result) => {
        if (result.error) {
          setError(result.error)
          return
        }
        setTotalCount(result.count)
        if (result.count > 500) {
          setTooMany(true)
          return
        }
        setAllPmids(result.pmids)
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))
  }, [isOpen, query])

  // Fetch page details + abstracts
  const fetchPage = useCallback(
    async (pageIndex: number, pmids: string[]) => {
      const start = pageIndex * PAGE_SIZE
      const pagePmids = pmids.slice(start, start + PAGE_SIZE)
      if (pagePmids.length === 0) {
        setPapers([])
        return
      }

      setPageLoading(true)
      try {
        const [details, citations, abstractResult] = await Promise.all([
          window.api.pubmed.fetchDetails(pagePmids),
          window.api.citations.fetch(pagePmids),
          window.api.pubmed.fetchAbstracts(pagePmids),
        ])

        if (abstractResult.error) {
          setAbstractFetchError(abstractResult.error)
          setShowAll(true)  // Don't hide papers if we couldn't score them
        } else {
          setAbstractFetchError(null)
        }
        const abstracts = abstractResult.abstracts

        const items: PaperItem[] = pagePmids.map((pmid) => {
          const d = details[pmid]
          const citationCount = citations[pmid] || 0
          const journalQuality = d ? getJournalQuality(d.journal) : 40
          const compositeScore = calculateCompositeScore(citationCount, journalQuality)
          const abstract = abstracts[pmid] || ''
          const relevance = scoreGeneRelevance(abstract, d?.title || '')
          return {
            pmid,
            title: d?.title,
            doi: d?.doi,
            pmc: d?.pmc,
            url: d?.url || `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`,
            journal: d?.journal,
            authors: d?.authors,
            citationCount,
            compositeScore,
            pubYear: d?.pubYear,
            abstract,
            relevance,
            publicationTypes: d?.publicationTypes || [],
          }
        })

        setPapers(items)

        // Auto-select papers with medium+ gene relevance (only on first page load)
        if (pageIndex === 0) {
          const autoSelected = new Set<string>()
          items.forEach((p) => {
            if (p.pmid && p.relevance && (p.relevance.tier === 'high' || p.relevance.tier === 'medium')) {
              autoSelected.add(p.pmid)
            }
          })
          setSelected(autoSelected)
        }
      } catch (err) {
        setError(String(err))
      } finally {
        setPageLoading(false)
      }
    },
    []
  )

  useEffect(() => {
    if (allPmids.length > 0) {
      fetchPage(page, allPmids)
    }
  }, [page, allPmids, fetchPage])

  // Sorting
  const sortedPapers = [...papers].sort((a, b) => {
    if (sortMode === 'recent') {
      return (b.pubYear || '').localeCompare(a.pubYear || '')
    }
    if (sortMode === 'impact') {
      return (b.compositeScore || 0) - (a.compositeScore || 0)
    }
    if (sortMode === 'gene-relevance') {
      return (b.relevance?.score || 0) - (a.relevance?.score || 0)
    }
    return 0 // relevance = original order
  })

  // Filtering: hide low-relevance papers unless showAll is on
  const visiblePapers = useMemo(() => {
    if (showAll) return sortedPapers
    return sortedPapers.filter(
      (p) => !p.relevance || p.relevance.tier === 'high' || p.relevance.tier === 'medium'
    )
  }, [sortedPapers, showAll])

  const hiddenCount = sortedPapers.length - visiblePapers.length

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
    // Collect selected papers from all pages - we only have details for current page
    // so pass what we have; the parent should enrich as needed
    const selectedPapers = sortedPapers.filter((p) => p.pmid && selected.has(p.pmid))
    // Also include any selected PMIDs not on current page as minimal items
    selected.forEach((pmid) => {
      if (!selectedPapers.some((p) => p.pmid === pmid)) {
        selectedPapers.push({ pmid, url: `https://pubmed.ncbi.nlm.nih.gov/${pmid}/` })
      }
    })
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
      {/* Abstract fetch error banner */}
      {abstractFetchError && (
        <div className="flex-shrink-0 bg-amber-50 border-b border-amber-200 px-6 py-2 flex items-center justify-between">
          <p className="text-sm text-amber-800">
            Could not load abstracts for relevance scoring — showing all papers. Gene relevance badges unavailable.
          </p>
          <button
            onClick={() => setAbstractFetchError(null)}
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
              {hiddenCount > 0 && !showAll && (
                <span className="text-slate-400">
                  {' '}&middot; showing {visiblePapers.length}, {hiddenCount} low-relevance hidden
                </span>
              )}
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
            {hiddenCount > 0 && (
              <button
                onClick={() => setShowAll(!showAll)}
                className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors"
              >
                {showAll ? (
                  <EyeOff className="w-4 h-4" />
                ) : (
                  <Eye className="w-4 h-4" />
                )}
                {showAll ? 'Hide low relevance' : `Show all (${hiddenCount} hidden)`}
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <ArrowUpDown className="w-4 h-4 text-slate-400" />
            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as SortMode)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
            >
              <option value="relevance">Best Match</option>
              <option value="recent">Most Recent</option>
              <option value="impact">By Impact</option>
              <option value="gene-relevance">Gene Relevance</option>
            </select>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 text-brand-600 animate-spin" />
            <span className="ml-2 text-sm text-slate-500">Searching PubMed...</span>
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

        {pageLoading && !loading && (
          <div className="space-y-3">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="p-4 rounded-xl border border-slate-200 bg-white animate-pulse">
                <div className="flex items-start gap-3">
                  <div className="w-5 h-5 rounded bg-slate-200 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0 space-y-3">
                    <div className="flex items-center gap-2">
                      <div className="h-4 w-20 rounded bg-slate-200" />
                      <div className="h-4 w-12 rounded bg-slate-100" />
                      <div className="h-4 w-24 rounded bg-slate-100" />
                    </div>
                    <div className="h-5 w-3/4 rounded bg-slate-200" />
                    <div className="h-4 w-1/2 rounded bg-slate-100" />
                    <div className="h-3 w-2/5 rounded bg-slate-100" />
                    <div className="flex gap-3">
                      <div className="h-3 w-32 rounded bg-slate-100" />
                      <div className="h-3 w-20 rounded bg-slate-100" />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && !pageLoading && !tooMany && visiblePapers.length > 0 && (
          <div className="space-y-3">
            {visiblePapers.map((paper) => {
              const isSelected = paper.pmid ? selected.has(paper.pmid) : false
              const journalScore = paper.journal ? getJournalQuality(paper.journal) : null
              const lowRelevance = isLowRelevance(paper)
              return (
                <div
                  key={paper.pmid}
                  className={`w-full text-left rounded-xl border transition-all ${
                    isSelected
                      ? 'border-brand-300 bg-brand-50/50 shadow-sm ring-1 ring-brand-200'
                      : lowRelevance
                        ? 'border-slate-200 bg-slate-50/50 opacity-60 hover:opacity-80 hover:border-slate-300'
                        : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
                  }`}
                >
                  <button
                    onClick={() => paper.pmid && toggleSelect(paper.pmid)}
                    className="w-full text-left p-4"
                  >
                  <div className="flex items-start gap-3">
                    <div className={`w-5 h-5 mt-0.5 flex-shrink-0 rounded ${isSelected ? 'bg-brand-600 text-white' : lowRelevance ? 'border-2 border-slate-200' : 'border-2 border-slate-300 hover:border-brand-400'} flex items-center justify-center transition-colors`}>
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
                        {journalScore !== null && (
                          <span
                            className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                              journalScore >= 80
                                ? 'bg-emerald-100 text-emerald-700'
                                : journalScore >= 60
                                  ? 'bg-amber-100 text-amber-700'
                                  : 'bg-slate-100 text-slate-500'
                            }`}
                          >
                            Q{journalScore >= 80 ? '1' : journalScore >= 60 ? '2' : '3'}
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
                        {paper.compositeScore !== undefined && (
                          <span
                            onClick={(e) => {
                              e.stopPropagation()
                              setExpandedScore(expandedScore === paper.pmid ? null : (paper.pmid || null))
                            }}
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium cursor-pointer hover:ring-2 hover:ring-offset-1 hover:ring-brand-300 transition-all ${getScoreBadgeColor(paper.compositeScore)}`}
                          >
                            Impact: {paper.compositeScore}
                          </span>
                        )}
                      </div>

                    </div>
                  </div>
                  </button>
                  {/* Expandable panels — outside button to avoid nesting interactive elements */}
                  {expandedScore === paper.pmid && paper.citationCount !== undefined && paper.journal && (() => {
                    const bd = getScoreBreakdown(paper.citationCount!, getJournalQuality(paper.journal!))
                    return (
                      <div className="mx-4 mb-3 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                        <p className="font-semibold text-slate-700 mb-2">Impact Score Breakdown</p>
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Citations</span>
                            <span className="font-mono text-slate-700">{bd.citationCount}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Normalized citations (0-100)</span>
                            <span className="font-mono text-slate-700">{bd.normalizedCitations}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Citation component (60%)</span>
                            <span className="font-mono text-blue-600 font-medium">{bd.citationComponent}</span>
                          </div>
                          <div className="border-t border-slate-200 my-1" />
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Journal</span>
                            <span className="text-slate-700">{paper.journal}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Journal tier</span>
                            <span className={`font-medium ${bd.tier === 'Tier 1' ? 'text-emerald-600' : bd.tier === 'Tier 2' ? 'text-blue-600' : bd.tier === 'Tier 3' ? 'text-amber-600' : 'text-slate-500'}`}>{bd.tier} ({bd.journalQuality}/100)</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-500">Journal component (40%)</span>
                            <span className="font-mono text-emerald-600 font-medium">{bd.journalComponent}</span>
                          </div>
                          <div className="border-t border-slate-200 my-1" />
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-slate-700">Composite Score</span>
                            <span className="font-mono font-bold text-slate-900">{bd.composite}</span>
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
