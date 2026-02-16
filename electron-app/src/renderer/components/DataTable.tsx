import { useState, type ReactNode } from 'react';

export interface Column<T> {
  key: string;
  label: string;
  sortable?: boolean;
  render?: (row: T) => ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  sortColumn: string;
  sortDirection: 'asc' | 'desc';
  onSort: (column: string) => void;
  onRowClick?: (row: T) => void;
  rowKey: (row: T) => string;
  emptyMessage?: string;
  expandedContent?: (row: T) => ReactNode;
}

export function DataTable<T>({
  columns,
  data,
  sortColumn,
  sortDirection,
  onSort,
  onRowClick,
  rowKey,
  emptyMessage = 'No data available',
  expandedContent,
}: DataTableProps<T>) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  function handleRowClick(row: T) {
    const key = rowKey(row);
    if (expandedContent) {
      setExpandedRow(expandedRow === key ? null : key);
    }
    onRowClick?.(row);
  }

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-[var(--color-text-muted)]">
        <svg className="h-12 w-12 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
        <p className="text-sm">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="overflow-auto rounded-xl border border-[var(--color-border-subtle)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[var(--color-bg-surface)]">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`
                  px-4 py-3 text-left font-medium text-[var(--color-text-secondary)]
                  ${col.sortable !== false ? 'cursor-pointer hover:text-[var(--color-text-primary)] select-none' : ''}
                  ${col.className ?? ''}
                `}
                onClick={() => col.sortable !== false && onSort(col.key)}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {col.sortable !== false && sortColumn === col.key && (
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d={sortDirection === 'asc' ? 'M5 15l7-7 7 7' : 'M19 9l-7 7-7-7'}
                      />
                    </svg>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-border-subtle)]">
          {data.map((row) => {
            const key = rowKey(row);
            const isExpanded = expandedRow === key;
            return (
              <tr key={key} className="group">
                <td colSpan={columns.length} className="p-0">
                  <div
                    className={`
                      flex cursor-pointer transition-colors
                      ${isExpanded ? 'bg-[var(--color-bg-surface)]' : 'hover:bg-[var(--color-bg-surface)]/50'}
                    `}
                    onClick={() => handleRowClick(row)}
                  >
                    {columns.map((col) => (
                      <div
                        key={col.key}
                        className={`px-4 py-3 ${col.className ?? ''}`}
                        style={{ flex: '1 1 0%', minWidth: 0 }}
                      >
                        {col.render
                          ? col.render(row)
                          : String((row as Record<string, unknown>)[col.key] ?? '')}
                      </div>
                    ))}
                  </div>
                  {isExpanded && expandedContent && (
                    <div className="px-4 py-4 bg-[var(--color-bg-surface)] border-t border-[var(--color-border-subtle)]">
                      {expandedContent(row)}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
