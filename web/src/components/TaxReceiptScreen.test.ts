import { describe, expect, it } from 'vitest'
import { receiptYearContext } from './TaxReceiptScreen'

describe('receipt year context', () => {
  it('keeps loading distinct from verified missing history', () => {
    expect(receiptYearContext(2026, undefined, 'loading')).toBe(
      'current tax evidence 2026 · loading earlier FIR context.',
    )
  })

  it('reports a registry failure without claiming that history is absent', () => {
    expect(receiptYearContext(2026, undefined, 'unavailable')).toBe(
      'current tax evidence 2026 · earlier FIR context is temporarily unavailable.',
    )
  })

  it('lists verified FIR years separately from the receipt calculation', () => {
    expect(receiptYearContext(2026, [2025, 2024, 2023], 'ready')).toBe(
      'current tax evidence 2026 · FIR history 2025, 2024, 2023. FIR years stay separate from this receipt calculation.',
    )
  })

  it('only makes a no-history claim after a successful registry lookup', () => {
    expect(receiptYearContext(2026, [], 'ready')).toBe(
      'current tax evidence 2026 · no 2023–2025 FIR history available. FIR years stay separate from this receipt calculation.',
    )
  })
})
