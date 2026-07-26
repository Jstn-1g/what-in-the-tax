import { describe, expect, it, vi } from 'vitest'
import {
  loadOntarioFirRegistryWithFetcher,
  ontarioFirRegistryUrl,
  toFirFinderRecord,
  validateOntarioFirRegistry,
} from './ontarioFirRegistry'

function registryFixture() {
  return {
    schemaVersion: 'ontario-fir-public-index-1.0.0',
    artifactKind: 'historical-financial-return-directory',
    jurisdiction: 'CA-ON',
    fiscalYear: 2023,
    isReceipt: false,
    source: {
      publisher: 'Government of Ontario',
      title: 'Financial Information Return',
      officialIndexUrl: 'https://example.test/index',
      downloadUrl: 'https://example.test/archive.zip',
      dataCatalogueUrl: 'https://example.test/catalogue',
      licenceUrl: 'https://example.test/licence',
      licenceAttribution: 'Contains licensed information.',
      sha256: 'a'.repeat(64),
      lastUpdated: '2026-07-24',
    },
    coverage: {
      recordsPresent: 4,
      expectedOntarioReturns: 5,
      recordsNotPresent: 1,
      tierCounts: {
        lowerTier: 4,
        singleTier: 0,
        upperTier: 0,
      },
      status: 'incomplete',
    },
    method: {
      primaryKey: 'assessmentCode',
      runtimeAiRequired: false,
      runtimeGovernmentRequestsRequired: false,
      containsFinancialMetrics: false,
      currentTaxBylaw: false,
      findingsSupported: false,
    },
    rolloutPlan: {
      basis: 'Documented cohort',
      sharedUpperTierAssessmentCode: '3000',
      cohort: [
        { order: 1, assessmentCode: '3001', label: 'North Dumfries' },
        { order: 2, assessmentCode: '3024', label: 'Wellesley' },
        { order: 3, assessmentCode: '3018', label: 'Wilmot' },
        { order: 4, assessmentCode: '3029', label: 'Woolwich' },
      ],
    },
    caveat: 'Historical directory only; not a receipt.',
    records: [
      {
        assessmentCode: '3001',
        displayName: 'North Dumfries',
        sourceName: 'North Dumfries Tp',
        typeLabel: 'Township',
        tier: 'lower-tier',
        lastUpdated: '2026-07-24',
      },
      {
        assessmentCode: '3018',
        displayName: 'Wilmot',
        sourceName: 'Wilmot Tp',
        typeLabel: 'Township',
        tier: 'lower-tier',
        lastUpdated: '2026-07-24',
      },
      {
        assessmentCode: '3024',
        displayName: 'Wellesley',
        sourceName: 'Wellesley Tp',
        typeLabel: 'Township',
        tier: 'lower-tier',
        lastUpdated: '2026-07-24',
      },
      {
        assessmentCode: '3029',
        displayName: 'Woolwich',
        sourceName: 'Woolwich Tp',
        typeLabel: 'Township',
        tier: 'lower-tier',
        lastUpdated: '2026-07-24',
      },
    ],
  }
}

describe('Ontario FIR public registry', () => {
  it('validates a closed, historical directory contract', () => {
    const registry = validateOntarioFirRegistry(registryFixture())

    expect(registry.records).toHaveLength(4)
    expect(registry.isReceipt).toBe(false)
    expect(registry.method.runtimeAiRequired).toBe(false)
    expect(registry.method.currentTaxBylaw).toBe(false)
  })

  it('rejects duplicate codes and unreconciled coverage', () => {
    const duplicate = registryFixture()
    duplicate.records[1] = {
      ...duplicate.records[1],
      assessmentCode: '3001',
      sourceName: 'Different Tp',
    }
    expect(() => validateOntarioFirRegistry(duplicate)).toThrow(/unique/)

    const badCoverage = registryFixture()
    badCoverage.coverage.recordsNotPresent = 0
    expect(() => validateOntarioFirRegistry(badCoverage)).toThrow(/reconcile/)
  })

  it('rejects any receipt, current-by-law, AI, or financial-metric claim', () => {
    for (const mutate of [
      (value: ReturnType<typeof registryFixture>) => {
        value.isReceipt = true
      },
      (value: ReturnType<typeof registryFixture>) => {
        value.method.currentTaxBylaw = true
      },
      (value: ReturnType<typeof registryFixture>) => {
        value.method.runtimeAiRequired = true
      },
      (value: ReturnType<typeof registryFixture>) => {
        value.method.containsFinancialMetrics = true
      },
    ]) {
      const value = registryFixture()
      mutate(value)
      expect(() => validateOntarioFirRegistry(value)).toThrow(/must be false/)
    }
  })

  it('loads one static artifact below the configured base URL', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => registryFixture(),
    })

    await expect(
      loadOntarioFirRegistryWithFetcher(fetcher, '/tax-receipt-prototype/'),
    ).resolves.toMatchObject({ fiscalYear: 2023 })
    expect(fetcher).toHaveBeenCalledWith(
      '/tax-receipt-prototype/registry/ontario-fir-2023.json',
    )
    expect(ontarioFirRegistryUrl('/')).toBe(
      '/registry/ontario-fir-2023.json',
    )
  })

  it('keeps FIR records informational and gives the next targets honest copy', () => {
    const registry = validateOntarioFirRegistry(registryFixture())
    const targets = new Map(
      registry.rolloutPlan.cohort.map((target) => [
        target.assessmentCode,
        target,
      ]),
    )
    const wellesley = toFirFinderRecord(registry.records[2], targets)
    const wilmot = toFirFinderRecord(registry.records[1], targets)

    expect(wellesley).toMatchObject({
      id: 'fir-on-3024',
      availability: 'fir-record',
      releaseStatus: 'Next receipt target',
    })
    expect(wilmot.releaseStatus).toBe('Queued after Wellesley')
    expect(wellesley).not.toHaveProperty('href')
  })
})
