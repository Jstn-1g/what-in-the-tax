export type LineClassification =
  | 'necessary'
  | 'pass_through'
  | 'flagged_admin'
  | 'flagged_capital'
  | 'flagged_unusual'

export type UiFilter = 'all' | 'necessary' | 'flagged' | 'pass_through'

export type ReceiptLineItem = {
  id: string
  tier: string
  category: string
  label: string
  amountCad: number
  classification: LineClassification
  necessary: boolean
  flagged: boolean
  flagIds: string[]
}

export type ForensicFinding = {
  id: string
  tier: string
  title: string
  evidence: string
  opportunitySeverity: string
  estimatedBillImpactCad: number
  uiHint?: string
}

export type TaxpayerReceipt = {
  purpose: string
  generatedAt: string
  jurisdiction: {
    lowerTier: string
    upperTier: string
    province: string
    populationCensus2021: number
    medianAssessmentUsedInTownshipDocs: number
  }
  hypotheticalBill: {
    amountCad: number
    currency: string
  }
  methodology: {
    jurisdictionSplit: {
      basis: string
      townshipRate: number
      regionRate: number
      educationRate: number
      sharesOfTotalBill: {
        township: number
        region: number
        education: number
      }
    }
  }
  jurisdictionBreakdown: Array<{
    id: string
    label: string
    amountCad: number
    shareOfBill: number
    children?: Array<{
      id: string
      label: string
      amountCad: number
      shareOfBill: number
    }>
  }>
  receiptLineItems: ReceiptLineItem[]
  receiptTotals: {
    billCad: number
    necessaryCad: number
    flaggedCad: number
    passThroughCad: number
    necessaryExcludingPassThroughCad: number
    flaggedShareOfBill: number
    necessaryShareOfBill: number
    byClassification: Record<string, number>
    uiSummary: {
      headline: string
      necessaryLabel: string
      flaggedLabel: string
      passThroughLabel: string
    }
  }
  forensicFindings: {
    administrativeBloat: ForensicFinding[]
    questionableCapitalProjects: ForensicFinding[]
    unusualLineItems: ForensicFinding[]
  }
  uiModelHints: {
    heroMetric: {
      label: string
      primaryValueCad: number
      segments: Array<{
        key: string
        label: string
        valueCad: number
        colorToken: string
      }>
    }
    marqueeFlags: string[]
  }
  budgetSnapshots: {
    northDumfries2026Draft: {
      perCapita: {
        populationBasis: number
        corporateServicesPerCapita: number
        netZeroArenaProjectPerCapita: number
      }
    }
  }
}
