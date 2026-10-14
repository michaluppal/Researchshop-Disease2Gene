#!/usr/bin/env node
/**
 * Download a private CPython and install pipeline/requirements.txt into it.
 * electron-builder copies build/python-runtime into the app, so a person
 * who installs the DMG or EXE never needs Python or pip on their computer.
 */
import { createHash } from 'crypto'
import { spawnSync } from 'child_process'
import { createWriteStream, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'
import { Readable } from 'stream'
import { pipeline } from 'stream/promises'
import { fileURLToPath } from 'url'

const RELEASE = '20261013'
const VERSION = '3.12.15'
const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dest = join(root, 'build', 'python-runtime')
const requirements = join(root, 'pipeline', 'requirements.txt')

function archiveName() {
  const tag = `cpython-${VERSION}+${RELEASE}`
  if (process.platform === 'darwin' && process.arch === 'arm64') {
    return `${tag}-aarch64-apple-darwin-install_only.tar.gz`
  }
  if (process.platform === 'darwin' && process.arch === 'x64') {
    return `${tag}-x86_64-apple-darwin-install_only.tar.gz`
  }
  if (process.platform === 'win32' && process.arch === 'x64') {
    return `${tag}-x86_64-pc-windows-msvc-install_only.tar.gz`
  }
  if (process.platform === 'linux' && process.arch === 'x64') {
    return `${tag}-x86_64-unknown-linux-gnu-install_only.tar.gz`
  }
  if (process.platform === 'linux' && process.arch === 'arm64') {
    return `${tag}-aarch64-unknown-linux-gnu-install_only.tar.gz`
  }
  throw new Error(`No private Python build for ${process.platform} ${process.arch}`)
}

function pythonBin() {
  if (process.platform === 'win32') return join(dest, 'python', 'python.exe')
  return join(dest, 'python', 'bin', 'python3')
}

const archive = archiveName()
const reqHash = createHash('sha256').update(readFileSync(requirements)).digest('hex').slice(0, 16)
const marker = join(dest, '.bundle-complete')
const stamp = `${archive}\n${reqHash}\n`

if (existsSync(marker) && readFileSync(marker, 'utf8') === stamp && existsSync(pythonBin())) {
  console.log(`[bundle-python] already ready (${archive})`)
  process.exit(0)
}

console.log(`[bundle-python] preparing ${archive}`)
rmSync(dest, { recursive: true, force: true })
mkdirSync(dest, { recursive: true })

const url = `https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE}/${archive}`
const archivePath = join(root, 'build', archive)
if (!existsSync(archivePath)) {
  console.log(`[bundle-python] downloading ${url}`)
  const response = await fetch(url, { headers: { 'User-Agent': 'ResearchShop' } })
  if (!response.ok || !response.body) {
    console.error(`[bundle-python] download failed (${response.status})`)
    process.exit(1)
  }
  await pipeline(Readable.fromWeb(response.body), createWriteStream(archivePath))
} else {
  console.log(`[bundle-python] using ${archivePath}`)
}

const extracted = spawnSync('tar', ['-xzf', archivePath, '-C', dest], { stdio: 'inherit' })
if (extracted.status !== 0) process.exit(extracted.status ?? 1)

const python = pythonBin()
if (!existsSync(python)) {
  console.error(`[bundle-python] ${python} is missing after extract`)
  process.exit(1)
}

console.log('[bundle-python] installing research packages')
const pipEnv = { ...process.env, PIP_DISABLE_PIP_VERSION_CHECK: '1', PYTHONNOUSERSITE: '1' }
if (process.platform === 'win32') {
  const systemRoot = process.env.SystemRoot || 'C:\\Windows'
  pipEnv.PATH = [join(dest, 'python'), join(dest, 'python', 'Scripts'), join(systemRoot, 'System32'), systemRoot].join(';')
}
const pip = spawnSync(
  python,
  ['-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', '-r', requirements],
  { stdio: 'inherit', env: pipEnv }
)
if (pip.status !== 0) process.exit(pip.status ?? 1)

const check = spawnSync(
  python,
  ['-c', 'import google.genai, pandas, tqdm, Bio, trafilatura, lxml, lxml_html_clean, pdfminer, pubmed_parser, openpyxl, requests'],
  { stdio: 'inherit' }
)
if (check.status !== 0) process.exit(check.status ?? 1)

writeFileSync(marker, stamp)
console.log(`[bundle-python] ready ${python}`)
