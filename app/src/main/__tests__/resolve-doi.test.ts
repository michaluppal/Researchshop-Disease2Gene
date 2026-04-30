import { describe, it, expect } from 'vitest'
import { resolveDoisToPmids, type FetchJson, type FetchJsonResponse } from '../pubmed-resolvers'

function response(idlist: string[], ok = true): FetchJsonResponse {
  return {
    ok,
    json: async () => ({ esearchresult: { idlist } }),
  }
}

function sequenceFetch(responses: Array<FetchJsonResponse | Error>): { fetcher: FetchJson; calls: string[] } {
  const calls: string[] = []
  const fetcher: FetchJson = async (url) => {
    calls.push(url)
    const next = responses.shift()
    if (next instanceof Error) throw next
    return next ?? response([])
  }
  return { fetcher, calls }
}

describe('resolveDoisToPmids', () => {
  it('T_D1: single valid DOI -> one fetch, correct URL, resolved PMID', async () => {
    const { fetcher, calls } = sequenceFetch([response(['12345678'])])
    const result = await resolveDoisToPmids(['10.1038/nature12373'], fetcher, 0)

    expect(calls).toHaveLength(1)
    expect(calls[0]).toContain('esearch.fcgi')
    expect(calls[0]).toContain('db=pubmed')
    expect(calls[0]).toContain('10.1038%2Fnature12373[AID]')
    expect(result).toEqual({ '10.1038/nature12373': '12345678' })
  })

  it('T_D2: empty array -> no fetch, empty result', async () => {
    const { fetcher, calls } = sequenceFetch([])
    const result = await resolveDoisToPmids([], fetcher, 0)
    expect(calls).toHaveLength(0)
    expect(result).toEqual({})
  })

  it('T_D3: duplicate DOIs -> single fetch call', async () => {
    const { fetcher, calls } = sequenceFetch([response(['11111111'])])
    const result = await resolveDoisToPmids([
      '10.1038/nature12373',
      '10.1038/nature12373',
    ], fetcher, 0)

    expect(calls).toHaveLength(1)
    expect(result).toEqual({ '10.1038/nature12373': '11111111' })
  })

  it('T_D4: no results -> null mapping', async () => {
    const { fetcher } = sequenceFetch([response([])])
    const result = await resolveDoisToPmids(['10.9999/no-result'], fetcher, 0)
    expect(result).toEqual({ '10.9999/no-result': null })
  })

  it('T_D5: fetch throws on DOI 1, succeeds on DOI 2', async () => {
    const { fetcher } = sequenceFetch([
      new Error('network down'),
      response(['22222222']),
    ])

    const result = await resolveDoisToPmids([
      '10.1038/broken',
      '10.1038/works',
    ], fetcher, 0)
    expect(result['10.1038/broken']).toBeNull()
    expect(result['10.1038/works']).toBe('22222222')
  })

  it('T_D6: DOI with URL-special chars is URL-encoded', async () => {
    const { fetcher, calls } = sequenceFetch([response([])])
    await resolveDoisToPmids(['10.1234/foo[bar]'], fetcher, 0)
    expect(calls[0]).toContain('10.1234%2Ffoo%5Bbar%5D[AID]')
    expect(calls[0]).not.toContain('foo[bar]')
  })

  it('T_D7: mixed-case DOI result is keyed by original case', async () => {
    const { fetcher, calls } = sequenceFetch([response(['33333333'])])
    const result = await resolveDoisToPmids(['10.1038/Nature12373'], fetcher, 0)
    expect(result).toHaveProperty('10.1038/Nature12373', '33333333')
    expect(calls[0]).toContain('10.1038%2Fnature12373')
  })

  it('T_D8: calls are sequential, not parallel', async () => {
    const invocationOrder: string[] = []
    const fetcher: FetchJson = async (url) => {
      invocationOrder.push(url)
      await new Promise((resolve) => setTimeout(resolve, 5))
      return response(['1'])
    }

    await resolveDoisToPmids(['10.1/a', '10.1/b', '10.1/c'], fetcher, 0)

    expect(invocationOrder).toHaveLength(3)
    expect(invocationOrder[0]).toContain('10.1%2Fa')
    expect(invocationOrder[1]).toContain('10.1%2Fb')
    expect(invocationOrder[2]).toContain('10.1%2Fc')
  })
})
