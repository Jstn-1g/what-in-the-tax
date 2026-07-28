import type { PlaceSearchRecord } from './placeSearch'

const SCHEMA_VERSION = 'ontario-municipal-history-index-2.0.0'
const JURISDICTION = 'CA-ON'
const FIR_YEARS = [2025, 2024, 2023] as const

export type FirYear = (typeof FIR_YEARS)[number]
export type FirTier = 'lower-tier' | 'single-tier' | 'upper-tier'

export type OntarioFirYearRecord = {
  fiscalYear: FirYear
  lastUpdated: string
  sourceName: string
}

export type OntarioMunicipalityRecord = {
  directoryId: string
  assessmentCode: string | null
  displayName: string
  officialName: string
  sourceNameAliases: string[]
  typeLabel: string
  tier: FirTier
  geographicArea: string
  latestFirYear: FirYear | null
  firYears: OntarioFirYearRecord[]
  fallbackReason: string | null
}

export type OntarioFirRelease = {
  fiscalYear: FirYear
  downloadUrl: string
  sha256: string
  postedDate: string
  sourceLastUpdated: string
  rowCount: number
  uniqueAssessmentCodes: number
  coverageBasis: string
}

export type OntarioMunicipalHistoryRegistry = {
  schemaVersion: typeof SCHEMA_VERSION
  artifactKind: 'current-municipality-directory-with-fir-history'
  jurisdiction: typeof JURISDICTION
  sourceSnapshotDate: string
  isReceipt: false
  sources: {
    currentMunicipalities: {
      publisher: string
      title: string
      dataCatalogueUrl: string
      downloadUrl: string
      sha256: string
      lastUpdated: string
    }
    fir: {
      publisher: string
      title: string
      officialIndexUrl: string
      dataCatalogueUrl: string
      releases: OntarioFirRelease[]
    }
    licenceUrl: string
    licenceAttribution: string
  }
  coverage: {
    currentMunicipalities: number
    withFirHistory: number
    withoutFirHistory: number
    latestFirYearCounts: Record<`${FirYear}`, number> & {
      unavailable: number
    }
    firYearRecordCounts: Record<`${FirYear}`, number>
    tierCounts: {
      lowerTier: number
      singleTier: number
      upperTier: number
    }
    status: 'complete-current-directory'
  }
  method: {
    currentIdentitySource: string
    firSelectionOrder: FirYear[]
    selectionGrain: 'municipality'
    runtimeAiRequired: false
    runtimeGovernmentRequestsRequired: false
    containsFinancialMetrics: false
    currentTaxBylaw: false
    findingsSupported: false
    mixedYearFinancialComparisonsSupported: false
  }
  caveat: string
  records: OntarioMunicipalityRecord[]
}

export type DirectoryFinderRecord = PlaceSearchRecord & {
  kind: 'directory-record'
  id: `directory-${string}`
  directoryId: string
  assessmentCode: string | null
  latestFirYear: FirYear | null
  firYears: FirYear[]
  availability: 'directory-record'
}

export type MunicipalHistoryFetchResponse = {
  ok: boolean
  status: number
  json(): Promise<unknown>
}

export type MunicipalHistoryFetcher = (
  url: string,
) => Promise<MunicipalHistoryFetchResponse>

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function requireObject(
  value: unknown,
  label: string,
): Record<string, unknown> {
  if (!isObject(value)) throw new Error(`${label} must be an object.`)
  return value
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} must be a non-empty string.`)
  }
  return value
}

function requireNullableString(
  value: unknown,
  label: string,
): string | null {
  if (value === null) return null
  return requireString(value, label)
}

function requireInteger(value: unknown, label: string): number {
  if (!Number.isInteger(value) || (value as number) < 0) {
    throw new Error(`${label} must be a non-negative integer.`)
  }
  return value as number
}

function requireFalse(value: unknown, label: string): asserts value is false {
  if (value !== false) throw new Error(`${label} must be false.`)
}

function requireHttps(value: unknown, label: string): string {
  const url = requireString(value, label)
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    throw new Error(`${label} must be a valid URL.`)
  }
  if (parsed.protocol !== 'https:') throw new Error(`${label} must use HTTPS.`)
  return url
}

function requireIsoDate(value: unknown, label: string): string {
  const date = requireString(value, label)
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  if (!match) {
    throw new Error(`${label} must be an ISO calendar date.`)
  }
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    throw new Error(`${label} must be an ISO calendar date.`)
  }
  return date
}

function requireSha256(value: unknown, label: string): string {
  const digest = requireString(value, label)
  if (!/^[a-f0-9]{64}$/.test(digest)) {
    throw new Error(`${label} must be a lowercase SHA-256 digest.`)
  }
  return digest
}

function requireFirYear(value: unknown, label: string): FirYear {
  if (!FIR_YEARS.includes(value as FirYear)) {
    throw new Error(`${label} must be 2025, 2024, or 2023.`)
  }
  return value as FirYear
}

function requireStringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array.`)
  return value.map((item, index) =>
    requireString(item, `${label}[${index}]`),
  )
}

function requireAssessmentCode(
  value: unknown,
  label: string,
): string | null {
  if (value === null) return null
  const code = requireString(value, label)
  if (!/^\d{4}$/.test(code)) {
    throw new Error(`${label} must be four digits or null.`)
  }
  return code
}

function parseFirHistory(
  value: unknown,
  label: string,
): OntarioFirYearRecord[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array.`)
  const years = new Set<FirYear>()
  const history = value.map((candidate, index) => {
    const row = requireObject(candidate, `${label}[${index}]`)
    const fiscalYear = requireFirYear(
      row.fiscalYear,
      `${label}[${index}].fiscalYear`,
    )
    if (years.has(fiscalYear)) {
      throw new Error(`${label} fiscal years must be unique.`)
    }
    years.add(fiscalYear)
    return {
      fiscalYear,
      lastUpdated: requireIsoDate(
        row.lastUpdated,
        `${label}[${index}].lastUpdated`,
      ),
      sourceName: requireString(
        row.sourceName,
        `${label}[${index}].sourceName`,
      ),
    }
  })
  const sortedYears = [...years].sort((left, right) => right - left)
  if (
    history.some(
      (item, index) => item.fiscalYear !== sortedYears[index],
    )
  ) {
    throw new Error(`${label} must be newest first.`)
  }
  return history
}

function parseMunicipalityRecord(
  value: unknown,
  index: number,
): OntarioMunicipalityRecord {
  const label = `records[${index}]`
  const row = requireObject(value, label)
  const tier = requireString(row.tier, `${label}.tier`)
  if (!['lower-tier', 'single-tier', 'upper-tier'].includes(tier)) {
    throw new Error(`${label}.tier is unsupported.`)
  }
  const assessmentCode = requireAssessmentCode(
    row.assessmentCode,
    `${label}.assessmentCode`,
  )
  const history = parseFirHistory(row.firYears, `${label}.firYears`)
  const latestFirYear =
    row.latestFirYear === null
      ? null
      : requireFirYear(row.latestFirYear, `${label}.latestFirYear`)
  if ((history[0]?.fiscalYear ?? null) !== latestFirYear) {
    throw new Error(`${label}.latestFirYear does not match FIR history.`)
  }
  if ((assessmentCode === null) !== (history.length === 0)) {
    throw new Error(
      `${label} assessment code and FIR history availability do not reconcile.`,
    )
  }
  const fallbackReason = requireNullableString(
    row.fallbackReason,
    `${label}.fallbackReason`,
  )
  if (
    (latestFirYear === 2025 && fallbackReason !== null) ||
    (latestFirYear !== 2025 && fallbackReason === null)
  ) {
    throw new Error(`${label}.fallbackReason does not match FIR availability.`)
  }

  return {
    directoryId: requireString(row.directoryId, `${label}.directoryId`),
    assessmentCode,
    displayName: requireString(row.displayName, `${label}.displayName`),
    officialName: requireString(row.officialName, `${label}.officialName`),
    sourceNameAliases: requireStringArray(
      row.sourceNameAliases,
      `${label}.sourceNameAliases`,
    ),
    typeLabel: requireString(row.typeLabel, `${label}.typeLabel`),
    tier: tier as FirTier,
    geographicArea: requireString(
      row.geographicArea,
      `${label}.geographicArea`,
    ),
    latestFirYear,
    firYears: history,
    fallbackReason,
  }
}

export function validateOntarioMunicipalHistory(
  value: unknown,
): OntarioMunicipalHistoryRegistry {
  const root = requireObject(value, 'Ontario municipal history')
  if (
    root.schemaVersion !== SCHEMA_VERSION ||
    root.artifactKind !== 'current-municipality-directory-with-fir-history' ||
    root.jurisdiction !== JURISDICTION
  ) {
    throw new Error('Ontario municipal history scope is invalid.')
  }
  requireFalse(root.isReceipt, 'isReceipt')

  const sources = requireObject(root.sources, 'sources')
  const currentSource = requireObject(
    sources.currentMunicipalities,
    'sources.currentMunicipalities',
  )
  const firSource = requireObject(sources.fir, 'sources.fir')
  if (!Array.isArray(firSource.releases)) {
    throw new Error('sources.fir.releases must be an array.')
  }
  const releases = firSource.releases.map((candidate, index) => {
    const row = requireObject(candidate, `sources.fir.releases[${index}]`)
    return {
      fiscalYear: requireFirYear(
        row.fiscalYear,
        `sources.fir.releases[${index}].fiscalYear`,
      ),
      downloadUrl: requireHttps(
        row.downloadUrl,
        `sources.fir.releases[${index}].downloadUrl`,
      ),
      sha256: requireSha256(
        row.sha256,
        `sources.fir.releases[${index}].sha256`,
      ),
      postedDate: requireIsoDate(
        row.postedDate,
        `sources.fir.releases[${index}].postedDate`,
      ),
      sourceLastUpdated: requireIsoDate(
        row.sourceLastUpdated,
        `sources.fir.releases[${index}].sourceLastUpdated`,
      ),
      rowCount: requireInteger(
        row.rowCount,
        `sources.fir.releases[${index}].rowCount`,
      ),
      uniqueAssessmentCodes: requireInteger(
        row.uniqueAssessmentCodes,
        `sources.fir.releases[${index}].uniqueAssessmentCodes`,
      ),
      coverageBasis: requireString(
        row.coverageBasis,
        `sources.fir.releases[${index}].coverageBasis`,
      ),
    }
  })
  if (
    releases.length !== FIR_YEARS.length ||
    releases.some((release, index) => release.fiscalYear !== FIR_YEARS[index])
  ) {
    throw new Error('FIR releases must be 2025, 2024, and 2023, newest first.')
  }
  const sourceSnapshotDate = requireIsoDate(
    root.sourceSnapshotDate,
    'sourceSnapshotDate',
  )
  const latestPostedDate = releases
    .map((release) => release.postedDate)
    .sort()
    .at(-1)
  if (sourceSnapshotDate !== latestPostedDate) {
    throw new Error('sourceSnapshotDate must equal the latest FIR posted date.')
  }

  const coverage = requireObject(root.coverage, 'coverage')
  const latestCounts = requireObject(
    coverage.latestFirYearCounts,
    'coverage.latestFirYearCounts',
  )
  const yearCounts = requireObject(
    coverage.firYearRecordCounts,
    'coverage.firYearRecordCounts',
  )
  const tierCounts = requireObject(coverage.tierCounts, 'coverage.tierCounts')
  const currentMunicipalities = requireInteger(
    coverage.currentMunicipalities,
    'coverage.currentMunicipalities',
  )
  const withFirHistory = requireInteger(
    coverage.withFirHistory,
    'coverage.withFirHistory',
  )
  const withoutFirHistory = requireInteger(
    coverage.withoutFirHistory,
    'coverage.withoutFirHistory',
  )
  const latestFirYearCounts = {
    '2025': requireInteger(latestCounts['2025'], 'latestFirYearCounts.2025'),
    '2024': requireInteger(latestCounts['2024'], 'latestFirYearCounts.2024'),
    '2023': requireInteger(latestCounts['2023'], 'latestFirYearCounts.2023'),
    unavailable: requireInteger(
      latestCounts.unavailable,
      'latestFirYearCounts.unavailable',
    ),
  }
  const firYearRecordCounts = {
    '2025': requireInteger(yearCounts['2025'], 'firYearRecordCounts.2025'),
    '2024': requireInteger(yearCounts['2024'], 'firYearRecordCounts.2024'),
    '2023': requireInteger(yearCounts['2023'], 'firYearRecordCounts.2023'),
  }
  if (
    releases.some(
      (release) =>
        release.uniqueAssessmentCodes !==
        firYearRecordCounts[`${release.fiscalYear}`],
    )
  ) {
    throw new Error('FIR release counts do not reconcile with coverage.')
  }
  const parsedTierCounts = {
    lowerTier: requireInteger(tierCounts.lowerTier, 'tierCounts.lowerTier'),
    singleTier: requireInteger(tierCounts.singleTier, 'tierCounts.singleTier'),
    upperTier: requireInteger(tierCounts.upperTier, 'tierCounts.upperTier'),
  }
  if (
    coverage.status !== 'complete-current-directory' ||
    withFirHistory + withoutFirHistory !== currentMunicipalities ||
    latestFirYearCounts['2025'] +
      latestFirYearCounts['2024'] +
      latestFirYearCounts['2023'] !==
      withFirHistory ||
    latestFirYearCounts.unavailable !== withoutFirHistory ||
    parsedTierCounts.lowerTier +
      parsedTierCounts.singleTier +
      parsedTierCounts.upperTier !==
      currentMunicipalities
  ) {
    throw new Error('Ontario municipal history coverage does not reconcile.')
  }

  const method = requireObject(root.method, 'method')
  if (
    method.selectionGrain !== 'municipality' ||
    !Array.isArray(method.firSelectionOrder) ||
    method.firSelectionOrder.some(
      (year, index) => year !== FIR_YEARS[index],
    )
  ) {
    throw new Error('Ontario FIR selection policy is invalid.')
  }
  requireFalse(method.runtimeAiRequired, 'method.runtimeAiRequired')
  requireFalse(
    method.runtimeGovernmentRequestsRequired,
    'method.runtimeGovernmentRequestsRequired',
  )
  requireFalse(
    method.containsFinancialMetrics,
    'method.containsFinancialMetrics',
  )
  requireFalse(method.currentTaxBylaw, 'method.currentTaxBylaw')
  requireFalse(method.findingsSupported, 'method.findingsSupported')
  requireFalse(
    method.mixedYearFinancialComparisonsSupported,
    'method.mixedYearFinancialComparisonsSupported',
  )

  if (
    !Array.isArray(root.records) ||
    root.records.length !== currentMunicipalities
  ) {
    throw new Error('Ontario municipality record count does not reconcile.')
  }
  const records = root.records.map(parseMunicipalityRecord)
  const directoryIds = new Set(records.map((record) => record.directoryId))
  const officialNames = new Set(records.map((record) => record.officialName))
  const assessmentCodes = new Set(
    records.flatMap((record) =>
      record.assessmentCode ? [record.assessmentCode] : [],
    ),
  )
  if (
    directoryIds.size !== records.length ||
    officialNames.size !== records.length ||
    assessmentCodes.size !== withFirHistory
  ) {
    throw new Error('Ontario municipality identifiers must be unique.')
  }

  const observedLatest = {
    '2025': records.filter((record) => record.latestFirYear === 2025).length,
    '2024': records.filter((record) => record.latestFirYear === 2024).length,
    '2023': records.filter((record) => record.latestFirYear === 2023).length,
    unavailable: records.filter((record) => record.latestFirYear === null)
      .length,
  }
  const observedYears = {
    '2025': records.filter((record) =>
      record.firYears.some((item) => item.fiscalYear === 2025),
    ).length,
    '2024': records.filter((record) =>
      record.firYears.some((item) => item.fiscalYear === 2024),
    ).length,
    '2023': records.filter((record) =>
      record.firYears.some((item) => item.fiscalYear === 2023),
    ).length,
  }
  const observedTiers = {
    lowerTier: records.filter((record) => record.tier === 'lower-tier').length,
    singleTier: records.filter((record) => record.tier === 'single-tier').length,
    upperTier: records.filter((record) => record.tier === 'upper-tier').length,
  }
  if (
    JSON.stringify(observedLatest) !== JSON.stringify(latestFirYearCounts) ||
    JSON.stringify(observedYears) !== JSON.stringify(firYearRecordCounts) ||
    JSON.stringify(observedTiers) !== JSON.stringify(parsedTierCounts)
  ) {
    throw new Error('Ontario municipality year or tier counts do not reconcile.')
  }

  return {
    schemaVersion: SCHEMA_VERSION,
    artifactKind: 'current-municipality-directory-with-fir-history',
    jurisdiction: JURISDICTION,
    sourceSnapshotDate,
    isReceipt: false,
    sources: {
      currentMunicipalities: {
        publisher: requireString(
          currentSource.publisher,
          'sources.currentMunicipalities.publisher',
        ),
        title: requireString(
          currentSource.title,
          'sources.currentMunicipalities.title',
        ),
        dataCatalogueUrl: requireHttps(
          currentSource.dataCatalogueUrl,
          'sources.currentMunicipalities.dataCatalogueUrl',
        ),
        downloadUrl: requireHttps(
          currentSource.downloadUrl,
          'sources.currentMunicipalities.downloadUrl',
        ),
        sha256: requireSha256(
          currentSource.sha256,
          'sources.currentMunicipalities.sha256',
        ),
        lastUpdated: requireIsoDate(
          currentSource.lastUpdated,
          'sources.currentMunicipalities.lastUpdated',
        ),
      },
      fir: {
        publisher: requireString(
          firSource.publisher,
          'sources.fir.publisher',
        ),
        title: requireString(firSource.title, 'sources.fir.title'),
        officialIndexUrl: requireHttps(
          firSource.officialIndexUrl,
          'sources.fir.officialIndexUrl',
        ),
        dataCatalogueUrl: requireHttps(
          firSource.dataCatalogueUrl,
          'sources.fir.dataCatalogueUrl',
        ),
        releases,
      },
      licenceUrl: requireHttps(sources.licenceUrl, 'sources.licenceUrl'),
      licenceAttribution: requireString(
        sources.licenceAttribution,
        'sources.licenceAttribution',
      ),
    },
    coverage: {
      currentMunicipalities,
      withFirHistory,
      withoutFirHistory,
      latestFirYearCounts,
      firYearRecordCounts,
      tierCounts: parsedTierCounts,
      status: 'complete-current-directory',
    },
    method: {
      currentIdentitySource: requireString(
        method.currentIdentitySource,
        'method.currentIdentitySource',
      ),
      firSelectionOrder: [...FIR_YEARS],
      selectionGrain: 'municipality',
      runtimeAiRequired: false,
      runtimeGovernmentRequestsRequired: false,
      containsFinancialMetrics: false,
      currentTaxBylaw: false,
      findingsSupported: false,
      mixedYearFinancialComparisonsSupported: false,
    },
    caveat: requireString(root.caveat, 'caveat'),
    records,
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/`
}

export function ontarioMunicipalHistoryUrl(baseUrl: string): string {
  return `${normalizeBaseUrl(baseUrl)}registry/ontario-municipal-history.json`
}

export async function loadOntarioMunicipalHistoryWithFetcher(
  fetcher: MunicipalHistoryFetcher,
  baseUrl: string,
): Promise<OntarioMunicipalHistoryRegistry> {
  const response = await fetcher(ontarioMunicipalHistoryUrl(baseUrl))
  if (!response.ok) {
    throw new Error(
      `Ontario municipality directory request failed (${response.status}).`,
    )
  }
  return validateOntarioMunicipalHistory(await response.json())
}

let registryCache: Promise<OntarioMunicipalHistoryRegistry> | null = null

export function loadOntarioMunicipalHistory(): Promise<OntarioMunicipalHistoryRegistry> {
  if (registryCache) return registryCache
  registryCache = loadOntarioMunicipalHistoryWithFetcher(
    (url) => fetch(url),
    import.meta.env.BASE_URL,
  ).catch((error: unknown) => {
    registryCache = null
    throw error
  })
  return registryCache
}

export function toDirectoryFinderRecord(
  record: OntarioMunicipalityRecord,
): DirectoryFinderRecord {
  // Describes what evidence a record already has, never what is planned for it.
  // Publishing a sequence commits the project to an order in public and invites
  // "why not my town yet" against a roadmap that capacity, not ambition, sets.
  const releaseStatus = record.latestFirYear
    ? `Latest FIR ${record.latestFirYear}`
    : 'Current directory only'

  return {
    kind: 'directory-record',
    id: `directory-${record.directoryId}`,
    directoryId: record.directoryId,
    assessmentCode: record.assessmentCode,
    latestFirYear: record.latestFirYear,
    firYears: record.firYears.map((item) => item.fiscalYear),
    label: record.displayName,
    aliases: [
      record.officialName,
      ...record.sourceNameAliases,
      ...(record.assessmentCode ? [record.assessmentCode] : []),
      record.geographicArea,
    ],
    province: 'Ontario',
    typeLabel: record.typeLabel,
    releaseStatus,
    availability: 'directory-record',
  }
}
