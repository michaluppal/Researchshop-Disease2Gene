import { create } from 'zustand';
import type { PipelineConfig } from '../types';
import { useUIStore } from './uiStore';

const DEFAULT_CONFIG: PipelineConfig = {
  query: '',
  pmids: '',
  authorSearch: '',
  provider: 'gemini',
  model: 'gemini-2.5-flash',
  customColumns: [],
  maxResults: 50,
  topNCited: 20,
};

interface PipelineState {
  isRunning: boolean;
  stage: string;
  progress: number;
  logs: string[];
  config: PipelineConfig;
  setConfig: (config: Partial<PipelineConfig>) => void;
  startPipeline: () => Promise<void>;
  stopPipeline: () => Promise<void>;
  addLog: (log: string) => void;
  setProgress: (stage: string, progress: number) => void;
  reset: () => void;
}

export const usePipelineStore = create<PipelineState>((set, get) => ({
  isRunning: false,
  stage: '',
  progress: 0,
  logs: [],
  config: { ...DEFAULT_CONFIG },

  setConfig: (partial) =>
    set((state) => ({ config: { ...state.config, ...partial } })),

  startPipeline: async () => {
    const { config } = get();
    set({ isRunning: true, stage: 'Initializing...', progress: 0, logs: [] });
    try {
      await window.electronAPI.runPipeline(config);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Pipeline failed to start';
      useUIStore.getState().addToast({ type: 'error', message });
      set({ isRunning: false, stage: '', progress: 0 });
    }
  },

  stopPipeline: async () => {
    try {
      await window.electronAPI.stopPipeline();
      set({ isRunning: false, stage: 'Stopped' });
      useUIStore.getState().addToast({ type: 'warning', message: 'Pipeline stopped by user' });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to stop pipeline';
      useUIStore.getState().addToast({ type: 'error', message });
    }
  },

  addLog: (log) =>
    set((state) => ({ logs: [...state.logs, log] })),

  setProgress: (stage, progress) =>
    set({ stage, progress }),

  reset: () =>
    set({
      isRunning: false,
      stage: '',
      progress: 0,
      logs: [],
      config: { ...DEFAULT_CONFIG },
    }),
}));
