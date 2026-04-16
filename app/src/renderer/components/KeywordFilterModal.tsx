import { useState, useRef, useEffect } from 'react'
import { X, Plus, Filter, Search } from 'lucide-react'

interface KeywordFilterModalProps {
  isOpen: boolean
  onClose: () => void
  authorName?: string
  initialKeywords?: string[]
  initialLogic?: 'AND' | 'OR'
  initialStartYear?: string
  initialEndYear?: string
  onApply: (keywords: string[], logic: 'AND' | 'OR', startYear: string, endYear: string) => void
}

export default function KeywordFilterModal({
  isOpen,
  onClose,
  authorName,
  initialKeywords = [],
  initialLogic = 'AND',
  initialStartYear = '',
  initialEndYear = '',
  onApply,
}: KeywordFilterModalProps) {
  const [keywords, setKeywords] = useState<string[]>(initialKeywords)
  const [logic, setLogic] = useState<'AND' | 'OR'>(initialLogic)
  const [startYear, setStartYear] = useState(initialStartYear)
  const [endYear, setEndYear] = useState(initialEndYear)
  const [keywordInput, setKeywordInput] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isOpen) inputRef.current?.focus()
  }, [isOpen])

  if (!isOpen) return null

  const addKeyword = () => {
    const kw = keywordInput.trim()
    if (kw && !keywords.includes(kw)) {
      setKeywords([...keywords, kw])
    }
    setKeywordInput('')
  }

  const removeKeyword = (kw: string) => {
    setKeywords(keywords.filter((k) => k !== kw))
  }

  const handleApply = () => {
    onApply(keywords, logic, startYear, endYear)
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-white">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
            <Filter className="w-5 h-5 text-brand-600" />
            Configure Filters
          </h2>
          {authorName && <p className="text-sm text-slate-500 mt-0.5">For author: {authorName}</p>}
        </div>
        <button onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-xl mx-auto space-y-8">
          {/* Date Range */}
          <div>
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Date Range</h3>
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-xs text-slate-500 mb-1">From Year</label>
                <input
                  type="number"
                  value={startYear}
                  onChange={(e) => setStartYear(e.target.value)}
                  placeholder="e.g. 2015"
                  min={1900}
                  max={2030}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
                />
              </div>
              <div className="flex-1">
                <label className="block text-xs text-slate-500 mb-1">To Year</label>
                <input
                  type="number"
                  value={endYear}
                  onChange={(e) => setEndYear(e.target.value)}
                  placeholder="e.g. 2024"
                  min={1900}
                  max={2030}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
                />
              </div>
            </div>
          </div>

          {/* Keywords */}
          <div>
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Keywords</h3>

            {/* Logic toggle */}
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs text-slate-500">Match logic:</span>
              <button
                onClick={() => setLogic('AND')}
                className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors ${
                  logic === 'AND'
                    ? 'bg-brand-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                AND
              </button>
              <button
                onClick={() => setLogic('OR')}
                className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors ${
                  logic === 'OR'
                    ? 'bg-brand-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                OR
              </button>
            </div>

            {/* Input */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                <input
                  ref={inputRef}
                  value={keywordInput}
                  onChange={(e) => setKeywordInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addKeyword()
                    }
                  }}
                  placeholder="Add a keyword..."
                  className="w-full rounded-lg border border-slate-300 pl-9 pr-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-shadow"
                />
              </div>
              <button
                onClick={addKeyword}
                disabled={!keywordInput.trim()}
                className="inline-flex items-center gap-1 px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add
              </button>
            </div>

            {/* Chips */}
            {keywords.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {keywords.map((kw) => (
                  <span
                    key={kw}
                    className="inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1 rounded-full bg-brand-50 border border-brand-200 text-brand-700 text-sm font-medium transition-colors hover:bg-brand-100"
                  >
                    {kw}
                    <button
                      onClick={() => removeKeyword(kw)}
                      className="p-0.5 rounded-full hover:bg-brand-200 hover:text-brand-900 transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            {keywords.length === 0 && (
              <p className="text-xs text-slate-400 mt-3">No keywords added yet. Type above and press Enter or click Add.</p>
            )}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 bg-white">
        <span className="text-sm text-slate-500">
          {keywords.length === 0
            ? 'No filters configured'
            : `${keywords.length} keyword${keywords.length === 1 ? '' : 's'} selected`}
        </span>
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-700 rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleApply}
            className="px-4 py-2 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 transition-colors"
          >
            Apply Filters
          </button>
        </div>
      </div>
    </div>
  )
}
