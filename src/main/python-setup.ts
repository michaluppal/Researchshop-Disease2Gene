import { spawn, execSync } from 'child_process'
import { BrowserWindow } from 'electron'
import { join } from 'path'
import { existsSync } from 'fs'
import { app } from 'electron'

function getPythonDir(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'python')
  }
  return join(__dirname, '../../python')
}

function getVenvPython(pythonDir: string): string {
  if (process.platform === 'win32') {
    return join(pythonDir, '.venv', 'Scripts', 'python.exe')
  }
  return join(pythonDir, '.venv', 'bin', 'python3')
}

function send(channel: string, data: unknown): void {
  const win = BrowserWindow.getAllWindows()[0]
  win?.webContents.send(channel, data)
}

function sendProgress(stage: string, message: string): void {
  send('python-setup:progress', { stage, message })
}

function sendLog(line: string): void {
  send('python-setup:log', line)
}

function parseVersion(versionStr: string): number[] {
  const match = versionStr.match(/Python (\d+)\.(\d+)\.(\d+)/)
  if (!match) return [0, 0, 0]
  return [parseInt(match[1]), parseInt(match[2]), parseInt(match[3])]
}

function findSystemPython(): string {
  // Search common paths explicitly — packaged .app bundles don't inherit shell PATH
  const candidates = [
    '/opt/homebrew/bin/python3',
    '/usr/local/bin/python3',
    '/opt/homebrew/bin/python3.13',
    '/opt/homebrew/bin/python3.12',
    '/opt/homebrew/bin/python3.11',
    '/opt/homebrew/bin/python3.10',
    '/usr/local/bin/python3.13',
    '/usr/local/bin/python3.12',
    '/usr/local/bin/python3.11',
    '/usr/local/bin/python3.10',
    'python3',
    '/usr/bin/python3',
    'python',
  ]

  let bestCmd: string | null = null
  let bestVersion: number[] = [0, 0, 0]

  for (const cmd of candidates) {
    try {
      if (cmd.startsWith('/') && !existsSync(cmd)) continue
      const version = execSync(`"${cmd}" --version`, { stdio: 'pipe', timeout: 5000 }).toString().trim()
      const parsed = parseVersion(version)
      if (parsed[0] >= 3 && parsed[1] >= 10) {
        sendLog(`$ ${cmd} --version`)
        sendLog(version)
        return cmd
      }
      if (parsed[0] >= 3 && (parsed[1] > bestVersion[1] || (parsed[1] === bestVersion[1] && parsed[2] > bestVersion[2]))) {
        bestCmd = cmd
        bestVersion = parsed
      }
    } catch {
      continue
    }
  }

  if (bestCmd) {
    sendLog(`$ ${bestCmd} --version`)
    sendLog(`Python ${bestVersion.join('.')} (warning: 3.10+ recommended)`)
    return bestCmd
  }

  throw new Error(
    'Python 3 not found. Please install Python 3.10+ (e.g. via Homebrew: brew install python3).'
  )
}

function runSpawn(command: string, args: string[], cwd: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const cmdStr = `$ ${command} ${args.join(' ')}`
    sendLog(cmdStr)

    const proc = spawn(command, args, { cwd, env: { ...process.env }, stdio: 'pipe' })
    let stderr = ''

    proc.stdout?.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n')
      for (const line of lines) {
        if (line.trim()) sendLog(line)
      }
    })

    proc.stderr?.on('data', (data: Buffer) => {
      stderr += data.toString()
      const lines = data.toString().split('\n')
      for (const line of lines) {
        if (line.trim()) sendLog(line)
      }
    })

    proc.on('close', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`Command failed (exit ${code}): ${stderr.slice(-500)}`))
    })
    proc.on('error', (err) => reject(err))
  })
}

export async function ensurePythonEnv(): Promise<{ ready: boolean; error?: string }> {
  try {
    const pythonDir = getPythonDir()
    const venvPython = getVenvPython(pythonDir)
    const requirementsPath = join(pythonDir, 'requirements.txt')

    sendLog('ResearchShop Python Environment Setup')
    sendLog('='.repeat(50))
    sendLog('')

    if (!existsSync(requirementsPath)) {
      return { ready: false, error: `requirements.txt not found at ${requirementsPath}` }
    }

    let needsSetup = false

    if (existsSync(venvPython)) {
      sendProgress('checking', 'Verifying Python dependencies...')
      sendLog(`[check] Found venv at ${venvPython}`)
      sendLog(`[check] Verifying installed packages...`)
      try {
        // Use pip list instead of importing — google.genai import takes 2+ minutes cold
        const pipList = execSync(`"${venvPython}" -m pip list --format=columns`, {
          stdio: 'pipe',
          timeout: 15000
        }).toString().toLowerCase()
        const required = ['google-genai', 'pandas', 'tqdm', 'biopython', 'trafilatura', 'lxml', 'pdfminer']
        const missing = required.filter(pkg => !pipList.includes(pkg))
        if (missing.length === 0) {
          sendLog('[check] All dependencies verified ✓')
          sendLog('')
          sendProgress('ready', 'Python environment is ready')
          return { ready: true }
        }
        sendLog(`[check] Missing packages: ${missing.join(', ')}`)
        needsSetup = true
      } catch {
        sendLog('[check] Could not verify packages, reinstalling...')
        sendLog('')
        needsSetup = true
      }
    } else {
      sendLog('[check] No virtual environment found')
      sendLog('')
      needsSetup = true
    }

    if (needsSetup) {
      sendProgress('finding-python', 'Looking for Python 3...')
      sendLog('[setup] Searching for Python 3 installation...')
      const systemPython = findSystemPython()
      sendLog(`[setup] Using: ${systemPython}`)
      sendLog('')

      if (!existsSync(venvPython)) {
        sendProgress('creating-venv', 'Creating virtual environment...')
        sendLog('[venv] Creating isolated virtual environment...')
        await runSpawn(systemPython, ['-m', 'venv', join(pythonDir, '.venv')], pythonDir)
        sendLog('[venv] Virtual environment created ✓')
        sendLog('')
      }

      sendProgress('installing', 'Installing dependencies...')
      sendLog('[pip] Installing packages from requirements.txt...')
      sendLog('')
      await runSpawn(venvPython, ['-m', 'pip', 'install', '--no-input', '-r', requirementsPath], pythonDir)
      sendLog('')
      sendLog('[pip] All packages installed ✓')
      sendLog('')

      sendProgress('verifying', 'Verifying installation...')
      sendLog('[verify] Checking installed packages...')
      try {
        const pipList = execSync(`"${venvPython}" -m pip list --format=columns`, {
          stdio: 'pipe',
          timeout: 15000
        }).toString().toLowerCase()
        const required = ['google-genai', 'pandas', 'tqdm', 'biopython', 'trafilatura', 'lxml', 'pdfminer']
        const missing = required.filter(pkg => !pipList.includes(pkg))
        if (missing.length > 0) {
          return {
            ready: false,
            error: `Missing packages after install: ${missing.join(', ')}`
          }
        }
        sendLog('[verify] All packages installed ✓')
      } catch (err) {
        return {
          ready: false,
          error: `Verification failed: ${err instanceof Error ? err.message : String(err)}`
        }
      }

      sendLog('')
      sendLog('Setup complete. Starting ResearchShop...')
      sendProgress('ready', 'Python environment is ready')
      return { ready: true }
    }

    return { ready: true }
  } catch (err) {
    return { ready: false, error: err instanceof Error ? err.message : String(err) }
  }
}
