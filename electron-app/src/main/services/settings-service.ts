/**
 * Settings Service — persistent settings and secure API key storage.
 * Uses electron-store for general preferences and safeStorage for API keys.
 */

import { app, safeStorage } from "electron";
import Store from "electron-store";
import path from "node:path";
import fs from "node:fs";
import type { Settings } from "../types.js";
import { logger } from "./logger-service.js";

// ---------------------------------------------------------------------------
// Default settings
// ---------------------------------------------------------------------------

const DEFAULT_SETTINGS: Settings = {
  entrezEmail: "",
  outputDir: path.join(app.getPath("home"), "Disease2Gene"),
  fetchMaxWorkers: 3,
  fetchThreadTimeout: 120,
  aiPerPaperTimeout: 600,
  geneBatchThreshold: 8,
  enablePaperRanking: true,
  enableCitationValidation: true,
  theme: "dark",
};

// ---------------------------------------------------------------------------
// Settings store
// ---------------------------------------------------------------------------

let store: Store<Settings> | null = null;

function getStore(): Store<Settings> {
  if (!store) {
    store = new Store<Settings>({
      name: "settings",
      defaults: DEFAULT_SETTINGS,
    });
  }
  return store;
}

export function getSettings(): Settings {
  const s = getStore();
  return { ...DEFAULT_SETTINGS, ...s.store };
}

export function saveSettings(partial: Partial<Settings>): void {
  const s = getStore();
  for (const [key, value] of Object.entries(partial)) {
    s.set(key as keyof Settings, value);
  }
  logger.info("Settings saved", "SettingsService");
}

export function getSetting<K extends keyof Settings>(key: K): Settings[K] {
  return getStore().get(key, DEFAULT_SETTINGS[key]) as Settings[K];
}

export function setSetting<K extends keyof Settings>(
  key: K,
  value: Settings[K],
): void {
  getStore().set(key, value);
}

// ---------------------------------------------------------------------------
// Secure API key storage (using safeStorage + a local JSON file)
// ---------------------------------------------------------------------------

interface KeyStore {
  [provider: string]: string; // base64-encoded encrypted blob
}

function getKeyStorePath(): string {
  return path.join(app.getPath("userData"), "api-keys.json");
}

function readKeyStore(): KeyStore {
  try {
    const raw = fs.readFileSync(getKeyStorePath(), "utf-8");
    return JSON.parse(raw) as KeyStore;
  } catch {
    return {};
  }
}

function writeKeyStore(data: KeyStore): void {
  fs.writeFileSync(getKeyStorePath(), JSON.stringify(data, null, 2), "utf-8");
}

export function saveApiKey(provider: string, key: string): void {
  if (!safeStorage.isEncryptionAvailable()) {
    logger.warn(
      "safeStorage encryption not available — storing key in plaintext",
      "SettingsService",
    );
    const ks = readKeyStore();
    ks[provider] = Buffer.from(key, "utf-8").toString("base64");
    writeKeyStore(ks);
    return;
  }

  const encrypted = safeStorage.encryptString(key);
  const ks = readKeyStore();
  ks[provider] = encrypted.toString("base64");
  writeKeyStore(ks);
  logger.info(`API key saved for provider: ${provider}`, "SettingsService");
}

export function getApiKey(provider: string): string {
  const ks = readKeyStore();
  const encoded = ks[provider];
  if (!encoded) return "";

  if (!safeStorage.isEncryptionAvailable()) {
    return Buffer.from(encoded, "base64").toString("utf-8");
  }

  try {
    const buf = Buffer.from(encoded, "base64");
    return safeStorage.decryptString(buf);
  } catch (err) {
    logger.error(
      `Failed to decrypt API key for ${provider}: ${String(err)}`,
      "SettingsService",
    );
    return "";
  }
}

export function deleteApiKey(provider: string): void {
  const ks = readKeyStore();
  delete ks[provider];
  writeKeyStore(ks);
  logger.info(`API key deleted for provider: ${provider}`, "SettingsService");
}

export function listStoredProviders(): string[] {
  const ks = readKeyStore();
  return Object.keys(ks);
}
