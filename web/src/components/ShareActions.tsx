import { useState } from 'react'
import { buildReceiptCsv, downloadTextFile } from '../lib/csv'
import type { TaxpayerReceipt } from '../types'

type Props = {
  summaryText: string
  view: TaxpayerReceipt
}

export default function ShareActions({ summaryText, view }: Props) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'shared' | 'error' | 'csv'>('idle')

  const mark = (next: typeof status) => {
    setStatus(next)
    window.setTimeout(() => setStatus('idle'), 1800)
  }

  return (
    <div className="share-actions">
      <div className="share-buttons">
        <button
          type="button"
          className="cta apply-bill"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(summaryText)
              mark('copied')
            } catch {
              mark('error')
            }
          }}
        >
          Copy summary
        </button>

        {'share' in navigator ? (
          <button
            type="button"
            className="cta cta-secondary"
            onClick={async () => {
              try {
                await navigator.share({
                  title: 'Taxpayer Receipt',
                  text: summaryText,
                })
                mark('shared')
              } catch {
                // user cancel is fine; leave idle
              }
            }}
          >
            Share
          </button>
        ) : null}

        <button
          type="button"
          className="cta cta-secondary"
          onClick={() => {
            downloadTextFile(
              `taxpayer-receipt-${view.receiptTotals.billCad}.csv`,
              buildReceiptCsv(view),
              'text/csv;charset=utf-8',
            )
            mark('csv')
          }}
        >
          Export CSV
        </button>

        <button
          type="button"
          className="cta cta-secondary"
          onClick={() => window.print()}
        >
          Print receipt
        </button>
      </div>

      <p className="copy-status" aria-live="polite">
        {status === 'copied' ? 'Copied to clipboard.' : null}
        {status === 'shared' ? 'Shared.' : null}
        {status === 'csv' ? 'CSV downloaded.' : null}
        {status === 'error' ? 'Could not copy.' : null}
      </p>
    </div>
  )
}
