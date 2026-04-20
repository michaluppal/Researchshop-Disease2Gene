import { describe, it, expect } from 'vitest'
import { parseIdentifiers } from '../SmartInput'

describe('parseIdentifiers', () => {
  it('T_P1: raw PMID digits', () => {
    const res = parseIdentifiers('12345678')
    expect(res).toHaveLength(1)
    expect(res[0]).toMatchObject({ type: 'pmid', value: '12345678' })
  })

  it('T_P2: PMID: prefix', () => {
    const res = parseIdentifiers('PMID: 12345678')
    expect(res).toHaveLength(1)
    expect(res[0]).toMatchObject({ type: 'pmid', value: '12345678' })
  })

  it('T_P3: raw DOI', () => {
    const res = parseIdentifiers('10.1038/nature12373')
    expect(res).toHaveLength(1)
    expect(res[0]).toMatchObject({ type: 'doi', value: '10.1038/nature12373' })
  })

  it('T_P4: DOI: prefix', () => {
    const res = parseIdentifiers('DOI: 10.1038/nature12373')
    expect(res).toHaveLength(1)
    expect(res[0]).toMatchObject({ type: 'doi', value: '10.1038/nature12373' })
  })

  it('T_P5: doi.org URL', () => {
    const res = parseIdentifiers('https://doi.org/10.1038/nature12373')
    expect(res).toHaveLength(1)
    expect(res[0]).toMatchObject({ type: 'doi', value: '10.1038/nature12373' })
  })

  it('T_P6: uppercase PMC ID', () => {
    const res = parseIdentifiers('PMC9035072')
    expect(res).toHaveLength(1)
    expect(res[0]).toMatchObject({ type: 'pmc', value: 'PMC9035072' })
  })

  it('T_P7: lowercase pmc ID is upcased', () => {
    const res = parseIdentifiers('pmc9035072')
    expect(res).toHaveLength(1)
    expect(res[0]).toMatchObject({ type: 'pmc', value: 'PMC9035072' })
  })

  it('T_P8: PMC URL', () => {
    const res = parseIdentifiers('https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9035072/')
    expect(res).toHaveLength(1)
    expect(res[0]).toMatchObject({ type: 'pmc', value: 'PMC9035072' })
  })

  it('T_P9: PubMed URL', () => {
    const res = parseIdentifiers('https://pubmed.ncbi.nlm.nih.gov/12345678/')
    expect(res).toHaveLength(1)
    expect(res[0]).toMatchObject({ type: 'pmid', value: '12345678' })
  })

  it('T_P10: random text → unknown', () => {
    const res = parseIdentifiers('random text')
    expect(res).toHaveLength(1)
    expect(res[0].type).toBe('unknown')
  })

  it('T_P11: newline-separated mixed identifiers', () => {
    const res = parseIdentifiers('12345678\nDOI: 10.1038/nature12373\nPMC9035072')
    expect(res).toHaveLength(3)
    expect(res[0]).toMatchObject({ type: 'pmid', value: '12345678' })
    expect(res[1]).toMatchObject({ type: 'doi', value: '10.1038/nature12373' })
    expect(res[2]).toMatchObject({ type: 'pmc', value: 'PMC9035072' })
  })

  it('T_P12: semicolon and comma separators', () => {
    const res = parseIdentifiers('12345678;10.1038/nature12373,PMC9035072')
    expect(res).toHaveLength(3)
    const types = res.map((r) => r.type).sort()
    expect(types).toEqual(['doi', 'pmc', 'pmid'])
  })

  it('T_P13: empty string → 0 items', () => {
    expect(parseIdentifiers('')).toHaveLength(0)
    expect(parseIdentifiers('   ')).toHaveLength(0)
  })
})
