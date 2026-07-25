import { money } from '../lib/format'
import type { ForensicFinding } from '../types'

type Props = {
  flags: ForensicFinding[]
  onOpen: (flagId: string) => void
}

export default function MarqueeFlags({ flags, onOpen }: Props) {
  if (flags.length === 0) return null

  return (
    <section className="section marquee-flags" aria-labelledby="marquee-title">
      <div className="section-head">
        <h2 id="marquee-title">Watch these first</h2>
        <p>Highest-signal forensic flags from the current bill model.</p>
      </div>
      <ul className="marquee-list">
        {flags.map((flag) => (
          <li key={flag.id}>
            <button type="button" className="marquee-card" onClick={() => onOpen(flag.id)}>
              <span className="flag-id">{flag.id}</span>
              <strong>{flag.title}</strong>
              <span className="marquee-impact">{money(flag.estimatedBillImpactCad)}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
