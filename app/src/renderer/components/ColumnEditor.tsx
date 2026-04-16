import { useState, useEffect, useRef } from 'react'
import { Plus, X, Info, GripVertical, Lock } from 'lucide-react'

interface ColumnEditorProps {
  columns: Record<string, string>
  onChange: (columns: Record<string, string>) => void
  requiredColumns?: Set<string>
}

export const DEFAULT_COLUMNS: Record<string, string> = {
  'Disease Association': 'The disease or medical condition associated with this gene/variant',
  'Key Finding': 'Main research finding about this gene from the paper',
  'Statistical Evidence': 'P-values, odds ratios, or other statistical measures',
  'Conclusion': 'Author conclusions specifically about this gene or variant',
}

export const REQUIRED_COLUMN_NAMES = new Set(['Key Finding', 'Disease Association'])

function toEntries(columns: Record<string, string>): Array<{ id: string; name: string; description: string }> {
  return Object.entries(columns).map(([name, description]) => ({
    id: crypto.randomUUID(),
    name,
    description,
  }))
}

export default function ColumnEditor({ columns, onChange, requiredColumns = REQUIRED_COLUMN_NAMES }: ColumnEditorProps) {
  // Keep local array state so empty names/duplicate names don't get swallowed while typing
  const [entries, setEntries] = useState(() => toEntries(columns))
  const dragItem = useRef<string | null>(null)
  const dragOverItem = useRef<string | null>(null)

  // Guard: do not call onChange on the initial render — only sync upward when user edits
  const isMounted = useRef(false)

  // Sync to parent when entries change (filtering out empty names)
  useEffect(() => {
    if (!isMounted.current) {
      isMounted.current = true
      return
    }
    const result: Record<string, string> = {}
    for (const entry of entries) {
      const trimmedName = entry.name.trim()
      if (trimmedName) {
        result[trimmedName] = entry.description.trim()
      }
    }
    onChange(result)
  }, [entries])

  const update = (id: string, field: 'name' | 'description', value: string) => {
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, [field]: value } : e)))
  }

  const remove = (id: string) => {
    setEntries((prev) => prev.filter((e) => e.id !== id))
  }

  const add = () => {
    setEntries((prev) => [...prev, { id: crypto.randomUUID(), name: '', description: '' }])
  }

  const isRequired = (name: string) => requiredColumns.has(name.trim())

  const handleDragStart = (id: string) => {
    dragItem.current = id
  }

  const handleDragOver = (e: React.DragEvent, id: string) => {
    e.preventDefault()
    dragOverItem.current = id
  }

  const handleDrop = () => {
    if (!dragItem.current || !dragOverItem.current || dragItem.current === dragOverItem.current) return
    setEntries((prev) => {
      const items = [...prev]
      const fromIdx = items.findIndex((e) => e.id === dragItem.current)
      const toIdx = items.findIndex((e) => e.id === dragOverItem.current)
      if (fromIdx === -1 || toIdx === -1) return prev
      const [moved] = items.splice(fromIdx, 1)
      items.splice(toIdx, 0, moved)
      return items
    })
    dragItem.current = null
    dragOverItem.current = null
  }

  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-3">Extraction Columns</label>

      <div className="space-y-2">
        {entries.map((col) => {
          const locked = isRequired(col.name)
          return (
            <div
              key={col.id}
              draggable
              onDragStart={() => handleDragStart(col.id)}
              onDragOver={(e) => handleDragOver(e, col.id)}
              onDrop={handleDrop}
              className="group flex items-start gap-2 rounded-lg border border-slate-200 bg-white p-3 hover:border-brand-300 hover:bg-brand-50/30 transition-colors"
            >
              <div className="cursor-grab pt-1 text-slate-300 group-hover:text-slate-400 transition-colors">
                <GripVertical className="w-4 h-4" />
              </div>

              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center gap-1.5">
                  <input
                    value={col.name}
                    onChange={(e) => update(col.id, 'name', e.target.value)}
                    placeholder="Column name"
                    disabled={locked}
                    className="font-medium text-sm text-slate-800 bg-transparent border-0 p-0 focus:ring-0 focus:outline-none placeholder:text-slate-300 disabled:text-slate-600 w-full"
                  />
                  {locked && (
                    <Lock className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                  )}
                </div>
                <input
                  value={col.description}
                  onChange={(e) => update(col.id, 'description', e.target.value)}
                  placeholder="Extraction instructions for the AI..."
                  className="w-full text-xs text-slate-500 bg-transparent border-0 p-0 focus:ring-0 focus:outline-none placeholder:text-slate-300"
                />
              </div>

              {locked ? (
                <div className="w-7 h-7" />
              ) : (
                <button
                  type="button"
                  onClick={() => remove(col.id)}
                  className="p-1.5 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors opacity-0 group-hover:opacity-100"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )
        })}

        <button
          type="button"
          onClick={add}
          className="w-full flex items-center justify-center gap-1.5 rounded-lg border-2 border-dashed border-slate-200 hover:border-brand-400 p-3 text-sm text-slate-400 hover:text-brand-600 hover:bg-brand-50/30 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Column
        </button>
      </div>

      <div className="mt-3 flex items-start gap-2 p-3 rounded-lg bg-slate-50 border border-slate-200">
        <Info className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-slate-500">
          Paper metadata (Title, Authors, Journal, etc.) is extracted automatically.
          Define additional columns here for custom AI extraction.
        </p>
      </div>
    </div>
  )
}
