import { useMemo, useState } from 'react'
import { money } from '../lib/format'
import {
  buildEvidenceIndex,
  citationLabel,
  resolveCitation,
  type EvidenceIndex,
} from '../lib/evidenceLookup'
import type {
  Derived,
  Fact,
  Finding,
  Gap,
  ReceiptLineItem,
  Source,
  TaxpayerReceipt,
} from '../types'
import FlagDetailDrawer from './FlagDetailDrawer'
import MarqueeFlags from './MarqueeFlags'

const FINDING_TABS = [
  { id: 'administrative_scale', label: 'Admin' },
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

function SourceAnchor({
  evidence,
  factId,
}: {
  evidence: EvidenceIndex
  factId?: string
}) {
  if (!factId) return null
  const citation = resolveCitation(evidence, factId)
  if (!citation.href) {
    return citation.kind === 'DERIVED' ? (
      <span className="source-link source-link-static">{citationLabel(citation)}</span>
    ) : null
  }
  return (
    <a className="source-link" href={citation.href} target="_blank" rel="noreferrer">
      {citation.source ? shortSourceName(citation.source.title) : 'Open source'}
      {citation.page != null ? ` · p.${citation.page}` : ''}
    </a>
  )
}

function shortSourceName(title: string) {
  if (title.includes('By-law 3637')) return 'By-law 3637-26 Schedule A'
  if (title.includes('Draft Budget')) return 'ND 2026 budget binder'
  if (title.includes('Final Budget Book')) return 'Region 2026 budget book'
  if (title.includes('Summary Booklet')) return 'Region budget summary'
  if (title.includes('17-10-0155')) return 'StatCan population estimates'
  if (title.includes('FIR')) return 'Ontario FIR 2023'
  if (title.includes('Census')) return 'StatCan 2021 Census'
  return title.length > 42 ? `${title.slice(0, 40)}…` : title
}

function LineList({
  id,
  title,
  subtitle,
  totalCad,
  lines,
  evidence,
}: {
  id: string
  title: string
  subtitle: string
  totalCad: number
  lines: ReceiptLineItem[]
  evidence: EvidenceIndex
}) {
  const sorted = [...lines].sort((a, b) => Math.abs(b.amountCad) - Math.abs(a.amountCad))
  return (
    <section className="section receipt-section" id={id} aria-labelledby={`${id}-title`}>
      <div className="section-head">
        <p className="section-kicker">On the bill</p>
        <h2 id={`${id}-title`}>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <div className="receipt-sheet">
        <div className="perforation" aria-hidden="true" />
        <ol className="receipt-lines">
          {sorted.map((line, index) => (
            <li
              key={line.id}
              className={['receipt-line', lineTone(line).row].join(' ')}
              style={{ animationDelay: `${index * 25}ms` }}
            >
              <div className="line-main">
                <div>
                  <p className="line-service">{line.label}</p>
                  <p className="line-meta">
                    {lineTone(line).label}
                    {line.note ? ` · ${line.note}` : ''}
                  </p>
                  <SourceAnchor evidence={evidence} factId={line.sourceFactId} />
                </div>
                <div className="line-right">
                  <span className={'badge ' + lineTone(line).badge}>{lineTone(line).label}</span>
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
  sources,
  facts,
  derived,
}: {
  data: TaxpayerReceipt
  gaps: Gap[]
  evidenceRules: string[]
  sources: Source[]
  facts: Fact[]
  derived: Derived[]
}) {
  const profile = data.profiles.supportedAverageHousehold
  const combined = profile.combinedAtAssessment
  const [flagTab, setFlagTab] = useState<FindingTab>('questionable_capital')
  const [selectedFlagId, setSelectedFlagId] = useState<string | null>(null)

  const evidence = useMemo(
    () => buildEvidenceIndex(sources, facts, derived),
    [sources, facts, derived],
  )

  const findingsById = useMemo(() => {
    return new Map(data.findings.map((finding) => [finding.id, finding]))
  }, [data.findings])

  const gapsById = useMemo(() => new Map(gaps.map((gap) => [gap.id, gap])), [gaps])

  const marqueeFlags = useMemo(() => {
    return data.uiModelHints.marqueeFindings
      .map((id) => findingsById.get(id))
      .filter((flag): flag is Finding => Boolean(flag))
  }, [data.uiModelHints.marqueeFindings, findingsById])

  const tabFindings = useMemo(
    () => data.findings.filter((finding) => finding.category === flagTab && !finding.belowMateriality),
    [data.findings, flagTab],
  )

  const selectedFlag = selectedFlagId ? findingsById.get(selectedFlagId) ?? null : null
  const townshipLines = profile.township.lineItems ?? []
  const regionLines = profile.region.lineItems ?? []

  const primarySources = sources.filter((s) =>
    ['nd-2026-tax-rate-bylaw', 'nd-2026-draft', 'row-2026-book', 'nd-2026-budget-minutes'].includes(
      s.id,
    ),
  )

  return (
    <div className="page">
      <header className="hero">
        <div className="hero-atmosphere" aria-hidden="true" />
        <div className="hero-inner">
          <p className="brand">Taxpayer Receipt</p>
          <h1>What a $455,000 rural bill pays in 2026</h1>
          <p className="hero-support">
            One assessment. Three rates from By-law 3637-26 Schedule A. Every dollar traces to a
            published source.
          </p>
          <div className="hero-cta-row">
            <a className="cta" href="#bill">
              Your bill
            </a>
            <a className="cta cta-ghost" href="#sources">
              Sources
            </a>
            <a className="cta cta-ghost" href="#gaps">
              Gaps
            </a>
          </div>
          <p className="hero-amount" aria-live="polite">
            <span className="hero-amount-label">Total residential bill · rural · By-law 3637-26</span>
            <span className="hero-amount-value">{money(profile.combinedTotalCad ?? 0)}</span>
          </p>
        </div>
      </header>

      <nav className="page-nav" aria-label="On this page">
        <a href="#bill">Bill</a>
        <a href="#township">Township</a>
        <a href="#region">Region</a>
        <a href="#watch">Watch</a>
        <a href="#findings">Findings</a>
        <a href="#gaps">Gaps</a>
        <a href="#sources">Sources</a>
      </nav>

      <main>
        <section className="section bill-section" id="bill" aria-labelledby="bill-title">
          <div className="section-head">
            <p className="section-kicker">1 · Combined receipt</p>
            <h2 id="bill-title">How the total is built</h2>
            <p>
              {combined?.basis ??
                'Township + Region + Education at one $455,000 assessment.'}
            </p>
          </div>

          <ol className="bill-stack">
            {(combined?.components ?? []).map((component) => (
              <li key={component.label} className="bill-stack-row">
                <div>
                  <h3>{component.label}</h3>
                  <p className="line-meta">
                    Rate {component.rate.toFixed(8)} × {money(combined?.assessmentCad ?? 455000)}
                  </p>
                  <SourceAnchor evidence={evidence} factId={component.sourceFactId} />
                </div>
                <strong className="bill-stack-amount">{money(component.amountCad)}</strong>
              </li>
            ))}
          </ol>

          <div className="bill-stack-total">
            <span>Combined total</span>
            <strong>{money(combined?.totalCad ?? profile.combinedTotalCad ?? 0)}</strong>
          </div>

          <p className="bill-note">{profile.combinedTotalNote}</p>

          <details className="fold">
            <summary>Model notes &amp; caveats</summary>
            <ul className="child-list">
              {profile.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
              <li>
                Township rural avg @ $455k: {money(profile.township.amountCad ?? 0)} (approved
                operating allocation below)
              </li>
              <li>
                Region rural HH table @ $354.5k: {money(profile.region.amountCad ?? 0)} — different
                assessment base; do not add to the combined total above
              </li>
              <li>{data.profiles.hypothetical5000.message}</li>
            </ul>
          </details>
        </section>

        <LineList
          id="township"
          title="Township portion"
          subtitle={profile.township.basis}
          totalCad={profile.township.amountCad ?? 0}
          lines={townshipLines}
          evidence={evidence}
        />

        <LineList
          id="region"
          title="Region portion (rural household table)"
          subtitle={profile.region.basis}
          totalCad={profile.region.amountCad ?? 0}
          lines={regionLines}
          evidence={evidence}
        />

        <div id="watch">
          <MarqueeFlags flags={marqueeFlags} onOpen={setSelectedFlagId} />
        </div>

        <section className="section" id="findings" aria-labelledby="findings-title">
          <div className="section-head">
            <p className="section-kicker">2 · Needs explanation</p>
            <h2 id="findings-title">Findings</h2>
            <p>Cited to facts; bill dollars stay null until a formula is approved.</p>
            <p className="line-meta">
              {data.uiModelHints.flaggedDefinition ??
                'Flagged means this line needs an explanation. It does not mean the money was wasted.'}
            </p>
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
            {tabFindings.map((flag) => {
              const firstCite = flag.citedFactIds[0]
                ? resolveCitation(evidence, flag.citedFactIds[0])
                : null
              return (
                <li key={flag.id} className={`flag-item severity-${flag.opportunitySeverity}`}>
                  <button
                    type="button"
                    className="flag-button"
                    onClick={() => setSelectedFlagId(flag.id)}
                  >
                    <div className="flag-top">
                      <div>
                        <p className="flag-id">{flag.id}</p>
                        <h3>{flag.title}</h3>
                      </div>
                      <span className="flag-impact">review</span>
                    </div>
                    <p>{flag.evidenceSummary}</p>
                    {firstCite?.source ? (
                      <p className="line-meta">Primary: {citationLabel(firstCite)}</p>
                    ) : null}
                    <span className="flag-cta">Open citations</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>

        <section className="section" id="gaps" aria-labelledby="gaps-title">
          <div className="section-head">
            <p className="section-kicker">3 · Still missing</p>
            <h2 id="gaps-title">Evidence gaps</h2>
            <p>Missing proof is listed — not filled with invented numbers.</p>
          </div>
          <ul className="flag-list">
            {gaps.map((gap) => (
              <li key={gap.id} id={gap.id} className="flag-item severity-watch">
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
          <details className="fold">
            <summary>Evidence policy</summary>
            <ul className="child-list">
              {evidenceRules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          </details>
        </section>

        <section className="section sources-section" id="sources" aria-labelledby="sources-title">
          <div className="section-head">
            <p className="section-kicker">References</p>
            <h2 id="sources-title">Direct sources</h2>
            <p>Open the published documents behind this receipt.</p>
          </div>

          <div className="source-priority">
            <h3>Start here</h3>
            <ul className="source-list">
              {primarySources.map((source) => (
                <li key={source.id}>
                  <a className="source-card" href={source.url} target="_blank" rel="noreferrer">
                    <span className="source-auth">{source.authority ?? 'source'}</span>
                    <strong>{source.title}</strong>
                    <span className="source-open">Open document →</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <h3 className="source-all-heading">Full bibliography</h3>
          <ul className="source-list source-list-compact">
            {sources.map((source) => (
              <li key={source.id}>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.title}
                </a>
                {source.asOf ? <span className="line-meta"> · as of {source.asOf}</span> : null}
                {source.note ? <p className="line-meta">{source.note}</p> : null}
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
        <FlagDetailDrawer
          flag={selectedFlag}
          evidence={evidence}
          gapsById={gapsById}
          onClose={() => setSelectedFlagId(null)}
        />
      ) : null}
    </div>
  )
}
