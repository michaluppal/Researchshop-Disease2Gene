import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Same electron/module stubs as resolve-doi.test.ts
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

import { resolvePmcsToPmids } from '../ipc-handlers'

type FetchMock = ReturnType<typeof vi.fn>

function elinkResponse(
  pairs: Array<{ pmcDigit: string; pmid: string | null }>,
  ok = true
): Response {
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
  } as unknown as Response
}

describe('resolvePmcsToPmids', () => {
  let fetchMock: FetchMock

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('T_C1: single valid PMC → one elink fetch, correct URL, resolved PMID', async () => {
    fetchMock.mockResolvedValueOnce(
      elinkResponse([{ pmcDigit: '9035072', pmid: '35152405' }])
    )
    const result = await resolvePmcsToPmids(['PMC9035072'])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const calledUrl = fetchMock.mock.calls[0][0] as string
    expect(calledUrl).toContain('elink.fcgi')
    expect(calledUrl).toContain('dbfrom=pmc')
    expect(calledUrl).toContain('db=pubmed')
    // digits only, no PMC prefix in the id= param
    expect(calledUrl).toContain('id=9035072')
    expect(calledUrl).not.toContain('id=PMC')
    expect(result).toEqual({ PMC9035072: '35152405' })
  })

  it('T_C2: empty array → no fetch, empty result', async () => {
    const result = await resolvePmcsToPmids([])
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result).toEqual({})
  })

  it('T_C3: multiple PMCs → ONE batched fetch, all resolved', async () => {
    fetchMock.mockResolvedValueOnce(
      elinkResponse([
        { pmcDigit: '1111', pmid: '111' },
        { pmcDigit: '2222', pmid: '222' },
        { pmcDigit: '3333', pmid: '333' },
      ])
    )
    const result = await resolvePmcsToPmids(['PMC1111', 'PMC2222', 'PMC3333'])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const calledUrl = fetchMock.mock.calls[0][0] as string
    expect(calledUrl).toContain('id=1111,2222,3333')
    expect(result).toEqual({
      PMC1111: '111',
      PMC2222: '222',
      PMC3333: '333',
    })
  })

  it('T_C4: invalid PMC IDs → filtered out, mapped to null', async () => {
    // "PMC" alone and "PMCabc" are invalid; only PMC9035072 is valid.
    fetchMock.mockResolvedValueOnce(
      elinkResponse([{ pmcDigit: '9035072', pmid: '35152405' }])
    )
    const result = await resolvePmcsToPmids(['PMC', 'PMCabc', 'PMC9035072'])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const calledUrl = fetchMock.mock.calls[0][0] as string
    expect(calledUrl).toContain('id=9035072')
    expect(result.PMC).toBeNull()
    expect(result.PMCabc).toBeNull()
    expect(result.PMC9035072).toBe('35152405')
  })

  it('T_C5: linksetdbs missing for one PMC → that one is null', async () => {
    fetchMock.mockResolvedValueOnce(
      elinkResponse([
        { pmcDigit: '1111', pmid: '111' },
        { pmcDigit: '2222', pmid: null }, // no linksetdbs
      ])
    )
    const result = await resolvePmcsToPmids(['PMC1111', 'PMC2222'])
    expect(result).toEqual({ PMC1111: '111', PMC2222: null })
  })

  it('T_C6: linksets returned in different order from input', async () => {
    fetchMock.mockResolvedValueOnce(
      elinkResponse([
        // Reversed from input order
        { pmcDigit: '3333', pmid: '333' },
        { pmcDigit: '1111', pmid: '111' },
        { pmcDigit: '2222', pmid: '222' },
      ])
    )
    const result = await resolvePmcsToPmids(['PMC1111', 'PMC2222', 'PMC3333'])
    expect(result).toEqual({
      PMC1111: '111',
      PMC2222: '222',
      PMC3333: '333',
    })
  })
})
