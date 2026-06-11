import { useState, useCallback, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Play, Settings, FileText, Search, Users, AlertCircle } from 'lucide-react'
import StartScreen from '../components/StartScreen'
import QueryConditionForm from '../components/QueryConditionForm'
import TopicResultsModal from '../components/TopicResultsModal'
import SmartInput from '../components/SmartInput'
import AuthorListInput from '../components/AuthorListInput'
import ColumnEditor from '../components/ColumnEditor'
import FinalReviewModal from '../components/FinalReviewModal'
import { usePipeline } from '../hooks/usePipeline'
import type {
  ProtocolConfig,
  QueryFilters,
  RunInputMode,
  RunInputPaper,
  RunInputSnapshot,
} from '../../shared/run-input'

type PaperItem = RunInputPaper
type RestoreMode = 'review' | 'clone'

interface RestorableJob {
  id: string
  query: string
  columns: string
  run_input: string | null
}

const DEFAULT_FILTERS: QueryFilters = {
  openAccessOnly: false,
  humansOnly: false,
  excludeReviews: false,
  excludeCaseReports: false,
}

const DEFAULT_COLUMNS: Record<string, string> = {
  'Disease Association': 'The disease or medical condition associated with this gene/variant',
  'Key Finding': 'Main research finding about this gene from the paper',
  'Statistical Evidence': 'P-values, odds ratios, or other statistical measures',
  'Conclusion': 'Author conclusions specifically about this gene or variant',
}

function parseRunInputSnapshot(raw: string | null): RunInputSnapshot | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<RunInputSnapshot>
    if (
      parsed.schemaVersion === 1 &&
      parsed.activeModules &&
      typeof parsed.protocolName === 'string'
    ) {
      return parsed as RunInputSnapshot
    }
  } catch {
    return null
  }
  return null
}

function parseJobColumns(raw: string): Record<string, string> {
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, string>
    }
  } catch {
    // fall through to defaults
  }
  return DEFAULT_COLUMNS
}

function paperKey(paper: PaperItem): string {
  return paper.pmid || paper.doi || paper.pmc || paper.url
}

function mergePapers(existing: PaperItem[], incoming: PaperItem[]): PaperItem[] {
  const merged = new Map<string, PaperItem>()
  for (const paper of existing) {
    merged.set(paperKey(paper), paper)
  }
  for (const paper of incoming) {
    merged.set(paperKey(paper), paper)
  }
  return Array.from(merged.values())
}

export default function QueryBuilder() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { start: startPipeline } = usePipeline()
  const restoreJobId = searchParams.get('fromJob') || ''
  const requestedRestoreMode: RestoreMode = searchParams.get('mode') === 'clone' ? 'clone' : 'review'

  // Protocol selection
  const [activeModules, setActiveModules] = useState<ProtocolConfig | null>(null)
  const [protocolName, setProtocolName] = useState('')

  // Topic search state — single editable query string + filter toggles + date range
  const [baseQuery, setBaseQuery] = useState('')
  const [startYear, setStartYear] = useState('')
  const [endYear, setEndYear] = useState('')
  const [paperCount, setPaperCount] = useState<number | null>(null)
  const [filters, setFilters] = useState<QueryFilters>(DEFAULT_FILTERS)
  const [isTopicPreviewOpen, setIsTopicPreviewOpen] = useState(false)
  const [topicPapers, setTopicPapers] = useState<PaperItem[]>([])

  // Specific papers state
  const [specificPmids, setSpecificPmids] = useState<string[]>([])
  const [specificPapers, setSpecificPapers] = useState<PaperItem[]>([])

  // Author state
  const [authorPapers, setAuthorPapers] = useState<PaperItem[]>([])

  // Columns
  const [columns, setColumns] = useState<Record<string, string>>(DEFAULT_COLUMNS)

  // Final review
  const [isFinalReviewOpen, setIsFinalReviewOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [restoredJob, setRestoredJob] = useState<RestorableJob | null>(null)
  const [restoreMode, setRestoreMode] = useState<RestoreMode | null>(null)
  const [originalPmids, setOriginalPmids] = useState<string[]>([])

  // Compose the final query: baseQuery (user-edited) + filter toggles + date range.
  const constructQuery = useCallback(() => {
    let query = baseQuery.trim()

    const andClauses: string[] = []
    const notClauses: string[] = []
    if (filters.openAccessOnly) andClauses.push('"loattrfull text"[sb]')
    if (filters.humansOnly) andClauses.push('"humans"[MeSH Terms]')
    if (filters.excludeReviews) {
      notClauses.push('"review"[Publication Type]', '"meta-analysis"[Publication Type]')
    }
    if (filters.excludeCaseReports) {
      notClauses.push('"case reports"[Publication Type]', '"editorial"[Publication Type]')
    }
    if (query && (andClauses.length || notClauses.length)) {
      let wrapped = `(${query})`
      for (const c of andClauses) wrapped += ` AND ${c}`
      if (notClauses.length) wrapped += ` NOT (${notClauses.join(' OR ')})`
      query = wrapped
    }

    if (startYear || endYear) {
      const s = startYear || '1900'
      const e = endYear || '3000'
      query = query ? `(${query}) AND ${s}:${e}[dp]` : `${s}:${e}[dp]`
    }
    return query
  }, [baseQuery, startYear, endYear, filters])

  // Debounced paper count fetch
  useEffect(() => {
    if (!activeModules?.topic) return
    const query = constructQuery()
    if (!query) {
      setPaperCount(null)
      return
    }
    const timer = setTimeout(async () => {
      const result = await window.api.pubmed.count(query)
      setPaperCount(result.count)
    }, 1000)
    return () => clearTimeout(timer)
  }, [constructQuery, activeModules])

  const handleStartProtocol = (config: ProtocolConfig, name: string) => {
    setActiveModules(config)
    setProtocolName(name)
  }

  const handleTopicSelect = (papers: PaperItem[]) => {
    const next = papers.map((p) => ({ ...p, source: 'topic' }))
    setTopicPapers((prev) => (restoreMode === 'review' ? mergePapers(prev, next) : next))
  }

  const handleSpecificPapersChange = (pmids: string[], papers: PaperItem[]) => {
    const next = papers.map((p) => ({ ...p, source: 'specific' }))
    setSpecificPmids((prev) =>
      restoreMode === 'review' ? Array.from(new Set([...prev, ...pmids])) : pmids
    )
    setSpecificPapers((prev) => (restoreMode === 'review' ? mergePapers(prev, next) : next))
  }

  const handleAuthorPapersChange = (papers: PaperItem[]) => {
    const next = papers.map((p) => ({ ...p, source: 'author' }))
    setAuthorPapers((prev) => (restoreMode === 'review' ? mergePapers(prev, next) : next))
  }

  const removeTopicPaper = (pmid: string) => {
    setTopicPapers((prev) => prev.filter((p) => p.pmid !== pmid))
  }
  const removeAuthorPaper = (pmid: string) => {
    setAuthorPapers((prev) => prev.filter((p) => p.pmid !== pmid))
  }
  const removeSpecificPaper = (pmid: string) => {
    setSpecificPapers((prev) => prev.filter((p) => p.pmid !== pmid))
    setSpecificPmids((prev) => prev.filter((id) => id !== pmid))
  }

  const totalPapers = topicPapers.length + specificPapers.length + authorPapers.length
  const selectedPmids = useMemo(
    () =>
      Array.from(
        new Set([
          ...topicPapers.map((p) => p.pmid).filter(Boolean),
          ...specificPapers.map((p) => p.pmid).filter(Boolean),
          ...authorPapers.map((p) => p.pmid).filter(Boolean),
        ])
      ) as string[],
    [topicPapers, specificPapers, authorPapers]
  )
  const originalPmidSet = useMemo(() => new Set(originalPmids), [originalPmids])
  const addedPmids = useMemo(
    () => selectedPmids.filter((pmid) => !originalPmidSet.has(pmid)),
    [selectedPmids, originalPmidSet]
  )

  useEffect(() => {
    if (!restoreJobId) return
    let cancelled = false

    async function restoreFromJob() {
      setRestoreError(null)
      const job = await window.api.history.get(restoreJobId)
      if (cancelled) return
      if (!job) {
        setRestoreError('Could not find the selected history run.')
        return
      }

      const snapshot = parseRunInputSnapshot(job.run_input)
      setRestoredJob({
        id: job.id,
        query: job.query,
        columns: job.columns,
        run_input: job.run_input,
      })
      setRestoreMode(requestedRestoreMode)

      if (!snapshot) {
        const fallbackModules = { topic: !!job.query, papers: !job.query, authors: false }
        setActiveModules(fallbackModules)
        setProtocolName('Restored Query')
        setBaseQuery(job.query || '')
        setStartYear('')
        setEndYear('')
        setFilters(DEFAULT_FILTERS)
        setTopicPapers([])
        setSpecificPmids([])
        setSpecificPapers([])
        setAuthorPapers([])
        setColumns(parseJobColumns(job.columns))
        setOriginalPmids([])
        if (requestedRestoreMode === 'review') {
          setRestoreError('This older run does not include a saved study-selection snapshot.')
        }
        return
      }

      setActiveModules(snapshot.activeModules)
      setProtocolName(
        requestedRestoreMode === 'clone' ? `${snapshot.protocolName} Copy` : snapshot.protocolName
      )
      setBaseQuery(snapshot.baseQuery || snapshot.constructedQuery || job.query || '')
      setStartYear(snapshot.startYear || '')
      setEndYear(snapshot.endYear || '')
      setFilters({ ...DEFAULT_FILTERS, ...(snapshot.filters || {}) })
      setColumns(Object.keys(snapshot.columns || {}).length ? snapshot.columns : parseJobColumns(job.columns))
      setOriginalPmids(snapshot.selectedPmids || [])

      if (requestedRestoreMode === 'clone') {
        setTopicPapers([])
        setSpecificPmids([])
        setSpecificPapers([])
        setAuthorPapers([])
      } else {
        setTopicPapers((snapshot.topicPapers || []).map((p) => ({ ...p, source: 'topic' })))
        setSpecificPmids(snapshot.specificPmids || [])
        setSpecificPapers((snapshot.specificPapers || []).map((p) => ({ ...p, source: 'specific' })))
        setAuthorPapers((snapshot.authorPapers || []).map((p) => ({ ...p, source: 'author' })))
      }
    }

    restoreFromJob().catch((err) => {
      if (!cancelled) setRestoreError(String(err))
    })
    return () => {
      cancelled = true
    }
  }, [restoreJobId, requestedRestoreMode])

  const buildRunInput = (
    runMode: RunInputMode,
    runPmids: string[],
    allSelectedPmids: string[]
  ): RunInputSnapshot => ({
    schemaVersion: 1,
    protocolName,
    activeModules: activeModules || { topic: false, papers: false, authors: false },
    baseQuery,
    constructedQuery: activeModules?.topic ? constructQuery() : '',
    startYear,
    endYear,
    filters,
    topicPapers,
    specificPmids,
    specificPapers,
    authorPapers,
    columns,
    selectedPmids: allSelectedPmids,
    runPmids,
    runMode,
    sourceJobId: restoredJob?.id,
  })

  const handleRunPipeline = async (requestedRunMode: RunInputMode = 'standard') => {
    setLoading(true)
    setError(null)

    const runMode: RunInputMode =
      requestedRunMode === 'standard' && restoreMode === 'clone'
        ? 'new_from_query'
        : requestedRunMode === 'standard' && restoreMode === 'review'
          ? 'review_all'
          : requestedRunMode
    const runPmids = runMode === 'added_only' ? addedPmids : selectedPmids

    if (runMode === 'added_only' && runPmids.length === 0) {
      setLoading(false)
      setError('No newly added studies are selected.')
      return
    }

    const query = activeModules?.topic ? constructQuery() : ''

    const result = await startPipeline({
      query,
      pmids: runPmids,
      authors: [],
      columns,
      topN: runPmids.length || 9999,
      runInput: buildRunInput(runMode, runPmids, selectedPmids),
    })

    setLoading(false)
    if (result.error) {
      setError(result.error)
    } else {
      setIsFinalReviewOpen(false)
      navigate('/pipeline')
    }
  }

  // If no protocol selected, show StartScreen
  if (!activeModules) {
    return <StartScreen onStartProtocol={handleStartProtocol} />
  }

  // Protocol selected, show the builder
  return (
    <div className="max-w-3xl mx-auto p-8">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            onClick={() => setActiveModules(null)}
            className="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            title="Back to protocol selection"
            aria-label="Back to protocol selection"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="min-w-0">
            <h1 className="text-2xl font-bold leading-tight text-slate-900">Query Builder</h1>
            <p className="truncate text-sm text-slate-500">{protocolName}</p>
          </div>
        </div>

        {totalPapers > 0 && (
          <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-2">
            {restoreMode === 'review' && (
              <button
                onClick={() => handleRunPipeline('added_only')}
                disabled={addedPmids.length === 0 || loading}
                className="inline-flex h-10 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Play className="w-4 h-4" />
                Run Added Only ({addedPmids.length})
              </button>
            )}
            <button
              onClick={() => setIsFinalReviewOpen(true)}
              className="inline-flex h-10 items-center gap-2 whitespace-nowrap rounded-lg bg-brand-600 px-4 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700"
            >
              <Play className="w-4 h-4" />
              {restoreMode === 'review' ? `Review & Run All (${totalPapers})` : `Review & Run (${totalPapers})`}
            </button>
          </div>
        )}
      </div>

      {restoredJob && (
        <div className="mb-6 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                {restoreMode === 'clone' ? 'Rerun same query' : 'Restored study selection'}
              </p>
              <p className="mt-1 truncate text-sm font-medium text-slate-700">
                {restoredJob.query || 'PMID-only run'}
              </p>
              {restoreMode === 'review' && (
                <p className="mt-1 text-xs text-slate-500">
                  {originalPmids.length} original selected paper{originalPmids.length !== 1 ? 's' : ''};
                  {' '}{addedPmids.length} newly added.
                </p>
              )}
            </div>
            <button
              onClick={() => navigate('/history')}
              className="inline-flex h-8 flex-shrink-0 items-center rounded-md border border-slate-200 px-3 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900"
            >
              History
            </button>
          </div>
        </div>
      )}

      <div className="space-y-8">
        {/* Topic Search Module */}
        {activeModules.topic && (
          <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-1 flex items-center gap-2">
              <Search className="w-5 h-5 text-brand-600" /> Topic Search
            </h2>
            <p className="text-sm text-slate-400 mb-5">
              Build a PubMed query using Boolean operators to find relevant papers
            </p>

            {topicPapers.length > 0 && (
              <div className="mb-4 p-3 bg-brand-50 border border-brand-200 rounded-lg text-sm text-brand-700">
                {topicPapers.length} papers selected from topic search
              </div>
            )}

            <QueryConditionForm
              baseQuery={baseQuery}
              onBaseQueryChange={setBaseQuery}
              startYear={startYear}
              endYear={endYear}
              onStartYearChange={setStartYear}
              onEndYearChange={setEndYear}
              filters={filters}
              onFiltersChange={setFilters}
              constructedQuery={constructQuery()}
              paperCount={paperCount}
              onPreview={() => setIsTopicPreviewOpen(true)}
            />
          </section>
        )}

        {/* Specific Papers Module */}
        {activeModules.papers && (
          <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-1 flex items-center gap-2">
              <FileText className="w-5 h-5 text-purple-600" /> Specific Papers
            </h2>
            <p className="text-sm text-slate-400 mb-5">Paste PMIDs, DOIs, or PMC IDs to add individual papers directly</p>
            {specificPapers.length > 0 && (
              <div className="mb-4 p-3 bg-violet-50 border border-violet-200 rounded-lg text-sm text-violet-700">
                {specificPapers.length} specific paper{specificPapers.length !== 1 ? 's' : ''} selected
              </div>
            )}
            <SmartInput onPapersChange={handleSpecificPapersChange} />
          </section>
        )}

        {/* Authors Module */}
        {activeModules.authors && (
          <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-1 flex items-center gap-2">
              <Users className="w-5 h-5 text-emerald-600" /> Authors
            </h2>
            <p className="text-sm text-slate-400 mb-5">Search for papers by author name to include their publications</p>
            {authorPapers.length > 0 && (
              <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-700">
                {authorPapers.length} author paper{authorPapers.length !== 1 ? 's' : ''} selected
              </div>
            )}
            <AuthorListInput onPapersChange={handleAuthorPapersChange} />
          </section>
        )}

        {/* Column Configuration */}
        <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
          <h2 className="text-lg font-semibold text-slate-900 mb-1 flex items-center gap-2">
            <Settings className="w-5 h-5 text-slate-600" /> Extraction Columns
          </h2>
          <p className="text-sm text-slate-400 mb-5">
            Customize the data columns extracted for each gene. Add, remove, or edit column definitions.
          </p>
          <ColumnEditor columns={columns} onChange={setColumns} />
        </section>

        {/* Error display */}
        {error && (
          <div className="p-3 rounded-lg bg-red-50 text-red-600 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {restoreError && (
          <div className="p-3 rounded-lg bg-amber-50 text-amber-700 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {restoreError}
          </div>
        )}

        {/* Bottom action */}
        <div className="space-y-2">
          {restoreMode === 'review' && (
            <button
              onClick={() => handleRunPipeline('added_only')}
              disabled={addedPmids.length === 0 || loading}
              className="w-full py-3 rounded-xl font-semibold text-base inline-flex items-center justify-center gap-2 transition-colors border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed"
            >
              <Play className="w-4 h-4" />
              Run Added Studies Only ({addedPmids.length})
            </button>
          )}
          <button
            onClick={() => setIsFinalReviewOpen(true)}
            disabled={totalPapers === 0}
            className={`w-full py-3.5 rounded-xl font-semibold text-base inline-flex items-center justify-center gap-2 transition-all shadow-md ${
              totalPapers > 0
                ? 'bg-brand-600 text-white hover:bg-brand-700 hover:shadow-lg active:bg-brand-800'
                : 'bg-slate-100 text-slate-400 cursor-not-allowed shadow-none'
            }`}
          >
            <Play className="w-4 h-4" />
            {totalPapers > 0
              ? `${restoreMode === 'review' ? 'Review & Run All' : 'Review & Run Analysis'} (${totalPapers} paper${totalPapers !== 1 ? 's' : ''})`
              : 'Select papers above to begin'}
          </button>
        </div>
      </div>

      {/* Topic Results Modal */}
      <TopicResultsModal
        isOpen={isTopicPreviewOpen}
        onClose={() => setIsTopicPreviewOpen(false)}
        query={constructQuery()}
        onSelectPapers={handleTopicSelect}
      />

      {/* Final Review Modal */}
      <FinalReviewModal
        isOpen={isFinalReviewOpen}
        onClose={() => setIsFinalReviewOpen(false)}
        topicPapers={topicPapers}
        authorPapers={authorPapers}
        specificPapers={specificPapers}
        onRemoveTopicPaper={removeTopicPaper}
        onRemoveAuthorPaper={removeAuthorPaper}
        onRemoveSpecificPaper={removeSpecificPaper}
        onRunPipeline={() => handleRunPipeline()}
        loading={loading}
      />
    </div>
  )
}
