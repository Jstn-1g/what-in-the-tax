import { useMemo, useState } from 'react'
import { money } from '../lib/format'
import type { Finding, Gap, ReceiptLineItem, TaxpayerReceipt } from '../types'
import FlagDetailDrawer from './FlagDetailDrawer'
import MarqueeFlags from './MarqueeFlags'

const FINDING_TABS = [
  { id: 'administrative_bloat', label: 'Admin' },
  { id: 'questionable_capital', label: 'Capital' },
  { id: 'unusual_line_items', label: 'Unusual' },
] as const

type FindingTab = (typeof FINDING_TABS)[number]['id']

function lineTone(line: ReceiptLineItem) {
  if (line.classification === 'reconciling_item') {
    return { row: 'pass_through', badge: 'badge-pass', label: 'ROUNDING' }
  }
  if (line.evidenceStatus === 'GAP') {
    return { row: 'flagged', badge: 'badge-flagged', label: line.evidenceStatus }
  }
  return { row: 'necessary', badge: 'badge-necessary', label: line.evidenceStatus }
}

function LineList({
  title,
  subtitle,
  totalCad,
  lines,
}: {
  title: string
  subtitle: string
  totalCad: number
  lines: ReceiptLineItem[]
}) {
  const sorted = [...lines].sort((a, b) => Math.abs(b.amountCad) - Math.abs(a.amountCad))
  return (
    <section className="section receipt-section" aria-labelledby={`${title}-id`}>
      <div className="section-head">
        <h2 id={`${title}-id`}>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <div className="receipt-sheet">
        <div className="perforation" aria-hidden="true" />
        <ol className="receipt-lines">
          {sorted.map((line, index) => (
            <li
              key={line.id}
              className={[
                'receipt-line',
                lineTone(line).row,
              ].join(' ')}
              style={{ animationDelay: `${index * 25}ms` }}
            >
              <div className="line-main">
                <div>
                  <p className="line-service">{line.label}</p>
                  <p className="line-meta">
                    {lineTone(line).label}
                    {line.note ? ` · ${line.note}` : ''}
                  </p>
                </div>
                <div className="line-right">
                  <span
                    className={
                      'badge ' + lineTone(line).badge
                    }
                  >
                    {lineTone(line).label}
                  </span>
                  <strong>{money(line.amountCad)}</strong>
                </div>
              </div>
            </li>
          ))}
        </ol>
        <div className="receipt-total">
          <span>Published / allocated total</span>
          <strong>{money(totalCad)}</strong>
        </div>
      </div>
    </section>
  )
}

export default function TaxReceiptScreen({
  data,
  gaps,
  evidenceRules,
}: {
  data: TaxpayerReceipt
  gaps: Gap[]
  evidenceRules: string[]
}) {
  const profile = data.profiles.supportedAverageHousehold
  const [flagTab, setFlagTab] = useState<FindingTab>('questionable_capital')
  const [selectedFlagId, setSelectedFlagId] = useState<string | null>(null)

  const findingsById = useMemo(() => {
    return new Map(data.findings.map((finding) => [finding.id, finding]))
  }, [data.findings])

  const marqueeFlags = useMemo(() => {
    return data.uiModelHints.marqueeFindings
      .map((id) => findingsById.get(id))
      .filter((flag): flag is Finding => Boolean(flag))
  }, [data.uiModelHints.marqueeFindings, findingsById])

  const tabFindings = useMemo(
    () => data.findings.filter((finding) => finding.category === flagTab),
    [data.findings, flagTab],
  )

  const selectedFlag = selectedFlagId ? findingsById.get(selectedFlagId) ?? null : null
  const townshipLines = profile.township.lineItems ?? []
  const regionLines = profile.region.lineItems ?? []

  return (
    <div className="page">
      <header className="hero">
        <div className="hero-atmosphere" aria-hidden="true" />
        <div className="hero-inner">
          <p className="brand">Taxpayer Receipt</p>
          <h1>Evidence-based household profile</h1>
          <p className="hero-support">
            North Dumfries approved + Region rural household table · no filler allocations
          </p>
          <div className="hero-cta-row">
            <a className="cta" href="#gaps">
              See gaps
            </a>
            <a className="cta cta-ghost" href="#findings">
              Findings
            </a>
          </div>
          <p className="hero-amount" aria-live="polite">
            <span className="hero-amount-label">Supported slices (not one combined bill)</span>
            <span className="hero-amount-value">
              Twp {money(profile.township.amountCad ?? 0)} · Reg {money(profile.region.amountCad ?? 0)}
            </span>
          </p>
        </div>
      </header>

      <main>
        <section className="section" id="gaps" aria-labelledby="gaps-title">
          <div className="section-head">
            <h2 id="gaps-title">Evidence gaps</h2>
            <p>Missing proof is listed — not filled with invented numbers.</p>
          </div>
          <ul className="flag-list">
            {gaps.map((gap) => (
              <li key={gap.id} className="flag-item severity-watch">
                <div className="flag-top">
                  <div>
                    <p className="flag-id">{gap.id}</p>
                    <h3>{gap.title}</h3>
                  </div>
                  <span className="flag-impact">gap</span>
                </div>
                <p>{gap.detail}</p>
                {gap.neededEvidence.length > 0 ? (
                  <p className="line-meta">Need: {gap.neededEvidence.join(' · ')}</p>
                ) : null}
              </li>
            ))}
          </ul>
          <div className="section-head" style={{ marginTop: '1.5rem' }}>
            <h3>Policy</h3>
            <ul className="child-list">
              {evidenceRules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          </div>
        </section>

        <section className="section mix-section" aria-labelledby="status-title">
          <div className="section-head">
            <h2 id="status-title">Model status</h2>
            <p>{data.purpose}</p>
          </div>
          <ul className="mix-legend">
            <li>
              <span className="swatch necessary" />
              Township rural avg @ $455k: {money(profile.township.amountCad ?? 0)} (approved)
            </li>
            <li>
              <span className="swatch pass" />
              Region rural HH @ $354.5k: {money(profile.region.amountCad ?? 0)} (final table)
            </li>
            <li>
              <span className="swatch pass" />
              Education rate: FACT (By-law 3637-26) · combined $5k bill deferred
            </li>
          </ul>
          <ul className="child-list">
            {profile.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
            <li>{profile.combinedTotalNote}</li>
            <li>{data.profiles.hypothetical5000.message}</li>
          </ul>
        </section>

        <MarqueeFlags flags={marqueeFlags} onOpen={setSelectedFlagId} />

        <LineList
          title="Township portion"
          subtitle={profile.township.basis}
          totalCad={profile.township.amountCad ?? 0}
          lines={townshipLines}
        />

        <LineList
          title="Region portion (rural household)"
          subtitle={profile.region.basis}
          totalCad={profile.region.amountCad ?? 0}
          lines={regionLines}
        />

        <section className="section" id="findings" aria-labelledby="findings-title">
          <div className="section-head">
            <h2 id="findings-title">Findings (judgment)</h2>
            <p>Cited to facts; bill dollars stay null until a formula is approved.</p>
          </div>
          <div className="filter-row" role="tablist" aria-label="Finding categories">
            {FINDING_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={flagTab === tab.id}
                className={flagTab === tab.id ? 'filter active' : 'filter'}
                onClick={() => setFlagTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <ul className="flag-list">
            {tabFindings.map((flag) => (
              <li key={flag.id} className={`flag-item severity-${flag.opportunitySeverity}`}>
                <button type="button" className="flag-button" onClick={() => setSelectedFlagId(flag.id)}>
                  <div className="flag-top">
                    <div>
                      <p className="flag-id">{flag.id}</p>
                      <h3>{flag.title}</h3>
                    </div>
                    <span className="flag-impact">n/a</span>
                  </div>
                  <p>{flag.evidenceSummary}</p>
                  <span className="flag-cta">View citations</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <footer className="footer">
          <p>{data.status}</p>
          <p>{data.evidencePolicyRef}</p>
        </footer>
      </main>

      {selectedFlag ? (
        <FlagDetailDrawer flag={selectedFlag} onClose={() => setSelectedFlagId(null)} />
      ) : null}
    </div>
  )
}
