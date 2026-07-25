import { describe, expect, it } from 'vitest'
import receipt from '../data/taxpayer-receipt.json'
import ledger from '../data/evidence-ledger.json'

const ASSESSMENT = 455_000

type RateRow = { id: string; value?: number | null }

describe('combined bill from By-law 3637-26 Schedule A', () => {
  const combined = receipt.profiles.supportedAverageHousehold.combinedAtAssessment
  const rates: RateRow[] = ledger.facts
  const rate = (id: string) => rates.find((r) => r.id === id)?.value ?? 0

  it('is built at a single assessment', () => {
    expect(combined.assessmentCad).toBe(ASSESSMENT)
  })

  it('each component equals its by-law rate times the assessment, to the cent', () => {
    for (const component of combined.components) {
      expect(component.amountCad).toBeCloseTo(Math.round(component.rate * ASSESSMENT * 100) / 100, 2)
    }
  })

  it('component rates sum exactly to the printed Total 2026 Rate', () => {
    const summed = combined.components.reduce((acc, c) => acc + c.rate, 0)
    expect(summed).toBeCloseTo(rate('ND-TAXRATE-RES-TOTAL-2026-FINAL'), 10)
    expect(summed).toBeCloseTo(combined.totalRate, 10)
  })

  it('component dollars sum to the stated rural total', () => {
    const summed = combined.components.reduce((acc, c) => acc + c.amountCad, 0)
    expect(summed).toBeCloseTo(combined.totalCad, 2)
    expect(combined.totalCad).toBeCloseTo(5395.61, 2)
  })

  it('the township component reproduces the separately cited township figure', () => {
    const township = combined.components.find((c) => c.label.includes('North Dumfries'))
    expect(township?.amountCad).toBeCloseTo(
      receipt.profiles.supportedAverageHousehold.township.amountCad,
      2,
    )
  })

  it('the Ayr urban variant differs from rural by exactly the Special Area Rate', () => {
    const ayr = combined.ayrUrbanVariant
    expect(ayr.totalCad - combined.totalCad).toBeCloseTo(ayr.specialAreaRateCad, 2)
    expect(ayr.totalRate - combined.totalRate).toBeCloseTo(rate('ND-TAXRATE-RES-AYR-SAR-2026-FINAL'), 10)
  })

  it('township rate plus Ayr SAR reproduces the draft binder urban figure', () => {
    const urban = (rate('ND-TAXRATE-RES-TOWNSHIP-2026-FINAL') + rate('ND-TAXRATE-RES-AYR-SAR-2026-FINAL')) * ASSESSMENT
    expect(urban).toBeCloseTo(1505.47, 1)
  })

  it('the $5,000 profile is derived, not invented: shares sum to 1 and imply the stated assessment', () => {
    const h = receipt.profiles.hypothetical5000
    const shares = h.compositionShares.reduce((acc, s) => acc + s.share, 0)
    expect(shares).toBeCloseTo(1, 5)
    expect(h.impliedAssessmentCad * combined.totalRate).toBeCloseTo(5000, 0)
  })
})
