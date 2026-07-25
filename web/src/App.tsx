import TaxReceiptScreen from './components/TaxReceiptScreen'
import receipt from './data/taxpayer-receipt.json'
import type { TaxpayerReceipt } from './types'

export default function App() {
  return <TaxReceiptScreen data={receipt as unknown as TaxpayerReceipt} />
}
