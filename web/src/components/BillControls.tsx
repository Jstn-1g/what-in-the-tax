import { money } from '../lib/format'

type Props = {
  billCad: number
  onChange: (value: number) => void
}

const PRESETS = [3500, 5000, 6500, 8000]

export default function BillControls({ billCad, onChange }: Props) {
  return (
    <section className="section bill-controls" aria-labelledby="bill-controls-title">
      <div className="section-head">
        <h2 id="bill-controls-title">Set your annual bill</h2>
        <p>Scale the whole receipt from the $5,000 model. Presets are common local ranges.</p>
      </div>

      <div className="bill-controls-row">
        <label className="bill-input-label" htmlFor="bill-amount">
          Annual property tax
          <input
            id="bill-amount"
            type="number"
            min={1000}
            max={20000}
            step={50}
            value={billCad}
            onChange={(event) => {
              const next = Number(event.target.value)
              if (Number.isFinite(next)) onChange(Math.min(20000, Math.max(1000, next)))
            }}
          />
        </label>
        <p className="bill-live">{money(billCad)}</p>
      </div>

      <label className="bill-slider-label" htmlFor="bill-slider">
        <span className="sr-only">Adjust annual bill</span>
        <input
          id="bill-slider"
          type="range"
          min={1000}
          max={20000}
          step={50}
          value={billCad}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </label>

      <div className="preset-row" role="group" aria-label="Bill presets">
        {PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            className={billCad === preset ? 'filter active' : 'filter'}
            onClick={() => onChange(preset)}
          >
            {money(preset)}
          </button>
        ))}
      </div>
    </section>
  )
}
