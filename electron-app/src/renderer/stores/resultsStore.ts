import { create } from 'zustand';
import type { GeneResult } from '../types';
import { useUIStore } from './uiStore';

interface ResultsState {
  results: GeneResult[];
  isLoading: boolean;
  sortColumn: string;
  sortDirection: 'asc' | 'desc';
  searchQuery: string;
  setResults: (results: GeneResult[]) => void;
  setSorting: (column: string) => void;
  setSearch: (query: string) => void;
  exportResults: (format: 'csv' | 'json') => Promise<void>;
  filteredResults: () => GeneResult[];
}

export const useResultsStore = create<ResultsState>((set, get) => ({
  results: [],
  isLoading: false,
  sortColumn: 'gene',
  sortDirection: 'asc',
  searchQuery: '',

  setResults: (results) => set({ results }),

  setSorting: (column) =>
    set((state) => ({
      sortColumn: column,
      sortDirection:
        state.sortColumn === column && state.sortDirection === 'asc'
          ? 'desc'
          : 'asc',
    })),

  setSearch: (query) => set({ searchQuery: query }),

  exportResults: async (format) => {
    const results = get().filteredResults();
    try {
      const filePath = await window.electronAPI.exportResults(format, results);
      useUIStore.getState().addToast({
        type: 'success',
        message: `Results exported to ${filePath}`,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Export failed';
      useUIStore.getState().addToast({ type: 'error', message });
    }
  },

  filteredResults: () => {
    const { results, searchQuery, sortColumn, sortDirection } = get();
    let filtered = results;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = results.filter(
        (r) =>
          r.gene.toLowerCase().includes(q) ||
          r.variant.toLowerCase().includes(q) ||
          r.title.toLowerCase().includes(q) ||
          r.journal.toLowerCase().includes(q) ||
          r.pmid.includes(q),
      );
    }

    const sorted = [...filtered].sort((a, b) => {
      const aVal = a[sortColumn];
      const bVal = b[sortColumn];
      if (aVal == null || bVal == null) return 0;
      const cmp =
        typeof aVal === 'number' && typeof bVal === 'number'
          ? aVal - bVal
          : String(aVal).localeCompare(String(bVal));
      return sortDirection === 'asc' ? cmp : -cmp;
    });

    return sorted;
  },
}));
