import { describe, expect, it } from 'vitest'
import receipt from '../data/brant/taxpayer-receipt.json'
import ledger from '../data/brant/evidence-ledger.json'
import type { TaxpayerReceipt } from '../types'

describe('brant-county-on / Paris receipt', () => {
  const data = receipt as unknown as TaxpayerReceipt
  const profile = data.profiles.supportedAverageHousehold

  it('resolves Paris as County of Brant single-tier', () => {
    expect(data.jurisdiction?.slug).toBe('brant-county-on')
    expect(data.jurisdiction?.aliases).toContain('Paris')
    expect(data.jurisdiction?.level).toBe('single-tier')
  })

  it('builds the full RT bill at the County median assessment', () => {
    expect(profile.combinedAtAssessment?.assessmentCad).toBe(391000)
    expect(profile.combinedTotalCad).toBeCloseTo(4893.56, 2)
    expect(profile.township.amountCad).toBeCloseTo(4295.33, 2)
    expect(profile.education.amountCad).toBeCloseTo(598.23, 2)
  })

  it('does not invent an upper-tier Region column', () => {
    expect(profile.region.amountCad).toBeNull()
    expect(profile.region.evidenceStatus).toBe('GAP')
    expect(profile.region.gapId).toBe('GAP-BRANT-NO-UPPER-TIER')
  })

  it('keeps department shares tied to the municipal portion', () => {
    const lines = profile.township.lineItems ?? []
    const sum = lines.reduce((acc, line) => acc + line.amountCad, 0)
    expect(sum).toBeCloseTo(profile.township.amountCad ?? 0, 2)
  })

  it('ships Tier 0 with no findings and null bill impacts forever', () => {
    expect(data.findings).toEqual([])
    expect(ledger.gaps.some((g) => g.id === 'GAP-PARIS-ALIAS')).toBe(true)
  })

  it('rate components sum to the printed total rate', () => {
    const combined = profile.combinedAtAssessment
    const rateSum = (combined?.components ?? []).reduce((acc, c) => acc + c.rate, 0)
    expect(rateSum).toBeCloseTo(combined?.totalRate ?? 0, 8)
  })
})
