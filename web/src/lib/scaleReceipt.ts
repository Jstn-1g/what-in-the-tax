import type { ForensicFinding, TaxpayerReceipt } from '../types'

function scale(amount: number, factor: number): number {
  return Math.round(amount * factor * 100) / 100
}

export function scaleReceipt(data: TaxpayerReceipt, billCad: number) {
  const base = data.receiptTotals.billCad || 5000
  const factor = billCad / base

  const receiptLineItems = data.receiptLineItems.map((line) => ({
    ...line,
    amountCad: scale(line.amountCad, factor),
  }))

  const jurisdictionBreakdown = data.jurisdictionBreakdown.map((slice) => ({
    ...slice,
    amountCad: scale(slice.amountCad, factor),
    children: slice.children?.map((child) => ({
      ...child,
      amountCad: scale(child.amountCad, factor),
    })),
  }))

  const scaleFlags = (flags: ForensicFinding[]) =>
    flags.map((flag) => ({
      ...flag,
      estimatedBillImpactCad: scale(flag.estimatedBillImpactCad, factor),
    }))

  const forensicFindings = {
    administrativeBloat: scaleFlags(data.forensicFindings.administrativeBloat),
    questionableCapitalProjects: scaleFlags(data.forensicFindings.questionableCapitalProjects),
    unusualLineItems: scaleFlags(data.forensicFindings.unusualLineItems),
  }

  const totals = data.receiptTotals
  const necessaryExcludingPassThroughCad = scale(totals.necessaryExcludingPassThroughCad, factor)
  const passThroughCad = scale(totals.passThroughCad, factor)
  const flaggedCad = scale(totals.flaggedCad, factor)
  const necessaryCad = scale(totals.necessaryCad, factor)

  const receiptTotals = {
    ...totals,
    billCad,
    necessaryCad,
    flaggedCad,
    passThroughCad,
    necessaryExcludingPassThroughCad,
    byClassification: Object.fromEntries(
      Object.entries(totals.byClassification).map(([key, value]) => [key, scale(value, factor)]),
    ),
    uiSummary: {
      ...totals.uiSummary,
      headline: `Of your ${billCad.toLocaleString('en-CA', {
        style: 'currency',
        currency: 'CAD',
        maximumFractionDigits: 0,
      })} property tax bill, about ${flaggedCad.toLocaleString('en-CA', {
        style: 'currency',
        currency: 'CAD',
      })} (${Math.round(totals.flaggedShareOfBill * 100)}%) maps to flagged admin overhead, questionable capital ambition, or unusual discretionary items — the rest funds core township, regional, police, and education services.`,
    },
  }

  const uiModelHints = {
    ...data.uiModelHints,
    heroMetric: {
      ...data.uiModelHints.heroMetric,
      label: `Your ${billCad.toLocaleString('en-CA', {
        style: 'currency',
        currency: 'CAD',
        maximumFractionDigits: 0,
      })} breakdown`,
      primaryValueCad: billCad,
      segments: data.uiModelHints.heroMetric.segments.map((segment) => ({
        ...segment,
        valueCad: scale(segment.valueCad, factor),
      })),
    },
  }

  return {
    ...data,
    receiptLineItems,
    jurisdictionBreakdown,
    forensicFindings,
    receiptTotals,
    uiModelHints,
  } satisfies TaxpayerReceipt
}
