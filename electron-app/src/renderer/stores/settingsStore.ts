import { create } from 'zustand';
import { useUIStore } from './uiStore';

interface ApiKeyInfo {
  configured: boolean;
  maskedKey: string;
}

interface SettingsState {
  apiKeys: Record<string, ApiKeyInfo>;
  entrezEmail: string;
  outputDir: string;
  maxWorkers: number;
  timeout: number;
  appVersion: string;
  loadSettings: () => Promise<void>;
  saveApiKey: (provider: string, key: string) => Promise<void>;
  deleteApiKey: (provider: string) => Promise<void>;
  updateSetting: (key: string, value: unknown) => void;
  saveAllSettings: () => Promise<void>;
}

function maskKey(key: string): string {
  if (key.length <= 8) return '****';
  return key.slice(0, 4) + '****' + key.slice(-4);
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  apiKeys: {},
  entrezEmail: '',
  outputDir: '',
  maxWorkers: 3,
  timeout: 120,
  appVersion: '',

  loadSettings: async () => {
    try {
      const [settings, providers, version] = await Promise.all([
        window.electronAPI.getSettings(),
        window.electronAPI.getStoredProviders(),
        window.electronAPI.getAppVersion(),
      ]);

      const apiKeys: Record<string, ApiKeyInfo> = {};
      for (const provider of providers) {
        const key = await window.electronAPI.getApiKey(provider);
        apiKeys[provider] = { configured: true, maskedKey: maskKey(key) };
      }

      set({
        apiKeys,
        entrezEmail: (settings['entrezEmail'] as string) ?? '',
        outputDir: (settings['outputDir'] as string) ?? '',
        maxWorkers: (settings['maxWorkers'] as number) ?? 3,
        timeout: (settings['timeout'] as number) ?? 120,
        appVersion: version,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load settings';
      useUIStore.getState().addToast({ type: 'error', message });
    }
  },

  saveApiKey: async (provider, key) => {
    try {
      await window.electronAPI.saveApiKey(provider, key);
      set((state) => ({
        apiKeys: {
          ...state.apiKeys,
          [provider]: { configured: true, maskedKey: maskKey(key) },
        },
      }));
      useUIStore.getState().addToast({
        type: 'success',
        message: `API key for ${provider} saved`,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save API key';
      useUIStore.getState().addToast({ type: 'error', message });
    }
  },

  deleteApiKey: async (provider) => {
    try {
      await window.electronAPI.deleteApiKey(provider);
      set((state) => {
        const updated = { ...state.apiKeys };
        delete updated[provider];
        return { apiKeys: updated };
      });
      useUIStore.getState().addToast({
        type: 'info',
        message: `API key for ${provider} removed`,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete API key';
      useUIStore.getState().addToast({ type: 'error', message });
    }
  },

  updateSetting: (key, value) =>
    set((state) => ({ ...state, [key]: value })),

  saveAllSettings: async () => {
    const { entrezEmail, outputDir, maxWorkers, timeout } = get();
    try {
      await window.electronAPI.saveSettings({
        entrezEmail,
        outputDir,
        maxWorkers,
        timeout,
      });
      useUIStore.getState().addToast({
        type: 'success',
        message: 'Settings saved',
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save settings';
      useUIStore.getState().addToast({ type: 'error', message });
    }
  },
}));
