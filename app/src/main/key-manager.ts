import { app, safeStorage } from 'electron'
import Store from 'electron-store'
import crypto from 'crypto'

interface KeyStoreSchema {
  encryptedKey: string
}

let _key: string | null = null

export async function initEncryptionKey(): Promise<void> {
  await app.whenReady()

  if (!safeStorage.isEncryptionAvailable()) {
    // Fallback: derive from app data path — not OS-keychain-protected, but not hardcoded
    console.warn(
      '[key-manager] safeStorage unavailable — using derived fallback key (not OS-keychain-protected)'
    )
    _key = crypto.createHash('sha256').update(app.getPath('userData')).digest('hex')
    return
  }

  let keyStore: Store<KeyStoreSchema>
  try {
    keyStore = new Store<KeyStoreSchema>({ name: 'keystore' })
  } catch (err) {
    // keystore file corrupted — fall back to generating a fresh key (user must re-enter API key)
    console.warn('[key-manager] keystore unreadable — generating new key. User must re-enter API key.', err)
    _key = crypto.randomBytes(32).toString('hex')
    return
  }
  const stored = keyStore.get('encryptedKey', '')

  if (stored) {
    try {
      _key = safeStorage.decryptString(Buffer.from(stored, 'base64'))
      return
    } catch (err) {
      console.warn(
        '[key-manager] Failed to decrypt stored key — regenerating. User must re-enter API key.',
        err
      )
    }
  }

  // Generate new per-install key
  const newKey = crypto.randomBytes(32).toString('hex')
  const encrypted = safeStorage.encryptString(newKey)
  keyStore.set('encryptedKey', Buffer.from(encrypted).toString('base64'))
  _key = newKey
}

export function getKey(): string {
  if (!_key) throw new Error('[key-manager] Encryption key not initialized — call initEncryptionKey() first')
  return _key
}

export function migrateFromHardcodedKey(): void {
  const OLD_KEY = 'researchshop-desktop-v1'
  try {
    const oldStore = new Store<Record<string, unknown>>({
      name: 'settings',
      encryptionKey: OLD_KEY
    })
    const geminiApiKey = oldStore.get('geminiApiKey', '') as string
    if (!geminiApiKey) return // Nothing to migrate

    // Import lazily to avoid circular init order issues
    const { setSetting } =
      require('./settings-store') as typeof import('./settings-store')
    const fields = [
      'geminiApiKey',
      'entrezEmail',
      'outputDirectory',
      'theme',
      'onboardingComplete'
    ] as const
    for (const field of fields) {
      const val = oldStore.get(field)
      if (val !== undefined && val !== null && val !== '') {
        setSetting(field as keyof import('./settings-store').SettingsSchema, val as never)
      }
    }
    oldStore.clear()
    console.log('[key-manager] Migrated settings from legacy encryption key')
  } catch {
    // Old store unreadable (already migrated, or never existed) — skip silently
  }
}
