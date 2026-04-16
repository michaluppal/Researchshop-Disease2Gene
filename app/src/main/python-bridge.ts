import { ChildProcess, spawn, execSync } from 'child_process'
import { BrowserWindow } from 'electron'
import { join } from 'path'
import { existsSync } from 'fs'
import { getSettings } from './settings-store'
import { updateJob, getJob } from './job-store'
import { addGeminiApiCalls } from './usage-store'
import { app } from 'electron'

export interface PipelineArgs {
  query: string
  pmids: string[]
  authors: string[]
  columns: Record<string, string>
  topN: number
}

// Payload type guards for Python stdout protocol
function isProgressPayload(p: unknown): p is { stage: string; percent: number; stats: Record<string, number> } {
  return typeof p === 'object' && p !== null && 'stage' in p && 'percent' in p
}
function isLogPayload(p: unknown): p is { level: string; msg: string; detail?: string | null } {
  return typeof p === 'object' && p !== null && 'level' in p && 'msg' in p
}
function isResultPayload(p: unknown): p is { local_path?: string; metadata_path?: string; excel_path?: string; json_path?: string; error?: string } {
  return typeof p === 'object' && p !== null
}

let currentProcess: ChildProcess | null = null
let currentJobId: string | null = null
let lastJobApiCalls = 0 // tracks cumulative count for current job (delta calculation)

function getPythonPath(): string {
  // Prefer the bundled venv if it exists
  const pythonDir = getPythonDir()
  const venvCandidates = [
    join(pythonDir, '.venv', 'bin', 'python3'),
    join(pythonDir, '.venv', 'Scripts', 'python.exe'),
  ]
  for (const venvPython of venvCandidates) {
    if (existsSync(venvPython)) return venvPython
  }

  const candidates = ['python3', 'python']
  for (const cmd of candidates) {
    try {
      execSync(`${cmd} --version`, { stdio: 'pipe' })
      return cmd
    } catch {
      continue
    }
  }
  throw new Error('Python 3 not found. Please install Python 3 and ensure it is in your PATH.')
}

function getPythonDir(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'pipeline')
  }
  // Dev: __dirname is out/main at runtime → ../../pipeline
  return join(__dirname, '../../pipeline')
}

export function startPipeline(jobId: string, args: PipelineArgs): void {
  const settings = getSettings()
  const pythonPath = getPythonPath()
  const pythonDir = getPythonDir()
  const scriptPath = join(pythonDir, 'run_pipeline.py')

  if (!existsSync(scriptPath)) {
    throw new Error(`Pipeline script not found at ${scriptPath}`)
  }

  currentJobId = jobId
  lastJobApiCalls = 0

  const spawnArgs = [
    scriptPath,
    '--query', args.query,
    '--pmids', JSON.stringify(args.pmids),
    '--authors', JSON.stringify(args.authors),
    '--columns', JSON.stringify(args.columns),
    '--top-n', String(args.topN || 9999),
    '--output-dir', settings.outputDirectory
  ]

  // Pass secrets via environment variables, never as CLI args (visible in `ps aux`)
  currentProcess = spawn(pythonPath, spawnArgs, {
    cwd: pythonDir,
    env: {
      ...process.env,
      GEMINI_API_KEY: settings.geminiApiKey,
      ENTREZ_EMAIL: settings.entrezEmail,
      PARALLEL_ANALYSIS: settings.parallelAnalysis ? 'true' : 'false',
    }
  })
  updateJob(jobId, {
    status: 'running',
    error: null,
    completed_at: null
  })

  const mainWindow = BrowserWindow.getAllWindows()[0]

  let buffer = ''
  currentProcess.stdout?.on('data', (data: Buffer) => {
    buffer += data.toString()
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('PROGRESS:')) {
        try {
          const raw = JSON.parse(line.slice(9))
          if (!isProgressPayload(raw)) {
            console.error('[python-bridge] Invalid PROGRESS payload:', line.slice(0, 200))
          } else {
            // Accumulate Gemini API calls incrementally — store write happens before
            // the IPC send so the renderer's getDailyUsage() reads an up-to-date value
            if (raw.stats?.gemini_api_calls != null) {
              const current = raw.stats.gemini_api_calls as number
              const delta = current - lastJobApiCalls
              if (delta > 0) {
                addGeminiApiCalls(delta)
                lastJobApiCalls = current
              }
            }
            mainWindow?.webContents.send('pipeline:progress', raw)
            if (raw.stats) {
              updateJob(jobId, { stats: JSON.stringify(raw.stats) })
            }
          }
        } catch {
          console.error('[python-bridge] Failed to parse PROGRESS line:', line.slice(0, 200))
        }
      } else if (line.startsWith('LOG:')) {
        try {
          const raw = JSON.parse(line.slice(4))
          if (!isLogPayload(raw)) {
            console.error('[python-bridge] Invalid LOG payload:', line.slice(0, 200))
          } else {
            mainWindow?.webContents.send('pipeline:structured-log', {
              type: 'log',
              level: raw.level,
              msg: raw.msg,
              detail: raw.detail || null,
              timestamp: new Date().toISOString()
            })
          }
        } catch {
          console.error('[python-bridge] Failed to parse LOG line:', line.slice(0, 200))
        }
      } else if (line.startsWith('RESULT:')) {
        try {
          const raw = JSON.parse(line.slice(7))
          if (!isResultPayload(raw)) {
            console.error('[python-bridge] Invalid RESULT payload:', line.slice(0, 200))
          } else {
            const job = getJob(jobId)
            if (job?.status === 'cancelled') {
              continue
            }
            mainWindow?.webContents.send('pipeline:result', raw)
            if (raw.error) {
              updateJob(jobId, {
                status: 'failed',
                error: raw.error,
                completed_at: new Date().toISOString()
              })
            } else {
              updateJob(jobId, {
                status: 'completed',
                result_path: raw.local_path || null,
                metadata_path: raw.metadata_path || null,
                excel_path: raw.excel_path || null,
                json_path: raw.json_path || null,
                completed_at: new Date().toISOString()
              })
            }
          }
        } catch {
          console.error('[python-bridge] Failed to parse RESULT line:', line.slice(0, 200))
        }
      }
    }
  })

  currentProcess.stderr?.on('data', (data: Buffer) => {
    const text = data.toString()
    mainWindow?.webContents.send('pipeline:log', text)
  })

  currentProcess.on('close', (code) => {
    mainWindow?.webContents.send('pipeline:exit', { code })

    // If process exited without a RESULT line, mark as failed
    if (currentJobId === jobId) {
      const job = getJob(jobId)
      if (job?.status === 'running') {
        updateJob(jobId, {
          status: code === 0 ? 'completed' : 'failed',
          error: code !== 0 ? `Process exited with code ${code}` : null,
          completed_at: new Date().toISOString()
        })
      } else if (job?.status === 'cancelled' && !job.completed_at) {
        updateJob(jobId, {
          completed_at: new Date().toISOString()
        })
      }
      currentJobId = null
    }
    currentProcess = null
    lastJobApiCalls = 0
  })

  currentProcess.on('error', (err) => {
    mainWindow?.webContents.send('pipeline:error', { message: err.message })
    const job = getJob(jobId)
    if (job?.status !== 'cancelled') {
      updateJob(jobId, {
        status: 'failed',
        error: err.message,
        completed_at: new Date().toISOString()
      })
    }
    currentJobId = null
    currentProcess = null
    lastJobApiCalls = 0
  })
}

export function cancelPipeline(): boolean {
  if (currentProcess) {
    if (currentJobId) {
      updateJob(currentJobId, {
        status: 'cancelled',
        completed_at: new Date().toISOString()
      })
    }
    return currentProcess.kill('SIGTERM')
  }
  return false
}

export function isPipelineRunning(): boolean {
  return currentProcess !== null
}
