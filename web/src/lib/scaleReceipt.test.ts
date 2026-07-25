import { describe, expect, it } from 'vitest'
import receipt from '../data/taxpayer-receipt.json'
import ledger from '../data/evidence-ledger.json'
import type { TaxpayerReceipt } from '../types'

describe('evidence-first receipt', () => {
  const data = receipt as unknown as TaxpayerReceipt

  it('marks $5,000 combined bill as allocatable now that by-law rates are cited', () => {
    expect(data.profiles.hypothetical5000.allocatable).toBe(true)
  })

  it('keeps supported township and region totals', () => {
    const profile = data.profiles.supportedAverageHousehold
    expect(profile.township.amountCad).toBeCloseTo(1434.63, 2)
    expect(profile.region.amountCad).toBe(2543)
    expect(profile.combinedTotalCad).toBeCloseTo(5395.61, 2)
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

type LedgerRow = { id: string; amountCad?: number | null }
type ReceiptLine = { id: string; amountCad: number; subLines?: { amountCad: number }[] }

describe('allocation base reconciliation', () => {
  const derivedRows: LedgerRow[] = ledger.derived
  const factRows: LedgerRow[] = ledger.facts
  const byId = (rows: LedgerRow[], id: string) => rows.find((row) => row.id === id)

  it('expenditure base ties to published revenues with zero residual', () => {
    expect(byId(derivedRows, 'DRV-ND-BASE-TIES-TO-REVENUES')?.amountCad).toBe(0)
  })

  it('base equals the sum of its cited component facts', () => {
    const componentIds = [
      'ND-DEPT-CORPORATE-2026',
      'ND-DEPT-PROTECTIVE-2026',
      'ND-DEPT-PW-2026',
      'ND-DEPT-ENVIRONMENTAL-2026',
      'ND-DEPT-REC-2026',
      'ND-DEPT-PLANNING-2026',
      'ND-CAPITAL-FUNDED-BY-LEVY-2026',
    ]
    const sum = componentIds.reduce((acc, id) => acc + (byId(factRows, id)?.amountCad ?? 0), 0)
    expect(sum).toBe(byId(derivedRows, 'DRV-ND-DEPT-SUM')?.amountCad)
    expect(sum).toBe(10049624)
  })

  it('base is NOT the municipal levy - those are different quantities', () => {
    expect(byId(derivedRows, 'DRV-ND-DEPT-SUM')?.amountCad).not.toBe(9002499)
  })

  it('Council and Elections are inside Corporate Services, not separate base components', () => {
    const council = byId(factRows, 'ND-COUNCIL-2026')?.amountCad ?? 0
    const elections = byId(factRows, 'ND-ELECTIONS-2026')?.amountCad ?? 0
    const admin = byId(factRows, 'ND-CORP-SERV-ADMIN-2026')?.amountCad ?? 0
    expect(council + elections + admin + 5300 + 5500).toBe(
      byId(factRows, 'ND-DEPT-CORPORATE-2026')?.amountCad,
    )
  })

  it('governance sub-line is disclosure only and is never summed into the total', () => {
    const lines: ReceiptLine[] = receipt.profiles.supportedAverageHousehold.township.lineItems
    const sum = lines.reduce((acc, line) => acc + line.amountCad, 0)
    expect(sum).toBeCloseTo(1434.63, 2)
    const corporate = lines.find((line) => line.id === 'ND-DEPT-CORPORATE-2026')
    const subTotal = (corporate?.subLines ?? []).reduce((acc, sub) => acc + sub.amountCad, 0)
    expect(subTotal).toBeGreaterThan(0)
    expect(sum + subTotal).not.toBeCloseTo(1434.63, 2)
  })
})