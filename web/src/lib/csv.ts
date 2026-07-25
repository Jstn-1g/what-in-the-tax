import type { TaxpayerReceipt } from '../types'

function escapeCell(value: string | number | boolean): string {
  const text = String(value)
  if (/[",\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`
  return text
}

export function buildReceiptCsv(view: TaxpayerReceipt): string {
  const header = [
    'id',
    'tier',
    'category',
    'label',
    'amountCad',
    'classification',
    'necessary',
    'flagged',
    'flagIds',
  ]

  const rows = view.receiptLineItems.map((line) => [
    line.id,
    line.tier,
    line.category,
    line.label,
    line.amountCad,
    line.classification,
    line.necessary,
    line.flagged,
    line.flagIds.join('|'),
  ])

  return [header, ...rows].map((row) => row.map(escapeCell).join(',')).join('\n')
}

export function downloadTextFile(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
