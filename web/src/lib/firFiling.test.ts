import { describe, expect, it } from 'vitest'
import checkedFiling from '../../public/fir/2023/3001.json'
import {
  filingCodeFromSearch,
  firFilingUrl,
  loadFirFilingWithFetcher,
  validateFirFiling,
} from './firFiling'

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

describe('FIR functional filing', () => {
  it('accepts the checked-in North Dumfries filing and reconciles it', () => {
    const filing = validateFirFiling(checkedFiling)

    expect(filing.assessmentCode).toBe('3001')
    expect(filing.fiscalYear).toBe(2023)
    expect(filing.isReceipt).toBe(false)
    expect(filing.totals.grandTotalCad).toBe(10669698)

    const computed =
      filing.functions.reduce((sum, fn) => sum + fn.amountCad, 0) +
      filing.other.amountCad
    expect(Math.abs(computed - filing.totals.grandTotalCad)).toBeLessThan(0.51)

    for (const fn of filing.functions) {
      if (fn.components.length === 0) continue
      const componentSum = fn.components.reduce((sum, c) => sum + c.amountCad, 0)
      expect(Math.abs(componentSum - fn.amountCad)).toBeLessThan(0.51)
    }
  })

  it('refuses cross-municipality comparison and says why', () => {
    const filing = validateFirFiling(checkedFiling)
    expect(filing.comparability.crossMunicipalityComparable).toBe(false)
    expect(filing.comparability.blockers.length).toBeGreaterThan(0)
    expect(filing.comparability.blockers.map((b) => b.code)).toContain(
      'tier-scope-differs',
    )
  })

  it('rejects a filing that claims to be a receipt', () => {
    const tampered = clone(checkedFiling) as Record<string, unknown>
    tampered.isReceipt = true
    expect(() => validateFirFiling(tampered)).toThrow(/isReceipt/)
  })

  it('rejects a filing that claims to be comparable', () => {
    const tampered = clone(checkedFiling) as Record<string, unknown>
    ;(tampered.comparability as Record<string, unknown>).crossMunicipalityComparable =
      true
    expect(() => validateFirFiling(tampered)).toThrow(/refuse/)
  })

  it('catches a grand total that no longer matches its parts', () => {
    const tampered = clone(checkedFiling) as Record<string, unknown>
    ;(tampered.totals as Record<string, unknown>).grandTotalCad = 999
    expect(() => validateFirFiling(tampered)).toThrow(/sum/)
  })

  it('catches a function whose components no longer add up', () => {
    const tampered = clone(checkedFiling) as Record<string, unknown>
    const functions = tampered.functions as Record<string, unknown>[]
    const withComponents = functions.find(
      (fn) => (fn.components as unknown[]).length > 1,
    )
    expect(withComponents).toBeDefined()
    const components = withComponents!.components as Record<string, unknown>[]
    components[0].amountCad = (components[0].amountCad as number) + 1000
    expect(() => validateFirFiling(tampered)).toThrow(/components sum/)
  })

  it('rejects an unsupported schema version', () => {
    const tampered = clone(checkedFiling) as Record<string, unknown>
    tampered.schemaVersion = 'fir-functional-receipt-9.9.9'
    expect(() => validateFirFiling(tampered)).toThrow(/Unsupported/)
  })

  it('reads only well-formed assessment codes from the query string', () => {
    expect(filingCodeFromSearch('?filing=3001')).toBe('3001')
    expect(filingCodeFromSearch('?pack=north-dumfries-on')).toBeNull()
    expect(filingCodeFromSearch('')).toBeNull()
    // Anything that is not a bare four-digit code is not ours to route.
    expect(filingCodeFromSearch('?filing=../../etc/passwd')).toBeNull()
    expect(filingCodeFromSearch('?filing=30011')).toBeNull()
    expect(filingCodeFromSearch('?filing=abc')).toBeNull()
  })

  it('builds a filing URL under the deployment base', () => {
    expect(firFilingUrl('3001', 2023, '/')).toBe('/fir/2023/3001.json')
    expect(firFilingUrl('3001', 2023, '/preview/')).toBe(
      '/preview/fir/2023/3001.json',
    )
  })

  it('surfaces a failed fetch rather than rendering a partial filing', async () => {
    await expect(
      loadFirFilingWithFetcher(
        '9999',
        2023,
        async () => ({ ok: false, status: 404, json: async () => ({}) }),
        '/',
      ),
    ).rejects.toThrow(/9999/)
  })

  it('loads through the fetcher when the artifact is well formed', async () => {
    const filing = await loadFirFilingWithFetcher(
      '3001',
      2023,
      async (url) => {
        expect(url).toBe('/fir/2023/3001.json')
        return { ok: true, status: 200, json: async () => checkedFiling }
      },
      '/',
    )
    expect(filing.name).toContain('North Dumfries')
  })
})
