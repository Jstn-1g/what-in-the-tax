import { describe, expect, it } from 'vitest'
import { buildHeroBriefing } from './heroBriefing'
import kitReceipt from '../data/kitchener/taxpayer-receipt.json'
import kitLedger from '../data/kitchener/evidence-ledger.json'
import type { TaxpayerReceipt } from '../types'

describe('kitchener receipt', () => {
  it('builds a dual-tier combined bill at the published average assessment', () => {
    const profile = (kitReceipt as unknown as TaxpayerReceipt).profiles.supportedAverageHousehold
    const combined = profile.combinedAtAssessment!
    expect(combined.assessmentCad).toBe(326000)
    expect(combined.totalCad).toBeCloseTo(4583.55, 2)
    expect(combined.components.map((c) => c.label)).toEqual([
      'City of Kitchener',
      'Region of Waterloo',
      'Education (Province of Ontario)',
    ])
    expect(profile.township.amountCad).toBeCloseTo(1340.39, 2)
    expect(profile.region.amountCad).toBeCloseTo(2744.38, 2)
  })

  it('keeps department shares tied to the city portion', () => {
    const lines =
      (kitReceipt as unknown as TaxpayerReceipt).profiles.supportedAverageHousehold.township
        .lineItems ?? []
    const allocated = lines
      .filter((l) => l.classification === 'city_levy_allocated')
      .reduce((sum, l) => sum + l.amountCad, 0)
    const rounding = lines
      .filter((l) => l.classification === 'reconciling_item')
      .reduce((sum, l) => sum + l.amountCad, 0)
    expect(allocated + rounding).toBeCloseTo(1340.39, 2)
  })

  it('builds At a glance with City · Region · Education shares', () => {
    const model = buildHeroBriefing(
      kitReceipt as unknown as TaxpayerReceipt,
      kitLedger.gaps,
      null,
      { municipalBucketLabel: 'City portion' },
    )
    expect(model).not.toBeNull()
    expect(model!.shares.map((s) => s.shortLabel)).toEqual(['City', 'Region', 'Education'])
    expect(model!.destinationsStatus).toBe('allocated')
    expect(model!.destinations[0].label).toBe('Community Services')
    expect(model!.attention.find((c) => c.id === 'gaps')?.tone).toBe('gap')
  })

  it('keeps Region bill total as rate × $326k and imports urban schedule as illustration', () => {
    const profile = (kitReceipt as unknown as TaxpayerReceipt).profiles.supportedAverageHousehold
    expect(profile.region.amountCad).toBeCloseTo(2744.38, 2)
    expect(profile.region.lineItems?.map((l) => l.id)).toEqual(['KIT-REGION-RATE-PORTION'])
    const illustration = profile.regionIllustrationAt354500
    expect(illustration).toBeDefined()
    expect(illustration!.assessmentCad).toBe(354500)
    expect(illustration!.amountCad).toBe(2984)
    expect(illustration!.lineItemsSumCheckCad).toBe(2984)
    const serviceLines = (illustration!.lineItems ?? []).filter((l) =>
      /^ROW-HH-URBAN-\d{2}$/.test(l.id),
    )
    expect(serviceLines.length).toBe(23)
    // Regional Library is $0 on the urban column (area-rated to rural/woolwich/wilmot).
    expect(serviceLines.some((l) => l.amountCad === 0)).toBe(true)
  })

  it('closes GAP-KIT-REGION-SCHEDULE and keeps an assessment-bridge gap', () => {
    const closed = (kitLedger as { closedGaps?: { id: string }[] }).closedGaps ?? []
    const open = kitLedger.gaps
    expect(closed.some((g) => g.id === 'GAP-KIT-REGION-SCHEDULE')).toBe(true)
    expect(open.some((g) => g.id === 'GAP-KIT-REGION-ASSESSMENT-BRIDGE')).toBe(true)
    expect(open.some((g) => g.id === 'GAP-KIT-REGION-SCHEDULE')).toBe(false)
  })
})
