/**
 * FIR-grade functional filings.
 *
 * These are Ontario's own Schedule 40 expense breakdowns, built by
 * scripts/build_fir_functional_receipts.py. They are a lower evidence grade
 * than gold by-law packs and are deliberately kept on a separate route: a
 * filing never opens a ?pack= URL, and PACK_CATALOG never learns about one.
 *
 * Parsing is strict on purpose. A malformed artifact must fail loudly rather
 * than render a partial receipt that appears authoritative.
 */

export type FirFilingComponent = {
  code: string
  slc: string
  label: string
  amountCad: number
}

export type FirFilingFunction = FirFilingComponent & {
  shareOfTotal: number | null
  components: FirFilingComponent[]
}

export type FirFilingComparability = {
  crossMunicipalityComparable: boolean
  reason: string
  declaredPopulationFloor: number
  belowPopulationFloor: boolean
  blockers: { code: string; detail: string }[]
  note: string
}

export type FirFiling = {
  schemaVersion: string
  grade: string
  badge: string
  isReceipt: boolean
  slug: string
  assessmentCode: string
  name: string
  tier: string
  fiscalYear: number
  currency: string
  source: {
    title: string
    schedule: string
    measure: string
    url: string
    localZipSha256: string
    note: string
  }
  totals: {
    grandTotalCad: number
    populationFir: number | null
    perCapitaCad: number | null
    sharesReported: boolean
  }
  functions: FirFilingFunction[]
  other: FirFilingComponent & { components: FirFilingComponent[]; note: string }
  comparability: FirFilingComparability
  disclaimer: string
}

const SUPPORTED_SCHEMA = 'fir-functional-receipt-0.1.0'

/** Amounts may be negative (recoveries) but must be finite. */
function requireFiniteNumber(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number.`)
  }
  return value
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} must be a non-empty string.`)
  }
  return value
}

function requireObject(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`)
  }
  return value as Record<string, unknown>
}

function parseComponent(value: unknown, label: string): FirFilingComponent {
  const row = requireObject(value, label)
  return {
    code: requireString(row.code, `${label}.code`),
    slc: requireString(row.slc, `${label}.slc`),
    label: requireString(row.label, `${label}.label`),
    amountCad: requireFiniteNumber(row.amountCad, `${label}.amountCad`),
  }
}

export function validateFirFiling(value: unknown): FirFiling {
  const root = requireObject(value, 'FIR filing')
  const schemaVersion = requireString(root.schemaVersion, 'schemaVersion')
  if (schemaVersion !== SUPPORTED_SCHEMA) {
    throw new Error(
      `Unsupported FIR filing schema ${schemaVersion}; expected ${SUPPORTED_SCHEMA}.`,
    )
  }
  if (root.isReceipt !== false) {
    // The builder marks these false. A true here would mean something upstream
    // started calling a filing a receipt, which is the one claim it must not make.
    throw new Error('FIR filing must declare isReceipt: false.')
  }

  const totals = requireObject(root.totals, 'totals')
  const grandTotalCad = requireFiniteNumber(totals.grandTotalCad, 'totals.grandTotalCad')
  const population =
    totals.populationFir === null
      ? null
      : requireFiniteNumber(totals.populationFir, 'totals.populationFir')
  const perCapita =
    totals.perCapitaCad === null
      ? null
      : requireFiniteNumber(totals.perCapitaCad, 'totals.perCapitaCad')
  const sharesReported = totals.sharesReported === true

  if (!Array.isArray(root.functions) || root.functions.length === 0) {
    throw new Error('functions must be a non-empty array.')
  }
  const functions: FirFilingFunction[] = root.functions.map((entry, index) => {
    const row = requireObject(entry, `functions[${index}]`)
    const base = parseComponent(entry, `functions[${index}]`)
    const rawComponents = Array.isArray(row.components) ? row.components : []
    const components = rawComponents.map((child, childIndex) =>
      parseComponent(child, `functions[${index}].components[${childIndex}]`),
    )
    // Re-derive the group identity in the browser. The builder asserts it too,
    // but a reader should not have to trust bytes that travelled over a network.
    const componentSum = components.reduce((sum, item) => sum + item.amountCad, 0)
    if (components.length > 0 && Math.abs(componentSum - base.amountCad) > 0.51) {
      throw new Error(
        `functions[${index}] components sum to ${componentSum} but the filing reports ${base.amountCad}.`,
      )
    }
    return {
      ...base,
      shareOfTotal:
        typeof row.shareOfTotal === 'number' && Number.isFinite(row.shareOfTotal)
          ? row.shareOfTotal
          : null,
      components,
    }
  })

  const otherRow = requireObject(root.other, 'other')
  const otherComponents = (
    Array.isArray(otherRow.components) ? otherRow.components : []
  ).map((child, index) => parseComponent(child, `other.components[${index}]`))
  const other = {
    code: requireString(otherRow.code, 'other.code'),
    slc: typeof otherRow.slc === 'string' ? otherRow.slc : '',
    label: requireString(otherRow.label, 'other.label'),
    amountCad: requireFiniteNumber(otherRow.amountCad, 'other.amountCad'),
    components: otherComponents,
    note: requireString(otherRow.note, 'other.note'),
  }

  // The identity the whole filing rests on, re-checked client side.
  const computed =
    functions.reduce((sum, item) => sum + item.amountCad, 0) + other.amountCad
  if (Math.abs(computed - grandTotalCad) > 0.51) {
    throw new Error(
      `Functions plus other sum to ${computed} but the filing reports ${grandTotalCad}.`,
    )
  }

  const comparabilityRow = requireObject(root.comparability, 'comparability')
  if (comparabilityRow.crossMunicipalityComparable !== false) {
    throw new Error('FIR filings must refuse cross-municipality comparison.')
  }
  const blockers = (
    Array.isArray(comparabilityRow.blockers) ? comparabilityRow.blockers : []
  ).map((entry, index) => {
    const row = requireObject(entry, `comparability.blockers[${index}]`)
    return {
      code: requireString(row.code, `comparability.blockers[${index}].code`),
      detail: requireString(row.detail, `comparability.blockers[${index}].detail`),
    }
  })

  const sourceRow = requireObject(root.source, 'source')

  return {
    schemaVersion,
    grade: requireString(root.grade, 'grade'),
    badge: requireString(root.badge, 'badge'),
    isReceipt: false,
    slug: requireString(root.slug, 'slug'),
    assessmentCode: requireString(root.assessmentCode, 'assessmentCode'),
    name: requireString(root.name, 'name'),
    tier: requireString(root.tier, 'tier'),
    fiscalYear: requireFiniteNumber(root.fiscalYear, 'fiscalYear'),
    currency: requireString(root.currency, 'currency'),
    source: {
      title: requireString(sourceRow.title, 'source.title'),
      schedule: requireString(sourceRow.schedule, 'source.schedule'),
      measure: requireString(sourceRow.measure, 'source.measure'),
      url: requireString(sourceRow.url, 'source.url'),
      localZipSha256: requireString(sourceRow.localZipSha256, 'source.localZipSha256'),
      note: requireString(sourceRow.note, 'source.note'),
    },
    totals: {
      grandTotalCad,
      populationFir: population,
      perCapitaCad: perCapita,
      sharesReported,
    },
    functions,
    other,
    comparability: {
      crossMunicipalityComparable: false,
      reason: requireString(comparabilityRow.reason, 'comparability.reason'),
      declaredPopulationFloor: requireFiniteNumber(
        comparabilityRow.declaredPopulationFloor,
        'comparability.declaredPopulationFloor',
      ),
      belowPopulationFloor: comparabilityRow.belowPopulationFloor === true,
      blockers,
      note: requireString(comparabilityRow.note, 'comparability.note'),
    },
    disclaimer: requireString(root.disclaimer, 'disclaimer'),
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/`
}

export function firFilingUrl(
  assessmentCode: string,
  fiscalYear: number,
  baseUrl: string,
): string {
  return `${normalizeBaseUrl(baseUrl)}fir/${fiscalYear}/${encodeURIComponent(
    assessmentCode,
  )}.json`
}

export type FirFilingFetchResponse = {
  ok: boolean
  status: number
  json(): Promise<unknown>
}

export type FirFilingFetcher = (url: string) => Promise<FirFilingFetchResponse>

const filingCache = new Map<string, Promise<FirFiling>>()

export async function loadFirFilingWithFetcher(
  assessmentCode: string,
  fiscalYear: number,
  fetcher: FirFilingFetcher,
  baseUrl: string,
): Promise<FirFiling> {
  const response = await fetcher(firFilingUrl(assessmentCode, fiscalYear, baseUrl))
  if (!response.ok) {
    throw new Error(
      `FIR filing request failed for ${assessmentCode} (${response.status}).`,
    )
  }
  return validateFirFiling(await response.json())
}

/** Fetch one municipality's committed filing artifact. */
export function loadFirFiling(
  assessmentCode: string,
  fiscalYear: number,
): Promise<FirFiling> {
  const key = `${fiscalYear}:${assessmentCode}`
  const cached = filingCache.get(key)
  if (cached) return cached

  const pending = loadFirFilingWithFetcher(
    assessmentCode,
    fiscalYear,
    (url) => fetch(url),
    import.meta.env.BASE_URL,
  ).catch((error: unknown) => {
    filingCache.delete(key)
    throw error
  })
  filingCache.set(key, pending)
  return pending
}

/** Fiscal years with published filings, newest first. */
export const FIR_FILING_YEARS = [2025, 2024, 2023] as const

export type FilingRoute = { code: string; year: number | null }

/**
 * Read ?filing=<assessmentCode>&year=<fiscalYear> without disturbing pack
 * routing. A missing or unrecognised year is null, which the caller resolves to
 * that municipality's newest published filing - Ontario files on its own
 * schedule, so the newest year differs by place.
 */
export function filingRouteFromSearch(search: string): FilingRoute | null {
  const params = new URLSearchParams(search)
  const requested = params.get('filing')
  // Assessment codes are short numeric strings. Anything else is not ours.
  if (!requested || !/^\d{4}$/.test(requested)) return null
  const rawYear = params.get('year')
  const parsed = rawYear && /^\d{4}$/.test(rawYear) ? Number(rawYear) : null
  const year =
    parsed !== null && (FIR_FILING_YEARS as readonly number[]).includes(parsed)
      ? parsed
      : null
  return { code: requested, year }
}

/** Retained for callers that only need the municipality. */
export function filingCodeFromSearch(search: string): string | null {
  return filingRouteFromSearch(search)?.code ?? null
}
