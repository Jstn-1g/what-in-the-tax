import { money } from '../lib/format'

type Props = {
  baseBillCad: number
  currentBillCad: number
  baseFlaggedCad: number
  currentFlaggedCad: number
  onReset: () => void
}

export default function BaselineCompare({
  baseBillCad,
  currentBillCad,
  baseFlaggedCad,
  currentFlaggedCad,
  onReset,
}: Props) {
  if (currentBillCad === baseBillCad) return null

  const flaggedDelta = currentFlaggedCad - baseFlaggedCad
  const billDelta = currentBillCad - baseBillCad
  const sign = (value: number) => (value > 0 ? '+' : '')

  return (
    <section className="section baseline-compare" aria-labelledby="baseline-title">
      <div className="section-head">
        <h2 id="baseline-title">
          Compared with {money(baseBillCad)} model
        </h2>
        <p>Your current bill changes the absolute dollars; shares stay the same.</p>
      </div>
      <ul className="baseline-grid">
        <li>
          <span>Bill delta</span>
          <strong>
            {sign(billDelta)}
            {money(billDelta)}
          </strong>
        </li>
        <li>
          <span>Flagged delta</span>
          <strong className={flaggedDelta >= 0 ? 'delta-up' : 'delta-down'}>
            {sign(flaggedDelta)}
            {money(flaggedDelta)}
          </strong>
        </li>
        <li>
          <span>Flagged now</span>
          <strong>{money(currentFlaggedCad)}</strong>
        </li>
      </ul>
      <button type="button" className="filter" onClick={onReset}>
        Reset to {money(baseBillCad)}
      </button>
    </section>
  )
}
