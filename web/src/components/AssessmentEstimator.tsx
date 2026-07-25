import { useMemo } from 'react'
import { money } from '../lib/format'

type Props = {
  assessment: number
  onAssessmentChange: (value: number) => void
  rates: {
    townshipRate: number
    regionRate: number
    educationRate: number
  }
  onApplyBill: (billCad: number) => void
}

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100
}

export default function AssessmentEstimator({
  assessment,
  onAssessmentChange,
  rates,
  onApplyBill,
}: Props) {
  const estimate = useMemo(() => {
    const township = roundMoney(assessment * rates.townshipRate)
    const region = roundMoney(assessment * rates.regionRate)
    const education = roundMoney(assessment * rates.educationRate)
    const total = roundMoney(township + region + education)
    return { township, region, education, total }
  }, [assessment, rates])

  return (
    <section className="section assessment-estimator" aria-labelledby="assessment-title">
      <div className="section-head">
        <h2 id="assessment-title">Estimate from assessment</h2>
        <p>
          Enter an MPAC assessed value. We apply illustrative residential rates to estimate
          your annual bill, then load that into the receipt.
        </p>
      </div>

      <label className="bill-input-label" htmlFor="assessment-value">
        Assessed value (CVA)
        <input
          id="assessment-value"
          type="number"
          min={50000}
          max={5000000}
          step={1000}
          value={assessment}
          onChange={(event) => {
            const next = Number(event.target.value)
            if (Number.isFinite(next)) {
              onAssessmentChange(Math.min(5000000, Math.max(50000, next)))
            }
          }}
        />
      </label>

      <ul className="estimate-breakdown">
        <li>
          <span>Township</span>
          <strong>{money(estimate.township)}</strong>
        </li>
        <li>
          <span>Region (incl. police)</span>
          <strong>{money(estimate.region)}</strong>
        </li>
        <li>
          <span>Education</span>
          <strong>{money(estimate.education)}</strong>
        </li>
        <li className="estimate-total">
          <span>Estimated annual bill</span>
          <strong>{money(estimate.total)}</strong>
        </li>
      </ul>

      <button
        type="button"
        className="cta apply-bill"
        onClick={() => onApplyBill(Math.max(1000, Math.min(20000, Math.round(estimate.total))))}
      >
        Apply {money(estimate.total)} to receipt
      </button>

      <p className="estimate-note">
        Uses published residential rate ratios as a modeling proxy (not an official tax
        calculator). Actual bills vary with class, phase-in, and special area rates.
      </p>
    </section>
  )
}
