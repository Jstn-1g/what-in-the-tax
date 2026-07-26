import type { Finding } from '../types'

type Props = {
  flags: Finding[]
  onOpen: (flagId: string) => void
}

export default function MarqueeFlags({ flags, onOpen }: Props) {
  if (flags.length === 0) return null

  return (
    <section className="section marquee-flags" aria-labelledby="marquee-title">
      <div className="section-head">
        <p className="section-kicker">Checked against the record</p>
        <h2 id="marquee-title">Watch these first</h2>
        <p>Highest-signal findings — judgment only; no invented bill dollars.</p>
      </div>
      <ul className="marquee-list">
        {flags.map((flag) => (
          <li key={flag.id}>
            <button type="button" className="marquee-card" onClick={() => onOpen(flag.id)}>
              <span className="flag-id">{flag.id}</span>
              <strong>{flag.title}</strong>
              <span className="marquee-impact">review</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
