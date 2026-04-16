#!/usr/bin/env node
/**
 * Build a compact SJR journal lookup from the Scimago CSV download.
 *
 * Usage:
 *   node app/scripts/build-sjr-lookup.js [path/to/scimagojr.csv]
 *
 * Default input:  scimagojr.csv in repo root (or first CLI arg)
 * Output:         app/src/renderer/data/sjr-lookup.json
 *
 * The output JSON has two maps:
 *   byIssn  — ISSN (hyphenated, e.g. "0028-0836") → { q, sjr, name }
 *   byName  — normalized journal name → { q, sjr }
 */

const fs = require('fs')
const path = require('path')

// __dirname = app/scripts; repo root = ../..
const repoRoot = path.join(__dirname, '..', '..')
const inputPath = process.argv[2] || path.join(repoRoot, 'scimagojr.csv')
const outputPath = path.join(repoRoot, 'app', 'src', 'renderer', 'data', 'sjr-lookup.json')

if (!fs.existsSync(inputPath)) {
  console.error(`SJR CSV not found at: ${inputPath}`)
  console.error('Download from https://www.scimagojr.com/journalrank.php')
  process.exit(1)
}

const raw = fs.readFileSync(inputPath, 'utf-8')
const lines = raw.split('\n').filter(l => l.trim())
const header = lines[0].split(';')

// Find column indices
const col = (name) => {
  const idx = header.indexOf(name)
  if (idx === -1) throw new Error(`Column "${name}" not found. Headers: ${header.join(', ')}`)
  return idx
}

const iTitle = col('Title')
const iIssn = col('Issn')
const iSjr = col('SJR')
const iQuartile = col('SJR Best Quartile')

function normalizeJournalName(name) {
  return name.toLowerCase().replace(/^the\s+/i, '').replace(/[^\w\s]/g, '').trim()
}

function formatIssn(raw) {
  // SJR gives ISSNs without hyphens (e.g. "00280836"). PubMed gives them with hyphens ("0028-0836").
  // Normalize to hyphenated 8-char format.
  const digits = raw.replace(/\D/g, '')
  if (digits.length === 8) return `${digits.slice(0, 4)}-${digits.slice(4)}`
  return raw.trim()
}

const Q_RANK = { Q1: 1, Q2: 2, Q3: 3, Q4: 4 }
const byIssn = {}
const byName = {}
let skipped = 0

for (let i = 1; i < lines.length; i++) {
  // SJR CSV uses semicolons as delimiter but also within quoted fields.
  // Fields are quoted with double quotes when they contain semicolons.
  const fields = []
  let field = ''
  let inQuotes = false
  for (const ch of lines[i]) {
    if (ch === '"') {
      inQuotes = !inQuotes
    } else if (ch === ';' && !inQuotes) {
      fields.push(field)
      field = ''
    } else {
      field += ch
    }
  }
  fields.push(field)

  const title = (fields[iTitle] || '').trim()
  const issnRaw = (fields[iIssn] || '').trim()
  const sjrRaw = (fields[iSjr] || '').replace(',', '.').trim()
  const quartile = (fields[iQuartile] || '').trim()

  if (!quartile || !['Q1', 'Q2', 'Q3', 'Q4'].includes(quartile)) {
    skipped++
    continue
  }

  const sjr = parseFloat(sjrRaw) || 0
  // Index by each ISSN (store quartile string only — keeps JSON small)
  const issns = issnRaw.split(',').map(s => formatIssn(s.trim())).filter(s => s.length >= 8)
  for (const issn of issns) {
    byIssn[issn] = quartile
  }

  // Index by normalized name
  const normName = normalizeJournalName(title)
  if (normName) {
    // Keep the higher-SJR entry if name collides
    const existing = byName[normName]
    if (!existing || Q_RANK[existing] > Q_RANK[quartile]) {
      byName[normName] = quartile
    }
  }
}

// Ensure output directory exists
const outDir = path.dirname(outputPath)
if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true })
}

const output = { byIssn, byName }
fs.writeFileSync(outputPath, JSON.stringify(output), 'utf-8')

const issnCount = Object.keys(byIssn).length
const nameCount = Object.keys(byName).length
const sizeKB = Math.round(fs.statSync(outputPath).size / 1024)

console.log(`SJR lookup built:`)
console.log(`  ${issnCount} ISSN entries`)
console.log(`  ${nameCount} name entries`)
console.log(`  ${skipped} journals skipped (no quartile)`)
console.log(`  Output: ${outputPath} (${sizeKB} KB)`)
