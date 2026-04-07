import { contextBridge, ipcRenderer } from 'electron'

export interface ElectronAPI {
  settings: {
    get: () => Promise<{
      geminiApiKey: string
      entrezEmail: string
      outputDirectory: string
      theme: 'light' | 'dark' | 'system'
      onboardingComplete: boolean
      parallelAnalysis: boolean
    }>
    set: (key: string, value: unknown) => Promise<boolean>
    validateGeminiKey: (key: string) => Promise<{ valid: boolean; error?: string }>
  }
  pipeline: {
    start: (args: {
      query: string
      pmids: string[]
      authors: string[]
      columns: Record<string, string>
      topN: number
    }) => Promise<{ jobId?: string; error?: string }>
    cancel: () => Promise<{ cancelled: boolean }>
    onProgress: (
      callback: (data: { stage: string; percent: number; stats: Record<string, number> }) => void
    ) => () => void
    onResult: (callback: (data: { local_path?: string; metadata_path?: string; excel_path?: string; json_path?: string; error?: string }) => void) => () => void
    onLog: (callback: (text: string) => void) => () => void
    onStructuredLog: (
      callback: (data: { type: 'log'; level: string; msg: string; detail: string | null; timestamp: string }) => void
    ) => () => void
    onExit: (callback: (data: { code: number | null }) => void) => () => void
    onError: (callback: (data: { message: string }) => void) => () => void
  }
  results: {
    exists: (filePath: string) => Promise<{ exists: boolean }>
    load: (filePath: string) => Promise<{ content?: string; error?: string }>
    export: (defaultPath: string) => Promise<Electron.SaveDialogReturnValue>
  }
  history: {
    list: () => Promise<
      Array<{
        id: string
        query: string
        columns: string
        status: string
        created_at: string
        completed_at: string | null
        result_path: string | null
        metadata_path: string | null
        excel_path: string | null
        json_path: string | null
        stats: string | null
        error: string | null
      }>
    >
    get: (id: string) => Promise<unknown>
    delete: (id: string) => Promise<boolean>
  }
  dialog: {
    saveFile: (options: unknown) => Promise<unknown>
    openDirectory: () => Promise<unknown>
  }
  shell: {
    openExternal: (url: string) => Promise<boolean>
    openPath: (path: string) => Promise<boolean>
  }
  pubmed: {
    search: (query: string, retmax?: number) => Promise<{ count: number; pmids: string[]; error?: string }>
    fetchDetails: (pmids: string[]) => Promise<Record<string, { title: string; journal: string; authors: string[]; pubYear: string; doi?: string; pmc?: string; url: string; publicationTypes: string[] }>>
    fetchAbstracts: (pmids: string[]) => Promise<{ abstracts: Record<string, string>; error: string | null }>
    count: (query: string) => Promise<{ count: number }>
    expandQuery: (query: string) => Promise<{ expandedQuery?: string; changes?: string; error?: string }>
    buildQuery: (description: string) => Promise<{ query?: string; explanation?: string; error?: string }>
  }
  citations: {
    fetch: (pmids: string[]) => Promise<Record<string, number>>
  }
  app: {
    version: () => Promise<string>
  }
  updater: {
    onStatus: (callback: (data: {
      status: 'checking' | 'available' | 'not-available' | 'downloading' | 'downloaded' | 'error'
      version?: string
      releaseNotes?: string
      percent?: number
      error?: string
    }) => void) => () => void
    download: () => Promise<boolean>
    install: () => Promise<boolean>
  }
  gemini: {
    getDailyUsage: () => Promise<{ used: number; limit: number; date: string }>
    onUsageChanged: (callback: (data: { used: number; limit: number; date: string }) => void) => () => void
  }
  pythonSetup: {
    onProgress: (callback: (data: { stage: string; message: string }) => void) => () => void
    onLog: (callback: (line: string) => void) => () => void
    onComplete: (callback: (data: { ready: boolean; error?: string }) => void) => () => void
  }
}

const api: ElectronAPI = {
  settings: {
    get: () => ipcRenderer.invoke('settings:get'),
    set: (key, value) => ipcRenderer.invoke('settings:set', key, value),
    validateGeminiKey: (key) => ipcRenderer.invoke('settings:validate-gemini-key', key)
  },
  pipeline: {
    start: (args) => ipcRenderer.invoke('pipeline:start', args),
    cancel: () => ipcRenderer.invoke('pipeline:cancel'),
    onProgress: (callback) => {
      const handler = (_event: unknown, data: Parameters<typeof callback>[0]) => callback(data)
      ipcRenderer.on('pipeline:progress', handler)
      return () => ipcRenderer.removeListener('pipeline:progress', handler)
    },
    onResult: (callback) => {
      const handler = (_event: unknown, data: Parameters<typeof callback>[0]) => callback(data)
      ipcRenderer.on('pipeline:result', handler)
      return () => ipcRenderer.removeListener('pipeline:result', handler)
    },
    onLog: (callback) => {
      const handler = (_event: unknown, text: string) => callback(text)
      ipcRenderer.on('pipeline:log', handler)
      return () => ipcRenderer.removeListener('pipeline:log', handler)
    },
    onStructuredLog: (callback) => {
      const handler = (_event: unknown, data: Parameters<typeof callback>[0]) => callback(data)
      ipcRenderer.on('pipeline:structured-log', handler)
      return () => ipcRenderer.removeListener('pipeline:structured-log', handler)
    },
    onExit: (callback) => {
      const handler = (_event: unknown, data: Parameters<typeof callback>[0]) => callback(data)
      ipcRenderer.on('pipeline:exit', handler)
      return () => ipcRenderer.removeListener('pipeline:exit', handler)
    },
    onError: (callback) => {
      const handler = (_event: unknown, data: Parameters<typeof callback>[0]) => callback(data)
      ipcRenderer.on('pipeline:error', handler)
      return () => ipcRenderer.removeListener('pipeline:error', handler)
    }
  },
  results: {
    exists: (filePath) => ipcRenderer.invoke('results:exists', filePath),
    load: (filePath) => ipcRenderer.invoke('results:load', filePath),
    export: (defaultPath) => ipcRenderer.invoke('results:export', defaultPath)
  },
  history: {
    list: () => ipcRenderer.invoke('history:list'),
    get: (id) => ipcRenderer.invoke('history:get', id),
    delete: (id) => ipcRenderer.invoke('history:delete', id)
  },
  dialog: {
    saveFile: (options) => ipcRenderer.invoke('dialog:save-file', options),
    openDirectory: () => ipcRenderer.invoke('dialog:open-directory')
  },
  shell: {
    openExternal: (url) => ipcRenderer.invoke('shell:open-external', url),
    openPath: (path) => ipcRenderer.invoke('shell:open-path', path)
  },
  pubmed: {
    search: (query, retmax) => ipcRenderer.invoke('pubmed:search', query, retmax),
    fetchDetails: (pmids) => ipcRenderer.invoke('pubmed:fetch-details', pmids),
    fetchAbstracts: (pmids) => ipcRenderer.invoke('pubmed:fetch-abstracts', pmids),
    count: (query) => ipcRenderer.invoke('pubmed:count', query),
    expandQuery: (query) => ipcRenderer.invoke('pubmed:expand-query', query),
    buildQuery: (description) => ipcRenderer.invoke('pubmed:build-query', description)
  },
  citations: {
    fetch: (pmids) => ipcRenderer.invoke('citations:fetch', pmids)
  },
  app: {
    version: () => ipcRenderer.invoke('app:version')
  },
  updater: {
    onStatus: (callback) => {
      const handler = (_event: unknown, data: Parameters<typeof callback>[0]) => callback(data)
      ipcRenderer.on('updater:status', handler)
      return () => ipcRenderer.removeListener('updater:status', handler)
    },
    download: () => ipcRenderer.invoke('updater:download'),
    install: () => ipcRenderer.invoke('updater:install')
  },
  gemini: {
    getDailyUsage: () => ipcRenderer.invoke('gemini:getDailyUsage'),
    onUsageChanged: (callback) => {
      const handler = (_event: unknown, data: Parameters<typeof callback>[0]) => callback(data)
      ipcRenderer.on('gemini:usage-changed', handler)
      return () => ipcRenderer.removeListener('gemini:usage-changed', handler)
    }
  },
  pythonSetup: {
    onProgress: (callback) => {
      const handler = (_event: unknown, data: Parameters<typeof callback>[0]) => callback(data)
      ipcRenderer.on('python-setup:progress', handler)
      return () => ipcRenderer.removeListener('python-setup:progress', handler)
    },
    onLog: (callback) => {
      const handler = (_event: unknown, line: string) => callback(line)
      ipcRenderer.on('python-setup:log', handler)
      return () => ipcRenderer.removeListener('python-setup:log', handler)
    },
    onComplete: (callback) => {
      const handler = (_event: unknown, data: Parameters<typeof callback>[0]) => callback(data)
      ipcRenderer.on('python-setup:complete', handler)
      return () => ipcRenderer.removeListener('python-setup:complete', handler)
    }
  }
}

contextBridge.exposeInMainWorld('api', api)
