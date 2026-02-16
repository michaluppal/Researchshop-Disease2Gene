export interface PipelineConfig {
  query: string;
  pmids: string;
  authorSearch: string;
  provider: Provider;
  model: string;
  customColumns: CustomColumn[];
  maxResults: number;
  topNCited: number;
}

export type Provider =
  | 'gemini'
  | 'anthropic'
  | 'deepseek'
  | 'openrouter'
  | 'together';

export const PROVIDER_LABELS: Record<Provider, string> = {
  gemini: 'Gemini',
  anthropic: 'Anthropic',
  deepseek: 'DeepSeek',
  openrouter: 'OpenRouter',
  together: 'Together AI',
};

export const PROVIDER_MODELS: Record<Provider, string[]> = {
  gemini: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash'],
  anthropic: ['claude-sonnet-4-5-20250929', 'claude-haiku-4-5-20251001'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  openrouter: ['google/gemini-2.5-flash', 'anthropic/claude-sonnet-4-5', 'meta-llama/llama-3.3-70b'],
  together: ['meta-llama/Llama-3.3-70B-Instruct-Turbo', 'Qwen/Qwen2.5-72B-Instruct-Turbo'],
};

export interface CustomColumn {
  id: string;
  name: string;
  description: string;
}

export interface GeneResult {
  gene: string;
  variant: string;
  pmid: string;
  title: string;
  year: number;
  journal: string;
  citations: number;
  [key: string]: unknown;
}

export interface PubMedResult {
  pmid: string;
  title: string;
  authors: string[];
  journal: string;
  year: number;
  abstract: string;
}

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
  duration?: number;
}

export interface ProgressData {
  stage: string;
  progress: number;
  message?: string;
}

export interface ResultData {
  results: GeneResult[];
}

export interface ErrorData {
  message: string;
  stage?: string;
}
