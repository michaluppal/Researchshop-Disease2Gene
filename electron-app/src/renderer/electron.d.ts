import type { PipelineConfig, ProgressData, ResultData, ErrorData } from './types';

declare global {
  interface Window {
    electronAPI: {
      saveApiKey(provider: string, key: string): Promise<void>;
      getApiKey(provider: string): Promise<string>;
      deleteApiKey(provider: string): Promise<void>;
      getStoredProviders(): Promise<string[]>;
      runPipeline(config: PipelineConfig): Promise<void>;
      stopPipeline(): Promise<void>;
      onPipelineProgress(callback: (data: ProgressData) => void): () => void;
      onPipelineResult(callback: (data: ResultData) => void): () => void;
      onPipelineError(callback: (data: ErrorData) => void): () => void;
      exportResults(format: 'csv' | 'json', data: unknown): Promise<string>;
      getSettings(): Promise<Record<string, unknown>>;
      saveSettings(settings: Record<string, unknown>): Promise<void>;
      searchPubMed(query: string, maxResults: number): Promise<unknown[]>;
      getAppVersion(): Promise<string>;
      getPlatform(): string;
    };
  }
}

export {};
