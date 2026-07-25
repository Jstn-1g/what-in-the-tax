import TaxReceiptScreen from './components/TaxReceiptScreen'
import ledger from './data/evidence-ledger.json'
import receipt from './data/taxpayer-receipt.json'
import type { EvidenceLedger, TaxpayerReceipt } from './types'

export default function App() {
  return (
    <TaxReceiptScreen
      data={receipt as unknown as TaxpayerReceipt}
      gaps={(ledger as unknown as EvidenceLedger).gaps}
      evidenceRules={(ledger as unknown as EvidenceLedger).evidencePolicy.rules}
    />
  )
}
