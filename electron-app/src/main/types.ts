/** Configuration passed to the Python pipeline process. */
export interface PipelineConfig {
  query: string;
  specificPmids: string[];
  specificAuthors: string[];
  userColumns: ColumnDefinition[];
  topNCited: number;
  maxResults: number | null;
  geminiApiKey: string;
  entrezEmail: string;
  entrezApiKey?: string;
  outputDir?: string;
}

export interface ColumnDefinition {
  name: string;
  description: string;
}

/** Progress update streamed from the running pipeline. */
export interface ProgressData {
  stage: string;
  percent: number;
  message: string;
  papersProcessed?: number;
  papersTotal?: number;
}

/** Final result data returned when the pipeline completes. */
export interface ResultData {
  outputPath: string;
  totalPapers: number;
  totalGenes: number;
  records: Record<string, unknown>[];
}

/** Error information sent when the pipeline fails. */
export interface ErrorData {
  message: string;
  stage?: string;
  details?: string;
}

/** Persisted application settings. */
export interface Settings {
  entrezEmail: string;
  outputDir: string;
  fetchMaxWorkers: number;
  fetchThreadTimeout: number;
  aiPerPaperTimeout: number;
  geneBatchThreshold: number;
  enablePaperRanking: boolean;
  enableCitationValidation: boolean;
  theme: "dark" | "light";
  [key: string]: unknown;
}
