/**
 * Load and check one municipality's Schedule 26A taxation receipt.
 *
 * Companion to firFiling.ts, and deliberately built the same way: the artifact
 * is re-checked in the browser rather than trusted because it arrived over the
 * network. The builder already asserts these identities, but a reader who is
 * being asked to believe a number about their own tax bill should not have to
 * take the transport on faith.
 *
 * The two identities are not equally strong, and the code says which is which.
 * Parts summing to the printed total is close to an accounting tautology - the
 * FIR form computes the total that way. Education over CVA landing on Ontario's
 * province-wide rate is a test against a constant the municipality does not
 * control, and it is the one that would actually catch a bad filing.
 */

const SUPPORTED_SCHEMA = 'fir-taxation-receipt-0.1.0'

/** Cent-level. FIR amounts are whole dollars, so more than this is real. */
const IDENTITY_TOLERANCE_CAD = 0.51

/** Ontario's province-wide residential education rate, and the declared band. */
export const PROVINCIAL_EDUCATION_RATE = 0.00153
export const EDUCATION_RATE_TOLERANCE = 0.00005

export type FirTaxationClass = {
  code: string
  label: string
  taxableAssessmentCvaCad: number | null
  totalTaxesCad: number
  municipalLowerOrSingleTierCad: number
  municipalUpperTierCad: number
  educationCad: number
}

export type FirTaxationShares = {
  municipalLowerOrSingleTier: number | null
  municipalUpperTier: number | null
  education: number | null
}

export type FirTaxationReceipt = {
  assessmentCode: string
  slug: string
  name: string
  tier: string
  fiscalYear: number
  residential: {
    taxableAssessmentCvaCad: number
    totalTaxesCad: number
    municipalLowerOrSingleTierCad: number
    municipalUpperTierCad: number
    educationCad: number
    shares: FirTaxationShares
    educationRate: number
  }
  classes: FirTaxationClass[]
  source: {
    title: string
    url: string
    schedule: string
    archiveMemberSha256: string
    note: string
  }
  disclaimer: string
}

function requireObject(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`)
  }
  return value as Record<string, unknown>
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} must be a non-empty string.`)
  }
  return value
}

function requireFiniteNumber(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number.`)
  }
  return value
}

function optionalNumber(value: unknown, label: string): number | null {
  if (value === null || value === undefined) return null
  return requireFiniteNumber(value, label)
}

function parseClass(value: unknown, label: string): FirTaxationClass {
  const row = requireObject(value, label)
  const total = requireFiniteNumber(row.totalTaxesCad, `${label}.totalTaxesCad`)
  const lower = requireFiniteNumber(
    row.municipalLowerOrSingleTierCad,
    `${label}.municipalLowerOrSingleTierCad`,
  )
  const upper = requireFiniteNumber(
    row.municipalUpperTierCad,
    `${label}.municipalUpperTierCad`,
  )
  const education = requireFiniteNumber(row.educationCad, `${label}.educationCad`)

  // Re-derive rather than trust. The builder checks this too; a figure that
  // reaches a reader having passed only one of the two is a figure nobody
  // checked after it left the machine that made it.
  const parts = lower + upper + education
  if (Math.abs(parts - total) > IDENTITY_TOLERANCE_CAD) {
    throw new Error(
      `${label} parts sum to ${parts} but the filing reports ${total}.`,
    )
  }

  return {
    code: requireString(row.code, `${label}.code`),
    label: requireString(row.label, `${label}.label`),
    taxableAssessmentCvaCad: optionalNumber(
      row.taxableAssessmentCvaCad,
      `${label}.taxableAssessmentCvaCad`,
    ),
    totalTaxesCad: total,
    municipalLowerOrSingleTierCad: lower,
    municipalUpperTierCad: upper,
    educationCad: education,
  }
}

export function validateFirTaxation(value: unknown): FirTaxationReceipt {
  const root = requireObject(value, 'FIR taxation receipt')
  const schemaVersion = requireString(root.schemaVersion, 'schemaVersion')
  if (schemaVersion !== SUPPORTED_SCHEMA) {
    throw new Error(
      `Unsupported FIR taxation schema ${schemaVersion}; expected ${SUPPORTED_SCHEMA}.`,
    )
  }
  if (root.isReceipt !== false) {
    // These are filings, not tax bills. A true here would mean something
    // upstream started making the one claim this artifact must not make.
    throw new Error('FIR taxation receipt must declare isReceipt: false.')
  }

  const res = requireObject(root.residential, 'residential')
  const cva = requireFiniteNumber(
    res.taxableAssessmentCvaCad,
    'residential.taxableAssessmentCvaCad',
  )
  if (cva <= 0) {
    throw new Error('residential.taxableAssessmentCvaCad must be positive.')
  }
  const total = requireFiniteNumber(res.totalTaxesCad, 'residential.totalTaxesCad')
  const lower = requireFiniteNumber(
    res.municipalLowerOrSingleTierCad,
    'residential.municipalLowerOrSingleTierCad',
  )
  const upper = requireFiniteNumber(
    res.municipalUpperTierCad,
    'residential.municipalUpperTierCad',
  )
  const education = requireFiniteNumber(res.educationCad, 'residential.educationCad')

  const parts = lower + upper + education
  if (Math.abs(parts - total) > IDENTITY_TOLERANCE_CAD) {
    throw new Error(
      `residential parts sum to ${parts} but the filing reports ${total}.`,
    )
  }

  // The check that is not self-referential: the province sets this rate, so a
  // filing that misses it disagrees with something its author does not control.
  const educationRate = education / cva
  if (Math.abs(educationRate - PROVINCIAL_EDUCATION_RATE) > EDUCATION_RATE_TOLERANCE) {
    throw new Error(
      `residential education rate is ${(educationRate * 100).toFixed(4)}%, outside ` +
        `${(EDUCATION_RATE_TOLERANCE * 100).toFixed(4)}pp of Ontario's ` +
        `${(PROVINCIAL_EDUCATION_RATE * 100).toFixed(4)}%.`,
    )
  }

  if (!Array.isArray(root.classes) || root.classes.length === 0) {
    throw new Error('classes must be a non-empty array.')
  }
  const classes = root.classes.map((entry, index) =>
    parseClass(entry, `classes[${index}]`),
  )

  const source = requireObject(root.source, 'source')
  const shares = requireObject(res.shares, 'residential.shares')

  return {
    assessmentCode: requireString(root.assessmentCode, 'assessmentCode'),
    slug: requireString(root.slug, 'slug'),
    name: requireString(root.name, 'name'),
    tier: requireString(root.tier, 'tier'),
    fiscalYear: requireFiniteNumber(root.fiscalYear, 'fiscalYear'),
    residential: {
      taxableAssessmentCvaCad: cva,
      totalTaxesCad: total,
      municipalLowerOrSingleTierCad: lower,
      municipalUpperTierCad: upper,
      educationCad: education,
      shares: {
        municipalLowerOrSingleTier: optionalNumber(
          shares.municipalLowerOrSingleTier,
          'residential.shares.municipalLowerOrSingleTier',
        ),
        municipalUpperTier: optionalNumber(
          shares.municipalUpperTier,
          'residential.shares.municipalUpperTier',
        ),
        education: optionalNumber(shares.education, 'residential.shares.education'),
      },
      educationRate,
    },
    classes,
    source: {
      title: requireString(source.title, 'source.title'),
      url: requireString(source.url, 'source.url'),
      schedule: requireString(source.schedule, 'source.schedule'),
      archiveMemberSha256: requireString(
        source.archiveMemberSha256,
        'source.archiveMemberSha256',
      ),
      note: requireString(source.note, 'source.note'),
    },
    disclaimer: requireString(root.disclaimer, 'disclaimer'),
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/`
}

export function firTaxationUrl(
  assessmentCode: string,
  fiscalYear: number,
  baseUrl: string,
): string {
  return `${normalizeBaseUrl(baseUrl)}fir-taxation/${fiscalYear}/${encodeURIComponent(
    assessmentCode,
  )}.json`
}

export type FirTaxationFetchResponse = {
  ok: boolean
  status: number
  json(): Promise<unknown>
}

export type FirTaxationFetcher = (url: string) => Promise<FirTaxationFetchResponse>

/**
 * Absent is not the same as broken.
 *
 * Ontario's 30 upper-tier municipalities have no taxation receipt because they
 * do not levy on assessment directly, and eight municipalities have no FIR
 * record at all. Both are facts about the source, so a 404 here resolves to
 * null and the screen says what is true, rather than throwing and rendering as
 * a failure the reader will read as our bug.
 */
export async function loadFirTaxationWithFetcher(
  assessmentCode: string,
  fiscalYear: number,
  fetcher: FirTaxationFetcher,
  baseUrl: string,
): Promise<FirTaxationReceipt | null> {
  const response = await fetcher(firTaxationUrl(assessmentCode, fiscalYear, baseUrl))
  if (response.status === 404) return null
  if (!response.ok) {
    throw new Error(
      `FIR taxation request failed for ${assessmentCode} (${response.status}).`,
    )
  }
  return validateFirTaxation(await response.json())
}

const taxationCache = new Map<string, Promise<FirTaxationReceipt | null>>()

/** Fetch one municipality's committed taxation artifact, or null if it has none. */
export function loadFirTaxation(
  assessmentCode: string,
  fiscalYear: number,
): Promise<FirTaxationReceipt | null> {
  const key = `${fiscalYear}:${assessmentCode}`
  const cached = taxationCache.get(key)
  if (cached) return cached

  const pending = loadFirTaxationWithFetcher(
    assessmentCode,
    fiscalYear,
    (url) => fetch(url),
    import.meta.env.BASE_URL,
  ).catch((error: unknown) => {
    taxationCache.delete(key)
    throw error
  })
  taxationCache.set(key, pending)
  return pending
}
