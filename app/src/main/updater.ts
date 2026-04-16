import { autoUpdater } from 'electron-updater'
import { BrowserWindow, app } from 'electron'
import log from 'electron-log'

// Route electron-updater logs through electron-log
autoUpdater.logger = log

// Don't auto-download — let the user decide
autoUpdater.autoDownload = false
autoUpdater.autoInstallOnAppQuit = true

export interface UpdateInfo {
  status: 'checking' | 'available' | 'not-available' | 'downloading' | 'downloaded' | 'error'
  version?: string
  releaseNotes?: string
  percent?: number
  error?: string
}

function broadcast(channel: string, data: unknown): void {
  BrowserWindow.getAllWindows().forEach(win => {
    if (!win.isDestroyed()) win.webContents.send(channel, data)
  })
}

export function initAutoUpdater(): void {
  // Skip updates in dev mode
  if (!app.isPackaged) {
    log.info('Auto-updater: skipped (dev mode)')
    return
  }

  autoUpdater.on('checking-for-update', () => {
    broadcast('updater:status', { status: 'checking' } satisfies UpdateInfo)
  })

  autoUpdater.on('update-available', (info) => {
    broadcast('updater:status', {
      status: 'available',
      version: info.version,
      releaseNotes: typeof info.releaseNotes === 'string' ? info.releaseNotes : undefined
    } satisfies UpdateInfo)
  })

  autoUpdater.on('update-not-available', () => {
    broadcast('updater:status', { status: 'not-available' } satisfies UpdateInfo)
  })

  autoUpdater.on('download-progress', (progress) => {
    broadcast('updater:status', {
      status: 'downloading',
      percent: Math.round(progress.percent)
    } satisfies UpdateInfo)
  })

  autoUpdater.on('update-downloaded', (info) => {
    broadcast('updater:status', {
      status: 'downloaded',
      version: info.version
    } satisfies UpdateInfo)
  })

  autoUpdater.on('error', (err) => {
    log.error('Auto-updater error:', err)
    broadcast('updater:status', {
      status: 'error',
      error: err.message
    } satisfies UpdateInfo)
  })

  // Check for updates 5 seconds after launch (don't block startup)
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((err) => {
      log.warn('Update check failed:', err.message)
    })
  }, 5000)

  // Then check every 4 hours
  setInterval(() => {
    autoUpdater.checkForUpdates().catch((err) => {
      log.warn('Periodic update check failed:', err.message)
    })
  }, 4 * 60 * 60 * 1000)
}

export function downloadUpdate(): void {
  autoUpdater.downloadUpdate().catch((err) => {
    log.error('Download update failed:', err)
    broadcast('updater:status', {
      status: 'error',
      error: err.message
    } satisfies UpdateInfo)
  })
}

export function installUpdate(): void {
  autoUpdater.quitAndInstall(false, true)
}
