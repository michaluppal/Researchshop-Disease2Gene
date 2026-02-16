import { useResultsStore } from '../stores/resultsStore';
import { Card } from '../components/Card';
import { Input } from '../components/Input';
import { Button } from '../components/Button';
import { DataTable, type Column } from '../components/DataTable';
import type { GeneResult } from '../types';

const columns: Column<GeneResult>[] = [
  { key: 'gene', label: 'Gene/Group' },
  { key: 'variant', label: 'Variant' },
  { key: 'pmid', label: 'PMID', className: 'w-28' },
  { key: 'title', label: 'Study Title' },
  { key: 'year', label: 'Year', className: 'w-20' },
  { key: 'journal', label: 'Journal' },
  {
    key: 'citations',
    label: 'Citations',
    className: 'w-24',
    render: (row) => (
      <span className="text-[var(--color-primary-light)] font-medium">
        {row.citations}
      </span>
    ),
  },
];

export function ResultsView() {
  const results = useResultsStore((s) => s.results);
  const filteredResults = useResultsStore((s) => s.filteredResults);
  const sortColumn = useResultsStore((s) => s.sortColumn);
  const sortDirection = useResultsStore((s) => s.sortDirection);
  const searchQuery = useResultsStore((s) => s.searchQuery);
  const setSorting = useResultsStore((s) => s.setSorting);
  const setSearch = useResultsStore((s) => s.setSearch);
  const exportResults = useResultsStore((s) => s.exportResults);

  const data = filteredResults();
  const uniqueGenes = new Set(results.map((r) => r.gene)).size;
  const uniquePapers = new Set(results.map((r) => r.pmid)).size;

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">
          Results
        </h1>
        {results.length > 0 && (
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => exportResults('csv')}>
              Export CSV
            </Button>
            <Button variant="secondary" size="sm" onClick={() => exportResults('json')}>
              Export JSON
            </Button>
          </div>
        )}
      </div>

      {/* Summary cards */}
      {results.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="Unique Genes" value={uniqueGenes} color="var(--color-primary)" />
          <StatCard label="Papers Analyzed" value={uniquePapers} color="var(--color-success)" />
          <StatCard label="Total Associations" value={results.length} color="var(--color-warning)" />
        </div>
      )}

      {/* Search */}
      {results.length > 0 && (
        <Input
          placeholder="Search genes, variants, titles, journals..."
          value={searchQuery}
          onChange={(e) => setSearch(e.target.value)}
        />
      )}

      {/* Table */}
      <DataTable<GeneResult>
        columns={columns}
        data={data}
        sortColumn={sortColumn}
        sortDirection={sortDirection}
        onSort={setSorting}
        rowKey={(row) => `${row.pmid}-${row.gene}-${row.variant}`}
        emptyMessage={
          results.length === 0
            ? 'No results yet. Run a pipeline to get started.'
            : 'No results match your search.'
        }
        expandedContent={(row) => (
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-[var(--color-text-muted)]">Full Title:</span>
              <p className="text-[var(--color-text-primary)] mt-1">{row.title}</p>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">Journal:</span>
              <p className="text-[var(--color-text-primary)] mt-1">{row.journal}</p>
            </div>
            {Object.entries(row)
              .filter(
                ([key]) =>
                  !['gene', 'variant', 'pmid', 'title', 'year', 'journal', 'citations'].includes(key),
              )
              .map(([key, value]) => (
                <div key={key}>
                  <span className="text-[var(--color-text-muted)]">{key}:</span>
                  <p className="text-[var(--color-text-primary)] mt-1">{String(value)}</p>
                </div>
              ))}
          </div>
        )}
      />
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <Card>
      <div className="text-center">
        <p className="text-3xl font-bold" style={{ color }}>
          {value.toLocaleString()}
        </p>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">{label}</p>
      </div>
    </Card>
  );
}
