import type { CitationAudit } from './lib/evidenceLookup'
import type {
  Derived,
  Fact,
  Gap,
  Source,
  TaxpayerReceipt,
} from './types'

export const PUBLIC_PACK_SCHEMA_VERSION = '1.0.0'
const RECEIPT_SCHEMA_VERSION = '2.0.0'
const PUBLIC_EVIDENCE_POLICY_REF = 'Evidence included with this preview'

type JsonObject = Record<string, unknown>

export type ValidatedPublicPack = {
  id: string
  receipt: TaxpayerReceipt
  evidence: {
    gaps: Gap[]
    evidencePolicy: { rules: string[] }
    sources: Source[]
    facts: Fact[]
    derived: Derived[]
  }
  audit: CitationAudit
}

const BANNED_PUBLIC_KEYS = new Set([
  'closedGaps',
  'extractedText',
  'localPath',
  'materialityFloorCad',
  'materialityNote',
  'searchTrail',
  'suppressed',
])

function fail(path: string, expectation: string): never {
  throw new Error(`Public pack ${path} ${expectation}.`)
}

function assertObject(value: unknown, path: string): asserts value is JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    fail(path, 'must be an object')
  }
}

function assertArray(value: unknown, path: string): asserts value is unknown[] {
  if (!Array.isArray(value)) fail(path, 'must be an array')
}

function assertString(value: unknown, path: string): asserts value is string {
  if (typeof value !== 'string' || value.length === 0) {
    fail(path, 'must be a non-empty string')
  }
}

function assertBoolean(value: unknown, path: string): asserts value is boolean {
  if (typeof value !== 'boolean') fail(path, 'must be a boolean')
}

function assertFiniteNumber(
  value: unknown,
  path: string,
): asserts value is number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    fail(path, 'must be a finite number')
  }
}

function assertNumberOrNull(
  value: unknown,
  path: string,
): asserts value is number | null {
  if (value !== null) assertFiniteNumber(value, path)
}

function assertOptionalString(value: unknown, path: string) {
  if (value !== undefined && typeof value !== 'string') {
    fail(path, 'must be a string when present')
  }
}

function assertOptionalNumber(value: unknown, path: string) {
  if (value !== undefined) assertFiniteNumber(value, path)
}

function assertStringArray(value: unknown, path: string): asserts value is string[] {
  assertArray(value, path)
  for (const [index, item] of value.entries()) {
    assertString(item, `${path}[${index}]`)
  }
}

function assertNoBannedKeys(value: unknown, path = '$') {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoBannedKeys(item, `${path}[${index}]`))
    return
  }
  if (typeof value !== 'object' || value === null) return
  for (const [key, child] of Object.entries(value)) {
    if (BANNED_PUBLIC_KEYS.has(key)) fail(`${path}.${key}`, 'is not public')
    assertNoBannedKeys(child, `${path}.${key}`)
  }
}

function assertOnlyKeys(value: JsonObject, path: string, allowed: string[]) {
  const allowedKeys = new Set(allowed)
  for (const key of Object.keys(value)) {
    if (!allowedKeys.has(key)) fail(`${path}.${key}`, 'is not allowed')
  }
}

function validateLineItem(value: unknown, path: string) {
  assertObject(value, path)
  assertOnlyKeys(value, path, [
    'id',
    'label',
    'amountCad',
    'classification',
    'evidenceStatus',
    'sourceFactId',
    'gapId',
    'note',
  ])
  assertString(value.id, `${path}.id`)
  assertString(value.label, `${path}.label`)
  assertFiniteNumber(value.amountCad, `${path}.amountCad`)
  assertString(value.classification, `${path}.classification`)
  assertString(value.evidenceStatus, `${path}.evidenceStatus`)
  assertOptionalString(value.sourceFactId, `${path}.sourceFactId`)
  assertOptionalString(value.gapId, `${path}.gapId`)
  assertOptionalString(value.note, `${path}.note`)
}

function validateProfileBucket(value: unknown, path: string) {
  assertObject(value, path)
  assertOnlyKeys(value, path, [
    'basis',
    'amountCad',
    'assessmentCad',
    'evidenceStatus',
    'sourceFactId',
    'gapId',
    'lineItems',
    'warnings',
    'note',
    'uiLabel',
    'description',
    'lineItemsSumCheckCad',
  ])
  assertString(value.basis, `${path}.basis`)
  assertNumberOrNull(value.amountCad, `${path}.amountCad`)
  assertString(value.evidenceStatus, `${path}.evidenceStatus`)
  assertOptionalNumber(value.assessmentCad, `${path}.assessmentCad`)
  assertOptionalString(value.sourceFactId, `${path}.sourceFactId`)
  assertOptionalString(value.gapId, `${path}.gapId`)
  assertOptionalString(value.note, `${path}.note`)
  assertOptionalString(value.uiLabel, `${path}.uiLabel`)
  assertOptionalString(value.description, `${path}.description`)
  assertOptionalNumber(value.lineItemsSumCheckCad, `${path}.lineItemsSumCheckCad`)
  if (value.warnings !== undefined) {
    assertStringArray(value.warnings, `${path}.warnings`)
  }
  if (value.lineItems !== undefined) {
    assertArray(value.lineItems, `${path}.lineItems`)
    value.lineItems.forEach((item, index) =>
      validateLineItem(item, `${path}.lineItems[${index}]`),
    )
  }
}

function validateCombinedAssessment(value: unknown, path: string) {
  assertObject(value, path)
  assertOnlyKeys(value, path, [
    'assessmentCad',
    'basis',
    'evidenceStatus',
    'components',
    'totalCad',
    'totalRate',
    'ayrUrbanVariant',
  ])
  assertFiniteNumber(value.assessmentCad, `${path}.assessmentCad`)
  assertString(value.basis, `${path}.basis`)
  assertString(value.evidenceStatus, `${path}.evidenceStatus`)
  assertArray(value.components, `${path}.components`)
  value.components.forEach((component, index) => {
    const componentPath = `${path}.components[${index}]`
    assertObject(component, componentPath)
    assertOnlyKeys(component, componentPath, [
      'label',
      'amountCad',
      'rate',
      'sourceFactId',
    ])
    assertString(component.label, `${componentPath}.label`)
    assertFiniteNumber(component.amountCad, `${componentPath}.amountCad`)
    assertFiniteNumber(component.rate, `${componentPath}.rate`)
    assertString(component.sourceFactId, `${componentPath}.sourceFactId`)
  })
  assertFiniteNumber(value.totalCad, `${path}.totalCad`)
  assertFiniteNumber(value.totalRate, `${path}.totalRate`)
  if (value.ayrUrbanVariant !== undefined) {
    const variantPath = `${path}.ayrUrbanVariant`
    assertObject(value.ayrUrbanVariant, variantPath)
    assertOnlyKeys(value.ayrUrbanVariant, variantPath, [
      'specialAreaRateCad',
      'totalCad',
      'totalRate',
      'note',
    ])
    assertFiniteNumber(
      value.ayrUrbanVariant.specialAreaRateCad,
      `${variantPath}.specialAreaRateCad`,
    )
    assertFiniteNumber(value.ayrUrbanVariant.totalCad, `${variantPath}.totalCad`)
    assertFiniteNumber(value.ayrUrbanVariant.totalRate, `${variantPath}.totalRate`)
    assertString(value.ayrUrbanVariant.note, `${variantPath}.note`)
  }
}

function validateReceipt(expectedId: string, value: unknown) {
  const path = '$.receipt'
  assertObject(value, path)
  assertOnlyKeys(value, path, [
    'schemaVersion',
    'artifact',
    'status',
    'purpose',
    'evidencePolicyRef',
    'jurisdiction',
    'profiles',
    'findings',
    'uiModelHints',
  ])
  if (value.schemaVersion !== RECEIPT_SCHEMA_VERSION) {
    fail(`${path}.schemaVersion`, `must equal ${RECEIPT_SCHEMA_VERSION}`)
  }
  if (value.artifact !== 'TaxpayerReceipt') {
    fail(`${path}.artifact`, 'must equal TaxpayerReceipt')
  }
  assertString(value.status, `${path}.status`)
  assertString(value.purpose, `${path}.purpose`)
  if (value.evidencePolicyRef !== PUBLIC_EVIDENCE_POLICY_REF) {
    fail(`${path}.evidencePolicyRef`, 'must be the public evidence label')
  }

  assertObject(value.jurisdiction, `${path}.jurisdiction`)
  assertOnlyKeys(value.jurisdiction, `${path}.jurisdiction`, [
    'slug',
    'displayName',
    'level',
    'aliases',
  ])
  if (value.jurisdiction.slug !== expectedId) {
    fail(`${path}.jurisdiction.slug`, `must equal ${expectedId}`)
  }
  assertString(value.jurisdiction.displayName, `${path}.jurisdiction.displayName`)
  assertOptionalString(value.jurisdiction.level, `${path}.jurisdiction.level`)
  if (value.jurisdiction.aliases !== undefined) {
    assertStringArray(
      value.jurisdiction.aliases,
      `${path}.jurisdiction.aliases`,
    )
  }

  assertObject(value.profiles, `${path}.profiles`)
  assertOnlyKeys(value.profiles, `${path}.profiles`, [
    'supportedAverageHousehold',
    'hypothetical5000',
  ])
  const supportedPath = `${path}.profiles.supportedAverageHousehold`
  assertObject(value.profiles.supportedAverageHousehold, supportedPath)
  const supported = value.profiles.supportedAverageHousehold
  assertOnlyKeys(supported, supportedPath, [
    'description',
    'township',
    'region',
    'regionIllustrationAt354500',
    'education',
    'combinedTotalCad',
    'combinedAtAssessment',
    'combinedTotalNote',
    'warnings',
  ])
  assertString(supported.description, `${supportedPath}.description`)
  validateProfileBucket(supported.township, `${supportedPath}.township`)
  validateProfileBucket(supported.region, `${supportedPath}.region`)
  validateProfileBucket(supported.education, `${supportedPath}.education`)
  if (supported.regionIllustrationAt354500 !== undefined) {
    validateProfileBucket(
      supported.regionIllustrationAt354500,
      `${supportedPath}.regionIllustrationAt354500`,
    )
  }
  assertNumberOrNull(supported.combinedTotalCad, `${supportedPath}.combinedTotalCad`)
  if (supported.combinedAtAssessment !== undefined) {
    validateCombinedAssessment(
      supported.combinedAtAssessment,
      `${supportedPath}.combinedAtAssessment`,
    )
  }
  assertString(supported.combinedTotalNote, `${supportedPath}.combinedTotalNote`)
  assertStringArray(supported.warnings, `${supportedPath}.warnings`)

  const hypotheticalPath = `${path}.profiles.hypothetical5000`
  assertObject(value.profiles.hypothetical5000, hypotheticalPath)
  const hypothetical = value.profiles.hypothetical5000
  assertOnlyKeys(hypothetical, hypotheticalPath, [
    'amountCad',
    'evidenceStatus',
    'gapId',
    'allocatable',
    'impliedAssessmentCad',
    'compositionShares',
    'message',
  ])
  assertFiniteNumber(hypothetical.amountCad, `${hypotheticalPath}.amountCad`)
  assertString(hypothetical.evidenceStatus, `${hypotheticalPath}.evidenceStatus`)
  assertOptionalString(hypothetical.gapId, `${hypotheticalPath}.gapId`)
  assertBoolean(hypothetical.allocatable, `${hypotheticalPath}.allocatable`)
  assertOptionalNumber(
    hypothetical.impliedAssessmentCad,
    `${hypotheticalPath}.impliedAssessmentCad`,
  )
  if (hypothetical.compositionShares !== undefined) {
    assertArray(
      hypothetical.compositionShares,
      `${hypotheticalPath}.compositionShares`,
    )
    hypothetical.compositionShares.forEach((share, index) => {
      const sharePath = `${hypotheticalPath}.compositionShares[${index}]`
      assertObject(share, sharePath)
      assertOnlyKeys(share, sharePath, ['label', 'share', 'sourceFactId'])
      assertString(share.label, `${sharePath}.label`)
      assertFiniteNumber(share.share, `${sharePath}.share`)
      assertString(share.sourceFactId, `${sharePath}.sourceFactId`)
    })
  }
  assertString(hypothetical.message, `${hypotheticalPath}.message`)

  assertArray(value.findings, `${path}.findings`)
  value.findings.forEach((finding, index) => {
    const findingPath = `${path}.findings[${index}]`
    assertObject(finding, findingPath)
    assertOnlyKeys(finding, findingPath, [
      'id',
      'kind',
      'category',
      'title',
      'opportunitySeverity',
      'citedFactIds',
      'evidenceSummary',
      'billImpactCad',
      'townshipResponse',
      'belowMateriality',
      'gapIds',
    ])
    for (const field of [
      'id',
      'kind',
      'category',
      'title',
      'opportunitySeverity',
      'evidenceSummary',
    ]) {
      assertString(finding[field], `${findingPath}.${field}`)
    }
    assertStringArray(finding.citedFactIds, `${findingPath}.citedFactIds`)
    assertNumberOrNull(finding.billImpactCad, `${findingPath}.billImpactCad`)
    if (
      finding.townshipResponse !== undefined &&
      finding.townshipResponse !== null
    ) {
      assertString(
        finding.townshipResponse,
        `${findingPath}.townshipResponse`,
      )
    }
    if (finding.belowMateriality !== undefined) {
      assertBoolean(
        finding.belowMateriality,
        `${findingPath}.belowMateriality`,
      )
    }
    assertStringArray(finding.gapIds, `${findingPath}.gapIds`)
  })

  const hintsPath = `${path}.uiModelHints`
  assertObject(value.uiModelHints, hintsPath)
  assertOnlyKeys(value.uiModelHints, hintsPath, [
    'defaultProfile',
    'showGapsAsFirstClassUi',
    'forbidFillerAllocation',
    'publishedFindingIds',
    'marqueeFindings',
    'municipalBucketLabel',
    'regionBucketLabel',
    'heroLabel',
  ])
  assertString(value.uiModelHints.defaultProfile, `${hintsPath}.defaultProfile`)
  assertBoolean(
    value.uiModelHints.showGapsAsFirstClassUi,
    `${hintsPath}.showGapsAsFirstClassUi`,
  )
  assertBoolean(
    value.uiModelHints.forbidFillerAllocation,
    `${hintsPath}.forbidFillerAllocation`,
  )
  assertStringArray(
    value.uiModelHints.publishedFindingIds,
    `${hintsPath}.publishedFindingIds`,
  )
  assertStringArray(
    value.uiModelHints.marqueeFindings,
    `${hintsPath}.marqueeFindings`,
  )
  assertOptionalString(
    value.uiModelHints.municipalBucketLabel,
    `${hintsPath}.municipalBucketLabel`,
  )
  assertOptionalString(
    value.uiModelHints.regionBucketLabel,
    `${hintsPath}.regionBucketLabel`,
  )
  assertOptionalString(value.uiModelHints.heroLabel, `${hintsPath}.heroLabel`)
}

function validateEvidenceAndAudit(
  evidenceValue: unknown,
  auditValue: unknown,
) {
  const evidencePath = '$.evidence'
  assertObject(evidenceValue, evidencePath)
  assertOnlyKeys(evidenceValue, evidencePath, [
    'evidencePolicy',
    'sources',
    'facts',
    'derived',
    'gaps',
  ])
  assertObject(evidenceValue.evidencePolicy, `${evidencePath}.evidencePolicy`)
  assertOnlyKeys(
    evidenceValue.evidencePolicy,
    `${evidencePath}.evidencePolicy`,
    ['rules'],
  )
  assertStringArray(
    evidenceValue.evidencePolicy.rules,
    `${evidencePath}.evidencePolicy.rules`,
  )

  assertArray(evidenceValue.sources, `${evidencePath}.sources`)
  const sourceIds = new Set<string>()
  evidenceValue.sources.forEach((source, index) => {
    const sourcePath = `${evidencePath}.sources[${index}]`
    assertObject(source, sourcePath)
    assertOnlyKeys(source, sourcePath, [
      'id',
      'title',
      'url',
      'asOf',
      'authority',
    ])
    assertString(source.id, `${sourcePath}.id`)
    if (sourceIds.has(source.id)) fail(`${sourcePath}.id`, 'must be unique')
    sourceIds.add(source.id)
    assertString(source.title, `${sourcePath}.title`)
    assertString(source.url, `${sourcePath}.url`)
    assertOptionalString(source.asOf, `${sourcePath}.asOf`)
    assertOptionalString(source.authority, `${sourcePath}.authority`)
  })

  assertArray(evidenceValue.facts, `${evidencePath}.facts`)
  const factIds = new Set<string>()
  evidenceValue.facts.forEach((fact, index) => {
    const factPath = `${evidencePath}.facts[${index}]`
    assertObject(fact, factPath)
    assertOnlyKeys(fact, factPath, [
      'id',
      'sourceId',
      'page',
      'label',
      'amountCad',
      'value',
      'excerpt',
      'status',
      'kind',
      'url',
    ])
    assertString(fact.id, `${factPath}.id`)
    if (factIds.has(fact.id)) fail(`${factPath}.id`, 'must be unique')
    factIds.add(fact.id)
    assertString(fact.sourceId, `${factPath}.sourceId`)
    if (!sourceIds.has(fact.sourceId)) {
      fail(`${factPath}.sourceId`, 'must reference a public source')
    }
    assertString(fact.label, `${factPath}.label`)
    assertOptionalNumber(fact.page, `${factPath}.page`)
    assertOptionalNumber(fact.amountCad, `${factPath}.amountCad`)
    assertOptionalNumber(fact.value, `${factPath}.value`)
    assertOptionalString(fact.excerpt, `${factPath}.excerpt`)
    assertOptionalString(fact.status, `${factPath}.status`)
    assertOptionalString(fact.kind, `${factPath}.kind`)
    assertOptionalString(fact.url, `${factPath}.url`)
  })

  assertArray(evidenceValue.derived, `${evidencePath}.derived`)
  const derivedIds = new Set<string>()
  evidenceValue.derived.forEach((derived, index) => {
    const derivedPath = `${evidencePath}.derived[${index}]`
    assertObject(derived, derivedPath)
    assertOnlyKeys(derived, derivedPath, [
      'id',
      'label',
      'amountCad',
      'formula',
      'inputs',
      'kind',
    ])
    assertString(derived.id, `${derivedPath}.id`)
    if (derivedIds.has(derived.id)) fail(`${derivedPath}.id`, 'must be unique')
    derivedIds.add(derived.id)
    assertString(derived.label, `${derivedPath}.label`)
    assertOptionalNumber(derived.amountCad, `${derivedPath}.amountCad`)
    assertOptionalString(derived.formula, `${derivedPath}.formula`)
    assertOptionalString(derived.kind, `${derivedPath}.kind`)
    if (derived.inputs !== undefined) {
      assertStringArray(derived.inputs, `${derivedPath}.inputs`)
    }
  })
  const calculationIds = new Set([...factIds, ...derivedIds])
  evidenceValue.derived.forEach((derived, index) => {
    assertObject(derived, `${evidencePath}.derived[${index}]`)
    if (Array.isArray(derived.inputs)) {
      for (const input of derived.inputs) {
        if (typeof input === 'string' && !calculationIds.has(input)) {
          fail(
            `${evidencePath}.derived[${index}].inputs`,
            `references missing input ${input}`,
          )
        }
      }
    }
  })

  assertArray(evidenceValue.gaps, `${evidencePath}.gaps`)
  const gapIds = new Set<string>()
  evidenceValue.gaps.forEach((gap, index) => {
    const gapPath = `${evidencePath}.gaps[${index}]`
    assertObject(gap, gapPath)
    assertOnlyKeys(gap, gapPath, [
      'id',
      'kind',
      'title',
      'detail',
      'blocks',
      'neededEvidence',
      'disposition',
    ])
    assertString(gap.id, `${gapPath}.id`)
    if (gapIds.has(gap.id)) fail(`${gapPath}.id`, 'must be unique')
    gapIds.add(gap.id)
    assertString(gap.kind, `${gapPath}.kind`)
    assertString(gap.title, `${gapPath}.title`)
    assertString(gap.detail, `${gapPath}.detail`)
    assertStringArray(gap.blocks, `${gapPath}.blocks`)
    assertStringArray(gap.neededEvidence, `${gapPath}.neededEvidence`)
    if (
      gap.disposition !== 'missing_evidence' &&
      gap.disposition !== 'not_applicable' &&
      gap.disposition !== 'resolved_context'
    ) {
      fail(
        `${gapPath}.disposition`,
        'must be missing_evidence, not_applicable, or resolved_context',
      )
    }
  })

  const auditPath = '$.audit'
  assertObject(auditValue, auditPath)
  assertOnlyKeys(auditValue, auditPath, ['counts', 'results'])
  const counts = auditValue.counts
  assertObject(counts, `${auditPath}.counts`)
  assertArray(auditValue.results, `${auditPath}.results`)
  const auditIds = new Set<string>()
  const calculatedCounts = new Map<string, number>()
  auditValue.results.forEach((result, index) => {
    const resultPath = `${auditPath}.results[${index}]`
    assertObject(result, resultPath)
    assertOnlyKeys(result, resultPath, ['id', 'tier'])
    assertString(result.id, `${resultPath}.id`)
    assertString(result.tier, `${resultPath}.tier`)
    if (auditIds.has(result.id)) fail(`${resultPath}.id`, 'must be unique')
    auditIds.add(result.id)
    calculatedCounts.set(
      result.tier,
      (calculatedCounts.get(result.tier) ?? 0) + 1,
    )
  })
  if (
    auditIds.size !== factIds.size ||
    [...factIds].some((factId) => !auditIds.has(factId))
  ) {
    fail(`${auditPath}.results`, 'must contain exactly one row per public fact')
  }
  for (const [tier, count] of Object.entries(counts)) {
    if (typeof count !== 'number' || !Number.isInteger(count) || count < 0) {
      fail(`${auditPath}.counts.${tier}`, 'must be a non-negative integer')
    }
    if (calculatedCounts.get(tier) !== count) {
      fail(`${auditPath}.counts.${tier}`, 'must match audit results')
    }
  }
  if (
    Object.keys(counts).length !== calculatedCounts.size ||
    [...calculatedCounts].some(([tier]) => !(tier in counts))
  ) {
    fail(`${auditPath}.counts`, 'must contain exactly the result tier counts')
  }

  return { calculationIds, gapIds }
}

function validateReceiptReferences(
  value: unknown,
  calculationIds: Set<string>,
  gapIds: Set<string>,
  path = '$.receipt',
) {
  if (Array.isArray(value)) {
    value.forEach((item, index) =>
      validateReceiptReferences(
        item,
        calculationIds,
        gapIds,
        `${path}[${index}]`,
      ),
    )
    return
  }
  if (typeof value !== 'object' || value === null) return
  for (const [key, child] of Object.entries(value)) {
    if (
      key === 'sourceFactId' &&
      typeof child === 'string' &&
      !calculationIds.has(child)
    ) {
      fail(`${path}.${key}`, `references missing evidence ${child}`)
    }
    if (key === 'gapId' && typeof child === 'string' && !gapIds.has(child)) {
      fail(`${path}.${key}`, `references missing gap ${child}`)
    }
    if (key === 'citedFactIds' && Array.isArray(child)) {
      for (const id of child) {
        if (typeof id === 'string' && !calculationIds.has(id)) {
          fail(`${path}.${key}`, `references missing evidence ${id}`)
        }
      }
    }
    if (key === 'gapIds' && Array.isArray(child)) {
      for (const id of child) {
        if (typeof id === 'string' && !gapIds.has(id)) {
          fail(`${path}.${key}`, `references missing gap ${id}`)
        }
      }
    }
    validateReceiptReferences(
      child,
      calculationIds,
      gapIds,
      `${path}.${key}`,
    )
  }
}

export function validatePublicPack(
  expectedId: string,
  value: unknown,
): ValidatedPublicPack {
  assertNoBannedKeys(value)
  assertObject(value, '$')
  assertOnlyKeys(value, '$', [
    'schemaVersion',
    'id',
    'receipt',
    'evidence',
    'audit',
  ])
  if (value.schemaVersion !== PUBLIC_PACK_SCHEMA_VERSION) {
    fail('$.schemaVersion', `must equal ${PUBLIC_PACK_SCHEMA_VERSION}`)
  }
  if (value.id !== expectedId) fail('$.id', `must equal ${expectedId}`)

  validateReceipt(expectedId, value.receipt)
  const { calculationIds, gapIds } = validateEvidenceAndAudit(
    value.evidence,
    value.audit,
  )
  validateReceiptReferences(value.receipt, calculationIds, gapIds)

  return {
    id: expectedId,
    receipt: value.receipt as TaxpayerReceipt,
    evidence: value.evidence as ValidatedPublicPack['evidence'],
    audit: value.audit as CitationAudit,
  }
}
