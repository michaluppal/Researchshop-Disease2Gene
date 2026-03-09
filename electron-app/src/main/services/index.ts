/**
 * Service index — re-exports all services for clean imports.
 */

// AI providers
export {
  type AIProvider,
  type AIModel,
  type ChatMessage,
  type ChatParams,
  type ChatResponse,
  AnthropicProvider,
  DeepSeekProvider,
  OpenRouterProvider,
  TogetherAIProvider,
  GeminiProvider,
  getProvider,
  listProviders,
  listAllModels,
} from "./ai-providers.js";

// Pipeline runner
export {
  startPipeline,
  stopPipeline,
  isPipelineRunning,
} from "./pipeline-runner.js";

// Settings
export {
  getSettings,
  saveSettings,
  getSetting,
  setSetting,
  saveApiKey,
  getApiKey,
  deleteApiKey,
  listStoredProviders,
} from "./settings-service.js";

// PubMed
export {
  type PubMedArticle,
  searchPubMed,
  countResults,
  resolvePmids,
  fetchAbstracts,
} from "./pubmed-service.js";

// Export
export {
  exportCSV,
  exportJSON,
  exportResults,
} from "./export-service.js";

// Logger
export { logger } from "./logger-service.js";
