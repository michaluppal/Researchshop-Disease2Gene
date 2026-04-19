import { useState } from 'react'
import { Plus, Trash2, Copy, ExternalLink, Eye, Code, Calendar, Sparkles, Check, X, Send, Filter, AlertTriangle, RotateCcw } from 'lucide-react'
import type { QueryFilters } from '../pages/QueryBuilder'

interface Condition {
  operator: string
  field: string
  term: string
}

interface QueryConditionFormProps {
  conditions: Condition[]
  onChange: (conditions: Condition[]) => void
  startYear: string
  endYear: string
  onStartYearChange: (year: string) => void
  onEndYearChange: (year: string) => void
  filters: QueryFilters
  onFiltersChange: (filters: QueryFilters) => void
  constructedQuery: string
  paperCount: number | null
  onPreview: () => void
  rawMode: boolean
  rawQuery: string
  onRawModeChange: (rawMode: boolean) => void
  onRawQueryChange: (rawQuery: string) => void
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

const OPERATORS = ['AND', 'OR', 'NOT']
const FIELDS = [
  { value: '[Title/Abstract]', label: 'Title/Abstract' },
  { value: '[Title]', label: 'Title' },
  { value: '[MeSH Terms]', label: 'MeSH Terms' },
  { value: '', label: 'All Fields' },
]

function FilterToggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string
  hint: string
  checked: boolean
  onChange: () => void
}) {
  return (
    <label
      className={`flex items-start gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors ${
        checked
          ? 'bg-brand-50 border-brand-300'
          : 'bg-white border-slate-200 hover:border-slate-300'
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="mt-0.5 w-4 h-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500 flex-shrink-0"
      />
      <div className="flex-1 min-w-0">
        <div className={`text-sm font-medium ${checked ? 'text-brand-700' : 'text-slate-700'}`}>
          {label}
        </div>
        <div className={`text-xs ${checked ? 'text-brand-600' : 'text-slate-500'}`}>
          {hint}
        </div>
      </div>
    </label>
  )
}

export default function QueryConditionForm({
  conditions,
  onChange,
  startYear,
  endYear,
  onStartYearChange,
  onEndYearChange,
  filters,
  onFiltersChange,
  constructedQuery,
  paperCount,
  onPreview,
  rawMode,
  rawQuery,
  onRawModeChange,
  onRawQueryChange,
}: QueryConditionFormProps) {
  const [copied, setCopied] = useState(false)

  // AI query builder — conversation thread. First turn is build; subsequent turns refine.
  const [input, setInput] = useState('')
  const [building, setBuilding] = useState(false)
  const [turns, setTurns] = useState<{ user: string; query: string; explanation: string }[]>([])
  const [aiError, setAiError] = useState<string | null>(null)

  const latestTurn = turns.length > 0 ? turns[turns.length - 1] : null
  const hasConversation = turns.length > 0

  const updateCondition = (index: number, field: keyof Condition, value: string) => {
    const updated = conditions.map((c, i) => (i === index ? { ...c, [field]: value } : c))
    onChange(updated)
  }

  const removeCondition = (index: number) => {
    onChange(conditions.filter((_, i) => i !== index))
  }

  const addCondition = () => {
    onChange([...conditions, { operator: 'AND', field: '[Title/Abstract]', term: '' }])
  }

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
    const result = hasConversation && latestTurn
      ? await window.api.pubmed.refineQuery({
          previousQuery: latestTurn.query,
          refinementRequest: userMessage,
        })
      : await window.api.pubmed.buildQuery(userMessage)
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
    onRawQueryChange(latestTurn.query)
    onRawModeChange(true)
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

  // Detect which preset (if any) the current startYear/endYear matches
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
  const showZeroResultHint =
    constructedQuery.trim().length > 0 && paperCount === 0

  return (
    <div className="space-y-5">
      {/* AI Query Builder — conversational refinement */}
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
            ? 'Refine the query below — e.g. "focus on last 5 years", "exclude reviews", "add PARP inhibitors".'
            : 'Describe your research topic in plain English and AI will build an optimized PubMed query for you.'}
        </p>

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
                      {idx === 0 ? 'You asked:' : 'You refined:'} <span className="not-italic">“{turn.user}”</span>
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
                ? 'Refine: focus on humans, last 5 years, exclude reviews…'
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

      {/* Divider */}
      <div className="flex items-center gap-3">
        <div className="flex-1 border-t border-slate-200" />
        <span className="text-xs text-slate-400 font-medium">or build manually</span>
        <div className="flex-1 border-t border-slate-200" />
      </div>

      {/* Mode toggle */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700">Manual Query Builder</h3>
        <button
          onClick={() => {
            if (!rawMode) onRawQueryChange(constructedQuery)
            onRawModeChange(!rawMode)
          }}
          className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 transition-colors"
        >
          {rawMode ? <Eye className="w-3.5 h-3.5" /> : <Code className="w-3.5 h-3.5" />}
          {rawMode ? 'Visual Builder' : 'Raw Query'}
        </button>
      </div>

      {rawMode ? (
        <textarea
          value={rawQuery}
          onChange={(e) => onRawQueryChange(e.target.value)}
          rows={4}
          placeholder='e.g. "BRCA1"[Gene] AND "breast cancer" AND "pathogenic variant"'
          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-mono transition-colors duration-150 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 focus:bg-white resize-none"
        />
      ) : (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-2">
          {conditions.map((cond, i) => (
            <div key={i} className="flex items-center gap-2">
              {/* Operator (hidden for first row) */}
              <div className="w-20 flex-shrink-0">
                {i === 0 ? (
                  <span className="text-xs text-slate-400 pl-2">WHERE</span>
                ) : (
                  <select
                    value={cond.operator}
                    onChange={(e) => updateCondition(i, 'operator', e.target.value)}
                    className="w-full rounded-lg border border-gray-200 bg-white px-2 py-2 text-sm transition-colors duration-150 focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
                  >
                    {OPERATORS.map((op) => (
                      <option key={op} value={op}>
                        {op}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Search term */}
              <input
                value={cond.term}
                onChange={(e) => updateCondition(i, 'term', e.target.value)}
                placeholder="Search term..."
                className={`flex-1 rounded-lg border bg-white px-3 py-2 text-sm transition-colors duration-150 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 ${
                  cond.term.trim() === '' ? 'border-red-300' : 'border-gray-200'
                }`}
              />

              {/* Field selector */}
              <select
                value={cond.field}
                onChange={(e) => updateCondition(i, 'field', e.target.value)}
                className="w-40 flex-shrink-0 rounded-lg border border-gray-200 bg-white px-2 py-2 text-sm transition-colors duration-150 focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              >
                {FIELDS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>

              {/* Remove */}
              <button
                onClick={() => removeCondition(i)}
                disabled={conditions.length <= 1}
                className="p-2 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-150"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
          {conditions.some((c) => c.term.trim() === '') && (
            <p className="text-xs text-red-500 mt-1">All search terms are required</p>
          )}

          <button
            onClick={addCondition}
            className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700 font-medium transition-colors duration-150 mt-1"
          >
            <Plus className="w-4 h-4" />
            Add Condition
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
        <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 mb-3">
          <Filter className="w-4 h-4 text-gray-400" />
          Filters
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <FilterToggle
            label="Open access only"
            hint="Full text available via PMC"
            checked={filters.openAccessOnly}
            onChange={() => toggleFilter('openAccessOnly')}
          />
          <FilterToggle
            label="Humans only"
            hint="Exclude animal / in vitro studies"
            checked={filters.humansOnly}
            onChange={() => toggleFilter('humansOnly')}
          />
          <FilterToggle
            label="Exclude reviews"
            hint="Skip review + meta-analysis papers"
            checked={filters.excludeReviews}
            onChange={() => toggleFilter('excludeReviews')}
          />
          <FilterToggle
            label="Exclude case reports"
            hint="Skip case reports + editorials"
            checked={filters.excludeCaseReports}
            onChange={() => toggleFilter('excludeCaseReports')}
          />
        </div>
      </div>

      {/* Date range */}
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
        <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 mb-2">
          <Calendar className="w-4 h-4 text-gray-400" />
          Date Range
        </label>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {DATE_PRESETS.map((p) => {
            const isActive = p.yearsAgo === activePreset
            return (
              <button
                key={p.label}
                onClick={() => applyDatePreset(p.yearsAgo)}
                className={`px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                  isActive
                    ? 'bg-brand-600 text-white border-brand-600'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-brand-400 hover:text-brand-600'
                }`}
              >
                {p.label}
              </button>
            )
          })}
          {activePreset === undefined && (
            <span className="inline-flex items-center px-2.5 py-1 text-xs font-medium rounded-full border border-slate-200 bg-slate-100 text-slate-500">
              Custom
            </span>
          )}
        </div>
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">Start Year</label>
            <input
              type="number"
              value={startYear}
              onChange={(e) => onStartYearChange(e.target.value)}
              placeholder="e.g. 2015"
              min={1900}
              max={2030}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm transition-colors duration-150 focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">End Year</label>
            <input
              type="number"
              value={endYear}
              onChange={(e) => onEndYearChange(e.target.value)}
              placeholder="e.g. 2024"
              min={1900}
              max={2030}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm transition-colors duration-150 focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
            />
          </div>
        </div>
      </div>

      {/* Query preview */}
      {constructedQuery && (
        <div className="bg-slate-900 rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-400">Query Preview</span>
            {paperCount !== null && (
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                paperCount === 0
                  ? 'bg-amber-500/20 text-amber-300'
                  : 'bg-brand-500/20 text-brand-300'
              }`}>
                {paperCount.toLocaleString()} papers found
              </span>
            )}
          </div>
          <p className="text-sm text-slate-200 font-mono break-all">{constructedQuery}</p>
        </div>
      )}

      {/* Validation hint — surfaced below the preview so the user knows WHY 0 results */}
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
              Common causes: terms too specific, filters too strict (try disabling "Open access only" or "Humans only"),
              date range too narrow, or a MeSH term that isn't indexed. Try "Test in PubMed" below to diagnose on NCBI.
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
