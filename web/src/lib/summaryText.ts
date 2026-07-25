import { money, pct } from './format'
import type { TaxpayerReceipt } from '../types'

export function buildReceiptSummary(view: TaxpayerReceipt): string {
  const totals = view.receiptTotals
  const topFlagged = [...view.receiptLineItems]
    .filter((line) => line.flagged)
    .sort((a, b) => b.amountCad - a.amountCad)
    .slice(0, 5)

  const lines = [
    'Taxpayer Receipt — North Dumfries / Region of Waterloo',
    `Modeled annual bill: ${money(totals.billCad)}`,
    '',
    `Necessary / core: ${money(totals.necessaryExcludingPassThroughCad)} (${pct((totals.necessaryExcludingPassThroughCad / totals.billCad) * 100)})`,
    `Education pass-through: ${money(totals.passThroughCad)} (${pct((totals.passThroughCad / totals.billCad) * 100)})`,
    `Flagged: ${money(totals.flaggedCad)} (${pct(totals.flaggedShareOfBill * 100)})`,
    '',
    'Where the bill goes:',
    ...view.jurisdictionBreakdown.map(
      (slice) => `- ${slice.label}: ${money(slice.amountCad)} (${pct(slice.shareOfBill * 100)})`,
    ),
    '',
    'Top flagged lines:',
    ...(topFlagged.length
      ? topFlagged.map((line) => `- ${line.label}: ${money(line.amountCad)}`)
      : ['- None']),
    '',
    'Prototype model from published 2026 municipal/regional budget materials.',
  ]

  return lines.join('\n')
}
