import { spawn, execSync } from 'child_process'
import { BrowserWindow } from 'electron'
import { join } from 'path'
import { createWriteStream, existsSync, mkdirSync, rmSync } from 'fs'
import { Readable } from 'stream'
import { pipeline } from 'stream/promises'
import { app } from 'electron'

const PYTHON_RELEASE = '20261013'
const PYTHON_VERSION = '3.12.15'

function getPythonDir(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'pipeline')
  }
  // Dev: __dirname is out/main at runtime → ../../pipeline
  return join(__dirname, '../../pipeline')
}

function getVenvDir(pythonDir: string): string {
  if (app.isPackaged) {
    return join(app.getPath('userData'), 'python', '.venv')
  }
  return join(pythonDir, '.venv')
}

function getVenvPython(venvDir: string): string {
  if (process.platform === 'win32') {
    return join(venvDir, 'Scripts', 'python.exe')
  }
  return join(venvDir, 'bin', 'python3')
}

function getBundledPython(): string {
  const root = app.isPackaged
    ? join(process.resourcesPath, 'python-runtime')
    : join(__dirname, '../../build/python-runtime')
  if (process.platform === 'win32') return join(root, 'python', 'python.exe')
  return join(root, 'python', 'bin', 'python3')
}

function getRuntimeDir(): string {
  return join(app.getPath('userData'), 'python', 'runtime')
}

function getRuntimePython(): string {
  if (process.platform === 'win32') {
    return join(getRuntimeDir(), 'python', 'python.exe')
  }
  return join(getRuntimeDir(), 'python', 'bin', 'python3')
}

function pythonArchiveName(): string {
  const tag = `cpython-${PYTHON_VERSION}+${PYTHON_RELEASE}`
  if (process.platform === 'win32' && process.arch === 'x64') {
    return `${tag}-x86_64-pc-windows-msvc-install_only.tar.gz`
  }
  if (process.platform === 'darwin' && process.arch === 'arm64') {
    return `${tag}-aarch64-apple-darwin-install_only.tar.gz`
  }
  if (process.platform === 'darwin' && process.arch === 'x64') {
    return `${tag}-x86_64-apple-darwin-install_only.tar.gz`
  }
  if (process.platform === 'linux' && process.arch === 'x64') {
    return `${tag}-x86_64-unknown-linux-gnu-install_only.tar.gz`
  }
  if (process.platform === 'linux' && process.arch === 'arm64') {
    return `${tag}-aarch64-unknown-linux-gnu-install_only.tar.gz`
  }
  throw new Error('This computer type is not supported yet.')
}

export function getPipelinePython(): string {
  const bundled = getBundledPython()
  if (existsSync(bundled)) return bundled
  if (app.isPackaged) {
    const runtimePython = getRuntimePython()
    if (existsSync(runtimePython)) return runtimePython
    throw new Error('ResearchShop is still preparing. Open the app again.')
  }

  const pythonDir = getPythonDir()
  const venvDir = getVenvDir(pythonDir)
  const venvCandidates = [
    join(venvDir, 'bin', 'python3'),
    join(venvDir, 'Scripts', 'python.exe'),
  ]
  for (const venvPython of venvCandidates) {
    if (existsSync(venvPython)) return venvPython
  }
  return process.platform === 'win32' ? 'python' : 'python3'
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

  throw new Error('Python 3.10 or newer was not found for this development run.')
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

function hasPip(python: string): boolean {
  try {
    execSync(`"${python}" -m pip --version`, { stdio: 'pipe', timeout: 20000 })
    return true
  } catch {
    return false
  }
}

async function downloadPrivatePython(): Promise<string> {
  const runtimeDir = getRuntimeDir()
  const python = getRuntimePython()
  if (existsSync(python) && hasPip(python)) return python

  sendProgress('downloading', 'Downloading ResearchShop components...')
  sendLog('[setup] Downloading the private Python runtime...')
  rmSync(runtimeDir, { recursive: true, force: true })
  mkdirSync(runtimeDir, { recursive: true })

  const archiveName = pythonArchiveName()
  const archivePath = join(app.getPath('temp'), archiveName)
  const url = `https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_RELEASE}/${archiveName}`
  const response = await fetch(url, { headers: { 'User-Agent': 'ResearchShop' } })
  if (!response.ok || !response.body) {
    throw new Error('ResearchShop could not download its components. Check the internet connection and open the app again.')
  }
  await pipeline(Readable.fromWeb(response.body as import('stream/web').ReadableStream), createWriteStream(archivePath))

  sendProgress('extracting', 'Preparing ResearchShop...')
  await runSpawn('tar', ['-xzf', archivePath, '-C', runtimeDir], runtimeDir)
  if (!existsSync(python) || !hasPip(python)) {
    throw new Error('ResearchShop could not prepare its research tools. Open the app again.')
  }
  sendLog('[setup] Private Python runtime is ready')
  return python
}

const REQUIRED_PACKAGES = ['google-genai', 'pandas', 'tqdm', 'biopython', 'trafilatura', 'lxml', 'pdfminer']

function missingPackages(python: string): string[] | null {
  try {
    const pipList = execSync(`"${python}" -m pip list --format=columns`, {
      stdio: 'pipe',
      timeout: 20000
    }).toString().toLowerCase()
    return REQUIRED_PACKAGES.filter(pkg => !pipList.includes(pkg))
  } catch {
    return null
  }
}

async function installRequirements(python: string, requirementsPath: string): Promise<void> {
  if (!hasPip(python)) {
    sendLog('[setup] Adding the package installer...')
    await runSpawn(python, ['-m', 'ensurepip', '--upgrade'], getPythonDir())
  }
  sendProgress('installing', 'Installing ResearchShop components...')
  sendLog('[setup] Installing research packages...')
  await runSpawn(python, ['-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', '-r', requirementsPath], getPythonDir())
  const missing = missingPackages(python)
  if (missing === null || missing.length > 0) {
    throw new Error('ResearchShop could not finish installing its research tools. Check the internet connection and open the app again.')
  }
}

function friendlySetupError(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err)
  if (/python 3\.10 or newer was not found/i.test(message)) return message
  if (/reinstall the app/i.test(message)) return message
  if (/internet connection/i.test(message)) return message
  if (/open the app again/i.test(message)) return message
  if (/still preparing/i.test(message)) return message
  return 'ResearchShop could not finish preparing. Check the internet connection and open the app again.'
}

async function ensureDevEnv(requirementsPath: string): Promise<{ ready: boolean; error?: string }> {
  const bundled = getBundledPython()
  if (existsSync(bundled)) {
    const bundledMissing = missingPackages(bundled)
    if (bundledMissing && bundledMissing.length === 0) {
      sendProgress('ready', 'ResearchShop is ready')
      return { ready: true }
    }
  }

  const pythonDir = getPythonDir()
  const venvDir = getVenvDir(pythonDir)
  const venvPython = getVenvPython(venvDir)

  sendLog('ResearchShop Python Environment Setup')
  sendLog('='.repeat(50))

  if (existsSync(venvPython)) {
    sendProgress('checking', 'Checking ResearchShop...')
    const missing = missingPackages(venvPython)
    if (missing && missing.length === 0) {
      sendProgress('ready', 'ResearchShop is ready')
      return { ready: true }
    }
    sendLog(missing ? `[check] Missing packages: ${missing.join(', ')}` : '[check] Could not verify packages')
  } else {
    sendProgress('finding-python', 'Preparing ResearchShop...')
    const systemPython = findSystemPython()
    sendLog(`[setup] Using: ${systemPython}`)
    await runSpawn(systemPython, ['-m', 'venv', venvDir], pythonDir)
  }

  await installRequirements(venvPython, requirementsPath)
  sendProgress('ready', 'ResearchShop is ready')
  return { ready: true }
}

async function ensurePackagedEnv(requirementsPath: string): Promise<{ ready: boolean; error?: string }> {
  sendProgress('checking', 'Preparing ResearchShop...')
  const bundled = getBundledPython()

  if (existsSync(bundled)) {
    const missing = missingPackages(bundled)
    if (missing && missing.length === 0) {
      sendLog('[setup] Bundled research tools are ready')
      sendProgress('ready', 'ResearchShop is ready')
      return { ready: true }
    }
    sendLog(missing ? `[setup] Bundled tools are incomplete (${missing.join(', ')})` : '[setup] Bundled tools could not be checked')
    try {
      await installRequirements(bundled, requirementsPath)
      sendProgress('ready', 'ResearchShop is ready')
      return { ready: true }
    } catch (err) {
      sendLog(`[setup] Could not update the installed copy: ${err instanceof Error ? err.message : String(err)}`)
    }
  } else {
    sendLog('[setup] Installed research tools were not found')
  }

  const python = await downloadPrivatePython()
  await installRequirements(python, requirementsPath)
  sendProgress('ready', 'ResearchShop is ready')
  return { ready: true }
}

export async function ensurePythonEnv(): Promise<{ ready: boolean; error?: string }> {
  try {
    const requirementsPath = join(getPythonDir(), 'requirements.txt')
    if (!existsSync(requirementsPath)) {
      return { ready: false, error: 'ResearchShop is missing part of its installation. Reinstall the app.' }
    }
    if (app.isPackaged) return await ensurePackagedEnv(requirementsPath)
    return await ensureDevEnv(requirementsPath)
  } catch (err) {
    return { ready: false, error: app.isPackaged ? friendlySetupError(err) : (err instanceof Error ? err.message : String(err)) }
  }
}
