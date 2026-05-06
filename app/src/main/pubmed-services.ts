import { calculateCompositeScore, getJournalQuality } from '../shared/journalQuality'
import { scoreGeneRelevance, type RelevanceResult } from '../shared/geneRelevanceScorer'
import {
  calculateGeneticsSignal,
  calculateRecommendationScore,
  compareRecommendedPapers,
} from '../shared/paperRecommendation'

export interface PubMedDetails {
  title: string
  journal: string
  authors: string[]
  pubYear: string
  doi?: string
  pmc?: string
  issn?: string
  url: string
  publicationTypes: string[]
}

export interface PubMedSearchResult {
  count: number
  pmids: string[]
  error?: string
}

export interface RankedPubMedPaper extends PubMedDetails {
  pmid: string
  citationCount: number
  compositeScore: number
  recommendationScore: number
  geneticsScore: number
  abstract: string
  relevance: RelevanceResult
  searchRank: number
}

export interface RankedPubMedSearchResult extends PubMedSearchResult {
  papers?: Record<string, RankedPubMedPaper>
  rankingWarning?: string
}

interface PubMedArticleId {
  idtype?: string
  value?: string
}

interface PubMedSummaryRecord {
  title?: string
  fulljournalname?: string
  source?: string
  authors?: Array<{ name?: string }>
  pubdate?: string
  sortpubdate?: string
  articleids?: PubMedArticleId[]
  issn?: string
  essn?: string
  pubtype?: string[]
  error?: string
}

interface PubMedSummaryResponse {
  result?: Record<string, PubMedSummaryRecord>
}

interface PubMedSearchResponse {
  esearchresult?: {
    count?: string
    idlist?: string[]
    ERROR?: string
  }
}

interface SemanticScholarBatchPaper {
  externalIds?: { PMID?: string }
  citationCount?: number
}

interface PubMedDetailsFetchResult {
  details: Record<string, PubMedDetails>
  warnings: string[]
}

interface SemanticScholarCitationBatchResult {
  citations: Record<string, number>
  failedPmids: string[]
  warnings: string[]
}

function sanitizePmids(pmids: string[]): string[] {
  return pmids.filter(id => /^\d+$/.test(String(id)))
}

function describeFetchError(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function joinWarnings(warnings: string[]): string | undefined {
  const uniqueWarnings = Array.from(new Set(warnings.filter(Boolean)))
  return uniqueWarnings.length > 0 ? uniqueWarnings.join(' ') : undefined
}

function fallbackPubMedDetails(pmid: string): PubMedDetails {
  return {
    title: 'Title unavailable',
    journal: 'Unknown Journal',
    authors: [],
    pubYear: '',
    url: `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`,
    publicationTypes: [],
  }
}

export async function searchPubMedIds(query: string, retmax = 10000): Promise<PubMedSearchResult> {
  try {
    const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${encodeURIComponent(query)}&retmax=${retmax}&retmode=json`
    const res = await fetch(url)
    if (!res.ok) return { count: 0, pmids: [], error: `PubMed search failed (HTTP ${res.status})` }
    const data = await res.json() as PubMedSearchResponse
    if (data?.esearchresult?.ERROR) {
      return { count: 0, pmids: [], error: `PubMed error: ${data.esearchresult.ERROR}` }
    }
    return {
      count: parseInt(data?.esearchresult?.count || '0'),
      pmids: data?.esearchresult?.idlist || [],
    }
  } catch (err) {
    return { count: 0, pmids: [], error: `Network error — check your internet connection (${String(err)})` }
  }
}

export async function fetchPubMedDetailsWithWarnings(pmids: string[]): Promise<PubMedDetailsFetchResult> {
  const safePmids = sanitizePmids(pmids)
  const results: Record<string, PubMedDetails> = {}
  const warnings: string[] = []

  for (let i = 0; i < safePmids.length; i += 200) {
    const batch = safePmids.slice(i, i + 200)
    const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=${batch.join(',')}&retmode=json`
    try {
      const res = await fetch(url)
      if (!res.ok) {
        warnings.push(`PubMed details unavailable for some papers (HTTP ${res.status}); showing fallback metadata.`)
        continue
      }
      const data = await res.json() as PubMedSummaryResponse
      if (!data?.result) {
        warnings.push('PubMed details unavailable for some papers; showing fallback metadata.')
        continue
      }

      for (const pmid of batch) {
        const d = data.result[pmid]
        if (!d || d.error) continue

        const doi = d.articleids?.find((id) => id.idtype === 'doi')?.value
        const pmc = d.articleids?.find((id) => id.idtype === 'pmc')?.value
        const issn = d.articleids?.find((id) => id.idtype === 'issn')?.value || d.issn || d.essn || ''

        results[pmid] = {
          title: d.title || 'Title unavailable',
          journal: d.fulljournalname || d.source || 'Unknown Journal',
          authors: d.authors?.slice(0, 3).map((a) => a.name || '').filter(Boolean) || [],
          pubYear: d.pubdate?.split(' ')[0] || d.sortpubdate?.substring(0, 4) || '',
          doi,
          pmc,
          issn,
          url: pmc ? `https://pmc.ncbi.nlm.nih.gov/articles/${pmc}` : `https://pubmed.ncbi.nlm.nih.gov/${pmid}`,
          publicationTypes: d.pubtype || [],
        }
      }
    } catch (err) {
      warnings.push(`PubMed details unavailable for some papers (${describeFetchError(err)}); showing fallback metadata.`)
    }
  }

  return { details: results, warnings }
}

export async function fetchPubMedDetails(pmids: string[]): Promise<Record<string, PubMedDetails>> {
  return (await fetchPubMedDetailsWithWarnings(pmids)).details
}

function stripXml(text: string): string {
  return text.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim()
}

export async function fetchPubMedAbstracts(pmids: string[]): Promise<{ abstracts: Record<string, string>; error: string | null }> {
  const safePmids = sanitizePmids(pmids)
  const abstracts: Record<string, string> = {}
  const warnings: string[] = []

  for (let i = 0; i < safePmids.length; i += 200) {
    const batch = safePmids.slice(i, i + 200)
    const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=${batch.join(',')}&rettype=xml&retmode=xml`
    try {
      const res = await fetch(url)
      if (!res.ok) {
        warnings.push(`PubMed abstracts unavailable for some papers (HTTP ${res.status}); relevance scores may be incomplete.`)
        continue
      }
      const xml = await res.text()
      const articleRegex = /<PubmedArticle>[\s\S]*?<\/PubmedArticle>/g
      let match
      while ((match = articleRegex.exec(xml)) !== null) {
        const article = match[0]
        const pmidMatch = article.match(/<PMID[^>]*>(\d+)<\/PMID>/)
        if (!pmidMatch) continue
        const pmid = pmidMatch[1]
        const abstractParts: string[] = []
        const absRegex = /<AbstractText[^>]*>([\s\S]*?)<\/AbstractText>/g
        let absMatch
        while ((absMatch = absRegex.exec(article)) !== null) {
          const text = stripXml(absMatch[1])
          if (text) abstractParts.push(text)
        }
        if (abstractParts.length > 0) abstracts[pmid] = abstractParts.join(' ')
      }
    } catch (err) {
      warnings.push(`PubMed abstracts unavailable for some papers (${describeFetchError(err)}); relevance scores may be incomplete.`)
    }
  }

  return { abstracts, error: joinWarnings(warnings) || null }
}

async function fetchSemanticScholarCitationBatch(pmids: string[]): Promise<SemanticScholarCitationBatchResult> {
  const safePmids = sanitizePmids(pmids)
  const results: Record<string, number> = Object.fromEntries(safePmids.map((pmid) => [pmid, 0]))
  const failedPmids: string[] = []
  const warnings: string[] = []

  for (let i = 0; i < safePmids.length; i += 500) {
    const batch = safePmids.slice(i, i + 500)
    try {
      const res = await fetch('https://api.semanticscholar.org/graph/v1/paper/batch?fields=externalIds,citationCount', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: batch.map((pmid) => `PMID:${pmid}`) }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const data = await res.json() as Array<SemanticScholarBatchPaper | null>
      batch.forEach((pmid, index) => {
        const paper = data[index]
        const resultPmid = paper?.externalIds?.PMID || pmid
        results[pmid] = paper?.citationCount || 0
        if (resultPmid !== pmid) results[resultPmid] = paper?.citationCount || 0
      })
    } catch (err) {
      failedPmids.push(...batch)
      warnings.push(`Semantic Scholar citation batch lookup failed for some papers (${describeFetchError(err)}); citation counts set to 0.`)
      batch.forEach((pmid) => {
        results[pmid] = 0
      })
    }
  }

  return { citations: results, failedPmids, warnings }
}

async function fetchSemanticScholarCitationSingles(pmids: string[]): Promise<Record<string, number>> {
  const safePmids = pmids.filter(id => /^\d+$/.test(String(id)))
  const results: Record<string, number> = {}
  const batchSize = 5

  for (let i = 0; i < safePmids.length; i += batchSize) {
    const batch = safePmids.slice(i, i + batchSize)
    const promises = batch.map(async (pmid) => {
      try {
        const res = await fetch(`https://api.semanticscholar.org/graph/v1/paper/PMID:${pmid}?fields=citationCount`)
        if (!res.ok) {
          results[pmid] = 0
          return
        }
        const data = await res.json() as { citationCount?: number }
        results[pmid] = data.citationCount || 0
      } catch {
        results[pmid] = 0
      }
    })
    await Promise.all(promises)
  }

  return results
}

export async function fetchSemanticScholarCitations(
  pmids: string[],
  options: { fallbackToSingles?: boolean } = {}
): Promise<Record<string, number>> {
  const safePmids = sanitizePmids(pmids)
  const batchResults = await fetchSemanticScholarCitationBatch(safePmids)
  if ((options.fallbackToSingles ?? true) && batchResults.failedPmids.length > 0) {
    const singleResults = await fetchSemanticScholarCitationSingles(batchResults.failedPmids)
    return { ...batchResults.citations, ...singleResults }
  }
  return batchResults.citations
}

export function buildRankedPubMedPaper(
  pmid: string,
  searchRank: number,
  details?: PubMedDetails,
  abstract = '',
  citationCount = 0
): RankedPubMedPaper {
  const d = details || fallbackPubMedDetails(pmid)
  const journalQuality = getJournalQuality(d.journal, d.issn)
  const compositeScore = calculateCompositeScore(citationCount, journalQuality)
  const relevance = scoreGeneRelevance(abstract, d.title)
  const geneticsScore = calculateGeneticsSignal(relevance)
  const recommendationScore = calculateRecommendationScore(geneticsScore, compositeScore)

  return {
    ...d,
    pmid,
    citationCount,
    compositeScore,
    recommendationScore,
    geneticsScore,
    abstract,
    relevance,
    searchRank,
  }
}

export async function searchPubMedRanked(query: string, retmax = 10000): Promise<RankedPubMedSearchResult> {
  const search = await searchPubMedIds(query, retmax)
  if (search.error || search.count === 0 || search.count > 500) return search

  const [detailsResult, abstractsResult, citationsResult] = await Promise.all([
    fetchPubMedDetailsWithWarnings(search.pmids),
    fetchPubMedAbstracts(search.pmids),
    fetchSemanticScholarCitationBatch(search.pmids),
  ])
  const details = detailsResult.details
  const abstracts = abstractsResult.abstracts
  const citations = citationsResult.citations
  const hasMissingDetails = search.pmids.some((pmid) => !details[pmid])
  const warnings = [
    ...detailsResult.warnings,
    ...(hasMissingDetails ? ['PubMed details unavailable for some papers; showing fallback metadata.'] : []),
    ...(abstractsResult.error ? [abstractsResult.error] : []),
    ...citationsResult.warnings,
  ]

  const rankedPapers = search.pmids
    .map((pmid, index) => buildRankedPubMedPaper(
      pmid,
      index,
      details[pmid],
      abstracts[pmid] || '',
      citations[pmid] || 0
    ))
    .sort((a, b) => compareRecommendedPapers(a, b, 'recommended'))

  return {
    count: search.count,
    pmids: rankedPapers.map((paper) => paper.pmid),
    papers: Object.fromEntries(rankedPapers.map((paper) => [paper.pmid, paper])),
    rankingWarning: joinWarnings(warnings),
  }
}
