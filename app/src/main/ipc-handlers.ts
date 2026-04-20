import { ipcMain, dialog, shell, app, BrowserWindow } from 'electron'
import { getSettings, setSetting, getDefaultOutputDir, SettingsSchema } from './settings-store'
import { createJob, getJob, updateJob, listJobs, deleteJob } from './job-store'
import { startPipeline, cancelPipeline, isPipelineRunning, PipelineArgs } from './python-bridge'
import { getGeminiDailyUsage, addGeminiApiCalls } from './usage-store'
import { downloadUpdate, installUpdate } from './updater'
import { readFileSync, existsSync } from 'fs'
import { randomUUID } from 'crypto'
import path from 'node:path'

/**
 * Reverse-lookup DOIs to PubMed PMIDs via NCBI esearch [AID] field.
 * Sequential calls with 100ms delay between (rate-limit friendly).
 * @returns map keyed by the original DOI; value is the resolved PMID or null.
 */
export async function resolveDoisToPmids(dois: string[]): Promise<Record<string, string | null>> {
  const results: Record<string, string | null> = {}
  const unique = Array.from(new Set(dois))
  for (const doi of unique) {
    try {
      const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${encodeURIComponent(doi.toLowerCase())}[AID]&retmode=json`
      const res = await fetch(url)
      if (!res.ok) {
        results[doi] = null
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const data = await res.json() as any
        const idlist = data?.esearchresult?.idlist || []
        results[doi] = idlist.length > 0 ? idlist[0] : null
      }
    } catch {
      results[doi] = null
    }
    await new Promise(r => setTimeout(r, 100))
  }
  return results
}

/**
 * Reverse-lookup PMC IDs to PubMed PMIDs via NCBI elink.
 * Single batched call for all valid PMCs (PMC\d+); invalid entries map to null.
 * @returns map keyed by the original (uppercase-form) PMC; value is the resolved PMID or null.
 */
export async function resolvePmcsToPmids(pmcs: string[]): Promise<Record<string, string | null>> {
  const results: Record<string, string | null> = {}
  const unique = Array.from(new Set(pmcs))
  const valid = unique.filter(p => /^PMC\d+$/i.test(p))
  // Invalid entries → null
  for (const p of unique) {
    if (!/^PMC\d+$/i.test(p)) results[p] = null
  }
  if (valid.length === 0) return results
  try {
    const digits = valid.map(p => p.replace(/^PMC/i, ''))
    const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pmc&db=pubmed&id=${digits.join(',')}&retmode=json`
    const res = await fetch(url)
    if (!res.ok) {
      for (const p of valid) results[p] = null
      return results
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = await res.json() as any
    const linksets = Array.isArray(data?.linksets) ? data.linksets : []
    // Build map: pmc-digit → pmid
    const digitToPmid: Record<string, string | null> = {}
    for (const ls of linksets) {
      const pmcDigit = ls?.ids?.[0] != null ? String(ls.ids[0]) : null
      if (!pmcDigit) continue
      const pmid = ls?.linksetdbs?.[0]?.links?.[0]
      digitToPmid[pmcDigit] = pmid != null ? String(pmid) : null
    }
    for (const p of valid) {
      const digit = p.replace(/^PMC/i, '')
      results[p] = digitToPmid[digit] ?? null
    }
  } catch {
    for (const p of valid) results[p] = null
  }
  return results
}

export function registerIpcHandlers(): void {
  function validateOutputPath(filePath: string): string {
    const settings = getSettings()
    const outputDir = settings.outputDirectory || getDefaultOutputDir()
    const resolved = path.resolve(filePath)
    const relative = path.relative(outputDir, resolved)
    if (relative.startsWith('..') || path.isAbsolute(relative)) {
      throw new Error(`Path outside output directory: ${filePath}`)
    }
    return resolved
  }

  // ---- Settings ----
  ipcMain.handle('settings:get', () => {
    const settings = getSettings()
    if (!settings.outputDirectory) {
      const defaultDir = getDefaultOutputDir()
      setSetting('outputDirectory', defaultDir)
      return { ...settings, outputDirectory: defaultDir }
    }
    return settings
  })

  ipcMain.handle('settings:set', (_e, key: keyof SettingsSchema, value: unknown) => {
    setSetting(key, value as never)
    return true
  })

  ipcMain.handle('settings:validate-gemini-key', async (_e, key: string) => {
    try {
      const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models?key=${key}`
      )
      if (response.ok) return { valid: true }
      if (response.status === 400 || response.status === 403) return { valid: false, error: 'Invalid API key' }
      if (response.status === 429) return { valid: false, error: 'Rate limited — try again shortly' }
      return { valid: false, error: `API error (HTTP ${response.status})` }
    } catch {
      return { valid: false, error: 'Network error — check your internet connection' }
    }
  })

  // ---- Pipeline ----
  ipcMain.handle('pipeline:start', (_e, args: PipelineArgs) => {
    if (isPipelineRunning()) {
      return { error: 'Pipeline already running' }
    }

    const jobId = randomUUID()
    createJob(jobId, args.query || (args.pmids?.length ? `${args.pmids.length} selected papers` : 'Custom query'), JSON.stringify(args.columns))

    try {
      startPipeline(jobId, args)
      return { jobId }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      updateJob(jobId, { status: 'failed', error: message, completed_at: new Date().toISOString() })
      return { error: message }
    }
  })

  ipcMain.handle('pipeline:cancel', () => {
    const cancelled = cancelPipeline()
    return { cancelled }
  })

  // ---- Results ----
  ipcMain.handle('results:exists', (_e, filePath: string) => {
    try {
      const safePath = validateOutputPath(filePath)
      return { exists: existsSync(safePath) }
    } catch {
      return { exists: false }
    }
  })

  ipcMain.handle('results:load', (_e, filePath: string) => {
    try {
      const safePath = validateOutputPath(filePath)
      if (!existsSync(safePath)) {
        return { error: 'File not found' }
      }
      const content = readFileSync(safePath, 'utf-8')
      return { content }
    } catch {
      return { error: 'Access denied: path outside output directory' }
    }
  })

  ipcMain.handle('results:export', async (_e, defaultPath: string) => {
    const result = await dialog.showSaveDialog({
      defaultPath,
      filters: [{ name: 'CSV', extensions: ['csv'] }]
    })
    return result
  })

  // ---- History ----
  ipcMain.handle('history:list', () => {
    return listJobs()
  })

  ipcMain.handle('history:get', (_e, id: string) => {
    return getJob(id)
  })

  ipcMain.handle('history:delete', (_e, id: string) => {
    deleteJob(id)
    return true
  })

  // ---- System ----
  ipcMain.handle('dialog:save-file', async (_e, options: Electron.SaveDialogOptions) => {
    return dialog.showSaveDialog(options)
  })

  ipcMain.handle('dialog:open-directory', async () => {
    return dialog.showOpenDialog({ properties: ['openDirectory'] })
  })

  ipcMain.handle('shell:open-external', (_e, url: string) => {
    shell.openExternal(url)
    return true
  })

  ipcMain.handle('shell:open-path', (_e, filePath: string) => {
    try {
      const safePath = validateOutputPath(filePath)
      shell.openPath(safePath)
      return true
    } catch {
      return false
    }
  })

  ipcMain.handle('app:version', () => {
    return app.getVersion()
  })

  // ---- Gemini usage ----
  ipcMain.handle('gemini:getDailyUsage', () => getGeminiDailyUsage())

  // ---- PubMed Search ----
  ipcMain.handle('pubmed:search', async (_e, query: string, retmax = 10000) => {
    try {
      const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${encodeURIComponent(query)}&retmax=${retmax}&retmode=json`
      const res = await fetch(url)
      if (!res.ok) return { count: 0, pmids: [], error: `PubMed search failed (HTTP ${res.status})` }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data = await res.json() as any
      if (data?.esearchresult?.ERROR) return { count: 0, pmids: [], error: `PubMed error: ${data.esearchresult.ERROR}` }
      return {
        count: parseInt(data?.esearchresult?.count || '0'),
        pmids: data?.esearchresult?.idlist || []
      }
    } catch (err) {
      return { count: 0, pmids: [], error: `Network error — check your internet connection (${String(err)})` }
    }
  })

  ipcMain.handle('pubmed:resolve-doi', (_e, dois: string[]) => resolveDoisToPmids(dois))

  ipcMain.handle('pubmed:resolve-pmc', (_e, pmcs: string[]) => resolvePmcsToPmids(pmcs))

  ipcMain.handle('pubmed:fetch-details', async (_e, pmids: string[]) => {
    try {
      const safePmids = pmids.filter(id => /^\d+$/.test(String(id)))
      // Batch in groups of 200
      const results: Record<string, any> = {}
      for (let i = 0; i < safePmids.length; i += 200) {
        const batch = safePmids.slice(i, i + 200)
        const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=${batch.join(',')}&retmode=json`
        const res = await fetch(url)
        const data = await res.json()
        if (data?.result) {
          for (const pmid of batch) {
            if (data.result[pmid] && !data.result[pmid].error) {
              const d = data.result[pmid]
              let doi, pmc, issn
              if (d.articleids) {
                doi = d.articleids.find((id: any) => id.idtype === 'doi')?.value
                pmc = d.articleids.find((id: any) => id.idtype === 'pmc')?.value
                issn = d.articleids.find((id: any) => id.idtype === 'issn')?.value
              }
              // Fallback: esummary also exposes issn/essn at top level
              if (!issn) issn = d.issn || d.essn || ''
              results[pmid] = {
                title: d.title || 'Title unavailable',
                journal: d.fulljournalname || d.source || 'Unknown Journal',
                authors: d.authors?.slice(0, 3).map((a: any) => a.name) || [],
                pubYear: d.pubdate?.split(' ')[0] || d.sortpubdate?.substring(0, 4) || '',
                doi, pmc, issn,
                url: pmc ? `https://pmc.ncbi.nlm.nih.gov/articles/${pmc}` : `https://pubmed.ncbi.nlm.nih.gov/${pmid}`,
                publicationTypes: (d.pubtype || []) as string[],
              }
            }
          }
        }
      }
      return results
    } catch (err) {
      return { error: String(err) }
    }
  })

  ipcMain.handle('pubmed:fetch-abstracts', async (_e, pmids: string[]) => {
    try {
      const safePmids = pmids.filter(id => /^\d+$/.test(String(id)))
      const abstracts: Record<string, string> = {}
      for (let i = 0; i < safePmids.length; i += 200) {
        const batch = safePmids.slice(i, i + 200)
        const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=${batch.join(',')}&rettype=xml&retmode=xml`
        const res = await fetch(url)
        const xml = await res.text()
        // Parse <AbstractText> per <PubmedArticle>
        const articleRegex = /<PubmedArticle>[\s\S]*?<\/PubmedArticle>/g
        let match
        while ((match = articleRegex.exec(xml)) !== null) {
          const article = match[0]
          const pmidMatch = article.match(/<PMID[^>]*>(\d+)<\/PMID>/)
          if (!pmidMatch) continue
          const pmid = pmidMatch[1]
          // Collect all <AbstractText> sections
          const abstractParts: string[] = []
          const absRegex = /<AbstractText[^>]*>([\s\S]*?)<\/AbstractText>/g
          let absMatch
          while ((absMatch = absRegex.exec(article)) !== null) {
            // Strip any remaining XML tags
            const text = absMatch[1].replace(/<[^>]+>/g, '').trim()
            if (text) abstractParts.push(text)
          }
          if (abstractParts.length > 0) {
            abstracts[pmid] = abstractParts.join(' ')
          }
        }
      }
      return { abstracts, error: null }
    } catch (err) {
      return { abstracts: {}, error: String(err) }
    }
  })

  ipcMain.handle('pubmed:count', async (_e, query: string) => {
    try {
      const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${encodeURIComponent(query)}&retmax=0&retmode=json`
      const res = await fetch(url)
      const data = await res.json()
      return { count: parseInt(data?.esearchresult?.count || '0') }
    } catch {
      return { count: 0 }
    }
  })

  // ---- PubMed AI Query Builder (Gemini-assisted) ----
  ipcMain.handle('pubmed:build-query', async (_e, description: unknown) => {
    if (typeof description !== 'string' || description.trim().length === 0) return { error: 'Please describe your research topic' }
    if (description.length > 2000) return { error: 'Description too long (max 2000 characters)' }

    const settings = getSettings()
    const apiKey = settings.geminiApiKey
    if (!apiKey) return { error: 'No Gemini API key configured. Add your key in Settings.' }

    const prompt = `You are a biomedical PubMed search expert. The user will describe their research topic in plain English. Your job is to construct the best possible PubMed query to find relevant papers.

User's research description: ${description}

Rules:
- Use valid PubMed Entrez syntax: quoted phrases, [tiab]/[MeSH Terms] field tags, AND/OR/NOT operators, parentheses
- For gene symbols, include known aliases and full gene names grouped with OR
- For diseases, include common synonyms and MeSH equivalents
- Use appropriate field tags ([tiab], [MeSH Terms], [Gene]) based on term type
- Balance precision and recall — the query should find relevant papers without too much noise
- Group related concepts with OR, connect different concepts with AND
- If the description mentions a date range, include it as YYYY:YYYY[dp]

Return a JSON object with exactly these fields:
{
  "query": "<the complete PubMed query string>",
  "explanation": "<brief explanation of the query structure and key terms included>"
}`

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 30_000)

    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key=${apiKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { responseMimeType: 'application/json', temperature: 0 }
        }),
        signal: controller.signal
      })
      if (!res.ok) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let geminiMsg: string | undefined
        try { geminiMsg = ((await res.json()) as any)?.error?.message } catch { /* ignore */ }
        if (res.status === 429) return { error: `Gemini rate limit reached — try again shortly${geminiMsg ? `: ${geminiMsg}` : ''}` }
        if (res.status === 400 || res.status === 403) return { error: geminiMsg ? `Gemini error: ${geminiMsg}` : 'Invalid Gemini API key' }
        return { error: geminiMsg ? `Gemini error: ${geminiMsg}` : `Gemini API error (HTTP ${res.status})` }
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data = await res.json() as any
      const text = data?.candidates?.[0]?.content?.parts?.[0]?.text
      if (!text) return { error: 'Empty response from Gemini' }
      let parsed: unknown
      try {
        parsed = JSON.parse(text)
      } catch {
        return { error: 'Gemini returned invalid JSON — try again' }
      }
      if (
        typeof parsed !== 'object' || parsed === null ||
        typeof (parsed as Record<string, unknown>).query !== 'string' ||
        !(parsed as Record<string, unknown>).query
      ) {
        return { error: 'Unexpected response format from Gemini' }
      }
      const p = parsed as Record<string, unknown>
      addGeminiApiCalls(1)
      const updatedUsage = getGeminiDailyUsage()
      BrowserWindow.getAllWindows().forEach(win => { if (!win.isDestroyed()) win.webContents.send('gemini:usage-changed', updatedUsage) })
      return { query: p.query as string, explanation: typeof p.explanation === 'string' ? p.explanation : '' }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return { error: 'Request timed out — try again' }
      return { error: `Query building failed: ${String(err)}` }
    } finally {
      clearTimeout(timeout)
    }
  })

  // ---- PubMed AI Query Refinement (Gemini-assisted) ----
  ipcMain.handle('pubmed:refine-query', async (_e, payload: unknown) => {
    if (typeof payload !== 'object' || payload === null) return { error: 'Invalid payload' }
    const p = payload as Record<string, unknown>
    const previousQuery = typeof p.previousQuery === 'string' ? p.previousQuery : ''
    const refinementRequest = typeof p.refinementRequest === 'string' ? p.refinementRequest : ''
    if (!previousQuery.trim()) return { error: 'No previous query to refine' }
    if (!refinementRequest.trim()) return { error: 'Please describe the refinement' }
    if (refinementRequest.length > 2000) return { error: 'Refinement too long (max 2000 characters)' }

    const settings = getSettings()
    const apiKey = settings.geminiApiKey
    if (!apiKey) return { error: 'No Gemini API key configured. Add your key in Settings.' }

    const prompt = `You are a biomedical PubMed search expert. The user has an existing PubMed query and wants to refine it. Modify the query to satisfy the refinement request while preserving the original research intent.

Current query:
${previousQuery}

User's refinement request:
${refinementRequest}

Rules:
- Use valid PubMed Entrez syntax: quoted phrases, [tiab]/[MeSH Terms]/[Publication Type]/[Gene] field tags, AND/OR/NOT, balanced parentheses
- Preserve the existing structure where possible — only change what the refinement asks for
- For date refinements: append \`AND YYYY:YYYY[dp]\`
- For organism filters: \`AND "humans"[MeSH Terms]\` or similar
- For publication-type exclusions: \`NOT "review"[Publication Type]\` etc.
- If the refinement is ambiguous, use your best biomedical judgment

Return JSON:
{
  "query": "<the updated complete PubMed query>",
  "explanation": "<1-2 sentences describing what changed and why>"
}`

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 30_000)

    try {
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key=${apiKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { responseMimeType: 'application/json', temperature: 0 }
        }),
        signal: controller.signal
      })
      if (!res.ok) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let geminiMsg: string | undefined
        try { geminiMsg = ((await res.json()) as any)?.error?.message } catch { /* ignore */ }
        if (res.status === 429) return { error: `Gemini rate limit reached — try again shortly${geminiMsg ? `: ${geminiMsg}` : ''}` }
        if (res.status === 400 || res.status === 403) return { error: geminiMsg ? `Gemini error: ${geminiMsg}` : 'Invalid Gemini API key' }
        return { error: geminiMsg ? `Gemini error: ${geminiMsg}` : `Gemini API error (HTTP ${res.status})` }
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data = await res.json() as any
      const text = data?.candidates?.[0]?.content?.parts?.[0]?.text
      if (!text) return { error: 'Empty response from Gemini' }
      let parsed: unknown
      try {
        parsed = JSON.parse(text)
      } catch {
        return { error: 'Gemini returned invalid JSON — try again' }
      }
      if (
        typeof parsed !== 'object' || parsed === null ||
        typeof (parsed as Record<string, unknown>).query !== 'string' ||
        !(parsed as Record<string, unknown>).query
      ) {
        return { error: 'Unexpected response format from Gemini' }
      }
      const rp = parsed as Record<string, unknown>
      addGeminiApiCalls(1)
      const updatedUsage = getGeminiDailyUsage()
      BrowserWindow.getAllWindows().forEach(win => { if (!win.isDestroyed()) win.webContents.send('gemini:usage-changed', updatedUsage) })
      return { query: rp.query as string, explanation: typeof rp.explanation === 'string' ? rp.explanation : '' }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return { error: 'Request timed out — try again' }
      return { error: `Query refinement failed: ${String(err)}` }
    } finally {
      clearTimeout(timeout)
    }
  })

  // ---- Auto-updater ----
  ipcMain.handle('updater:download', () => {
    downloadUpdate()
    return true
  })

  ipcMain.handle('updater:install', () => {
    installUpdate()
    return true
  })

  ipcMain.handle('citations:fetch', async (_e, pmids: string[]) => {
    const safePmids = pmids.filter(id => /^\d+$/.test(String(id)))
    const results: Record<string, number> = {}
    // Fetch in parallel but limit concurrency
    const batchSize = 5
    for (let i = 0; i < safePmids.length; i += batchSize) {
      const batch = safePmids.slice(i, i + batchSize)
      const promises = batch.map(async (pmid) => {
        try {
          const res = await fetch(`https://api.semanticscholar.org/graph/v1/paper/PMID:${pmid}?fields=citationCount`)
          if (res.ok) {
            const data = await res.json()
            results[pmid] = data.citationCount || 0
          } else {
            results[pmid] = 0
          }
        } catch {
          results[pmid] = 0
        }
      })
      await Promise.all(promises)
    }
    return results
  })
}
