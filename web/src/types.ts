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
}

export type TaxpayerReceipt = {
  schemaVersion: string
  artifact: string
  status: string
  purpose: string
  evidencePolicyRef: string
  profiles: {
    supportedAverageHousehold: {
      description: string
      township: ProfileBucket
      region: ProfileBucket
      education: ProfileBucket
      combinedTotalCad: number | null
      combinedAtAssessment?: {
        assessmentCad: number
        basis: string
        evidenceStatus: string
        components: { label: string; amountCad: number; rate: number; sourceFactId: string }[]
        totalCad: number
        totalRate: number
        ayrUrbanVariant: { specialAreaRateCad: number; totalCad: number; totalRate: number; note: string }
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
  }
}

export type EvidenceLedger = {
  gaps: Gap[]
  evidencePolicy: { rules: string[] }
  sources: Source[]
  facts: Fact[]
  derived: Derived[]
}
