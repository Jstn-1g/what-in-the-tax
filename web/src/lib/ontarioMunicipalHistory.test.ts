import { describe, expect, it, vi } from 'vitest'
import checkedArtifact from '../../public/registry/ontario-municipal-history.json'
import {
  loadOntarioMunicipalHistoryWithFetcher,
  ontarioMunicipalHistoryUrl,
  toDirectoryFinderRecord,
  validateOntarioMunicipalHistory,
} from './ontarioMunicipalHistory'

function record(
  assessmentCode: string,
  displayName: string,
  years: number[],
) {
  return {
    directoryId: `on-${assessmentCode}`,
    assessmentCode,
    displayName,
    officialName: `${displayName}, Township of`,
    sourceNameAliases: [`${displayName} Tp`],
    typeLabel: 'Township',
    tier: 'lower-tier',
    geographicArea: 'Waterloo',
    latestFirYear: years[0] ?? null,
    firYears: years.map((fiscalYear) => ({
      fiscalYear,
      lastUpdated: '2026-07-24',
      sourceName: `${displayName} Tp`,
    })),
    fallbackReason:
      years[0] === 2025 ? null : 'A newer locked FIR record is unavailable.',
  }
}

function registryFixture() {
  return {
    schemaVersion: 'ontario-municipal-history-index-2.0.0',
    artifactKind: 'current-municipality-directory-with-fir-history',
    jurisdiction: 'CA-ON',
    sourceSnapshotDate: '2026-07-25',
    isReceipt: false,
    sources: {
      currentMunicipalities: {
        publisher: 'Government of Ontario',
        title: 'Current municipality directory',
        dataCatalogueUrl: 'https://example.test/current',
        downloadUrl: 'https://example.test/current.csv',
        sha256: 'a'.repeat(64),
        lastUpdated: '2026-06-03',
      },
      fir: {
        publisher: 'Government of Ontario',
        title: 'Financial Information Return',
        officialIndexUrl: 'https://example.test/fir',
        dataCatalogueUrl: 'https://example.test/fir-catalogue',
        releases: [
          {
            fiscalYear: 2025,
            downloadUrl: 'https://example.test/2025.zip',
            sha256: 'b'.repeat(64),
            postedDate: '2026-07-25',
            sourceLastUpdated: '2026-07-24',
            rowCount: 10,
            uniqueAssessmentCodes: 1,
            coverageBasis: 'Unique assessment codes in the bulk file.',
          },
          {
            fiscalYear: 2024,
            downloadUrl: 'https://example.test/2024.zip',
            sha256: 'c'.repeat(64),
            postedDate: '2026-07-24',
            sourceLastUpdated: '2026-07-24',
            rowCount: 20,
            uniqueAssessmentCodes: 2,
            coverageBasis: 'Unique assessment codes in the bulk file.',
          },
          {
            fiscalYear: 2023,
            downloadUrl: 'https://example.test/2023.zip',
            sha256: 'd'.repeat(64),
            postedDate: '2026-07-24',
            sourceLastUpdated: '2026-07-24',
            rowCount: 30,
            uniqueAssessmentCodes: 4,
            coverageBasis: 'Unique assessment codes in the bulk file.',
          },
        ],
      },
      licenceUrl: 'https://example.test/licence',
      licenceAttribution: 'Contains licensed information.',
    },
    coverage: {
      currentMunicipalities: 4,
      withFirHistory: 4,
      withoutFirHistory: 0,
      latestFirYearCounts: {
        '2025': 1,
        '2024': 1,
        '2023': 2,
        unavailable: 0,
      },
      firYearRecordCounts: {
        '2025': 1,
        '2024': 2,
        '2023': 4,
      },
      tierCounts: {
        lowerTier: 4,
        singleTier: 0,
        upperTier: 0,
      },
      status: 'complete-current-directory',
    },
    method: {
      currentIdentitySource: 'Ontario municipalities dataset',
      firSelectionOrder: [2025, 2024, 2023],
      selectionGrain: 'municipality',
      runtimeAiRequired: false,
      runtimeGovernmentRequestsRequired: false,
      containsFinancialMetrics: false,
      currentTaxBylaw: false,
      findingsSupported: false,
      mixedYearFinancialComparisonsSupported: false,
    },
    caveat: 'Current identity and historical FIR years are separate.',
    records: [
      record('3001', 'North Dumfries', [2024, 2023]),
      record('3018', 'Wilmot', [2023]),
      record('3024', 'Wellesley', [2025, 2024, 2023]),
      record('3029', 'Woolwich', [2023]),
    ],
  }
}

describe('Ontario current directory with FIR history', () => {
  it('validates the checked 444-municipality current-first artifact', () => {
    const registry = validateOntarioMunicipalHistory(checkedArtifact)

    expect(registry.coverage).toMatchObject({
      currentMunicipalities: 444,
      withFirHistory: 436,
      withoutFirHistory: 8,
      latestFirYearCounts: {
        // Deep River T and Simcoe Co filed 2025 in the 2026-07-29
        // re-publication, so each moves from the 2024 bucket to the 2025 one:
        // 130 -> 132 and 273 -> 271. The pair still totals 403, which is what
        // says they moved together rather than one of them drifting.
        '2025': 132,
        '2024': 271,
        '2023': 33,
        unavailable: 8,
      },
    })
    expect(registry.isReceipt).toBe(false)
    expect(registry.method.runtimeAiRequired).toBe(false)
    expect(registry.method.mixedYearFinancialComparisonsSupported).toBe(false)
  })

  it('requires descending per-municipality years and reconciled counts', () => {
    const valid = validateOntarioMunicipalHistory(registryFixture())
    expect(valid.records.find((row) => row.assessmentCode === '3024')).toMatchObject({
      latestFirYear: 2025,
    })

    const wrongOrder = registryFixture()
    wrongOrder.records[2].firYears.reverse()
    expect(() => validateOntarioMunicipalHistory(wrongOrder)).toThrow(
      /newest first/,
    )

    const badCoverage = registryFixture()
    badCoverage.coverage.latestFirYearCounts['2025'] = 2
    expect(() => validateOntarioMunicipalHistory(badCoverage)).toThrow(
      /reconcile/,
    )

    const badReleaseCount = registryFixture()
    badReleaseCount.sources.fir.releases[0].uniqueAssessmentCodes = 2
    expect(() => validateOntarioMunicipalHistory(badReleaseCount)).toThrow(
      /release counts/,
    )

    const badFallback = registryFixture()
    badFallback.records[0].fallbackReason = null
    expect(() => validateOntarioMunicipalHistory(badFallback)).toThrow(
      /fallbackReason/,
    )
  })

  it('requires real calendar dates and a reconciled snapshot date', () => {
    const invalidCalendarDate = registryFixture()
    invalidCalendarDate.sourceSnapshotDate = '2026-02-30'
    expect(() =>
      validateOntarioMunicipalHistory(invalidCalendarDate),
    ).toThrow(/ISO calendar date/)

    const staleSnapshot = registryFixture()
    staleSnapshot.sourceSnapshotDate = '2026-07-24'
    expect(() => validateOntarioMunicipalHistory(staleSnapshot)).toThrow(
      /latest FIR posted date/,
    )
  })

  it('rejects receipt, current-law, AI, financial, and mixed-year claims', () => {
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
      (value: ReturnType<typeof registryFixture>) => {
        value.method.mixedYearFinancialComparisonsSupported = true
      },
    ]) {
      const value = registryFixture()
      mutate(value)
      expect(() => validateOntarioMunicipalHistory(value)).toThrow(
        /must be false/,
      )
    }
  })

  it('loads the stable multi-year artifact below the configured base URL', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => registryFixture(),
    })

    await expect(
      loadOntarioMunicipalHistoryWithFetcher(
        fetcher,
        '/what-in-the-tax/',
      ),
    ).resolves.toMatchObject({
      sourceSnapshotDate: '2026-07-25',
    })
    expect(fetcher).toHaveBeenCalledWith(
      '/what-in-the-tax/registry/ontario-municipal-history.json',
    )
    expect(ontarioMunicipalHistoryUrl('/')).toBe(
      '/registry/ontario-municipal-history.json',
    )
  })

  it('keeps directory records informational and exposes retained years', () => {
    const registry = validateOntarioMunicipalHistory(registryFixture())
    const wellesley = toDirectoryFinderRecord(registry.records[2])
    const wilmot = toDirectoryFinderRecord(registry.records[1])

    expect(wellesley).toMatchObject({
      id: 'directory-on-3024',
      kind: 'directory-record',
      availability: 'directory-record',
      latestFirYear: 2025,
      firYears: [2025, 2024, 2023],
      releaseStatus: 'Latest FIR 2025',
    })
    expect(wilmot.releaseStatus).not.toMatch(/queued|next|target/i)
    expect(wellesley).not.toHaveProperty('href')
  })
})
