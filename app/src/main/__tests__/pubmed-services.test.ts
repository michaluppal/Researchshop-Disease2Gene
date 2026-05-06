import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchSemanticScholarCitations,
  searchPubMedRanked,
} from '../pubmed-services'

function jsonResponse(body: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    json: async () => body,
    text: async () => '',
  } as Response
}

function textResponse(body: string, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    json: async () => ({}),
    text: async () => body,
  } as Response
}

function mockFetch(handler: (url: string, init?: { method?: string }) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: unknown, init?: unknown) => {
    return handler(String(input), init as { method?: string } | undefined)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function pubmedSearch(pmids: string[]): Response {
  return jsonResponse({
    esearchresult: {
      count: String(pmids.length),
      idlist: pmids,
    },
  })
}

function pubmedDetails(pmids: string[]): Response {
  return jsonResponse({
    result: Object.fromEntries(pmids.map((pmid) => [
      pmid,
      {
        title: `Paper ${pmid}`,
        fulljournalname: 'Genetics Journal',
        authors: [{ name: 'Ada Author' }],
        pubdate: '2024 Jan',
        pubtype: ['Journal Article'],
      },
    ])),
  })
}

function pubmedAbstractXml(entries: Record<string, string>): Response {
  const xml = Object.entries(entries).map(([pmid, abstract]) => `
    <PubmedArticle>
      <MedlineCitation>
        <PMID>${pmid}</PMID>
        <Article>
          <Abstract><AbstractText>${abstract}</AbstractText></Abstract>
        </Article>
      </MedlineCitation>
    </PubmedArticle>
  `).join('')
  return textResponse(xml)
}

describe('pubmed ranked services', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns fallback ranked papers with warnings when enrichment fetches fail', async () => {
    const fetchMock = mockFetch((url) => {
      if (url.includes('esearch.fcgi')) return pubmedSearch(['111', '222'])
      if (url.includes('esummary.fcgi')) throw new Error('details down')
      if (url.includes('efetch.fcgi')) throw new Error('abstracts down')
      if (url.includes('/paper/batch')) return jsonResponse({ error: 'rate limited' }, false, 429)
      if (url.includes('/paper/PMID:')) throw new Error('ranked search should not call individual citations')
      throw new Error(`Unexpected URL: ${url}`)
    })

    const result = await searchPubMedRanked('BRCA1 cancer')

    expect(result.error).toBeUndefined()
    expect(result.count).toBe(2)
    expect(result.pmids).toEqual(['111', '222'])
    expect(Object.keys(result.papers || {})).toEqual(['111', '222'])
    expect(result.papers?.['111']).toMatchObject({
      title: 'Title unavailable',
      journal: 'Unknown Journal',
      citationCount: 0,
      abstract: '',
      searchRank: 0,
    })
    expect(result.papers?.['111'].url).toBe('https://pubmed.ncbi.nlm.nih.gov/111/')
    expect(result.rankingWarning).toContain('fallback metadata')
    expect(result.rankingWarning).toContain('abstracts unavailable')
    expect(result.rankingWarning).toContain('citation batch lookup failed')
    expect(fetchMock.mock.calls.map(([input]) => String(input))).not.toContain(
      'https://api.semanticscholar.org/graph/v1/paper/PMID:111?fields=citationCount'
    )
  })

  it('ranks the full capped PMID set before returning ordered PMIDs', async () => {
    const highSignalAbstract = [
      'BRCA1 mutation variant sequencing identified pathogenic alleles and gene expression changes.',
      'The molecular genomic analysis included exome sequencing, copy number profiling, and mRNA validation.',
      'Additional genotype and polymorphism evidence linked variants in BRCA1 to phenotype.',
    ].join(' ')
    const lowSignalAbstract = 'Clinical cohort description without molecular gene content. '.repeat(4)

    mockFetch((url) => {
      if (url.includes('esearch.fcgi')) return pubmedSearch(['111', '222', '333'])
      if (url.includes('esummary.fcgi')) return pubmedDetails(['111', '222', '333'])
      if (url.includes('efetch.fcgi')) {
        return pubmedAbstractXml({
          '111': lowSignalAbstract,
          '222': lowSignalAbstract,
          '333': highSignalAbstract,
        })
      }
      if (url.includes('/paper/batch')) {
        return jsonResponse([
          { externalIds: { PMID: '111' }, citationCount: 0 },
          { externalIds: { PMID: '222' }, citationCount: 0 },
          { externalIds: { PMID: '333' }, citationCount: 0 },
        ])
      }
      throw new Error(`Unexpected URL: ${url}`)
    })

    const result = await searchPubMedRanked('BRCA1 cancer')

    expect(result.pmids[0]).toBe('333')
    expect(result.papers?.['333'].searchRank).toBe(2)
    expect(Object.keys(result.papers || {})).toHaveLength(3)
  })

  it('keeps individual citation fallback available outside ranked search', async () => {
    mockFetch((url) => {
      if (url.includes('/paper/batch')) return jsonResponse({ error: 'rate limited' }, false, 429)
      if (url.includes('/paper/PMID:111')) return jsonResponse({ citationCount: 7 })
      throw new Error(`Unexpected URL: ${url}`)
    })

    await expect(fetchSemanticScholarCitations(['111'])).resolves.toEqual({ '111': 7 })
  })
})
