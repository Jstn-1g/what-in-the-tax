import { describe, expect, it } from 'vitest'
import receipt from '../data/taxpayer-receipt.json'
import type { TaxpayerReceipt } from '../types'

describe('evidence-first receipt', () => {
  const data = receipt as unknown as TaxpayerReceipt

  it('marks $5,000 combined bill as not allocatable', () => {
    expect(data.profiles.hypothetical5000.allocatable).toBe(false)
  })

  it('keeps supported township and region totals', () => {
    const profile = data.profiles.supportedAverageHousehold
    expect(profile.township.amountCad).toBeCloseTo(1434.63, 2)
    expect(profile.region.amountCad).toBe(2543)
    expect(profile.combinedTotalCad).toBeNull()
  })

  it('keeps finding bill impacts null', () => {
    expect(data.findings.every((finding) => finding.billImpactCad === null)).toBe(true)
  })
})

describe('schema guards', () => {
  const data = receipt as unknown as TaxpayerReceipt

  it('every finding has a usable opportunitySeverity', () => {
    for (const finding of data.findings) {
      expect(typeof finding.opportunitySeverity, finding.id).toBe('string')
    }
  })

  it('no finding carries a stray severity-like key', () => {
    for (const finding of data.findings) {
      const strays = Object.keys(finding).filter(
        (key) => /severity/i.test(key) && key !== 'opportunitySeverity',
      )
      expect(strays, finding.id).toEqual([])
    }
  })

  it('every marquee finding resolves to a real finding', () => {
    const ids = new Set(data.findings.map((finding) => finding.id))
    for (const id of data.uiModelHints.marqueeFindings) {
      expect(ids.has(id), id).toBe(true)
    }
  })

  it('region line items reconcile to the published total', () => {
    const region = data.profiles.supportedAverageHousehold.region
    const sum = (region.lineItems ?? []).reduce((acc, line) => acc + line.amountCad, 0)
    expect(sum).toBe(region.amountCad)
  })

  it('township allocated lines tie to the cited township total', () => {
    const township = data.profiles.supportedAverageHousehold.township
    const sum = (township.lineItems ?? []).reduce((acc, line) => acc + line.amountCad, 0)
    expect(sum).toBeCloseTo(township.amountCad ?? 0, 2)
  })
})
