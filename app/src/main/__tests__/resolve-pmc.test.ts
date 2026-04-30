import { describe, it, expect } from 'vitest'
import { resolvePmcsToPmids, type FetchJson, type FetchJsonResponse } from '../pubmed-resolvers'

function elinkResponse(
  pairs: Array<{ pmcDigit: string; pmid: string | null }>,
  ok = true
): FetchJsonResponse {
  const linksets = pairs.map(({ pmcDigit, pmid }) => ({
    ids: [pmcDigit],
    linksetdbs:
      pmid === null
        ? undefined
        : [{ links: [pmid] }],
  }))
  return {
    ok,
    json: async () => ({ linksets }),
  }
}

function sequenceFetch(responses: Array<FetchJsonResponse | Error>): { fetcher: FetchJson; calls: string[] } {
  const calls: string[] = []
  const fetcher: FetchJson = async (url) => {
    calls.push(url)
    const next = responses.shift()
    if (next instanceof Error) throw next
    return next ?? elinkResponse([])
  }
  return { fetcher, calls }
}

describe('resolvePmcsToPmids', () => {
  it('T_C1: single valid PMC -> one elink fetch, correct URL, resolved PMID', async () => {
    const { fetcher, calls } = sequenceFetch([
      elinkResponse([{ pmcDigit: '9035072', pmid: '35152405' }]),
    ])
    const result = await resolvePmcsToPmids(['PMC9035072'], fetcher)

    expect(calls).toHaveLength(1)
    expect(calls[0]).toContain('elink.fcgi')
    expect(calls[0]).toContain('dbfrom=pmc')
    expect(calls[0]).toContain('db=pubmed')
    expect(calls[0]).toContain('id=9035072')
    expect(calls[0]).not.toContain('id=PMC')
    expect(result).toEqual({ PMC9035072: '35152405' })
  })

  it('T_C2: empty array -> no fetch, empty result', async () => {
    const { fetcher, calls } = sequenceFetch([])
    const result = await resolvePmcsToPmids([], fetcher)
    expect(calls).toHaveLength(0)
    expect(result).toEqual({})
  })

  it('T_C3: multiple PMCs -> one batched fetch, all resolved', async () => {
    const { fetcher, calls } = sequenceFetch([
      elinkResponse([
        { pmcDigit: '1111', pmid: '111' },
        { pmcDigit: '2222', pmid: '222' },
        { pmcDigit: '3333', pmid: '333' },
      ]),
    ])
    const result = await resolvePmcsToPmids(['PMC1111', 'PMC2222', 'PMC3333'], fetcher)
    expect(calls).toHaveLength(1)
    expect(calls[0]).toContain('id=1111,2222,3333')
    expect(result).toEqual({
      PMC1111: '111',
      PMC2222: '222',
      PMC3333: '333',
    })
  })

  it('T_C4: invalid PMC IDs -> filtered out, mapped to null', async () => {
    const { fetcher, calls } = sequenceFetch([
      elinkResponse([{ pmcDigit: '9035072', pmid: '35152405' }]),
    ])
    const result = await resolvePmcsToPmids(['PMC', 'PMCabc', 'PMC9035072'], fetcher)
    expect(calls).toHaveLength(1)
    expect(calls[0]).toContain('id=9035072')
    expect(result.PMC).toBeNull()
    expect(result.PMCabc).toBeNull()
    expect(result.PMC9035072).toBe('35152405')
  })

  it('T_C5: linksetdbs missing for one PMC -> that one is null', async () => {
    const { fetcher } = sequenceFetch([
      elinkResponse([
        { pmcDigit: '1111', pmid: '111' },
        { pmcDigit: '2222', pmid: null },
      ]),
    ])
    const result = await resolvePmcsToPmids(['PMC1111', 'PMC2222'], fetcher)
    expect(result).toEqual({ PMC1111: '111', PMC2222: null })
  })

  it('T_C6: linksets returned in different order from input', async () => {
    const { fetcher } = sequenceFetch([
      elinkResponse([
        { pmcDigit: '3333', pmid: '333' },
        { pmcDigit: '1111', pmid: '111' },
        { pmcDigit: '2222', pmid: '222' },
      ]),
    ])
    const result = await resolvePmcsToPmids(['PMC1111', 'PMC2222', 'PMC3333'], fetcher)
    expect(result).toEqual({
      PMC1111: '111',
      PMC2222: '222',
      PMC3333: '333',
    })
  })
})
