import TaxReceiptScreen from './components/TaxReceiptScreen'
import ledger from './data/evidence-ledger.json'
import receipt from './data/taxpayer-receipt.json'
import type { EvidenceLedger, TaxpayerReceipt } from './types'

const evidence = ledger as unknown as EvidenceLedger

export default function App() {
  return (
    <TaxReceiptScreen
      data={receipt as unknown as TaxpayerReceipt}
      gaps={evidence.gaps}
      evidenceRules={evidence.evidencePolicy.rules}
      sources={evidence.sources}
      facts={evidence.facts}
      derived={evidence.derived}
    />
  )
}
