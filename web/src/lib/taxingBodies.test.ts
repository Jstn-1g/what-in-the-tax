import { describe, expect, it } from 'vitest'

import brant from '../data/brant/taxpayer-receipt.json'
import kitchener from '../data/kitchener/taxpayer-receipt.json'
import northDumfries from '../data/taxpayer-receipt.json'
import {
  assertBillIsCoherent,
  billShares,
  TaxingBodyError,
  taxingBodiesFor,
} from './taxingBodies'
import type { TaxpayerReceipt } from '../types'

function profileOf(receipt: unknown) {
  const data = receipt as unknown as TaxpayerReceipt
  return { profile: data.profiles.supportedAverageHousehold }
}

describe('reading a declared bill', () => {
  // County of Brant is the case this change exists for, and it is already in
  // the repository rather than a fixture written to make a point.
  it('gives a single-tier municipality a shorter bill, not a phantom row', () => {
    const { profile } = profileOf(brant)
    const bill = taxingBodiesFor(profile, 'brant-county-on')
    expect(bill.bodies.map((b) => b.role)).toEqual(['local', 'special-area', 'education'])
    expect(bill.bodies.some((b) => b.label.includes('n/a'))).toBe(false)
  })

  it('shows the hospital levy the three-slot schema was hiding', () => {
    // $78.04 that Brant residents pay and the old shape folded into the County
    // portion, because there was no fourth slot to put it in.
    const { profile } = profileOf(brant)
    const hospital = taxingBodiesFor(profile, 'brant-county-on').bodies.find(
      (b) => b.role === 'special-area',
    )
    expect(hospital?.amountCad).toBeCloseTo(78.04, 2)
    expect(hospital?.sourceFactId).toBe('DRV-BRANT-BILL-HOSPITAL-391K')
  })

  it('says why there is no upper tier rather than leaving a hole', () => {
    const { profile } = profileOf(brant)
    const bill = taxingBodiesFor(profile, 'brant-county-on')
    expect(bill.inapplicable.map((entry) => entry.role)).toEqual(['upper-tier'])
    expect(bill.inapplicable[0].reason).toContain('single-tier')
  })

  it('adds up to the total the receipt prints, with one fewer body', () => {
    const { profile } = profileOf(brant)
    const bill = taxingBodiesFor(profile, 'brant-county-on')
    const summed = bill.bodies.reduce((sum, b) => sum + b.amountCad, 0)
    expect(Math.abs(summed - (profile.combinedTotalCad ?? 0))).toBeLessThan(0.05)
    expect(billShares(bill).reduce((sum, s) => sum + s.share, 0)).toBeCloseTo(1, 6)
  })
})

describe('every committed pack', () => {
  // All six declare their bodies now. This is the regression guard: if a builder
  // stops emitting them, the pack it produces stops rendering, and that should
  // fail here rather than in a browser.
  it.each([
    ['north-dumfries-on', northDumfries, ['local', 'upper-tier', 'education']],
    ['kitchener-on', kitchener, ['local', 'upper-tier', 'education']],
    ['brant-county-on', brant, ['local', 'special-area', 'education']],
  ])('%s declares a coherent bill', (slug, receipt, roles) => {
    const { profile } = profileOf(receipt)
    const bill = taxingBodiesFor(profile, slug)
    expect(bill.bodies.map((b) => b.role)).toEqual(roles)
    const summed = bill.bodies.reduce((sum, b) => sum + b.amountCad, 0)
    expect(Math.abs(summed - (profile.combinedTotalCad ?? 0))).toBeLessThan(0.05)
  })
})

describe('a receipt that has not declared its bodies', () => {
  it('is refused rather than guessed at', () => {
    // The legacy buckets cannot be converted honestly. A bucket cites an
    // allocation fact and a component cites a rate fact, at different
    // assessments, and their ids do not join - so the only way to pair them is
    // the display label, which this receipt's own disclaimer forbids using to
    // guess a role. Refusing is the only correct behaviour left.
    const undeclared = {
      ...profileOf(northDumfries).profile,
      taxingBodies: undefined,
    }
    expect(() => taxingBodiesFor(undeclared, 'somewhere-on')).toThrow(TaxingBodyError)
    expect(() => taxingBodiesFor(undeclared, 'somewhere-on')).toThrow(
      /somewhere-on does not declare taxingBodies/,
    )
    expect(() => taxingBodiesFor(undeclared, 'somewhere-on')).toThrow(/builder that produced/)
  })
})

describe('what a bill is refused for', () => {
  const local = {
    id: 'local', role: 'local' as const, label: 'City', order: 0,
    amountCad: 100, basis: 'b', evidenceStatus: 'DERIVED',
  }

  it('refuses a bill with no local municipality', () => {
    // Every property-tax bill is issued by somebody. A receipt without one is
    // not a receipt with a gap; it is not a receipt.
    expect(() =>
      assertBillIsCoherent(
        { bodies: [{ ...local, role: 'education', id: 'ed', label: 'Education' }], inapplicable: [] },
        100,
      ),
    ).toThrow(TaxingBodyError)
  })

  it('refuses two local governments', () => {
    expect(() =>
      assertBillIsCoherent({ bodies: [local, { ...local, id: 'other' }], inapplicable: [] }, 200),
    ).toThrow(/at most one local/)
  })

  it('refuses parts that do not add to the printed total', () => {
    // The failure this project can least afford: a receipt whose visible
    // breakdown disagrees with the number at the top of the page.
    expect(() => assertBillIsCoherent({ bodies: [local], inapplicable: [] }, 250)).toThrow(
      /sum to 100.00 but the receipt prints 250.00/,
    )
  })

  it('refuses a role that is both charged and declared not applicable', () => {
    expect(() =>
      assertBillIsCoherent(
        { bodies: [local], inapplicable: [{ role: 'local', reason: 'no' }] },
        100,
      ),
    ).toThrow(/both as a taxing body and as not applicable/)
  })

  it('accepts a bill with four bodies, including a special area rate', () => {
    // North Dumfries' Ayr urban variant is bolted onto combinedAtAssessment
    // today because there is no fourth slot. There is now.
    const bill = {
      bodies: [
        local,
        { ...local, id: 'area', role: 'special-area' as const, label: 'Ayr urban', order: 1, amountCad: 70 },
        { ...local, id: 'ut', role: 'upper-tier' as const, label: 'Region', order: 2, amountCad: 300 },
        { ...local, id: 'ed', role: 'education' as const, label: 'Education', order: 3, amountCad: 60 },
      ],
      inapplicable: [],
    }
    expect(() => assertBillIsCoherent(bill, 530)).not.toThrow()
    expect(billShares(bill).map((s) => s.body.role)).toEqual([
      'local', 'special-area', 'upper-tier', 'education',
    ])
  })
})
