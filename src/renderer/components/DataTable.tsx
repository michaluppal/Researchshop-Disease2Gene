import { useState, useMemo } from 'react'
import { ChevronUp, ChevronDown, Search, Database } from 'lucide-react'

interface DataTableProps {
  headers: string[]
  rows: string[][]
}

const PAGE_SIZE = 25

export default function DataTable({ headers, rows }: DataTableProps) {
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(0)
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    if (!filter) return rows
    const lower = filter.toLowerCase()
    return rows.filter((row) => row.some((cell) => cell.toLowerCase().includes(lower)))
  }, [rows, filter])

  const sorted = useMemo(() => {
    if (sortCol === null) return filtered
    return [...filtered].sort((a, b) => {
      const cmp = (a[sortCol] || '').localeCompare(b[sortCol] || '', undefined, { numeric: true })
      return sortAsc ? cmp : -cmp
    })
  }, [filtered, sortCol, sortAsc])

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const pageRows = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const toggleSort = (col: number) => {
    if (sortCol === col) {
      setSortAsc(!sortAsc)
    } else {
      setSortCol(col)
      setSortAsc(true)
    }
    setPage(0)
  }

  return (
    <div>
      <div className="mb-3 relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value)
            setPage(0)
          }}
          placeholder="Filter rows..."
          className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 z-10 bg-white shadow-sm">
            <tr className="border-b border-slate-200">
              {headers.map((h, i) => (
                <th
                  key={i}
                  onClick={() => toggleSort(i)}
                  className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-slate-100 whitespace-nowrap select-none border-r border-gray-100 last:border-r-0"
                >
                  <span className="inline-flex items-center gap-1">
                    {h}
                    {sortCol === i &&
                      (sortAsc ? (
                        <ChevronUp className="w-3 h-3" />
                      ) : (
                        <ChevronDown className="w-3 h-3" />
                      ))}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, ri) => (
              <tr
                key={ri}
                className={`border-b border-slate-100 transition-colors hover:bg-brand-50 ${ri % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}
              >
                {row.map((cell, ci) => (
                  <td
                    key={ci}
                    title={cell}
                    className="px-3 py-2 text-slate-700 max-w-xs truncate border-r border-gray-100 last:border-r-0"
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
            {pageRows.length === 0 && (
              <tr>
                <td colSpan={headers.length} className="px-3 py-12 text-center">
                  <Database className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                  <p className="text-slate-400 text-sm">No matching rows</p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-3 text-sm text-slate-500">
        <span>
          {sorted.length} row{sorted.length !== 1 ? 's' : ''}
          {filter && ` (filtered from ${rows.length})`}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1 rounded border border-slate-300 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Prev
          </button>
          <span>
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1 rounded border border-slate-300 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
