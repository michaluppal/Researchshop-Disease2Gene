import Store from 'electron-store'
import { join } from 'path'
import { getKey } from './key-manager'

export interface SettingsSchema {
  geminiApiKey: string
  entrezEmail: string
  outputDirectory: string
  theme: 'light' | 'dark' | 'system'
  onboardingComplete: boolean
  parallelAnalysis: boolean
}

const DEFAULTS: SettingsSchema = {
  geminiApiKey: '',
  entrezEmail: '',
  outputDirectory: '',
  theme: 'system',
  onboardingComplete: false,
  parallelAnalysis: false
}

let _store: Store<SettingsSchema> | null = null

function getStore(): Store<SettingsSchema> {
  if (!_store) {
    _store = new Store<SettingsSchema>({
      name: 'settings',
      encryptionKey: getKey(),
      defaults: DEFAULTS
    })
  }
  return _store
}

export function getSettings(): SettingsSchema {
  const s = getStore()
  return {
    geminiApiKey: s.get('geminiApiKey'),
    entrezEmail: s.get('entrezEmail'),
    outputDirectory: s.get('outputDirectory'),
    theme: s.get('theme'),
    onboardingComplete: s.get('onboardingComplete'),
    parallelAnalysis: s.get('parallelAnalysis')
  }
}

export function setSetting<K extends keyof SettingsSchema>(key: K, value: SettingsSchema[K]): void {
  getStore().set(key, value)
}

export function getDefaultOutputDir(): string {
  const home = process.env.HOME || process.env.USERPROFILE || ''
  return join(home, 'Documents', 'ResearchShop')
}

// Lazy proxy so any code that imported { settingsStore } still works
export const settingsStore = new Proxy({} as Store<SettingsSchema>, {
  get(_target, prop) {
    return (getStore() as unknown as Record<string | symbol, unknown>)[prop]
  }
})
