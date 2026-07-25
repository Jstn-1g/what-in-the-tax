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
