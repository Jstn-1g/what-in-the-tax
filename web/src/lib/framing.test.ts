import { describe, expect, it } from 'vitest'
import receipt from '../data/taxpayer-receipt.json'
import ledger from '../data/evidence-ledger.json'

type FindingRow = {
  id: string
  category: string
  title: string
  opportunitySeverity: string
  gapIds: string[]
  billImpactCad: number | null
  townshipResponse?: string | null
  belowMateriality?: boolean
}

const findings: FindingRow[] = ledger.findings
const gapIds = new Set(ledger.gaps.map((g: { id: string }) => g.id))
const hints = receipt.uiModelHints

describe('framing and language guardrails', () => {
  it('the word "bloat" appears nowhere in shipped data', () => {
    const blob = JSON.stringify(ledger) + JSON.stringify(receipt)
    expect(blob.toLowerCase()).not.toContain('bloat')
  })

  it('administrative findings use the administrative_scale category', () => {
    const admin = findings.filter((f) => f.id.startsWith('FIND-ADMIN-'))
    expect(admin.length).toBeGreaterThan(0)
    for (const f of admin) expect(f.category).toBe('administrative_scale')
  })

  it('every finding records whether the Township was asked', () => {
    for (const f of findings) expect('townshipResponse' in f).toBe(true)
  })

  it('"flagged" is defined on screen so it cannot be read as "wasted"', () => {
    expect(hints.flaggedDefinition).toBeTruthy()
    expect(String(hints.flaggedDefinition).toLowerCase()).toContain('explanation')
  })

  it('materiality floor is 0.25% of the municipal levy', () => {
    expect(hints.materialityFloorCad).toBe(Math.round(0.0025 * 9002499))
  })

  it('sub-floor findings stay in the ledger but leave published output', () => {
    const below = findings.filter((f) => f.belowMateriality)
    expect(below.map((f) => f.id).sort()).toEqual([
      'FIND-UNUSUAL-HERITAGE-SOFTWARE',
      'FIND-UNUSUAL-PARTNERSHIP-FEES',
    ])
    for (const f of below) {
      expect(hints.publishedFindingIds).not.toContain(f.id)
      expect(hints.marqueeFindings).not.toContain(f.id)
    }
  })

  it('the ACC finding is downgraded to watch and carries its counter-explanation', () => {
    const acc = findings.find((f) => f.id === 'FIND-CAP-DUAL-FACILITY')
    expect(acc?.opportunitySeverity).toBe('watch')
    expect(hints.marqueeFindings).not.toContain('FIND-CAP-DUAL-FACILITY')
  })

  it('every finding gap reference resolves to a live gap', () => {
    for (const f of findings) {
      for (const id of f.gapIds) expect(gapIds.has(id)).toBe(true)
    }
  })

  it('the three new evidence gaps exist', () => {
    for (const id of ['GAP-ND-POP-CURRENT', 'GAP-TWINPAD-OPERATING-DELTA', 'GAP-PEER-BENCHMARK']) {
      expect(gapIds.has(id)).toBe(true)
    }
  })

  it('no finding claims a bill impact', () => {
    for (const f of findings) expect(f.billImpactCad).toBeNull()
  })
})
