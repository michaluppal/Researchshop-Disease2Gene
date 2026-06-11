import { useState } from 'react'
import {
  Copy,
  ExternalLink,
  Eye,
  Calendar,
  Sparkles,
  Check,
  X,
  Send,
  Filter,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react'
import type { QueryFilters } from '../../shared/run-input'

interface QueryConditionFormProps {
  baseQuery: string
  onBaseQueryChange: (query: string) => void
  startYear: string
  endYear: string
  onStartYearChange: (year: string) => void
  onEndYearChange: (year: string) => void
  filters: QueryFilters
  onFiltersChange: (filters: QueryFilters) => void
  constructedQuery: string
  paperCount: number | null
  onPreview: () => void
}

const CURRENT_YEAR = new Date().getFullYear()

const DATE_PRESETS: { label: string; yearsAgo: number | null }[] = [
  { label: 'Last year', yearsAgo: 1 },
  { label: 'Last 5 yrs', yearsAgo: 5 },
  { label: 'Last 10 yrs', yearsAgo: 10 },
  { label: 'All time', yearsAgo: null },
]

// Heuristic validator — cheap client-side parse to explain why paperCount is 0.
function diagnoseQuery(query: string): string | null {
  if (!query.trim()) return null
  let opens = 0, closes = 0, quotes = 0
  for (const ch of query) {
    if (ch === '(') opens++
    else if (ch === ')') closes++
    else if (ch === '"') quotes++
  }
  if (opens !== closes) return `Parentheses mismatch: ${opens} "(" vs ${closes} ")"`
  if (quotes % 2 !== 0) return 'Odd number of quote marks — close your phrases with "'
  if (/\bAND\s*AND\b|\bOR\s*OR\b|\bAND\s*$|\bOR\s*$/i.test(query)) return 'Dangling AND/OR — finish or remove the operator'
  return null
}

// Build a human-readable constraints summary that is appended to the AI prompt.
function filterSummary(filters: QueryFilters, startYear: string, endYear: string): string {
  const parts: string[] = []
  if (filters.openAccessOnly) parts.push('open access only (restrict to PMC full-text papers)')
  if (filters.humansOnly) parts.push('humans only (exclude animal / in vitro studies)')
  if (filters.excludeReviews) parts.push('exclude review articles and meta-analyses')
  if (filters.excludeCaseReports) parts.push('exclude case reports and editorials')
  if (startYear || endYear) {
    const s = startYear || 'any'
    const e = endYear || 'present'
    parts.push(`date range ${s} to ${e}`)
  }
  return parts.length ? `\n\nConstraints:\n- ${parts.join('\n- ')}` : ''
}

function FilterChip({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: () => void
}) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
        checked
          ? 'bg-violet-600 text-white border-violet-600'
          : 'bg-white text-violet-700 border-violet-200 hover:border-violet-400'
      }`}
    >
      {checked && <Check className="w-3 h-3" />}
      {label}
    </button>
  )
}

export default function QueryConditionForm({
  baseQuery,
  onBaseQueryChange,
  startYear,
  endYear,
  onStartYearChange,
  onEndYearChange,
  filters,
  onFiltersChange,
  constructedQuery,
  paperCount,
  onPreview,
}: QueryConditionFormProps) {
  const [copied, setCopied] = useState(false)

  // AI assistant — conversation thread. First turn is build; subsequent turns refine.
  const [input, setInput] = useState('')
  const [building, setBuilding] = useState(false)
  const [turns, setTurns] = useState<{ user: string; query: string; explanation: string }[]>([])
  const [aiError, setAiError] = useState<string | null>(null)

  const latestTurn = turns.length > 0 ? turns[turns.length - 1] : null
  const hasConversation = turns.length > 0

  const copyQuery = () => {
    navigator.clipboard.writeText(constructedQuery)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const testInPubMed = () => {
    const url = `https://pubmed.ncbi.nlm.nih.gov/?term=${encodeURIComponent(constructedQuery)}`
    window.api.shell.openExternal(url)
  }

  const handleSendPrompt = async () => {
    const userMessage = input.trim()
    if (!userMessage || building) return
    setBuilding(true)
    setAiError(null)
    const constraints = filterSummary(filters, startYear, endYear)
    const promptWithConstraints = userMessage + constraints
    const result = hasConversation && latestTurn
      ? await window.api.pubmed.refineQuery({
          previousQuery: latestTurn.query,
          refinementRequest: promptWithConstraints,
        })
      : await window.api.pubmed.buildQuery(promptWithConstraints)
    setBuilding(false)
    if (result.error) {
      setAiError(result.error)
      return
    }
    if (result.query) {
      setTurns((prev) => [
        ...prev,
        { user: userMessage, query: result.query!, explanation: result.explanation || '' },
      ])
      setInput('')
    }
  }

  const applyAiQuery = () => {
    if (!latestTurn) return
    onBaseQueryChange(latestTurn.query)
  }

  const resetAiConversation = () => {
    setTurns([])
    setInput('')
    setAiError(null)
  }

  const applyDatePreset = (yearsAgo: number | null) => {
    if (yearsAgo === null) {
      onStartYearChange('')
      onEndYearChange('')
    } else {
      onStartYearChange(String(CURRENT_YEAR - yearsAgo))
      onEndYearChange('')
    }
  }

  const activePreset: number | null | undefined = (() => {
    if (!startYear && !endYear) return null // All time
    if (endYear) return undefined // custom
    const n = parseInt(startYear, 10)
    if (Number.isNaN(n)) return undefined
    const yearsAgo = CURRENT_YEAR - n
    return DATE_PRESETS.some((p) => p.yearsAgo === yearsAgo) ? yearsAgo : undefined
  })()

  const toggleFilter = (key: keyof QueryFilters) => {
    onFiltersChange({ ...filters, [key]: !filters[key] })
  }

  const queryDiagnostic = diagnoseQuery(constructedQuery)
  const showZeroResultHint = constructedQuery.trim().length > 0 && paperCount === 0

  return (
    <div className="space-y-5">
      {/* AI Query Assistant — filter + date inputs live inside the prompt form */}
      <div className="rounded-xl border border-violet-200 bg-gradient-to-b from-violet-50 to-white p-4 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-violet-600" />
            <h3 className="text-sm font-semibold text-violet-800">AI Query Assistant</h3>
          </div>
          {hasConversation && (
            <button
              onClick={resetAiConversation}
              className="inline-flex items-center gap-1 text-xs text-violet-600 hover:text-violet-800 transition-colors"
              title="Clear this conversation and start fresh"
            >
              <RotateCcw className="w-3 h-3" />
              Start over
            </button>
          )}
        </div>
        <p className="text-xs text-violet-600">
          {hasConversation
            ? 'Refine the query below — e.g. "focus on older studies", "add PARP inhibitors".'
            : 'Describe your research topic. Set filters + date range below; the AI will bake them into the generated query.'}
        </p>

        {/* Filter chips — inline constraints fed into the AI prompt */}
        <div className="flex items-start gap-2 flex-wrap">
          <div className="inline-flex items-center gap-1 text-xs font-medium text-violet-700 pt-1">
            <Filter className="w-3.5 h-3.5" />
            Filters:
          </div>
          <FilterChip label="Open access" checked={filters.openAccessOnly} onChange={() => toggleFilter('openAccessOnly')} />
          <FilterChip label="Humans only" checked={filters.humansOnly} onChange={() => toggleFilter('humansOnly')} />
          <FilterChip label="No reviews" checked={filters.excludeReviews} onChange={() => toggleFilter('excludeReviews')} />
          <FilterChip label="No case reports" checked={filters.excludeCaseReports} onChange={() => toggleFilter('excludeCaseReports')} />
        </div>

        {/* Date range — presets + custom inputs inline */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center gap-1 text-xs font-medium text-violet-700">
            <Calendar className="w-3.5 h-3.5" />
            Date:
          </div>
          {DATE_PRESETS.map((p) => {
            const isActive = p.yearsAgo === activePreset
            return (
              <button
                key={p.label}
                type="button"
                onClick={() => applyDatePreset(p.yearsAgo)}
                className={`px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                  isActive
                    ? 'bg-violet-600 text-white border-violet-600'
                    : 'bg-white text-violet-700 border-violet-200 hover:border-violet-400'
                }`}
              >
                {p.label}
              </button>
            )
          })}
          <input
            type="number"
            value={startYear}
            onChange={(e) => onStartYearChange(e.target.value)}
            placeholder="Start"
            min={1900}
            max={2030}
            className="w-20 rounded-lg border border-violet-200 bg-white px-2 py-1 text-xs transition-colors focus:ring-2 focus:ring-violet-400 focus:border-violet-400"
          />
          <span className="text-xs text-violet-500">to</span>
          <input
            type="number"
            value={endYear}
            onChange={(e) => onEndYearChange(e.target.value)}
            placeholder="End"
            min={1900}
            max={2030}
            className="w-20 rounded-lg border border-violet-200 bg-white px-2 py-1 text-xs transition-colors focus:ring-2 focus:ring-violet-400 focus:border-violet-400"
          />
          {activePreset === undefined && (startYear || endYear) && (
            <span className="text-xs italic text-violet-500">(custom)</span>
          )}
        </div>

        {/* Conversation thread */}
        {turns.length > 0 && (
          <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
            {turns.map((turn, idx) => {
              const isLatest = idx === turns.length - 1
              return (
                <div key={idx} className="space-y-2">
                  <div className="flex items-start gap-2 text-xs text-violet-700">
                    <span className="inline-block w-1 h-1 rounded-full bg-violet-400 mt-2 flex-shrink-0" />
                    <p className="flex-1 italic">
                      {idx === 0 ? 'You asked:' : 'You refined:'}{' '}
                      <span className="not-italic">“{turn.user}”</span>
                    </p>
                  </div>
                  <div className={`rounded-lg border p-3 ${isLatest ? 'border-violet-300 bg-white' : 'border-violet-100 bg-violet-50/50'}`}>
                    {turn.explanation && (
                      <p className="text-xs text-violet-600 mb-2">{turn.explanation}</p>
                    )}
                    <pre className="text-xs font-mono text-slate-800 whitespace-pre-wrap break-all">{turn.query}</pre>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* AI error */}
        {aiError && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            <X className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span className="flex-1">{aiError}</span>
            <button onClick={() => setAiError(null)} className="text-red-400 hover:text-red-600 transition-colors flex-shrink-0">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Input row */}
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendPrompt() } }}
            placeholder={
              hasConversation
                ? 'Refine: add PARP inhibitors, focus on older studies…'
                : 'e.g. BRCA1 mutations in breast cancer prognosis'
            }
            disabled={building}
            className="flex-1 rounded-lg border border-violet-200 bg-white px-3 py-2.5 text-sm placeholder:text-violet-300 transition-colors duration-150 focus:ring-2 focus:ring-violet-400 focus:border-violet-400 disabled:opacity-50"
          />
          <button
            onClick={handleSendPrompt}
            disabled={!input.trim() || building}
            className="inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium text-white bg-violet-600 rounded-lg hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {building ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            {building
              ? hasConversation ? 'Refining…' : 'Building…'
              : hasConversation ? 'Refine' : 'Build Query'}
          </button>
        </div>

        {/* Apply latest query */}
        {latestTurn && (
          <div className="flex items-center justify-between gap-2 pt-1">
            <p className="text-xs text-violet-500 italic">
              Review the latest query — verify it matches your research scope before applying.
            </p>
            <button
              onClick={applyAiQuery}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-violet-600 rounded-lg hover:bg-violet-700 transition-colors flex-shrink-0"
            >
              <Check className="w-4 h-4" />
              Use This Query
            </button>
          </div>
        )}
      </div>

      {/* Editable query — the single source of truth for what gets searched */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-slate-700">Query</label>
          {paperCount !== null && constructedQuery && (
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
              paperCount === 0
                ? 'bg-amber-100 text-amber-700'
                : 'bg-brand-100 text-brand-700'
            }`}>
              {paperCount.toLocaleString()} papers found
            </span>
          )}
        </div>
        <textarea
          value={baseQuery}
          onChange={(e) => onBaseQueryChange(e.target.value)}
          placeholder='Use the AI assistant above, or type a PubMed query directly — e.g. ("BRCA1"[Gene]) AND ("breast cancer"[tiab])'
          rows={4}
          className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-mono transition-colors focus:ring-2 focus:ring-brand-500 focus:border-brand-500 focus:bg-white resize-y"
        />
      </div>

      {/* Validation hint */}
      {queryDiagnostic && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span className="flex-1">{queryDiagnostic}</span>
        </div>
      )}
      {!queryDiagnostic && showZeroResultHint && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <div className="flex-1 space-y-1">
            <p className="font-medium">No papers match this query.</p>
            <p className="text-xs text-amber-700">
              Common causes: terms too specific, date range too narrow, or a MeSH term that isn't
              indexed. Try asking the AI to broaden the query, or "Test in PubMed" to diagnose.
            </p>
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={copyQuery}
          disabled={!constructedQuery}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-600 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Copy className="w-4 h-4" />
          {copied ? 'Copied!' : 'Copy Query'}
        </button>
        <button
          onClick={testInPubMed}
          disabled={!constructedQuery}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-600 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <ExternalLink className="w-4 h-4" />
          Test in PubMed
        </button>
        <button
          onClick={onPreview}
          disabled={!constructedQuery}
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors ml-auto"
        >
          <Eye className="w-4 h-4" />
          Preview &amp; Select
        </button>
      </div>
    </div>
  )
}
