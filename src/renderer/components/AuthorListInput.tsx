import { useState, useCallback } from 'react'
import {
  Plus,
  X,
  Loader2,
  ChevronDown,
  ChevronUp,
  Pencil,
  Trash2,
  ExternalLink,
  CheckSquare,
  Square,
  Filter,
  AlertTriangle,
  Users,
  Check,
  ArrowUpDown,
} from 'lucide-react'
import KeywordFilterModal from './KeywordFilterModal'
import { getJournalQuality, calculateCompositeScore, getScoreBreakdown } from '../utils/journalQuality'

interface PaperItem {
  title?: string
  pmid?: string
  doi?: string
  pmc?: string
  url: string
  journal?: string
  citationCount?: number
  compositeScore?: number
}

interface AuthorEntry {
  id: string
  name: string
  status: 'pending' | 'searching' | 'found' | 'not-found'
  papers: PaperItem[]
  selectedPaperIds: Set<string>
  isExpanded: boolean
  totalCount?: number
  isEditing?: boolean
  editName?: string
  startYear?: string
  endYear?: string
  keywords?: string[]
  keywordLogic?: 'AND' | 'OR'
}

interface AuthorListInputProps {
  onPapersChange: (papers: PaperItem[]) => void
}

let idCounter = 0
function generateId() {
  return `author-${++idCounter}-${Date.now()}`
}

function buildAuthorQuery(name: string, entry?: AuthorEntry): string {
  let query = `${name}[Author]`

  if (entry?.keywords && entry.keywords.length > 0) {
    const logic = entry.keywordLogic || 'AND'
    const kwPart = entry.keywords.map((k) => `"${k}"`).join(` ${logic} `)
    query = `(${query}) AND (${kwPart})`
  }

  if (entry?.startYear || entry?.endYear) {
    const from = entry.startYear || '1900'
    const to = entry.endYear || '2099'
    query += ` AND ("${from}"[Date - Publication] : "${to}"[Date - Publication])`
  }

  return query
}

export default function AuthorListInput({ onPapersChange }: AuthorListInputProps) {
  const [input, setInput] = useState('')
  const [authors, setAuthors] = useState<AuthorEntry[]>([])
  const [filterModal, setFilterModal] = useState<{ authorId: string } | null>(null)
  const [sortMode, setSortMode] = useState<'default' | 'impact'>('impact')
  const [expandedScore, setExpandedScore] = useState<string | null>(null)

  const totalSelected = authors.reduce((sum, a) => sum + a.selectedPaperIds.size, 0)

  const notifyPapersChange = useCallback(
    (updated: AuthorEntry[]) => {
      const allPapers: PaperItem[] = []
      for (const author of updated) {
        for (const paper of author.papers) {
          const id = paper.pmid || paper.doi || paper.url
          if (author.selectedPaperIds.has(id)) {
            allPapers.push(paper)
          }
        }
      }
      onPapersChange(allPapers)
    },
    [onPapersChange]
  )

  const searchAuthor = async (entry: AuthorEntry, allAuthors: AuthorEntry[]): Promise<AuthorEntry[]> => {
    // Try multiple name formats
    const nameParts = entry.name.split(/\s+/)
    let bestResult: { pmids: string[]; count: number } | null = null

    const queries = [entry.name]
    if (nameParts.length >= 2) {
      const last = nameParts[nameParts.length - 1]
      const firstInitial = nameParts[0][0]
      queries.push(`${last} ${firstInitial}`)
    }

    for (const nameFormat of queries) {
      const query = buildAuthorQuery(nameFormat, entry)
      const result = await window.api.pubmed.search(query)
      if (!result.error && result.count > 0) {
        if (!bestResult || result.count > bestResult.count) {
          bestResult = { pmids: result.pmids, count: result.count }
        }
        if (result.count <= 1000) break
      }
    }

    if (!bestResult || bestResult.count === 0) {
      return allAuthors.map((a) =>
        a.id === entry.id ? { ...a, status: 'not-found' as const, papers: [], totalCount: 0 } : a
      )
    }

    // Fetch details and citations
    const [details, citations] = await Promise.all([
      window.api.pubmed.fetchDetails(bestResult.pmids),
      window.api.citations.fetch(bestResult.pmids),
    ])
    const papers: PaperItem[] = bestResult.pmids.map((pmid) => {
      const d = details[pmid]
      const citationCount = citations[pmid] || 0
      const journalQuality = d ? getJournalQuality(d.journal) : 40
      const compositeScore = calculateCompositeScore(citationCount, journalQuality)
      return {
        pmid,
        title: d?.title,
        doi: d?.doi,
        pmc: d?.pmc,
        url: d?.url || `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`,
        journal: d?.journal,
        citationCount,
        compositeScore,
      }
    })

    const allSelected = new Set(papers.map((p) => p.pmid || p.doi || p.url))

    return allAuthors.map((a) =>
      a.id === entry.id
        ? {
            ...a,
            status: 'found' as const,
            papers,
            selectedPaperIds: allSelected,
            totalCount: bestResult!.count,
          }
        : a
    )
  }

  const addAuthor = async () => {
    const name = input.trim()
    if (!name) return
    if (authors.some((a) => a.name.toLowerCase() === name.toLowerCase())) return

    const entry: AuthorEntry = {
      id: generateId(),
      name,
      status: 'searching',
      papers: [],
      selectedPaperIds: new Set(),
      isExpanded: false,
    }

    const updated = [...authors, entry]
    setAuthors(updated)
    setInput('')

    try {
      const result = await searchAuthor(entry, updated)
      setAuthors(result)
      notifyPapersChange(result)
    } catch {
      setAuthors((prev) =>
        prev.map((a) => (a.id === entry.id ? { ...a, status: 'not-found' } : a))
      )
    }
  }

  const removeAuthor = (id: string) => {
    const updated = authors.filter((a) => a.id !== id)
    setAuthors(updated)
    notifyPapersChange(updated)
  }

  const toggleExpand = (id: string) => {
    setAuthors((prev) => prev.map((a) => (a.id === id ? { ...a, isExpanded: !a.isExpanded } : a)))
  }

  const togglePaper = (authorId: string, paperId: string) => {
    const updated = authors.map((a) => {
      if (a.id !== authorId) return a
      const next = new Set(a.selectedPaperIds)
      if (next.has(paperId)) next.delete(paperId)
      else next.add(paperId)
      return { ...a, selectedPaperIds: next }
    })
    setAuthors(updated)
    notifyPapersChange(updated)
  }

  const toggleAllForAuthor = (authorId: string) => {
    const updated = authors.map((a) => {
      if (a.id !== authorId) return a
      const allIds = a.papers.map((p) => p.pmid || p.doi || p.url)
      const allSelected = allIds.every((id) => a.selectedPaperIds.has(id))
      return {
        ...a,
        selectedPaperIds: allSelected ? new Set<string>() : new Set(allIds),
      }
    })
    setAuthors(updated)
    notifyPapersChange(updated)
  }

  const startEditing = (id: string) => {
    setAuthors((prev) =>
      prev.map((a) => (a.id === id ? { ...a, isEditing: true, editName: a.name } : a))
    )
  }

  const cancelEditing = (id: string) => {
    setAuthors((prev) => prev.map((a) => (a.id === id ? { ...a, isEditing: false } : a)))
  }

  const saveEditing = async (id: string) => {
    const author = authors.find((a) => a.id === id)
    if (!author || !author.editName?.trim()) return

    const updated = authors.map((a) =>
      a.id === id
        ? { ...a, name: a.editName!.trim(), isEditing: false, status: 'searching' as const }
        : a
    )
    setAuthors(updated)

    const entry = updated.find((a) => a.id === id)!
    try {
      const result = await searchAuthor(entry, updated)
      setAuthors(result)
      notifyPapersChange(result)
    } catch {
      setAuthors((prev) =>
        prev.map((a) => (a.id === id ? { ...a, status: 'not-found' } : a))
      )
    }
  }

  const applyFilters = async (
    authorId: string,
    keywords: string[],
    logic: 'AND' | 'OR',
    startYear: string,
    endYear: string
  ) => {
    const updated = authors.map((a) =>
      a.id === authorId
        ? { ...a, keywords, keywordLogic: logic, startYear, endYear, status: 'searching' as const }
        : a
    )
    setAuthors(updated)

    const entry = updated.find((a) => a.id === authorId)!
    try {
      const result = await searchAuthor(entry, updated)
      setAuthors(result)
      notifyPapersChange(result)
    } catch {
      setAuthors((prev) =>
        prev.map((a) => (a.id === authorId ? { ...a, status: 'not-found' } : a))
      )
    }
  }

  const filterAuthor = filterModal ? authors.find((a) => a.id === filterModal.authorId) : null

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <label className="block text-sm font-medium text-slate-700">Authors</label>
        {totalSelected > 0 && (
          <span className="text-xs text-brand-600 font-medium">
            {totalSelected} paper{totalSelected !== 1 ? 's' : ''} selected
          </span>
        )}
      </div>

      {/* Add input — chips + input in one container */}
      <div className="flex items-start gap-2 mb-4">
        <div className="flex-1 flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-300 px-2 py-1.5 focus-within:ring-2 focus-within:ring-brand-500 focus-within:border-brand-500 min-h-[38px]">
          {authors.map((author) => (
            <span
              key={author.id}
              className="inline-flex items-center gap-1 rounded-full bg-brand-50 text-brand-700 border border-brand-200 px-2.5 py-0.5 text-sm animate-chip-in"
            >
              {author.name}
              <button
                onClick={() => removeAuthor(author.id)}
                className="ml-0.5 rounded-full p-0.5 text-brand-400 hover:text-red-600 hover:bg-red-50 transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                addAuthor()
              }
            }}
            placeholder={authors.length === 0 ? 'Add author name and press Enter' : 'Add another author...'}
            className="flex-1 min-w-[150px] bg-transparent outline-none text-sm py-0.5 placeholder:text-slate-400"
          />
        </div>
        <button
          onClick={addAuthor}
          className="inline-flex items-center gap-1 px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors flex-shrink-0"
        >
          <Plus className="w-4 h-4" />
          Add
        </button>
      </div>

      {/* Author list */}
      {authors.length > 0 && (
        <div className="space-y-3">
          {authors.map((author) => {
            const allIds = author.papers.map((p) => p.pmid || p.doi || p.url)
            const allSelected = allIds.length > 0 && allIds.every((id) => author.selectedPaperIds.has(id))

            return (
              <div key={author.id} className="border border-slate-200 rounded-xl overflow-hidden">
                {/* Author header */}
                <div className="flex items-center gap-3 px-4 py-3 bg-white">
                  <Users className="w-4 h-4 text-slate-400 flex-shrink-0" />

                  {author.isEditing ? (
                    <div className="flex items-center gap-2 flex-1">
                      <input
                        value={author.editName || ''}
                        onChange={(e) =>
                          setAuthors((prev) =>
                            prev.map((a) =>
                              a.id === author.id ? { ...a, editName: e.target.value } : a
                            )
                          )
                        }
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEditing(author.id)
                          if (e.key === 'Escape') cancelEditing(author.id)
                        }}
                        className="flex-1 rounded-lg border border-slate-300 px-2 py-1 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
                        autoFocus
                      />
                      <button
                        onClick={() => saveEditing(author.id)}
                        className="p-1 text-emerald-600 hover:text-emerald-700 transition-colors"
                      >
                        <Check className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => cancelEditing(author.id)}
                        className="p-1 text-slate-400 hover:text-slate-600 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-medium text-slate-900">{author.name}</span>
                        <span className="ml-2 text-xs text-slate-500">
                          {author.status === 'searching' && (
                            <span className="inline-flex items-center gap-1">
                              <Loader2 className="w-3 h-3 animate-spin" />
                              Searching...
                            </span>
                          )}
                          {author.status === 'found' &&
                            `${author.papers.length} papers (${author.selectedPaperIds.size} selected)`}
                          {author.status === 'not-found' && (
                            <span className="text-amber-600">Not found</span>
                          )}
                        </span>

                        {/* Filter badges */}
                        {((author.keywords && author.keywords.length > 0) ||
                          author.startYear ||
                          author.endYear) && (
                          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                            {author.startYear && author.endYear && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs">
                                {author.startYear}-{author.endYear}
                              </span>
                            )}
                            {author.keywords?.map((kw) => (
                              <span
                                key={kw}
                                className="inline-flex items-center px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 text-xs"
                              >
                                {kw}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Warning for too many papers */}
                        {author.totalCount && author.totalCount > 1000 && !author.keywords?.length && (
                          <div className="flex items-center gap-1 mt-1">
                            <AlertTriangle className="w-3 h-3 text-amber-500" />
                            <span className="text-xs text-amber-600">
                              {author.totalCount.toLocaleString()} papers -- add filters to narrow results
                            </span>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                          onClick={() => setFilterModal({ authorId: author.id })}
                          className="p-1.5 text-slate-400 hover:text-brand-600 rounded-lg hover:bg-brand-50 transition-colors"
                          title="Configure Filters"
                        >
                          <Filter className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => startEditing(author.id)}
                          className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors"
                          title="Edit"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => removeAuthor(author.id)}
                          className="p-1.5 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors"
                          title="Remove"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                        {author.papers.length > 0 && (
                          <button
                            onClick={() => toggleExpand(author.id)}
                            className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors"
                          >
                            {author.isExpanded ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </button>
                        )}
                      </div>
                    </>
                  )}
                </div>

                {/* Expanded paper list */}
                {author.isExpanded && author.papers.length > 0 && (() => {
                  const sortedPapers = sortMode === 'impact'
                    ? [...author.papers].sort((a, b) => (b.compositeScore || 0) - (a.compositeScore || 0))
                    : author.papers

                  return (
                  <div className="border-t border-slate-100">
                    <div className="px-4 py-2 bg-slate-50 flex items-center justify-between">
                      <button
                        onClick={() => toggleAllForAuthor(author.id)}
                        className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900 transition-colors"
                      >
                        {allSelected ? (
                          <CheckSquare className="w-3.5 h-3.5 text-brand-600" />
                        ) : (
                          <Square className="w-3.5 h-3.5" />
                        )}
                        {allSelected ? 'Deselect All' : 'Select All'}
                      </button>
                      <div className="flex items-center gap-1.5">
                        <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
                        <select
                          value={sortMode}
                          onChange={(e) => setSortMode(e.target.value as 'default' | 'impact')}
                          className="rounded border border-slate-200 px-2 py-1 text-xs focus:ring-1 focus:ring-brand-500 focus:border-brand-500"
                        >
                          <option value="impact">By Impact</option>
                          <option value="default">Default Order</option>
                        </select>
                      </div>
                    </div>
                    <div className="max-h-80 overflow-auto">
                      <table className="w-full text-sm">
                        <tbody className="divide-y divide-slate-50">
                          {sortedPapers.map((paper) => {
                            const paperId = paper.pmid || paper.doi || paper.url
                            const isSelected = author.selectedPaperIds.has(paperId)
                            const scoreBadgeColor = !paper.compositeScore ? 'bg-slate-100 text-slate-500'
                              : paper.compositeScore >= 70 ? 'bg-emerald-100 text-emerald-700'
                              : paper.compositeScore >= 40 ? 'bg-amber-100 text-amber-700'
                              : 'bg-slate-100 text-slate-600'
                            return (
                              <tr
                                key={paperId}
                                onClick={() => togglePaper(author.id, paperId)}
                                className={`cursor-pointer transition-colors ${
                                  isSelected ? 'bg-brand-50/30' : 'hover:bg-slate-50'
                                }`}
                              >
                                <td className="px-4 py-2 w-8">
                                  {isSelected ? (
                                    <CheckSquare className="w-4 h-4 text-brand-600" />
                                  ) : (
                                    <Square className="w-4 h-4 text-slate-300" />
                                  )}
                                </td>
                                <td className="px-2 py-2">
                                  <p className="text-sm text-slate-900 line-clamp-1">
                                    {paper.title || 'Untitled'}
                                  </p>
                                  {paper.journal && (
                                    <p className="text-xs text-slate-400 mt-0.5">{paper.journal}</p>
                                  )}
                                  {/* Score breakdown (expanded) */}
                                  {expandedScore === paperId && paper.citationCount !== undefined && paper.journal && (() => {
                                    const bd = getScoreBreakdown(paper.citationCount!, getJournalQuality(paper.journal!))
                                    return (
                                      <div
                                        onClick={(e) => e.stopPropagation()}
                                        className="mt-2 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs"
                                      >
                                        <p className="font-semibold text-slate-700 mb-2">Impact Score Breakdown</p>
                                        <div className="space-y-1.5">
                                          <div className="flex items-center justify-between">
                                            <span className="text-slate-500">Citations</span>
                                            <span className="font-mono text-slate-700">{bd.citationCount}</span>
                                          </div>
                                          <div className="flex items-center justify-between">
                                            <span className="text-slate-500">Normalized (0-100)</span>
                                            <span className="font-mono text-slate-700">{bd.normalizedCitations}</span>
                                          </div>
                                          <div className="flex items-center justify-between">
                                            <span className="text-slate-500">Citation component (60%)</span>
                                            <span className="font-mono text-blue-600 font-medium">{bd.citationComponent}</span>
                                          </div>
                                          <div className="border-t border-slate-200 my-1" />
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
                                </td>
                                <td className="px-2 py-2 w-24">
                                  {paper.pmid && (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-xs font-mono">
                                      {paper.pmid}
                                    </span>
                                  )}
                                </td>
                                <td className="px-2 py-2 w-20">
                                  {paper.compositeScore !== undefined && (
                                    <span
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        setExpandedScore(expandedScore === paperId ? null : paperId)
                                      }}
                                      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium cursor-pointer hover:ring-2 hover:ring-offset-1 hover:ring-brand-300 transition-all ${scoreBadgeColor}`}
                                    >
                                      {paper.compositeScore}
                                    </span>
                                  )}
                                </td>
                                <td className="px-2 py-2 w-8">
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      window.api.shell.openExternal(paper.url)
                                    }}
                                    className="p-1 text-slate-400 hover:text-brand-600 transition-colors"
                                  >
                                    <ExternalLink className="w-3.5 h-3.5" />
                                  </button>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  )
                })()}
              </div>
            )
          })}
        </div>
      )}

      {/* Keyword filter modal */}
      {filterModal && filterAuthor && (
        <KeywordFilterModal
          isOpen={true}
          onClose={() => setFilterModal(null)}
          authorName={filterAuthor.name}
          initialKeywords={filterAuthor.keywords}
          initialLogic={filterAuthor.keywordLogic}
          initialStartYear={filterAuthor.startYear}
          initialEndYear={filterAuthor.endYear}
          onApply={(keywords, logic, startYear, endYear) => {
            applyFilters(filterModal.authorId, keywords, logic, startYear, endYear)
            setFilterModal(null)
          }}
        />
      )}
    </div>
  )
}
