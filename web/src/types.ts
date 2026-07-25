export type EvidenceStatus = 'FACT' | 'DERIVED' | 'GAP' | 'JUDGMENT'

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
      combinedTotalNote: string
      warnings: string[]
    }
    hypothetical5000: {
      amountCad: number
      evidenceStatus: string
      gapId: string
      allocatable: boolean
      message: string
    }
  }
  findings: Finding[]
  uiModelHints: {
    defaultProfile: string
    showGapsAsFirstClassUi: boolean
    forbidFillerAllocation: boolean
    marqueeFindings: string[]
  }
}

export type EvidenceLedger = {
  gaps: Gap[]
  evidencePolicy: { rules: string[] }
}
