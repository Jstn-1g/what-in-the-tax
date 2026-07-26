import { describe, expect, it } from 'vitest'
import { buildHeroBriefing } from './heroBriefing'
import ndReceipt from '../data/taxpayer-receipt.json'
import ndAudit from '../data/citation-audit.json'
import brantReceipt from '../data/brant/taxpayer-receipt.json'
import brantAudit from '../data/brant/citation-audit.json'
import brantLedger from '../data/brant/evidence-ledger.json'
import ndLedger from '../data/evidence-ledger.json'
import type { TaxpayerReceipt } from '../types'

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
    expect(model!.destinations.length).toBeGreaterThanOrEqual(3)
    expect(model!.destinations.length).toBeLessThanOrEqual(6)
    expect(model!.destinations[0].shareOfMunicipal).toBeGreaterThan(0)
    expect(model!.destinations[0].label).toMatch(/Public Works|Corporate|Recreation/i)
    expect(model!.destinationsBasis.toLowerCase()).toContain('township portion')
    expect(model!.attention.some((c) => c.id === 'watch' && c.tone === 'watch')).toBe(true)
    expect(model!.attention.find((c) => c.id === 'gaps')?.tone).toBe('gap')
    expect(model!.attention.find((c) => c.id === 'cite')?.tone).toBe('cite-ok')
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
    expect(model!.destinations[0].label).toBe('Operations')
    expect(model!.destinations[0].shareOfMunicipal).toBeGreaterThan(0.2)
    expect(model!.destinations.length).toBeGreaterThanOrEqual(3)
    expect(model!.destinations.length).toBeLessThanOrEqual(6)
    expect(model!.attention.find((c) => c.id === 'watch')?.label).toBe('0 Watch')
    expect(model!.attention.find((c) => c.id === 'watch')?.href).toBeUndefined()
    expect(model!.attention.find((c) => c.id === 'gaps')?.label).toBe('4 Gaps')
    expect(model!.attention.find((c) => c.id === 'cite')?.tone).toBe('cite-ok')
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
