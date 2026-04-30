export interface FetchJsonResponse {
  ok: boolean
  json: () => Promise<unknown>
}

export type FetchJson = (url: string) => Promise<FetchJsonResponse>

interface ESearchResponse {
  esearchresult?: {
    idlist?: unknown[]
  }
}

interface ELinkSet {
  ids?: unknown[]
  linksetdbs?: Array<{
    links?: unknown[]
  }>
}

interface ELinkResponse {
  linksets?: ELinkSet[]
}

function sleep(ms: number): Promise<void> {
  if (ms <= 0) return Promise.resolve()
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Reverse-lookup DOIs to PubMed PMIDs via NCBI esearch [AID] field.
 * Sequential calls with a production delay between requests for NCBI rate limits.
 */
export async function resolveDoisToPmids(
  dois: string[],
  fetcher: FetchJson = fetch,
  requestDelayMs = 100
): Promise<Record<string, string | null>> {
  const results: Record<string, string | null> = {}
  const unique = Array.from(new Set(dois))
  for (const doi of unique) {
    try {
      const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${encodeURIComponent(doi.toLowerCase())}[AID]&retmode=json`
      const res = await fetcher(url)
      if (!res.ok) {
        results[doi] = null
      } else {
        const data = await res.json() as ESearchResponse
        const idlist = Array.isArray(data?.esearchresult?.idlist) ? data.esearchresult.idlist : []
        results[doi] = idlist.length > 0 && idlist[0] != null ? String(idlist[0]) : null
      }
    } catch {
      results[doi] = null
    }
    await sleep(requestDelayMs)
  }
  return results
}

/**
 * Reverse-lookup PMC IDs to PubMed PMIDs via NCBI elink.
 * Uses a single batched call for all valid PMCs; invalid entries map to null.
 */
export async function resolvePmcsToPmids(
  pmcs: string[],
  fetcher: FetchJson = fetch
): Promise<Record<string, string | null>> {
  const results: Record<string, string | null> = {}
  const unique = Array.from(new Set(pmcs))
  const valid = unique.filter((p) => /^PMC\d+$/i.test(p))

  for (const p of unique) {
    if (!/^PMC\d+$/i.test(p)) results[p] = null
  }
  if (valid.length === 0) return results

  try {
    const digits = valid.map((p) => p.replace(/^PMC/i, ''))
    const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pmc&db=pubmed&id=${digits.join(',')}&retmode=json`
    const res = await fetcher(url)
    if (!res.ok) {
      for (const p of valid) results[p] = null
      return results
    }

    const data = await res.json() as ELinkResponse
    const linksets = Array.isArray(data?.linksets) ? data.linksets : []
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
