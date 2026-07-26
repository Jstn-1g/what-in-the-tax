import type { PlaceSearchRecord } from './placeSearch'

const SCHEMA_VERSION = 'ontario-fir-public-index-1.0.0'
const JURISDICTION = 'CA-ON'
const FISCAL_YEAR = 2023

export type FirTier = 'lower-tier' | 'single-tier' | 'upper-tier'

export type OntarioFirRecord = {
  assessmentCode: string
  displayName: string
  sourceName: string
  typeLabel: string
  tier: FirTier
  lastUpdated: string
}

export type OntarioFirRolloutTarget = {
  order: number
  assessmentCode: string
  label: string
}

export type OntarioFirRegistry = {
  schemaVersion: typeof SCHEMA_VERSION
  artifactKind: 'historical-financial-return-directory'
  jurisdiction: typeof JURISDICTION
  fiscalYear: typeof FISCAL_YEAR
  isReceipt: false
  source: {
    publisher: string
    title: string
    officialIndexUrl: string
    downloadUrl: string
    dataCatalogueUrl: string
    licenceUrl: string
    licenceAttribution: string
    sha256: string
    lastUpdated: string
  }
  coverage: {
    recordsPresent: number
    expectedOntarioReturns: number
    recordsNotPresent: number
    tierCounts: {
      lowerTier: number
      singleTier: number
      upperTier: number
    }
    status: 'incomplete'
  }
  method: {
    primaryKey: 'assessmentCode'
    runtimeAiRequired: false
    runtimeGovernmentRequestsRequired: false
    containsFinancialMetrics: false
    currentTaxBylaw: false
    findingsSupported: false
  }
  rolloutPlan: {
    basis: string
    sharedUpperTierAssessmentCode: string
    cohort: OntarioFirRolloutTarget[]
  }
  caveat: string
  records: OntarioFirRecord[]
}

export type FirFinderRecord = PlaceSearchRecord & {
  kind: 'fir-record'
  id: `fir-on-${string}`
  assessmentCode: string
  fiscalYear: typeof FISCAL_YEAR
  availability: 'fir-record'
}

export type FirRegistryFetchResponse = {
  ok: boolean
  status: number
  json(): Promise<unknown>
}

export type FirRegistryFetcher = (
  url: string,
) => Promise<FirRegistryFetchResponse>

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
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(Date.parse(date))) {
    throw new Error(`${label} must be an ISO calendar date.`)
  }
  return date
}

function parseRecord(value: unknown, index: number): OntarioFirRecord {
  const row = requireObject(value, `records[${index}]`)
  const assessmentCode = requireString(
    row.assessmentCode,
    `records[${index}].assessmentCode`,
  )
  if (!/^\d{4}$/.test(assessmentCode)) {
    throw new Error(`records[${index}].assessmentCode must be four digits.`)
  }
  const tier = requireString(row.tier, `records[${index}].tier`)
  if (!['lower-tier', 'single-tier', 'upper-tier'].includes(tier)) {
    throw new Error(`records[${index}].tier is unsupported.`)
  }

  return {
    assessmentCode,
    displayName: requireString(
      row.displayName,
      `records[${index}].displayName`,
    ),
    sourceName: requireString(row.sourceName, `records[${index}].sourceName`),
    typeLabel: requireString(row.typeLabel, `records[${index}].typeLabel`),
    tier: tier as FirTier,
    lastUpdated: requireIsoDate(
      row.lastUpdated,
      `records[${index}].lastUpdated`,
    ),
  }
}

function parseCohort(
  value: unknown,
  recordCodes: ReadonlySet<string>,
): OntarioFirRolloutTarget[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error('rolloutPlan.cohort must be a non-empty array.')
  }
  const seen = new Set<string>()
  return value.map((candidate, index) => {
    const row = requireObject(candidate, `rolloutPlan.cohort[${index}]`)
    const order = requireInteger(
      row.order,
      `rolloutPlan.cohort[${index}].order`,
    )
    const assessmentCode = requireString(
      row.assessmentCode,
      `rolloutPlan.cohort[${index}].assessmentCode`,
    )
    if (order !== index + 1) {
      throw new Error('rolloutPlan.cohort orders must be contiguous.')
    }
    if (!recordCodes.has(assessmentCode) || seen.has(assessmentCode)) {
      throw new Error('rolloutPlan.cohort must reference unique registry records.')
    }
    seen.add(assessmentCode)
    return {
      order,
      assessmentCode,
      label: requireString(row.label, `rolloutPlan.cohort[${index}].label`),
    }
  })
}

export function validateOntarioFirRegistry(value: unknown): OntarioFirRegistry {
  const root = requireObject(value, 'Ontario FIR registry')
  if (root.schemaVersion !== SCHEMA_VERSION) {
    throw new Error('Unsupported Ontario FIR registry schema.')
  }
  if (
    root.artifactKind !== 'historical-financial-return-directory' ||
    root.jurisdiction !== JURISDICTION ||
    root.fiscalYear !== FISCAL_YEAR
  ) {
    throw new Error('Ontario FIR registry scope is invalid.')
  }
  requireFalse(root.isReceipt, 'isReceipt')

  const source = requireObject(root.source, 'source')
  const sha256 = requireString(source.sha256, 'source.sha256')
  if (!/^[a-f0-9]{64}$/.test(sha256)) {
    throw new Error('source.sha256 must be a lowercase SHA-256 digest.')
  }

  const coverage = requireObject(root.coverage, 'coverage')
  const tierCounts = requireObject(coverage.tierCounts, 'coverage.tierCounts')
  const lowerTier = requireInteger(
    tierCounts.lowerTier,
    'coverage.tierCounts.lowerTier',
  )
  const singleTier = requireInteger(
    tierCounts.singleTier,
    'coverage.tierCounts.singleTier',
  )
  const upperTier = requireInteger(
    tierCounts.upperTier,
    'coverage.tierCounts.upperTier',
  )
  const recordsPresent = requireInteger(
    coverage.recordsPresent,
    'coverage.recordsPresent',
  )
  const expectedOntarioReturns = requireInteger(
    coverage.expectedOntarioReturns,
    'coverage.expectedOntarioReturns',
  )
  const recordsNotPresent = requireInteger(
    coverage.recordsNotPresent,
    'coverage.recordsNotPresent',
  )
  if (
    coverage.status !== 'incomplete' ||
    lowerTier + singleTier + upperTier !== recordsPresent ||
    recordsPresent + recordsNotPresent !== expectedOntarioReturns
  ) {
    throw new Error('Ontario FIR registry coverage does not reconcile.')
  }

  const method = requireObject(root.method, 'method')
  if (method.primaryKey !== 'assessmentCode') {
    throw new Error('Ontario FIR registry primary key is invalid.')
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

  if (!Array.isArray(root.records) || root.records.length !== recordsPresent) {
    throw new Error('Ontario FIR registry record count does not reconcile.')
  }
  const records = root.records.map(parseRecord)
  const codes = new Set(records.map((record) => record.assessmentCode))
  const names = new Set(records.map((record) => record.sourceName))
  if (codes.size !== records.length || names.size !== records.length) {
    throw new Error('Ontario FIR registry codes and source names must be unique.')
  }

  const observedTierCounts = {
    lowerTier: records.filter((record) => record.tier === 'lower-tier').length,
    singleTier: records.filter((record) => record.tier === 'single-tier').length,
    upperTier: records.filter((record) => record.tier === 'upper-tier').length,
  }
  if (
    observedTierCounts.lowerTier !== lowerTier ||
    observedTierCounts.singleTier !== singleTier ||
    observedTierCounts.upperTier !== upperTier
  ) {
    throw new Error('Ontario FIR registry record tiers do not reconcile.')
  }

  const rolloutPlan = requireObject(root.rolloutPlan, 'rolloutPlan')
  const cohort = parseCohort(rolloutPlan.cohort, codes)

  return {
    schemaVersion: SCHEMA_VERSION,
    artifactKind: 'historical-financial-return-directory',
    jurisdiction: JURISDICTION,
    fiscalYear: FISCAL_YEAR,
    isReceipt: false,
    source: {
      publisher: requireString(source.publisher, 'source.publisher'),
      title: requireString(source.title, 'source.title'),
      officialIndexUrl: requireHttps(
        source.officialIndexUrl,
        'source.officialIndexUrl',
      ),
      downloadUrl: requireHttps(source.downloadUrl, 'source.downloadUrl'),
      dataCatalogueUrl: requireHttps(
        source.dataCatalogueUrl,
        'source.dataCatalogueUrl',
      ),
      licenceUrl: requireHttps(source.licenceUrl, 'source.licenceUrl'),
      licenceAttribution: requireString(
        source.licenceAttribution,
        'source.licenceAttribution',
      ),
      sha256,
      lastUpdated: requireIsoDate(source.lastUpdated, 'source.lastUpdated'),
    },
    coverage: {
      recordsPresent,
      expectedOntarioReturns,
      recordsNotPresent,
      tierCounts: {
        lowerTier,
        singleTier,
        upperTier,
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
      basis: requireString(rolloutPlan.basis, 'rolloutPlan.basis'),
      sharedUpperTierAssessmentCode: requireString(
        rolloutPlan.sharedUpperTierAssessmentCode,
        'rolloutPlan.sharedUpperTierAssessmentCode',
      ),
      cohort,
    },
    caveat: requireString(root.caveat, 'caveat'),
    records,
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/`
}

export function ontarioFirRegistryUrl(baseUrl: string): string {
  return `${normalizeBaseUrl(baseUrl)}registry/ontario-fir-2023.json`
}

export async function loadOntarioFirRegistryWithFetcher(
  fetcher: FirRegistryFetcher,
  baseUrl: string,
): Promise<OntarioFirRegistry> {
  const response = await fetcher(ontarioFirRegistryUrl(baseUrl))
  if (!response.ok) {
    throw new Error(`Ontario FIR registry request failed (${response.status}).`)
  }
  return validateOntarioFirRegistry(await response.json())
}

let registryCache: Promise<OntarioFirRegistry> | null = null

export function loadOntarioFirRegistry(): Promise<OntarioFirRegistry> {
  if (registryCache) return registryCache
  registryCache = loadOntarioFirRegistryWithFetcher(
    (url) => fetch(url),
    import.meta.env.BASE_URL,
  ).catch((error: unknown) => {
    registryCache = null
    throw error
  })
  return registryCache
}

export function toFirFinderRecord(
  record: OntarioFirRecord,
  rolloutTargets: ReadonlyMap<string, OntarioFirRolloutTarget>,
): FirFinderRecord {
  const target = rolloutTargets.get(record.assessmentCode)
  const releaseStatus =
    target?.order === 2
      ? 'Next receipt target'
      : target?.order === 3
        ? 'Queued after Wellesley'
        : '2023 provincial filing'

  return {
    kind: 'fir-record',
    id: `fir-on-${record.assessmentCode}`,
    assessmentCode: record.assessmentCode,
    fiscalYear: FISCAL_YEAR,
    label: record.displayName,
    aliases: [record.sourceName, record.assessmentCode],
    province: 'Ontario',
    typeLabel: record.typeLabel,
    releaseStatus,
    availability: 'fir-record',
  }
}
