import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Play, Settings, FileText, Search, Users, AlertCircle } from 'lucide-react'
import StartScreen from '../components/StartScreen'
import QueryConditionForm from '../components/QueryConditionForm'
import TopicResultsModal from '../components/TopicResultsModal'
import SmartInput from '../components/SmartInput'
import AuthorListInput from '../components/AuthorListInput'
import ColumnEditor from '../components/ColumnEditor'
import FinalReviewModal from '../components/FinalReviewModal'
import { usePipeline } from '../hooks/usePipeline'

interface PaperItem {
  title?: string
  pmid?: string
  doi?: string
  pmc?: string
  url: string
  source?: string
}

interface ProtocolConfig {
  topic: boolean
  papers: boolean
  authors: boolean
}

interface Condition {
  operator: string
  field: string
  term: string
}

const DEFAULT_COLUMNS: Record<string, string> = {
  'Disease Association': 'The disease or medical condition associated with this gene/variant',
  'Key Finding': 'Main research finding about this gene from the paper',
  'Statistical Evidence': 'P-values, odds ratios, or other statistical measures',
  'Conclusion': 'Author conclusions specifically about this gene or variant',
}

export default function QueryBuilder() {
  const navigate = useNavigate()
  const { start: startPipeline } = usePipeline()

  // Protocol selection
  const [activeModules, setActiveModules] = useState<ProtocolConfig | null>(null)
  const [protocolName, setProtocolName] = useState('')

  // Topic search state
  const [conditions, setConditions] = useState<Condition[]>([
    { operator: '', field: 'tiab', term: '' },
  ])
  const [startYear, setStartYear] = useState('')
  const [endYear, setEndYear] = useState('')
  const [rawMode, setRawMode] = useState(false)
  const [rawQuery, setRawQuery] = useState('')
  const [paperCount, setPaperCount] = useState<number | null>(null)
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

  // Construct query from conditions (or return raw query when in raw mode)
  const constructQuery = useCallback(() => {
    if (rawMode) return rawQuery
    let query = ''
    conditions.forEach((cond, i) => {
      if (!cond.term.trim()) return
      const term = cond.term.includes(' ') ? `"${cond.term}"` : cond.term
      const field = cond.field ? `[${cond.field}]` : ''
      const part = `${term}${field}`
      if (i === 0 || !query) {
        query = part
      } else {
        query += ` ${cond.operator} ${part}`
      }
    })
    if (startYear || endYear) {
      const s = startYear || '1900'
      const e = endYear || '3000'
      query = query ? `(${query}) AND ${s}:${e}[dp]` : `${s}:${e}[dp]`
    }
    return query
  }, [conditions, startYear, endYear, rawMode, rawQuery])

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
    setTopicPapers(papers.map((p) => ({ ...p, source: 'topic' })))
  }

  const handleSpecificPapersChange = (pmids: string[], papers: PaperItem[]) => {
    setSpecificPmids(pmids)
    setSpecificPapers(papers.map((p) => ({ ...p, source: 'specific' })))
  }

  const handleAuthorPapersChange = (papers: PaperItem[]) => {
    setAuthorPapers(papers.map((p) => ({ ...p, source: 'author' })))
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

  const handleRunPipeline = async () => {
    setLoading(true)
    setError(null)

    // Collect all unique PMIDs
    const allPmids = Array.from(
      new Set([
        ...topicPapers.map((p) => p.pmid).filter(Boolean),
        ...specificPapers.map((p) => p.pmid).filter(Boolean),
        ...authorPapers.map((p) => p.pmid).filter(Boolean),
      ])
    ) as string[]

    const query = activeModules?.topic ? constructQuery() : ''

    const result = await startPipeline({
      query,
      pmids: allPmids,
      authors: [],
      columns,
      topN: allPmids.length || 9999,
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
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setActiveModules(null)}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Query Builder</h1>
            <p className="text-sm text-slate-500">{protocolName}</p>
          </div>
        </div>

        {totalPapers > 0 && (
          <button
            onClick={() => setIsFinalReviewOpen(true)}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 transition-colors shadow-sm"
          >
            <Play className="w-4 h-4" />
            Review & Run ({totalPapers})
          </button>
        )}
      </div>

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
              conditions={conditions}
              onChange={setConditions}
              startYear={startYear}
              endYear={endYear}
              onStartYearChange={setStartYear}
              onEndYearChange={setEndYear}
              constructedQuery={constructQuery()}
              paperCount={paperCount}
              onPreview={() => setIsTopicPreviewOpen(true)}
              rawMode={rawMode}
              rawQuery={rawQuery}
              onRawModeChange={(val) => { setRawMode(val); if (!val) setRawQuery('') }}
              onRawQueryChange={setRawQuery}
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

        {/* Bottom action */}
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
            ? `Review & Run Analysis (${totalPapers} paper${totalPapers !== 1 ? 's' : ''})`
            : 'Select papers above to begin'}
        </button>
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
        onRunPipeline={handleRunPipeline}
        loading={loading}
      />
    </div>
  )
}
