import { describe, expect, it } from 'vitest'
import watReceipt from '../data/waterloo/taxpayer-receipt.json'
import camReceipt from '../data/cambridge/taxpayer-receipt.json'
import wooReceipt from '../data/woolwich/taxpayer-receipt.json'
import type { TaxpayerReceipt } from '../types'

describe('config-driven lower-tier packs', () => {
  it('Waterloo builds urban dual-tier bill at $405,000', () => {
    const profile = (watReceipt as unknown as TaxpayerReceipt).profiles.supportedAverageHousehold
    const combined = profile.combinedAtAssessment!
    expect(combined.assessmentCad).toBe(405000)
    expect(combined.totalCad).toBeCloseTo(5800.65, 1)
    expect(profile.regionIllustrationAt354500?.amountCad).toBe(2984)
  })

  it('Cambridge builds urban dual-tier bill at $344,000', () => {
    const profile = (camReceipt as unknown as TaxpayerReceipt).profiles.supportedAverageHousehold
    const combined = profile.combinedAtAssessment!
    expect(combined.assessmentCad).toBe(344000)
    expect(combined.totalCad).toBeCloseTo(5201.9, 1)
    expect(profile.township.gapId).toMatch(/DEPT-SCHEDULE/)
  })

  it('Woolwich uses area-rated Region rate (not urban)', () => {
    const profile = (wooReceipt as unknown as TaxpayerReceipt).profiles.supportedAverageHousehold
    const region = profile.combinedAtAssessment!.components.find((c) =>
      c.label.includes('Region'),
    )!
    expect(region.rate).toBeCloseTo(0.00738314, 8)
    expect(region.rate).not.toBeCloseTo(0.00841834, 8)
    expect(profile.regionIllustrationAt354500?.assessmentCad).toBe(354500)
    // Woolwich column after PIL from shared schedule
    expect(profile.regionIllustrationAt354500?.amountCad).toBe(2617)
  })
})
