import { describe, expect, it } from 'vitest'

import receipt from '../../public/fir-taxation/2024/3001.json'
import {
  EDUCATION_RATE_TOLERANCE,
  PROVINCIAL_EDUCATION_RATE,
  firTaxationUrl,
  loadFirTaxationWithFetcher,
  validateFirTaxation,
} from './firTaxation'

function clone(): Record<string, unknown> {
  return structuredClone(receipt) as unknown as Record<string, unknown>
}

function res(payload: Record<string, unknown>): Record<string, unknown> {
  return payload.residential as Record<string, unknown>
}

function fetcherReturning(status: number, body: unknown = {}) {
  return async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })
}

describe('a committed taxation artifact', () => {
  it('validates, and reproduces the documented North Dumfries figures', () => {
    const parsed = validateFirTaxation(receipt)
    expect(parsed.name).toBe('North Dumfries Tp')
    expect(parsed.tier).toBe('LT')
    expect(parsed.residential.taxableAssessmentCvaCad).toBe(1_815_031_052)
    expect(parsed.residential.municipalLowerOrSingleTierCad).toBe(5_208_124)
    expect(parsed.residential.municipalUpperTierCad).toBe(11_175_909)
    expect(parsed.residential.educationCad).toBe(2_776_998)
    expect(parsed.residential.totalTaxesCad).toBe(19_161_031)
  })

  it('lands on the provincial education rate', () => {
    const parsed = validateFirTaxation(receipt)
    expect(
      Math.abs(parsed.residential.educationRate - PROVINCIAL_EDUCATION_RATE),
    ).toBeLessThanOrEqual(EDUCATION_RATE_TOLERANCE)
  })

  it('publishes shares that account for the whole bill', () => {
    const { shares } = validateFirTaxation(receipt).residential
    const sum =
      (shares.municipalLowerOrSingleTier ?? 0) +
      (shares.municipalUpperTier ?? 0) +
      (shares.education ?? 0)
    expect(sum).toBeCloseTo(1, 4)
  })
})

// The builder asserts these too. Checking them again in the browser is the
// point: a figure that passed only on the machine that produced it is a figure
// nobody checked after it crossed the network.
describe('what the reader refuses to render', () => {
  it('refuses a filing that calls itself a receipt', () => {
    const payload = clone()
    payload.isReceipt = true
    expect(() => validateFirTaxation(payload)).toThrow(/isReceipt: false/)
  })

  it('refuses an unsupported schema version', () => {
    const payload = clone()
    payload.schemaVersion = 'fir-taxation-receipt-9.9.9'
    expect(() => validateFirTaxation(payload)).toThrow(/Unsupported FIR taxation schema/)
  })

  it('refuses residential parts that miss the printed total', () => {
    const payload = clone()
    res(payload).educationCad = (res(payload).educationCad as number) + 5_000
    expect(() => validateFirTaxation(payload)).toThrow(/parts sum to/)
  })

  it('refuses a class whose parts miss its printed total', () => {
    const payload = clone()
    const classes = payload.classes as Record<string, unknown>[]
    const other = classes.find((row) => row.code !== '0010')
    expect(other, 'fixture needs a second class').toBeTruthy()
    other!.municipalLowerOrSingleTierCad =
      (other!.municipalLowerOrSingleTierCad as number) + 1_000
    expect(() => validateFirTaxation(payload)).toThrow(/parts sum to/)
  })

  it('refuses an education rate outside the provincial constant', () => {
    const payload = clone()
    // Move education and the total together, so the tautological check still
    // passes and only the province-wide rate catches it. That is the whole
    // reason the second identity exists.
    const bumped = (res(payload).educationCad as number) * 1.5
    res(payload).totalTaxesCad =
      (res(payload).municipalLowerOrSingleTierCad as number) +
      (res(payload).municipalUpperTierCad as number) +
      bumped
    res(payload).educationCad = bumped
    expect(() => validateFirTaxation(payload)).toThrow(/education rate/)
  })

  it('tolerates a cent, because FIR amounts are whole dollars', () => {
    const payload = clone()
    res(payload).totalTaxesCad = (res(payload).totalTaxesCad as number) + 0.01
    expect(() => validateFirTaxation(payload)).not.toThrow()
  })
})

describe('loading', () => {
  it('builds the artifact URL under the deployment base', () => {
    expect(firTaxationUrl('3001', 2024, '/')).toBe('/fir-taxation/2024/3001.json')
    expect(firTaxationUrl('3001', 2024, '/preview/')).toBe(
      '/preview/fir-taxation/2024/3001.json',
    )
  })

  it('treats a missing artifact as absent, not as a failure', async () => {
    // Upper tiers have no taxation receipt because they do not levy on
    // assessment, and eight municipalities have no FIR record at all. Both are
    // facts about the source; neither is our bug, and neither may render as one.
    await expect(
      loadFirTaxationWithFetcher('2400', 2024, fetcherReturning(404), '/'),
    ).resolves.toBeNull()
  })

  it('still fails loudly on a real transport error', async () => {
    await expect(
      loadFirTaxationWithFetcher('3001', 2024, fetcherReturning(500), '/'),
    ).rejects.toThrow(/request failed/)
  })

  it('validates what it loads', async () => {
    const parsed = await loadFirTaxationWithFetcher(
      '3001',
      2024,
      fetcherReturning(200, receipt),
      '/',
    )
    expect(parsed?.assessmentCode).toBe('3001')
  })
})
