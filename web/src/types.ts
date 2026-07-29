export type EvidenceStatus = 'FACT' | 'DERIVED' | 'GAP' | 'JUDGMENT'

export type Source = {
  id: string
  title: string
  url: string
  localPath?: string | null
  asOf?: string
  authority?: string
  note?: string
}

export type Fact = {
  id: string
  sourceId: string
  page?: number
  label: string
  amountCad?: number
  value?: number
  excerpt?: string
  status?: string
  note?: string
  kind?: string
  url?: string
}

export type Derived = {
  id: string
  label: string
  amountCad?: number
  formula?: string
  inputs?: string[]
  note?: string
  kind?: string
}

export type ReceiptLineItem = {
  id: string
  label: string
  amountCad: number
  classification: string
  evidenceStatus: EvidenceStatus | string
  sourceFactId?: string
  gapId?: string
  note?: string
}

export type ProfileBucket = {
  basis: string
  amountCad: number | null
  assessmentCad?: number
  evidenceStatus: string
  sourceFactId?: string
  gapId?: string
  lineItems?: ReceiptLineItem[]
  warnings?: string[]
  note?: string
  uiLabel?: string
}

/**
 * A body that levies part of the bill.
 *
 * The schema used to be three fixed slots - township, region, education - which
 * is the shape of one Ontario two-tier municipality and not the shape of the
 * province. 167 of Ontario's 405 taxing municipalities are single-tier and have
 * no upper tier at all; today they carry a placeholder bucket labelled
 * "Upper-tier (n/a)" because the field is required. Alberta apportions a
 * provincial education requisition rather than printing a rate. A municipality
 * with a special area rate has four bodies, not three.
 *
 * So the bill is a list. Absence is representable by a shorter list, which is
 * the whole point: nothing has to be invented to fill a slot.
 */
export type TaxingBodyRole = 'local' | 'upper-tier' | 'education' | 'special-area'

export type TaxingBody = {
  id: string
  role: TaxingBodyRole
  /** What the reader sees: "Township of North Dumfries", "Education". */
  label: string
  /** Position on the bill. Stable, so the bar and the list cannot disagree. */
  order: number
  amountCad: number
  basis: string
  evidenceStatus: string
  assessmentCad?: number
  sourceFactId?: string
  gapId?: string
  lineItems?: ReceiptLineItem[]
  warnings?: string[]
  note?: string
  uiLabel?: string
}

/**
 * A role that does not apply here, and why.
 *
 * A single-tier municipality has no upper tier. That is a fact about the
 * jurisdiction, not missing evidence, and it reads very differently from a gap.
 * Recorded rather than rendered as an empty row.
 */
export type InapplicableBody = {
  role: TaxingBodyRole
  reason: string
}

export type Finding = {
  id: string
  kind: string
  category: string
  title: string
  opportunitySeverity: string
  citedFactIds: string[]
  evidenceSummary: string
  billImpactCad: number | null
  townshipResponse?: string | null
  belowMateriality?: boolean
  gapIds: string[]
}

export type Gap = {
  id: string
  kind: string
  title: string
  detail: string
  blocks: string[]
  neededEvidence: string[]
  /** Required in generated public packs; optional in legacy internal ledgers. */
  disposition?: 'missing_evidence' | 'not_applicable' | 'resolved_context'
}

export type TaxpayerReceipt = {
  schemaVersion: string
  artifact: string
  fiscalYear: number
  currency: 'CAD'
  status: string
  publisher?: {
    name: string
    role: string
  }
  license?: {
    spdx: string
    scope: string
    sourceDocuments: string
  }
  correctionsRoute?: {
    type: string
    url: string | null
    status: string
  }
  publicationApproval?: {
    status: string
    approvedBy: string | null
    approvedAt: string | null
  }
  coverage?: {
    status: string
    tier: number
    fiscalYear: number
    currency: 'CAD'
    geography: string
    assessmentClass: string
    included: string[]
    excluded: string[]
    sourceCoverage?: {
      receiptDrivingSources: number
      reviewedSourceAndExtractPairs: number
      citedFacts: number
      loadBearingFacts: number
      citationAuditExpected?: {
        verbatim: number
        normalized: number
        hardFailures: number
        bindingIssues: number
      }
    }
    findingsCount: number
    openGapsCount: number
  }
  purpose: string
  evidencePolicyRef: string
  jurisdiction?: {
    slug: string
    displayName: string
    level?: string
    aliases?: string[]
  }
  profiles: {
    supportedAverageHousehold: {
      description: string
      /**
       * The bill, as a list of bodies. Optional only because artifacts built
       * before this field exist and must keep rendering; new builders emit it,
       * and readers should go through taxingBodiesFor() rather than the three
       * legacy buckets below.
       */
      taxingBodies?: TaxingBody[]
      inapplicableBodies?: InapplicableBody[]
      township: ProfileBucket
      region: ProfileBucket
      /** Informational Region schedule at a different assessment; not part of the bill stack. */
      regionIllustrationAt354500?: ProfileBucket & {
        description?: string
        lineItemsSumCheckCad?: number
      }
      education: ProfileBucket
      combinedTotalCad: number | null
      combinedAtAssessment?: {
        assessmentCad: number
        basis: string
        evidenceStatus: string
        components: { label: string; amountCad: number; rate: number; sourceFactId: string }[]
        totalCad: number
        totalRate: number
        ayrUrbanVariant?: {
          specialAreaRateCad: number
          totalCad: number
          totalRate: number
          note: string
        }
      }
      combinedTotalNote: string
      warnings: string[]
    }
    hypothetical5000: {
      amountCad: number
      evidenceStatus: string
      gapId?: string
      allocatable: boolean
      impliedAssessmentCad?: number
      compositionShares?: { label: string; share: number; sourceFactId: string }[]
      message: string
    }
  }
  findings: Finding[]
  uiModelHints: {
    defaultProfile: string
    showGapsAsFirstClassUi: boolean
    forbidFillerAllocation: boolean
    materialityFloorCad?: number
    materialityNote?: string
    flaggedDefinition?: string
    publishedFindingIds?: string[]
    marqueeFindings: string[]
    municipalBucketLabel?: string
    regionBucketLabel?: string
    heroLabel?: string
  }
}

export type EvidenceLedger = {
  gaps: Gap[]
  evidencePolicy: { rules: string[] }
  sources: Source[]
  facts: Fact[]
  derived: Derived[]
}
