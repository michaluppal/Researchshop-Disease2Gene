import { useState, useEffect, useMemo, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { Download, Loader2, AlertCircle, FileText, ChevronDown, ChevronUp, Settings2, X, Search, ChevronLeft, ChevronRight, FolderOpen, ArrowLeft } from 'lucide-react'
import Papa from 'papaparse'
import Tooltip from '../components/Tooltip'

// ── Confidence badge ────────────────────────────────────────────────────────

// Pipeline CSV outputs HIGH — display as CORROBORATED in the UI
function normalizeConfLevel(level: string): string {
  return level === 'HIGH' ? 'CORROBORATED' : level
}

const CONFIDENCE_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  CORROBORATED: { bg: 'bg-green-100',  text: 'text-green-800',  dot: 'bg-green-500'  },
  MEDIUM:       { bg: 'bg-yellow-100', text: 'text-yellow-800', dot: 'bg-yellow-500' },
  LOW:          { bg: 'bg-orange-100', text: 'text-orange-800', dot: 'bg-orange-500' },
  REVIEW:       { bg: 'bg-red-100',    text: 'text-red-800',    dot: 'bg-red-500'    },
}

const CONFIDENCE_TOOLTIPS: Record<string, string> = {
  CORROBORATED: 'Corroborated by multiple sources. Does NOT imply clinical validity. Requires independent expert verification.',
  MEDIUM: 'Partially corroborated — verify independently before use.',
  LOW: 'Low confidence — extracted from abstract only or with limited validation.',
  REVIEW: 'Requires manual review. May be a false positive or lack sufficient evidence.',
}

function getReviewTooltip(note: string): string {
  if (note.includes('Figure-only'))
    return 'Extracted from a figure (oncoprint, volcano plot, etc.) — less reliable than text-based extraction. Higher false-positive risk. Requires independent verification. Does NOT imply clinical validity.'
  if (note.includes('Citation text not found'))
    return 'AI-provided citation text could not be matched in the paper. Could indicate a false positive — verify gene presence independently. Does NOT imply clinical validity.'
  return CONFIDENCE_TOOLTIPS['REVIEW']
}

function ConfidenceBadge({ level, note }: { level: string; note?: string }) {
  const display = normalizeConfLevel(level)
  const style = CONFIDENCE_STYLES[display] ?? CONFIDENCE_STYLES['REVIEW']
  const tooltip = display === 'REVIEW' && note
    ? getReviewTooltip(note)
    : (CONFIDENCE_TOOLTIPS[display] ?? 'Requires review')
  return (
    <Tooltip content={tooltip}>
      <span
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium cursor-help ${style.bg} ${style.text}`}
      >
        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${style.dot}`} />
        {display}
      </span>
    </Tooltip>
  )
}

// ── Context-modifications cell formatter ─────────────────────────────────────

function formatContextMod(value: string): string {
  if (!value) return ''
  if (value === 'no_oa_full_text') return 'Abstract only (paywalled)'
  if (value === 'No modifications needed') return 'Full text'
  return value
}

// ── Confidence breakdown ────────────────────────────────────────────────────

function citationCoverage(rows: string[][], headers: string[]): number | null {
  const citCols = headers.reduce<number[]>((acc, h, i) => {
    if (h.endsWith(' Citation')) acc.push(i)
    return acc
  }, [])
  if (citCols.length === 0 || rows.length === 0) return null
  const filled = rows.filter(row => citCols.some(i => row[i] && row[i].trim())).length
  return filled / rows.length
}

function ConfidenceBreakdown({ rows, headers, abstractOnlyCount }: { rows: string[][]; headers: string[]; abstractOnlyCount: number | null }) {
  const confIdx = headers.findIndex((h) => h === 'Confidence')
  if (confIdx < 0) return null

  const counts: Record<string, number> = { CORROBORATED: 0, MEDIUM: 0, LOW: 0, REVIEW: 0 }
  for (const row of rows) {
    const level = normalizeConfLevel(row[confIdx])
    if (level in counts) counts[level]++
  }

  const coverage = citationCoverage(rows, headers)

  return (
    <div className="flex flex-col gap-2 mt-1">
      <div className="flex items-center gap-3 flex-wrap">
        {Object.entries(counts).map(([level, count]) => {
          if (count === 0) return null
          const styles = CONFIDENCE_STYLES[level]
          return (
            <span key={level} className="inline-flex items-center gap-1.5 text-sm">
              <span className={`w-2 h-2 rounded-full ${styles.dot}`} />
              <span className="text-slate-500 text-xs">{level}</span>
              <span className="font-semibold text-slate-900">{count}</span>
            </span>
          )
        })}
      </div>
      {coverage !== null && (
        <div className="flex items-center gap-2">
          <Tooltip content="% of gene rows that have at least one AI-sourced citation. Fluctuates 0-100% between runs due to stochastic LLM citation compliance — not a reflection of gene extraction quality.">
            <span className="text-xs text-slate-500 cursor-help">
              Citation coverage: <span className={`font-medium ${coverage < 0.2 ? 'text-amber-600' : 'text-slate-700'}`}>{Math.round(coverage * 100)}%</span>
            </span>
          </Tooltip>
          {coverage < 0.2 && (
            <Tooltip content="Low citation coverage is normal — the LLM stochastically provides citations. Re-running may produce higher coverage. Gene extraction quality is independent of citation coverage.">
              <span className="text-xs text-amber-600 cursor-help">
                · Low this run
              </span>
            </Tooltip>
          )}
        </div>
      )}
      {abstractOnlyCount !== null && abstractOnlyCount > 0 && (
        <Tooltip content="These genes were extracted from the abstract only — no open-access full text was available (paywalled). Abstract-only extraction produces LOW confidence. See the 'context_modifications' column for details.">
          <div className="text-xs text-slate-500 cursor-help">
            <span className="text-orange-600 font-medium">{abstractOnlyCount}</span> gene row{abstractOnlyCount !== 1 ? 's' : ''} from abstract-only papers (paywalled)
          </div>
        </Tooltip>
      )}
    </div>
  )
}

// ── Export dropdown ─────────────────────────────────────────────────────────

function ExportDropdown({ csvPath, excelPath, jsonPath }: { csvPath: string; excelPath: string; jsonPath: string }) {
  const [open, setOpen] = useState(false)
  const [fileExists, setFileExists] = useState<Record<string, boolean>>({})
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Check file existence for each non-empty path once on mount
  useEffect(() => {
    const paths: Record<string, string> = {}
    if (excelPath) paths.excel = excelPath
    if (jsonPath) paths.json = jsonPath
    if (csvPath) paths.csv = csvPath
    Promise.all(
      Object.entries(paths).map(async ([key, p]) => {
        const { exists } = await window.api.results.exists(p)
        return [key, exists] as [string, boolean]
      })
    ).then((results) => setFileExists(Object.fromEntries(results)))
  }, [csvPath, excelPath, jsonPath])

  const dir = csvPath.includes('/') || csvPath.includes('\\')
    ? csvPath.substring(0, Math.max(csvPath.lastIndexOf('/'), csvPath.lastIndexOf('\\')))
    : ''

  const actions = [
    { key: 'excel', icon: '📊', label: 'Open Excel', desc: '2-sheet workbook: Results + Metadata', path: excelPath, onClick: () => window.api.shell.openPath(excelPath) },
    { key: 'csv',   icon: '📁', label: 'Open CSV Folder', desc: 'Reveals folder with primary + metadata CSVs', path: dir, onClick: () => window.api.shell.openPath(dir) },
    { key: 'json',  icon: '{ }', label: 'Open JSON', desc: 'Primary results as JSON array of records', path: jsonPath, onClick: () => window.api.shell.openPath(jsonPath) },
  ]

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 px-4 py-2 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-700"
      >
        <Download className="w-4 h-4" />
        Export
        <ChevronDown className={`w-3 h-3 transition-transform duration-150 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-64 bg-white rounded-xl shadow-lg border border-slate-200 py-1 z-50">
          {actions.map((a) => {
            const disabled = !a.path || (a.key in fileExists && !fileExists[a.key])
            const tooltipText = !a.path
              ? 'Not generated by this pipeline run'
              : (a.key in fileExists && !fileExists[a.key])
                ? 'File not found — may have been moved or deleted'
                : undefined
            return (
              <Tooltip key={a.label} content={tooltipText ?? a.desc} position="left">
                <button
                  disabled={disabled}
                  onClick={() => { a.onClick(); setOpen(false) }}
                  className="w-full flex items-start gap-3 px-4 py-2.5 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed text-left"
                >
                  <span className="text-sm leading-none mt-0.5 font-mono">{a.icon}</span>
                  <div>
                    <div className="text-sm font-medium text-slate-900">{a.label}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{tooltipText ?? a.desc}</div>
                  </div>
                </button>
              </Tooltip>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Metadata column picker ──────────────────────────────────────────────────

const META_GROUPS = [
  { label: 'Pipeline',     matchers: ['Gene Source', 'Candidate Source', 'Normalization Applied', 'Validation Outcome', 'Dropped By Gate', 'validation_confidence', 'validation_source', 'validation_suggestions'] },
  { label: 'Citations',    matchers: ['_citation_valid', '_citation_confidence', '_citation_details', ' Citation'] },
  { label: 'Gene Details', matchers: ['NCBI Gene ID', 'Gene Full Name', 'Gene Aliases', 'Chromosome'] },
  { label: 'Context',      matchers: ['context_', 'Figure Count', 'Figure Analysis Enabled', 'Metadata'] },
]

function matchGroup(col: string, matchers: string[]): boolean {
  return matchers.some((m) => col.includes(m))
}

function MetadataPicker({
  metaHeaders,
  selectedCols,
  onToggle,
  onClose,
}: {
  metaHeaders: string[]
  selectedCols: Set<string>
  onToggle: (col: string) => void
  onClose: () => void
}) {
  const groups = META_GROUPS.map((g) => ({
    label: g.label,
    cols: metaHeaders.filter((h) => matchGroup(h, g.matchers)),
  })).filter((g) => g.cols.length > 0)

  const categorised = new Set(groups.flatMap((g) => g.cols))
  const other = metaHeaders.filter((h) => !categorised.has(h) && h !== 'PMID' && h !== 'Gene/Group' && h !== 'Variant Name')

  const selectedArr = Array.from(selectedCols)

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5 mb-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-900">Add Metadata Columns</h3>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600 p-1 rounded">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-4 max-h-64 overflow-y-auto pr-1">
        {groups.map((group) => (
          <div key={group.label}>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">{group.label}</p>
            <div className="space-y-1">
              {group.cols.map((col) => (
                <label key={col} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedCols.has(col)}
                    onChange={() => onToggle(col)}
                    className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  <span className="text-xs text-slate-700 font-mono">{col}</span>
                </label>
              ))}
            </div>
          </div>
        ))}

        {other.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">Other</p>
            <div className="space-y-1">
              {other.map((col) => (
                <label key={col} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedCols.has(col)}
                    onChange={() => onToggle(col)}
                    className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  <span className="text-xs text-slate-700 font-mono">{col}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      {selectedArr.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
          <span className="text-xs text-slate-500">{selectedArr.length} column{selectedArr.length !== 1 ? 's' : ''} added</span>
          <button
            onClick={() => selectedArr.forEach(onToggle)}
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            Clear all
          </button>
        </div>
      )}
    </div>
  )
}

// ── Sorting types ───────────────────────────────────────────────────────────

type SortDirection = 'asc' | 'desc'

interface SortConfig {
  column: number
  direction: SortDirection
}

// ── Results table (with Confidence badge rendering + metadata merge) ─────────

function ResultsTable({
  headers,
  rows,
  metaHeaders,
  metaRows,
  selectedMetaCols,
  sortConfig,
  onSort,
}: {
  headers: string[]
  rows: string[][]
  metaHeaders: string[]
  metaRows: string[][]
  selectedMetaCols: Set<string>
  sortConfig: SortConfig | null
  onSort: (colIdx: number) => void
}) {
  const confIdx = headers.findIndex((h) => h === 'Confidence')
  const confNoteIdx = headers.findIndex((h) => h === 'Confidence Note')
  const selectedList = Array.from(selectedMetaCols)
  const mergedHeaders = [...headers, ...selectedList]

  const mergedRows = rows.map((row, i) => {
    const metaRow = metaRows[i] ?? []
    const extra = selectedList.map((col) => {
      const idx = metaHeaders.indexOf(col)
      return idx >= 0 ? (metaRow[idx] ?? '') : ''
    })
    return [...row, ...extra]
  })

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="bg-slate-50 border-b border-slate-200">
          <tr>
            {mergedHeaders.map((h, i) => {
              const isSorted = sortConfig?.column === i
              return (
                <th
                  key={`h-${i}`}
                  className="px-3 py-2.5 font-medium text-slate-600 whitespace-nowrap text-xs cursor-pointer hover:bg-slate-100 select-none"
                  onClick={() => onSort(i)}
                >
                  <span className="inline-flex items-center gap-1">
                    {h}
                    {isSorted ? (
                      sortConfig.direction === 'asc' ? (
                        <ChevronUp className="w-3 h-3 text-brand-600" />
                      ) : (
                        <ChevronDown className="w-3 h-3 text-brand-600" />
                      )
                    ) : (
                      <span className="w-3 h-3" />
                    )}
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {mergedRows.map((row, rIdx) => (
            <tr key={rIdx} className="hover:bg-slate-50">
              {row.map((cell, cIdx) => (
                <td key={cIdx} className="px-3 py-2 text-slate-700 align-top text-xs max-w-xs">
                  {cIdx === confIdx ? (
                    <ConfidenceBadge level={cell} note={confNoteIdx >= 0 ? row[confNoteIdx] : undefined} />
                  ) : mergedHeaders[cIdx] === 'context_modifications' ? (
                    <span className="whitespace-pre-wrap break-words">{formatContextMod(cell)}</span>
                  ) : (
                    <span className="whitespace-pre-wrap break-words">{cell}</span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Pagination constants ────────────────────────────────────────────────────

const ROWS_PER_PAGE_OPTIONS = [25, 50, 100]

// ── Main Results page ───────────────────────────────────────────────────────

export default function Results() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const filePath  = searchParams.get('path')  || ''
  const excelPath = searchParams.get('excel') || ''
  const metaPath  = searchParams.get('meta')  || ''
  const jsonPath  = searchParams.get('json')  || ''

  const [headers, setHeaders] = useState<string[]>([])
  const [rows, setRows]       = useState<string[][]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  const [metaHeaders, setMetaHeaders]           = useState<string[]>([])
  const [metaRows, setMetaRows]                 = useState<string[][]>([])
  const [metaLoaded, setMetaLoaded]             = useState(false)
  const [metaLoading, setMetaLoading]           = useState(false)
  const [selectedMetaCols, setSelectedMetaCols] = useState<Set<string>>(new Set())
  const [showMetaPicker, setShowMetaPicker]     = useState(false)
  const [researchBannerDismissed, setResearchBannerDismissed] = useState(false)

  // Search, sort, pagination state
  const [searchQuery, setSearchQuery] = useState('')
  const [sortConfig, setSortConfig] = useState<SortConfig | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [rowsPerPage, setRowsPerPage] = useState(25)

  // Load primary CSV
  useEffect(() => {
    if (!filePath) { setError('No result file specified'); setLoading(false); return }
    window.api.results.load(filePath).then((res) => {
      if (res.error || !res.content) { setError(res.error || 'Failed to load file'); setLoading(false); return }
      const parsed = Papa.parse<string[]>(res.content, { header: false, skipEmptyLines: true })
      if (parsed.data.length > 0) { setHeaders(parsed.data[0]); setRows(parsed.data.slice(1)) }
      setLoading(false)
    })
  }, [filePath])

  // Lazy-load metadata CSV when picker is first opened
  const loadMeta = async () => {
    if (metaLoaded || !metaPath || metaLoading) return
    setMetaLoading(true)
    const res = await window.api.results.load(metaPath)
    if (!res.error && res.content) {
      const parsed = Papa.parse<string[]>(res.content, { header: false, skipEmptyLines: true })
      if (parsed.data.length > 0) { setMetaHeaders(parsed.data[0]); setMetaRows(parsed.data.slice(1)) }
    }
    setMetaLoaded(true)
    setMetaLoading(false)
  }

  const handleTogglePicker = () => {
    setShowMetaPicker((v) => !v)
    if (!metaLoaded) loadMeta()
  }

  const toggleMetaCol = (col: string) => {
    setSelectedMetaCols((prev) => {
      const next = new Set(prev)
      if (next.has(col)) next.delete(col); else next.add(col)
      return next
    })
  }

  // Eagerly load metadata on mount so context_modifications is visible by default
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (metaPath) loadMeta() }, [metaPath])

  // Auto-select context_modifications and context_truncated columns once metadata loads
  useEffect(() => {
    if (!metaLoaded) return
    const autoSelect = ['context_modifications', 'context_truncated'].filter(col => metaHeaders.includes(col))
    if (autoSelect.length === 0) return
    setSelectedMetaCols(prev => {
      if (autoSelect.every(col => prev.has(col))) return prev
      const next = new Set(prev)
      autoSelect.forEach(col => next.add(col))
      return next
    })
  }, [metaLoaded, metaHeaders])

  const stats = useMemo(() => {
    if (rows.length === 0) return { genes: 0, papers: 0 }
    const geneIdx  = headers.findIndex((h) => h === 'Gene' || h === 'Gene/Group')
    const pmidIdx  = headers.findIndex((h) => h === 'PMID')
    return {
      genes:  geneIdx >= 0 ? new Set(rows.map((r) => r[geneIdx]).filter(Boolean)).size : 0,
      papers: pmidIdx >= 0 ? new Set(rows.map((r) => r[pmidIdx]).filter(Boolean)).size : 0,
    }
  }, [headers, rows])

  // Count gene rows from paywalled / abstract-only papers
  const abstractOnlyCount = useMemo(() => {
    if (!metaLoaded || metaRows.length === 0) return null
    const ctxIdx = metaHeaders.indexOf('context_modifications')
    if (ctxIdx < 0) return null
    return metaRows.filter(row => (row[ctxIdx] ?? '').includes('no_oa_full_text')).length
  }, [metaLoaded, metaHeaders, metaRows])

  // Filtered rows (search)
  const filteredRows = useMemo(() => {
    if (!searchQuery.trim()) return rows
    const q = searchQuery.toLowerCase()
    return rows.filter(row => row.some(cell => cell.toLowerCase().includes(q)))
  }, [rows, searchQuery])

  // Sorted rows
  const sortedRows = useMemo(() => {
    if (!sortConfig) return filteredRows
    const { column, direction } = sortConfig
    const sorted = [...filteredRows].sort((a, b) => {
      const valA = (a[column] ?? '').toLowerCase()
      const valB = (b[column] ?? '').toLowerCase()
      // Try numeric comparison
      const numA = parseFloat(valA)
      const numB = parseFloat(valB)
      if (!isNaN(numA) && !isNaN(numB)) {
        return direction === 'asc' ? numA - numB : numB - numA
      }
      if (valA < valB) return direction === 'asc' ? -1 : 1
      if (valA > valB) return direction === 'asc' ? 1 : -1
      return 0
    })
    return sorted
  }, [filteredRows, sortConfig])

  // Pagination
  const totalPages = Math.max(1, Math.ceil(sortedRows.length / rowsPerPage))
  const paginatedRows = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage
    return sortedRows.slice(start, start + rowsPerPage)
  }, [sortedRows, currentPage, rowsPerPage])

  // Also paginate corresponding metaRows to keep indices aligned
  const paginatedMetaRows = useMemo(() => {
    if (!sortConfig && !searchQuery.trim()) {
      const start = (currentPage - 1) * rowsPerPage
      return metaRows.slice(start, start + rowsPerPage)
    }
    // When sorted/filtered, we need to map back to original indices
    const originalIndices = sortedRows.map(row => rows.indexOf(row))
    const start = (currentPage - 1) * rowsPerPage
    const pageIndices = originalIndices.slice(start, start + rowsPerPage)
    return pageIndices.map(i => metaRows[i] ?? [])
  }, [sortedRows, rows, metaRows, currentPage, rowsPerPage, sortConfig, searchQuery])

  // Reset page when search or sort changes
  useEffect(() => { setCurrentPage(1) }, [searchQuery, sortConfig, rowsPerPage])

  const handleSort = (colIdx: number) => {
    setSortConfig(prev => {
      if (prev?.column === colIdx) {
        return prev.direction === 'asc'
          ? { column: colIdx, direction: 'desc' }
          : null // third click clears sort
      }
      return { column: colIdx, direction: 'asc' }
    })
  }

  const handleOpenFolder = () => {
    const dir = filePath.includes('/') || filePath.includes('\\')
      ? filePath.substring(0, Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\')))
      : ''
    if (dir) window.api.shell.openPath(dir)
  }

  if (loading) return (
    <div className="flex items-center justify-center h-full">
      <Loader2 className="w-6 h-6 animate-spin text-brand-600" />
    </div>
  )

  if (error) return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="flex items-center gap-2 p-4 rounded-lg bg-red-50 text-red-600">
        <AlertCircle className="w-5 h-5" />
        <p>{error}</p>
      </div>
    </div>
  )

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Query
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 mb-1">Results</h1>
            <p className="text-sm text-slate-500">{filePath.split(/[/\\]/).pop()}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleOpenFolder}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-700 transition-colors"
          >
            <FolderOpen className="w-4 h-4" />
            View in Folder
          </button>
          {metaPath && (
            <button
              onClick={handleTogglePicker}
              className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border transition-colors ${
                showMetaPicker
                  ? 'border-brand-500 bg-brand-50 text-brand-700'
                  : 'border-slate-300 hover:bg-slate-50 text-slate-700'
              }`}
            >
              <Settings2 className="w-4 h-4" />
              {selectedMetaCols.size > 0 ? `Metadata (${selectedMetaCols.size})` : '+ Metadata'}
            </button>
          )}
          <ExportDropdown csvPath={filePath} excelPath={excelPath} jsonPath={jsonPath} />
        </div>
      </div>

      {/* Research use banner */}
      {!researchBannerDismissed && (
        <div className="flex items-center gap-3 px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg mb-4 text-sm text-amber-800">
          <span className="text-base flex-shrink-0">⚠️</span>
          <span className="flex-1">
            <strong>Research tool</strong> — AI-extracted associations require expert review before use in publications or clinical decisions.
          </span>
          <button
            onClick={() => setResearchBannerDismissed(true)}
            className="text-amber-600 hover:text-amber-800 flex-shrink-0 ml-2"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-4 mb-4">
        <div className="bg-white rounded-xl shadow-sm p-4">
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <FileText className="w-3.5 h-3.5" />
            Unique Genes
          </div>
          <p className="text-2xl font-bold text-slate-900">{stats.genes}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-4">
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <FileText className="w-3.5 h-3.5" />
            Unique Papers
          </div>
          <p className="text-2xl font-bold text-slate-900">{stats.papers}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-4 col-span-2">
          <div className="text-xs text-slate-500 mb-1">Confidence Breakdown</div>
          <ConfidenceBreakdown rows={rows} headers={headers} abstractOnlyCount={abstractOnlyCount} />
        </div>
      </div>

      {/* Metadata picker */}
      {showMetaPicker && (
        metaLoading ? (
          <div className="flex items-center gap-2 p-4 text-sm text-slate-500 mb-4">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading metadata columns…
          </div>
        ) : (
          <MetadataPicker
            metaHeaders={metaHeaders}
            selectedCols={selectedMetaCols}
            onToggle={toggleMetaCol}
            onClose={() => setShowMetaPicker(false)}
          />
        )
      )}

      {/* Search bar + row count */}
      <div className="flex items-center justify-between mb-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search genes, PMIDs, or any text..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 pr-4 py-2 w-80 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <span className="text-xs text-slate-500">
          Showing {paginatedRows.length} of {sortedRows.length} result{sortedRows.length !== 1 ? 's' : ''}
          {searchQuery && sortedRows.length !== rows.length && ` (filtered from ${rows.length})`}
        </span>
      </div>

      {/* Results table */}
      <div className="bg-white rounded-xl shadow-sm p-6 overflow-hidden">
        <ResultsTable
          headers={headers}
          rows={paginatedRows}
          metaHeaders={metaHeaders}
          metaRows={paginatedMetaRows}
          selectedMetaCols={selectedMetaCols}
          sortConfig={sortConfig}
          onSort={handleSort}
        />

        {/* Pagination controls */}
        {sortedRows.length > rowsPerPage && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-100">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Rows per page:</span>
              <select
                value={rowsPerPage}
                onChange={(e) => setRowsPerPage(Number(e.target.value))}
                className="text-xs border border-slate-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                {ROWS_PER_PAGE_OPTIONS.map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-500">
                Page {currentPage} of {totalPages}
              </span>
              <div className="flex gap-1">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-4 h-4 text-slate-600" />
                </button>
                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronRight className="w-4 h-4 text-slate-600" />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
