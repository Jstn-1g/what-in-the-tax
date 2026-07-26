import { describe, expect, it } from 'vitest'
import { buildHeroBriefing } from './heroBriefing'
import ndReceipt from '../data/taxpayer-receipt.json'
import ndAudit from '../data/citation-audit.json'
import brantReceipt from '../data/brant/taxpayer-receipt.json'
import brantAudit from '../data/brant/citation-audit.json'
import brantLedger from '../data/brant/evidence-ledger.json'
import ndLedger from '../data/evidence-ledger.json'
import kitReceipt from '../data/kitchener/taxpayer-receipt.json'
import kitLedger from '../data/kitchener/evidence-ledger.json'
import watReceipt from '../data/waterloo/taxpayer-receipt.json'
import watLedger from '../data/waterloo/evidence-ledger.json'
import type { Gap, TaxpayerReceipt } from '../types'

describe('buildHeroBriefing', () => {
  it('builds ND bill shares that sum to ~100% and flag Region as largest', () => {
    const model = buildHeroBriefing(
      ndReceipt as unknown as TaxpayerReceipt,
      ndLedger.gaps,
      ndAudit,
      { municipalBucketLabel: 'Township portion' },
    )
    expect(model).not.toBeNull()
    const shareSum = model!.shares.reduce((a, s) => a + s.share, 0)
    expect(shareSum).toBeCloseTo(1, 5)
    expect(model!.shares.map((s) => s.shortLabel)).toEqual(['Township', 'Region', 'Education'])
    const largest = [...model!.shares].sort((a, b) => b.share - a.share)[0]
    expect(largest.shortLabel).toBe('Region')
    expect(model!.destinationsStatus).toBe('allocated')
    expect(model!.destinations.length).toBeGreaterThanOrEqual(3)
    expect(model!.destinations.length).toBeLessThanOrEqual(6)
    expect(model!.destinations[0].shareOfMunicipal).toBeGreaterThan(0)
    expect(model!.destinations[0].label).toMatch(/Public Works|Corporate|Recreation/i)
    expect(model!.destinationsBasis.toLowerCase()).toContain('township portion')
    expect(model!.attention.some((c) => c.id === 'watch' && c.tone === 'watch')).toBe(true)
    expect(model!.attention.find((c) => c.id === 'gaps')?.tone).toBe('gap')
    expect(model!.attention.find((c) => c.id === 'cite')?.tone).toBe('cite-weak')
    expect(model!.footnote).toMatch(/Ayr urban|Special Area Rate/i)
  })

  it('builds Brant single-tier shares with County dominant and 0 Watch', () => {
    const model = buildHeroBriefing(
      brantReceipt as unknown as TaxpayerReceipt,
      brantLedger.gaps,
      brantAudit,
      { municipalBucketLabel: 'County portion' },
    )
    expect(model).not.toBeNull()
    expect(model!.totalCad).toBeCloseTo(4893.56, 2)
    expect(model!.shares.map((s) => s.shortLabel)).toEqual(['County', 'Hospital', 'Education'])
    expect(model!.destinationsStatus).toBe('allocated')
    expect(model!.destinations[0].label).toBe('Operations')
    expect(model!.destinations[0].shareOfMunicipal).toBeGreaterThan(0.2)
    expect(model!.destinations.length).toBeGreaterThanOrEqual(3)
    expect(model!.destinations.length).toBeLessThanOrEqual(6)
    expect(model!.attention.find((c) => c.id === 'watch')?.label).toBe('0 Watch')
    expect(model!.attention.find((c) => c.id === 'watch')?.href).toBeUndefined()
    expect(model!.attention.find((c) => c.id === 'gaps')?.label).toBe('2 Gaps')
    expect(model!.attention.find((c) => c.id === 'cite')?.tone).toBe('cite-ok')
  })

  it('builds Kitchener destinations as allocated department lines', () => {
    const model = buildHeroBriefing(
      kitReceipt as unknown as TaxpayerReceipt,
      kitLedger.gaps,
      null,
      { municipalBucketLabel: 'City portion' },
    )
    expect(model).not.toBeNull()
    expect(model!.destinationsStatus).toBe('allocated')
    expect(model!.destinationsGapId).toBeUndefined()
    expect(model!.destinations[0].label).toBe('Community Services')
    expect(model!.destinations.length).toBeGreaterThanOrEqual(3)
  })

  it('marks Waterloo destinations as gap with DEPT-SCHEDULE id (no invented split)', () => {
    const model = buildHeroBriefing(
      watReceipt as unknown as TaxpayerReceipt,
      watLedger.gaps as Gap[],
      null,
      { municipalBucketLabel: 'City portion' },
    )
    expect(model).not.toBeNull()
    expect(model!.shares.length).toBe(3)
    expect(model!.destinationsStatus).toBe('gap')
    expect(model!.destinations).toEqual([])
    expect(model!.destinationsGapId).toBe('GAP-WAT-DEPT-SCHEDULE')
    expect(model!.destinationsGapTitle).toMatch(/department|allocation/i)
    expect(model!.destinationsBasis).toMatch(/gap|not invented/i)
    expect(model!.attention.find((c) => c.id === 'gaps')?.detail).toMatch(/GAP-WAT-DEPT-SCHEDULE/)
    expect(model!.footnote).toMatch(/department destinations stay blank/i)
  })

  it('still builds the hero when township destinations are empty', () => {
    const base = watReceipt as unknown as TaxpayerReceipt
    const stripped: TaxpayerReceipt = {
      ...base,
      profiles: {
        ...base.profiles,
        supportedAverageHousehold: {
          ...base.profiles.supportedAverageHousehold,
          township: {
            ...base.profiles.supportedAverageHousehold.township,
            lineItems: [],
            gapId: undefined,
          },
        },
      },
    }
    const model = buildHeroBriefing(stripped, watLedger.gaps as Gap[], null)
    expect(model).not.toBeNull()
    expect(model!.destinationsStatus).toBe('gap')
    expect(model!.destinations).toEqual([])
    expect(model!.destinationsGapId).toBe('GAP-WAT-DEPT-SCHEDULE')
    expect(model!.shares.length).toBeGreaterThan(0)
  })

  it('excludes hospital special levy and credits from destination ranking', () => {
    const model = buildHeroBriefing(
      brantReceipt as unknown as TaxpayerReceipt,
      brantLedger.gaps,
      brantAudit,
    )
    const labels = model!.destinations.map((d) => d.label)
    expect(labels).not.toContain('Hospital special levy')
    expect(labels).not.toContain('Taxation & Corporate Finances')
  })

  it('links Watch chip only when there are published findings to open', () => {
    const withWatch = buildHeroBriefing(
      ndReceipt as unknown as TaxpayerReceipt,
      ndLedger.gaps,
      ndAudit,
    )
    expect(withWatch!.attention.find((c) => c.id === 'watch')?.href).toBe('#watch')
  })
})
