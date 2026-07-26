import { money, pct } from '../lib/format'
import type { HeroBriefingModel } from '../lib/heroBriefing'
import { simplifyShareLabel, uiCopy } from '../lib/eli5'
import SharePie, { destinationColor, toneColor } from './SharePie'

export default function HeroBriefing({
  model,
  onOpenHelp,
  simpleLanguage = false,
}: {
  model: HeroBriefingModel
  onOpenHelp?: () => void
  simpleLanguage?: boolean
}) {
  const copy = uiCopy(simpleLanguage)

  const shareSlices = model.shares.map((share) => ({
    id: share.label,
    label: simplifyShareLabel(share.shortLabel, simpleLanguage),
    share: share.share,
    color: toneColor(share.tone),
    title: `${share.label}: ${money(share.amountCad)} (${pct(share.share * 100)})`,
  }))

  const municipalAmount =
    model.shares.find((s) => s.tone === 'municipal')?.amountCad ?? model.totalCad

  const destSlices = model.destinations.map((dest, index) => ({
    id: dest.id,
    label: dest.label,
    share: dest.shareOfMunicipal,
    color: destinationColor(index, dest.id === 'dest-remainder'),
    title: `${dest.label}: ${money(dest.amountCad)} (${pct(dest.shareOfMunicipal * 100)})`,
  }))
  const showDestDonut = destSlices.length >= 2

  return (
    <div className="hero-briefing" aria-label={copy.atAGlance}>
      <div className="hero-briefing-perforation" aria-hidden="true" />

      <p className="hero-briefing-kicker">{copy.atAGlance}</p>

      <div className="hero-briefing-block">
        <div className="hero-briefing-block-head">
          <h2 className="hero-briefing-title">{copy.ofThisBill}</h2>
          <p className="hero-briefing-sub">
            {simpleLanguage
              ? copy.ofThisBillSub
              : model.shares.some((s) => s.tone === 'upper')
                ? model.shares.map((s) => s.shortLabel).join(' · ') + ' · same assessment'
                : copy.ofThisBillSub}
          </p>
        </div>
        <div className="hero-pie-layout">
            <SharePie
              slices={shareSlices}
              centerLabel={simpleLanguage ? 'Your bill' : 'Combined'}
              centerValue={money(model.totalCad)}
              ariaLabel={shareSlices
                .map((s) => `${s.label} ${pct(s.share * 100)}`)
                .join(', ')}
            />
          <ul className="hero-share-legend">
            {model.shares.map((share) => (
              <li key={share.label}>
                <span className={`hero-share-dot tone-${share.tone}`} aria-hidden="true" />
                <span className="hero-share-name">
                  {simplifyShareLabel(share.shortLabel, simpleLanguage)}
                </span>
                <span className="hero-share-pct">{pct(share.share * 100)}</span>
                <span className="hero-share-amt">{money(share.amountCad)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {model.destinations.length > 0 ? (
        <div className="hero-briefing-block">
          <div className="hero-briefing-block-head">
            <h2 className="hero-briefing-title">{copy.localDollar}</h2>
            <p className="hero-briefing-sub">{model.destinationsBasis}</p>
          </div>
          <div className={showDestDonut ? 'hero-pie-layout' : 'hero-pie-layout hero-pie-layout-list-only'}>
            {showDestDonut ? (
              <SharePie
                slices={destSlices}
                centerLabel={simpleLanguage ? 'Local share' : 'Local'}
                centerValue={money(municipalAmount)}
                ariaLabel={destSlices
                  .map((s) => `${s.label} ${pct(s.share * 100)}`)
                  .join(', ')}
              />
            ) : null}
            <ol className="hero-destinations">
              {model.destinations.map((dest, index) => {
                const isRemainder = dest.id === 'dest-remainder'
                const barPct = Math.max(dest.shareOfMunicipal * 100, 0)
                return (
                  <li
                    key={dest.id}
                    className={isRemainder ? 'hero-dest-remainder' : undefined}
                    style={{ animationDelay: `${0.35 + index * 0.07}s` }}
                  >
                    <div className="hero-dest-row">
                      <span
                        className="hero-dest-swatch"
                        style={{ background: destinationColor(index, isRemainder) }}
                        aria-hidden="true"
                      />
                      <span className="hero-dest-label">{dest.label}</span>
                      <span className="hero-dest-pct">{pct(barPct)}</span>
                      <span className="hero-dest-amt">{money(dest.amountCad)}</span>
                    </div>
                  </li>
                )
              })}
            </ol>
          </div>
          <a className="hero-briefing-jump" href="#township">
            {copy.fullReceiptJump}
          </a>
        </div>
      ) : null}

      <div className="hero-briefing-block hero-briefing-attention">
        <div className="hero-briefing-block-head">
          <h2 className="hero-briefing-title">{copy.evidenceState}</h2>
          <p className="hero-briefing-sub">
            {copy.evidenceStateSub}
            {onOpenHelp ? (
              <>
                {' · '}
                <button type="button" className="hero-inline-help" onClick={onOpenHelp}>
                  {copy.whatDoTheseMean}
                </button>
              </>
            ) : null}
          </p>
        </div>
        <ul className="hero-attention-chips">
          {model.attention.map((chip) => {
            const className = `hero-attention-chip tone-${chip.tone}`
            const body = (
              <>
                <strong>{chip.label}</strong>
                <span>{chip.detail}</span>
              </>
            )
            return (
              <li key={chip.id}>
                {chip.href ? (
                  <a className={className} href={chip.href} title={chip.detail}>
                    {body}
                  </a>
                ) : (
                  <span className={`${className} is-static`} title={chip.detail}>
                    {body}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      </div>

      <p className="hero-briefing-footnote">{model.footnote}</p>
    </div>
  )
}
