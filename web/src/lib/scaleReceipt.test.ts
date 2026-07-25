import { describe, expect, it } from 'vitest'
import type { TaxpayerReceipt } from '../types'
import { scaleReceipt } from './scaleReceipt'

const sample = {
  purpose: 'test',
  generatedAt: '2026-07-25',
  jurisdiction: {
    lowerTier: 'North Dumfries',
    upperTier: 'Region of Waterloo',
    province: 'Ontario',
    populationCensus2021: 10619,
    medianAssessmentUsedInTownshipDocs: 455000,
  },
  hypotheticalBill: { amountCad: 5000, currency: 'CAD' },
  methodology: {
    jurisdictionSplit: {
      basis: 'test',
      townshipRate: 0.00256586,
      regionRate: 0.00521492,
      educationRate: 0.00153,
      sharesOfTotalBill: { township: 0.2756, region: 0.5601, education: 0.1643 },
    },
  },
  jurisdictionBreakdown: [
    { id: 'township', label: 'Township', amountCad: 1377.8, shareOfBill: 0.2756 },
    { id: 'region', label: 'Region', amountCad: 2800.5, shareOfBill: 0.5601 },
    { id: 'education', label: 'Education', amountCad: 821.7, shareOfBill: 0.1643 },
  ],
  receiptLineItems: [
    {
      id: 'A',
      tier: 'region',
      category: 'Public Safety',
      label: 'Police',
      amountCad: 860.39,
      classification: 'necessary',
      necessary: true,
      flagged: false,
      flagIds: [],
    },
    {
      id: 'B',
      tier: 'township',
      category: 'Administration',
      label: 'Admin bloat',
      amountCad: 100,
      classification: 'flagged_admin',
      necessary: false,
      flagged: true,
      flagIds: ['ADMIN-01'],
    },
  ],
  receiptTotals: {
    billCad: 5000,
    necessaryCad: 4900,
    flaggedCad: 100,
    passThroughCad: 821.7,
    necessaryExcludingPassThroughCad: 4078.3,
    flaggedShareOfBill: 0.02,
    necessaryShareOfBill: 0.98,
    byClassification: { necessary: 4078.3, pass_through: 821.7, flagged_admin: 100 },
    uiSummary: {
      headline: 'test',
      necessaryLabel: 'Necessary',
      flaggedLabel: 'Flagged',
      passThroughLabel: 'Education',
    },
  },
  forensicFindings: {
    administrativeBloat: [
      {
        id: 'ADMIN-01',
        tier: 'township',
        title: 'Admin',
        evidence: 'test',
        opportunitySeverity: 'high',
        estimatedBillImpactCad: 50,
      },
    ],
    questionableCapitalProjects: [],
    unusualLineItems: [],
  },
  uiModelHints: {
    heroMetric: {
      label: 'Your $5,000 breakdown',
      primaryValueCad: 5000,
      segments: [
        { key: 'necessary', label: 'Necessary', valueCad: 4078.3, colorToken: 'necessary' },
        { key: 'pass_through', label: 'Education', valueCad: 821.7, colorToken: 'neutral' },
        { key: 'flagged', label: 'Flagged', valueCad: 100, colorToken: 'flagged' },
      ],
    },
    marqueeFlags: ['ADMIN-01'],
  },
  budgetSnapshots: {
    northDumfries2026Draft: {
      perCapita: {
        populationBasis: 10619,
        corporateServicesPerCapita: 197,
        netZeroArenaProjectPerCapita: 1525,
      },
    },
  },
} as TaxpayerReceipt

describe('scaleReceipt', () => {
  it('scales line items and flags by bill factor', () => {
    const scaled = scaleReceipt(sample, 10000)
    expect(scaled.receiptTotals.billCad).toBe(10000)
    expect(scaled.receiptLineItems[0].amountCad).toBe(1720.78)
    expect(scaled.receiptLineItems[1].amountCad).toBe(200)
    expect(scaled.forensicFindings.administrativeBloat[0].estimatedBillImpactCad).toBe(100)
    expect(scaled.receiptTotals.flaggedCad).toBe(200)
  })

  it('keeps share percentages stable when amounts scale', () => {
    const scaled = scaleReceipt(sample, 2500)
    expect(scaled.jurisdictionBreakdown[0].shareOfBill).toBe(0.2756)
    expect(scaled.receiptTotals.flaggedShareOfBill).toBe(0.02)
  })
})
