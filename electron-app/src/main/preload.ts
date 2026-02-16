import { contextBridge, ipcRenderer } from "electron";

import type { PipelineConfig, ProgressData, ResultData, ErrorData } from "./types.js";

export interface ElectronAPI {
  // API Key management (uses safeStorage)
  saveApiKey(provider: string, key: string): Promise<void>;
  getApiKey(provider: string): Promise<string>;
  deleteApiKey(provider: string): Promise<void>;
  getStoredProviders(): Promise<string[]>;

  // Pipeline execution
  runPipeline(config: PipelineConfig): Promise<void>;
  stopPipeline(): Promise<void>;
  onPipelineProgress(callback: (data: ProgressData) => void): () => void;
  onPipelineResult(callback: (data: ResultData) => void): () => void;
  onPipelineError(callback: (data: ErrorData) => void): () => void;

  // Results export
  exportResults(format: "csv" | "json", data: unknown): Promise<string>;

  // Settings
  getSettings(): Promise<Record<string, unknown>>;
  saveSettings(settings: Record<string, unknown>): Promise<void>;

  // PubMed search
  searchPubMed(query: string, maxResults: number): Promise<unknown[]>;

  // App info
  getAppVersion(): Promise<string>;
  getPlatform(): string;
}

const electronAPI: ElectronAPI = {
  // --- API Key management ---
  saveApiKey: (provider: string, key: string) =>
    ipcRenderer.invoke("api-key:save", provider, key),
  getApiKey: (provider: string) =>
    ipcRenderer.invoke("api-key:get", provider),
  deleteApiKey: (provider: string) =>
    ipcRenderer.invoke("api-key:delete", provider),
  getStoredProviders: () =>
    ipcRenderer.invoke("api-key:list-providers"),

  // --- Pipeline execution ---
  runPipeline: (config: PipelineConfig) =>
    ipcRenderer.invoke("pipeline:run", config),
  stopPipeline: () =>
    ipcRenderer.invoke("pipeline:stop"),
  onPipelineProgress: (callback: (data: ProgressData) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, data: ProgressData) =>
      callback(data);
    ipcRenderer.on("pipeline:progress", handler);
    return () => {
      ipcRenderer.removeListener("pipeline:progress", handler);
    };
  },
  onPipelineResult: (callback: (data: ResultData) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, data: ResultData) =>
      callback(data);
    ipcRenderer.on("pipeline:result", handler);
    return () => {
      ipcRenderer.removeListener("pipeline:result", handler);
    };
  },
  onPipelineError: (callback: (data: ErrorData) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, data: ErrorData) =>
      callback(data);
    ipcRenderer.on("pipeline:error", handler);
    return () => {
      ipcRenderer.removeListener("pipeline:error", handler);
    };
  },

  // --- Results export ---
  exportResults: (format: "csv" | "json", data: unknown) =>
    ipcRenderer.invoke("results:export", format, data),

  // --- Settings ---
  getSettings: () => ipcRenderer.invoke("settings:get"),
  saveSettings: (settings: Record<string, unknown>) =>
    ipcRenderer.invoke("settings:save", settings),

  // --- PubMed search ---
  searchPubMed: (query: string, maxResults: number) =>
    ipcRenderer.invoke("pubmed:search", query, maxResults),

  // --- App info ---
  getAppVersion: () => ipcRenderer.invoke("app:version"),
  getPlatform: () => process.platform,
};

contextBridge.exposeInMainWorld("electronAPI", electronAPI);
