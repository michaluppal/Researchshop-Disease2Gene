import { useState } from 'react'
import { Plus, Trash2, Copy, ExternalLink, Eye, Code, Calendar } from 'lucide-react'

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
  constructedQuery: string
  paperCount: number | null
  onPreview: () => void
}

const OPERATORS = ['AND', 'OR', 'NOT']
const FIELDS = [
  { value: '[Title/Abstract]', label: 'Title/Abstract' },
  { value: '[Title]', label: 'Title' },
  { value: '[MeSH Terms]', label: 'MeSH Terms' },
  { value: '', label: 'All Fields' },
]

export default function QueryConditionForm({
  conditions,
  onChange,
  startYear,
  endYear,
  onStartYearChange,
  onEndYearChange,
  constructedQuery,
  paperCount,
  onPreview,
}: QueryConditionFormProps) {
  const [rawMode, setRawMode] = useState(false)
  const [rawQuery, setRawQuery] = useState('')
  const [copied, setCopied] = useState(false)

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

  return (
    <div className="space-y-5">
      {/* Mode toggle */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700">Search Query</h3>
        <button
          onClick={() => {
            if (!rawMode) setRawQuery(constructedQuery)
            setRawMode(!rawMode)
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
          onChange={(e) => setRawQuery(e.target.value)}
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

      {/* Date range */}
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
        <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 mb-2">
          <Calendar className="w-4 h-4 text-gray-400" />
          Date Range
        </label>
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
              <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-brand-500/20 text-brand-300 text-xs font-medium">
                {paperCount.toLocaleString()} papers found
              </span>
            )}
          </div>
          <p className="text-sm text-slate-200 font-mono break-all">{constructedQuery}</p>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <button
          onClick={copyQuery}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-600 rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
        >
          <Copy className="w-4 h-4" />
          {copied ? 'Copied!' : 'Copy Query'}
        </button>
        <button
          onClick={testInPubMed}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-600 rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
        >
          <ExternalLink className="w-4 h-4" />
          Test in PubMed
        </button>
        <button
          onClick={onPreview}
          disabled={!constructedQuery}
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Eye className="w-4 h-4" />
          Preview &amp; Select
        </button>
      </div>
    </div>
  )
}
