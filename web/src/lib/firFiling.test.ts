import { describe, expect, it } from 'vitest'
import checkedFiling from '../../public/fir/2023/3001.json'
import {
  filingCodeFromSearch,
  filingRouteFromSearch,
  FIR_FILING_YEARS,
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

  it('reads an explicit filing year when it is one we publish', () => {
    expect(filingRouteFromSearch('?filing=1999&year=2025')).toEqual({
      code: '1999',
      year: 2025,
    })
    expect(filingRouteFromSearch('?filing=1999&year=2023')).toEqual({
      code: '1999',
      year: 2023,
    })
  })

  it('falls back to no year rather than guessing an unpublished one', () => {
    // A year we do not publish must resolve to null so the caller opens the
    // municipality's newest actual filing instead of fetching a 404.
    expect(filingRouteFromSearch('?filing=1999&year=1899')?.year).toBeNull()
    expect(filingRouteFromSearch('?filing=1999&year=abcd')?.year).toBeNull()
    expect(filingRouteFromSearch('?filing=1999')?.year).toBeNull()
  })

  it('publishes years newest first so the first entry is the default', () => {
    expect([...FIR_FILING_YEARS]).toEqual([2025, 2024, 2023])
    expect(FIR_FILING_YEARS[0]).toBe(Math.max(...FIR_FILING_YEARS))
  })

  it('builds a filing URL under the deployment base', () => {
    expect(firFilingUrl('3001', 2023, '/')).toBe('/fir/2023/3001.json')
    expect(firFilingUrl('3001', 2023, '/preview/')).toBe(
      '/preview/fir/2023/3001.json',
    )
  })

  it('keeps shares, with a note, when a line is merely negative', () => {
    // The common case: twelve Ontario filings book a recovery against one
    // function, so its share is negative and the rest add past 100%. Those
    // percentages are accurate and worth reading -- Faraday Tp 2023 spends
    // -63.6% on environmental services and that is the story of its page.
    // Suppressing them would have cost Mississauga its whole share column over
    // a single -0.1% line. Shares stay; the note explains.
    const negativeLine = clone(checkedFiling) as Record<string, unknown>
    const negTotals = negativeLine.totals as Record<string, unknown>
    negTotals.sharesNote =
      'One line below is negative, because this municipality booked a recovery.'

    const kept = validateFirFiling(negativeLine)
    expect(kept.totals.sharesReported).toBe(true)
    expect(kept.totals.sharesNote).toContain('negative')
    expect(kept.functions.every((fn) => fn.shareOfTotal !== null)).toBe(true)
  })

  it('carries the reason when a filing withholds its shares', () => {
    // The rare case, and the only one that drops the column: Carlow-Mayo Tp
    // 2023 files a -$1,751,200 "Other" against a $973,603 total, so the total
    // is net of a recovery bigger than itself and transportation alone read
    // 127.4% on the live site. A part cannot exceed the whole. This pins that
    // the reason survives parsing, because a blank column with no explanation
    // is worse than the bad number it replaced.
    const withheld = clone(checkedFiling) as Record<string, unknown>
    const totals = withheld.totals as Record<string, unknown>
    totals.sharesReported = false
    totals.sharesNote =
      "Percentages are withheld for this filing. Its 'Other' line is negative."

    const filing = validateFirFiling(withheld)
    expect(filing.totals.sharesReported).toBe(false)
    expect(filing.totals.sharesNote).toContain('withheld')
    // The amounts are the evidence and must be untouched by the suppression.
    expect(filing.totals.grandTotalCad).toBe(10669698)
    const computed =
      filing.functions.reduce((sum, fn) => sum + fn.amountCad, 0) +
      filing.other.amountCad
    expect(Math.abs(computed - filing.totals.grandTotalCad)).toBeLessThan(0.51)
  })

  it('renders a filing built before sharesNote existed', () => {
    // Every artifact already deployed predates the field. Missing must parse as
    // "no note", never as a validation failure - the amounts are still good.
    const legacy = clone(checkedFiling) as Record<string, unknown>
    delete (legacy.totals as Record<string, unknown>).sharesNote

    const filing = validateFirFiling(legacy)
    expect(filing.totals.sharesNote).toBeNull()
    expect(filing.totals.sharesReported).toBe(true)
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
