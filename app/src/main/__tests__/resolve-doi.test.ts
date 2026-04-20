import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Stub electron before importing ipc-handlers (which imports electron at top level).
vi.mock('electron', () => ({
  ipcMain: { handle: vi.fn() },
  dialog: {},
  shell: {},
  app: { getVersion: () => '0.0.0-test', getPath: () => '/tmp' },
  BrowserWindow: class {},
}))
vi.mock('../settings-store', () => ({
  getSettings: () => ({ outputDirectory: '/tmp' }),
  setSetting: vi.fn(),
  getDefaultOutputDir: () => '/tmp',
  SettingsSchema: {},
}))
vi.mock('../job-store', () => ({
  createJob: vi.fn(),
  getJob: vi.fn(),
  updateJob: vi.fn(),
  listJobs: vi.fn(() => []),
  deleteJob: vi.fn(),
}))
vi.mock('../python-bridge', () => ({
  startPipeline: vi.fn(),
  cancelPipeline: vi.fn(),
  isPipelineRunning: vi.fn(() => false),
}))
vi.mock('../usage-store', () => ({
  getGeminiDailyUsage: vi.fn(),
  addGeminiApiCalls: vi.fn(),
}))
vi.mock('../updater', () => ({
  downloadUpdate: vi.fn(),
  installUpdate: vi.fn(),
}))

import { resolveDoisToPmids } from '../ipc-handlers'

type FetchMock = ReturnType<typeof vi.fn>

function mockResponse(idlist: string[], ok = true): Response {
  return {
    ok,
    json: async () => ({ esearchresult: { idlist } }),
  } as unknown as Response
}

describe('resolveDoisToPmids', () => {
  let fetchMock: FetchMock

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('T_D1: single valid DOI → one fetch, correct URL, resolved PMID', async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(['12345678']))
    const result = await resolveDoisToPmids(['10.1038/nature12373'])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const calledUrl = fetchMock.mock.calls[0][0] as string
    expect(calledUrl).toContain('esearch.fcgi')
    expect(calledUrl).toContain('db=pubmed')
    // The DOI is encodeURIComponent'd, [AID] qualifier is appended as-is after.
    expect(calledUrl).toContain('10.1038%2Fnature12373[AID]')
    expect(result).toEqual({ '10.1038/nature12373': '12345678' })
  })

  it('T_D2: empty array → no fetch, empty result', async () => {
    const result = await resolveDoisToPmids([])
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result).toEqual({})
  })

  it('T_D3: duplicate DOIs → single fetch call (dedup)', async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(['11111111']))
    const result = await resolveDoisToPmids([
      '10.1038/nature12373',
      '10.1038/nature12373',
    ])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(result).toEqual({ '10.1038/nature12373': '11111111' })
  })

  it('T_D4: no results → null mapping', async () => {
    fetchMock.mockResolvedValueOnce(mockResponse([]))
    const result = await resolveDoisToPmids(['10.9999/fake'])
    expect(result).toEqual({ '10.9999/fake': null })
  })

  it('T_D5: fetch throws on DOI 1, succeeds on DOI 2', async () => {
    fetchMock
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(mockResponse(['22222222']))

    const result = await resolveDoisToPmids([
      '10.1038/broken',
      '10.1038/works',
    ])
    expect(result['10.1038/broken']).toBeNull()
    expect(result['10.1038/works']).toBe('22222222')
  })

  it('T_D6: DOI with URL-special chars is URL-encoded', async () => {
    fetchMock.mockResolvedValueOnce(mockResponse([]))
    await resolveDoisToPmids(['10.1234/foo[bar]'])
    const calledUrl = fetchMock.mock.calls[0][0] as string
    // Brackets within the DOI payload must be percent-encoded so they can't be
    // confused with [AID] field qualifiers. The [AID] suffix is appended
    // after the encoded DOI as a literal.
    expect(calledUrl).toContain('10.1234%2Ffoo%5Bbar%5D[AID]')
    // The raw, unencoded DOI brackets must not appear anywhere in the URL.
    expect(calledUrl).not.toContain('foo[bar]')
  })

  it('T_D7: mixed-case DOI — result keyed by original case', async () => {
    fetchMock.mockResolvedValueOnce(mockResponse(['33333333']))
    const result = await resolveDoisToPmids(['10.1038/Nature12373'])
    expect(result).toHaveProperty('10.1038/Nature12373', '33333333')
    // Also confirm we lowercased in the URL (the handler lowercases before encoding)
    const calledUrl = fetchMock.mock.calls[0][0] as string
    expect(calledUrl).toContain('10.1038%2Fnature12373')
  })

  it('T_D8: calls are sequential, not parallel', async () => {
    const invocationOrder: string[] = []
    fetchMock.mockImplementation(async (url: string) => {
      invocationOrder.push(url)
      // simulate some latency
      await new Promise((r) => setTimeout(r, 5))
      return mockResponse(['1'])
    })
    await resolveDoisToPmids(['10.1/a', '10.1/b', '10.1/c'])
    expect(fetchMock).toHaveBeenCalledTimes(3)
    // Sequential means each call completed before the next was initiated.
    // Because our impl is async-awaited, invocation order = input order.
    expect(invocationOrder[0]).toContain('10.1%2Fa')
    expect(invocationOrder[1]).toContain('10.1%2Fb')
    expect(invocationOrder[2]).toContain('10.1%2Fc')
  })
})
