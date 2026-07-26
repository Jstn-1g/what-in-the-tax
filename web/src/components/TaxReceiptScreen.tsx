import { useMemo, useState, type ReactNode } from 'react'
import { money, pct, yearFromText } from '../lib/format'
import {
  buildEvidenceIndex,
  citationLabel,
  resolveCitation,
  type CitationAudit,
  type EvidenceIndex,
} from '../lib/evidenceLookup'
import {
  badgeLabel,
  simplifyBucketLabel,
  simplifyComponentLabel,
  uiCopy,
} from '../lib/eli5'
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
import HeroBriefing from './HeroBriefing'
import MarqueeFlags from './MarqueeFlags'
import { buildHeroBriefing } from '../lib/heroBriefing'

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
  if (line.evidenceStatus === 'FACT') {
    return { row: 'necessary', badge: 'badge-fact', label: line.evidenceStatus }
  }
  if (line.evidenceStatus === 'DERIVED') {
    return { row: 'necessary', badge: 'badge-derived', label: line.evidenceStatus }
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
  const pageLabel =
    citation.page != null && citation.matchTier !== 'weak'
      ? ` · p.${citation.page}`
      : ''
  return (
    <a className="source-link" href={citation.href} target="_blank" rel="noreferrer">
      {citation.source ? shortSourceName(citation.source.title) : 'Open source'}
      {pageLabel}
    </a>
  )
}

function shortSourceName(title: string) {
  return title.length > 42 ? `${title.slice(0, 40)}…` : title
}

function LineList({
  id,
  title,
  subtitle,
  totalCad,
  lines,
  evidence,
  simpleLanguage = false,
  kicker,
}: {
  id: string
  title: string
  subtitle: string
  totalCad: number
  lines: ReceiptLineItem[]
  evidence: EvidenceIndex
  simpleLanguage?: boolean
  kicker?: string
}) {
  const sorted = [...lines].sort((a, b) => Math.abs(b.amountCad) - Math.abs(a.amountCad))
  const copy = uiCopy(simpleLanguage)
  const positiveTotal = sorted
    .filter((line) => line.amountCad > 0 && line.classification !== 'reconciling_item')
    .reduce((sum, line) => sum + line.amountCad, 0)
  const barBase = totalCad > 0 ? totalCad : positiveTotal
  return (
    <section className="section receipt-section" id={id} aria-labelledby={`${id}-title`}>
      <div className="section-head">
        <p className="section-kicker">{kicker ?? copy.onTheBill}</p>
        <h2 id={`${id}-title`}>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <div className="receipt-sheet">
        <div className="perforation" aria-hidden="true" />
        <ol className="receipt-lines">
          {sorted.map((line, index) => {
            const tone = lineTone(line)
            const status = badgeLabel(tone.label, simpleLanguage)
            const share =
              barBase > 0 && line.amountCad > 0 ? line.amountCad / barBase : 0
            const showBar =
              share > 0 &&
              line.classification !== 'reconciling_item' &&
              line.classification !== 'disclosure_subline'
            return (
              <li
                key={line.id}
                className={['receipt-line', tone.row].join(' ')}
                style={{ animationDelay: `${index * 25}ms` }}
              >
                <div className="line-main">
                  <div>
                    <p className="line-service">{line.label}</p>
                    <p className="line-meta">
                      {status}
                      {showBar ? ` · ${pct(share * 100)} of this share` : ''}
                      {line.note ? ` · ${line.note}` : ''}
                    </p>
                    <SourceAnchor evidence={evidence} factId={line.sourceFactId} />
                  </div>
                  <div className="line-right">
                    <span className={'badge ' + tone.badge}>{status}</span>
                    <strong>{money(line.amountCad)}</strong>
                  </div>
                </div>
                {showBar ? (
                  <div
                    className="line-share-track"
                    role="img"
                    aria-label={`${line.label}: ${pct(share * 100)} of ${title}`}
                  >
                    <span
                      className="line-share-fill"
                      style={{ width: `${Math.min(Math.max(share * 100, 1.2), 100)}%` }}
                    />
                  </div>
                ) : null}
              </li>
            )
          })}
        </ol>
        <div className="receipt-total">
          <span>{copy.publishedTotal}</span>
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
  citationAudit,
  bannerText,
  packSwitcher,
  onOpenHelp,
  simpleLanguage = false,
}: {
  data: TaxpayerReceipt
  gaps: Gap[]
  evidenceRules: string[]
  sources: Source[]
  facts: Fact[]
  derived: Derived[]
  citationAudit?: CitationAudit | null
  bannerText?: string
  packSwitcher?: ReactNode
  onOpenHelp?: () => void
  simpleLanguage?: boolean
}) {
  const profile = data.profiles.supportedAverageHousehold
  const combined = profile.combinedAtAssessment
  const [flagTab, setFlagTab] = useState<FindingTab>('questionable_capital')
  const [selectedFlagId, setSelectedFlagId] = useState<string | null>(null)
  const copy = uiCopy(simpleLanguage)

  const evidence = useMemo(
    () => buildEvidenceIndex(sources, facts, derived, citationAudit),
    [sources, facts, derived, citationAudit],
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

  const heroBriefing = useMemo(
    () =>
      buildHeroBriefing(data, gaps, citationAudit, {
        municipalBucketLabel:
          data.uiModelHints.municipalBucketLabel ?? profile.township.uiLabel,
      }),
    [data, gaps, citationAudit, profile.township.uiLabel],
  )

  const tabFindings = useMemo(
    () => data.findings.filter((finding) => finding.category === flagTab && !finding.belowMateriality),
    [data.findings, flagTab],
  )

  const selectedFlag = selectedFlagId ? findingsById.get(selectedFlagId) ?? null : null
  const townshipLines = profile.township.lineItems ?? []
  const regionLines = profile.region.lineItems ?? []
  const hasRegionBucket =
    profile.region.amountCad != null && (regionLines.length > 0 || profile.region.evidenceStatus !== 'GAP')
  const regionIllustration = profile.regionIllustrationAt354500
  const assessmentCad = combined?.assessmentCad ?? profile.township.assessmentCad ?? 0
  const displayName = data.jurisdiction?.displayName ?? 'North Dumfries'
  const receiptYear = yearFromText(
    data.purpose,
    profile.description,
    combined?.basis,
    profile.township.basis,
    profile.region.basis,
  )
  const municipalLabel = simplifyBucketLabel(
    data.uiModelHints.municipalBucketLabel ?? profile.township.uiLabel ?? 'Township portion',
    simpleLanguage,
  )
  const regionLabel = simplifyBucketLabel(
    data.uiModelHints.regionBucketLabel ?? profile.region.uiLabel ?? 'Region portion',
    simpleLanguage,
  )
  const heroLabel =
    data.uiModelHints.heroLabel ??
    `Illustrative residential total · ${money(assessmentCad)} assessment`

  const primarySources = useMemo(() => {
    const candidateFactIds = [
      ...(combined?.components ?? []).map((component) => component.sourceFactId),
      profile.township.sourceFactId,
      ...townshipLines.slice(0, 3).map((line) => line.sourceFactId),
      profile.region.sourceFactId,
      ...regionLines.slice(0, 3).map((line) => line.sourceFactId),
    ]
    const sourceIds = new Set(
      candidateFactIds
        .filter((id): id is string => Boolean(id))
        .map((id) => resolveCitation(evidence, id).source?.id)
        .filter((id): id is string => Boolean(id)),
    )
    const cited = sources.filter((source) => sourceIds.has(source.id))
    return cited.length > 0 ? cited : sources.slice(0, 3)
  }, [
    combined?.components,
    evidence,
    profile.region.sourceFactId,
    profile.township.sourceFactId,
    regionLines,
    sources,
    townshipLines,
  ])

  return (
    <div className="page">
      <a className="skip-link" href="#main-content">
        Skip to illustrative receipt
      </a>
      <div className="deploy-banner" role="status">
        {bannerText ??
          'Independent illustrative receipt · unaffiliated · citation status unavailable'}
      </div>
      {packSwitcher}
      <header className="hero" id="receipt-hero" tabIndex={-1}>
        <div className="hero-atmosphere" aria-hidden="true" />
        <div className="hero-inner">
          <div className="hero-masthead">
            <p className="hero-context">
              <span className="hero-place">{displayName}</span>
              {receiptYear ? (
                <>
                  <span className="hero-context-sep" aria-hidden="true">
                    ·
                  </span>
                  <span className="hero-year">{receiptYear}</span>
                </>
              ) : null}
            </p>
            <p className="brand">Taxpayer Receipt</p>
          </div>
          <h1>
            <span className="hero-assessment">{money(assessmentCad)}</span>{' '}
            {copy.heroHeadlineAfterAmount}
          </h1>
          <p className="hero-support">{copy.heroSupport}</p>
          <p className="hero-scenario-note">
            <strong>Illustrative scenario.</strong> {profile.description}
          </p>
          <div className="hero-cta-row">
            <a className="cta" href="#bill">
              Illustrative receipt
            </a>
            <a className="cta cta-ghost" href="#sources">
              {copy.sourcesCta}
            </a>
            <a className="cta cta-ghost" href="#gaps">
              {copy.gapsCta}
            </a>
            {onOpenHelp ? (
              <button
                type="button"
                className="cta cta-ghost"
                data-help-trigger="receipt-hero"
                onClick={onOpenHelp}
              >
                {copy.helpCta}
              </button>
            ) : null}
          </div>
          <p className="hero-amount" aria-live="polite">
            <span className="hero-amount-label">{heroLabel}</span>
            <span className="hero-amount-value">{money(profile.combinedTotalCad ?? 0)}</span>
          </p>
          {heroBriefing ? (
            <HeroBriefing
              model={heroBriefing}
              onOpenHelp={onOpenHelp}
              simpleLanguage={simpleLanguage}
            />
          ) : null}
        </div>
      </header>

      <nav className="page-nav" aria-label="On this page">
        <a href="#bill">Bill</a>
        <a href="#township">{municipalLabel.replace(/ portion$/i, '').replace(/'s share$/i, '')}</a>
        {hasRegionBucket ? <a href="#region">Region</a> : null}
        {marqueeFlags.length > 0 ? <a href="#watch">{copy.navWatch}</a> : null}
        {data.findings.length > 0 ? <a href="#findings">{copy.navFindings}</a> : null}
        <a href="#gaps">{copy.navGaps}</a>
        <a href="#sources">{copy.navSources}</a>
        {onOpenHelp ? (
          <button
            type="button"
            className="page-nav-help"
            data-help-trigger="receipt-page-nav"
            onClick={onOpenHelp}
          >
            {copy.navHelp}
          </button>
        ) : null}
      </nav>

      <main id="main-content" tabIndex={-1}>
        <section className="section bill-section" id="bill" aria-labelledby="bill-title">
          <div className="section-head">
            <p className="section-kicker">{copy.combinedKicker}</p>
            <h2 id="bill-title">{copy.combinedTitle}</h2>
            <p>
              {combined?.basis ??
                (hasRegionBucket
                  ? `${municipalLabel} + ${regionLabel} + education at one assessment.`
                  : `${municipalLabel} + education at one assessment.`)}
            </p>
          </div>

          <ol className="bill-stack">
            {(combined?.components ?? []).map((component) => {
              const billTotal = combined?.totalCad ?? profile.combinedTotalCad ?? 0
              const shareOfBill =
                billTotal > 0 ? Math.max(component.amountCad / billTotal, 0) : 0
              const tone = (() => {
                const lower = component.label.toLowerCase()
                if (lower.includes('education')) return 'education'
                if (lower.includes('hospital')) return 'special'
                if (lower.includes('region')) return 'upper'
                return 'municipal'
              })()
              return (
                <li key={component.label} className="bill-stack-row">
                  <div className="bill-stack-body">
                    <div className="bill-stack-copy">
                      <h3>{simplifyComponentLabel(component.label, simpleLanguage)}</h3>
                      <p className="line-meta">
                        Rate {component.rate.toFixed(8)} × {money(assessmentCad)}
                        {' · '}
                        {pct(shareOfBill * 100)} of bill
                      </p>
                      <SourceAnchor evidence={evidence} factId={component.sourceFactId} />
                    </div>
                    <strong className="bill-stack-amount">{money(component.amountCad)}</strong>
                  </div>
                  <div
                    className="bill-stack-track"
                    role="img"
                    aria-label={`${component.label}: ${pct(shareOfBill * 100)} of combined bill`}
                  >
                    <span
                      className={`bill-stack-fill tone-${tone}`}
                      style={{ width: `${Math.min(Math.max(shareOfBill * 100, 1.5), 100)}%` }}
                    />
                  </div>
                </li>
              )
            })}
          </ol>

          <div className="bill-stack-total">
            <span>{copy.combinedTotalLabel}</span>
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
                {municipalLabel} @ {money(assessmentCad)}: {money(profile.township.amountCad ?? 0)}
              </li>
              {hasRegionBucket ? (
                <li>
                  {regionLabel} @ {money(profile.region.assessmentCad ?? assessmentCad)}:{' '}
                  {money(profile.region.amountCad ?? 0)} — already included in the combined total
                  above at this household assessment
                </li>
              ) : (
                <li>{profile.region.note ?? profile.region.basis}</li>
              )}
              {regionIllustration ? (
                <li>
                  Region illustration @{' '}
                  {money(regionIllustration.assessmentCad ?? 354500)}:{' '}
                  {money(regionIllustration.amountCad ?? 0)} — different assessment base; do not
                  add to the combined total above
                </li>
              ) : null}
              <li>{data.profiles.hypothetical5000.message}</li>
            </ul>
          </details>
        </section>

        <LineList
          id="township"
          title={municipalLabel}
          subtitle={profile.township.basis}
          totalCad={profile.township.amountCad ?? 0}
          lines={townshipLines}
          evidence={evidence}
          simpleLanguage={simpleLanguage}
        />

        {hasRegionBucket ? (
          <LineList
            id="region"
            title={regionLabel}
            subtitle={profile.region.basis}
            totalCad={profile.region.amountCad ?? 0}
            lines={regionLines}
            evidence={evidence}
            simpleLanguage={simpleLanguage}
          />
        ) : null}

        {regionIllustration && (regionIllustration.lineItems?.length ?? 0) > 0 ? (
          <LineList
            id="region-illustration"
            title={
              regionIllustration.uiLabel ??
              `Region schedule @ ${money(regionIllustration.assessmentCad ?? 354500)}`
            }
            subtitle={`${
              regionIllustration.description ?? regionIllustration.basis
            } Different assessment — informational only; do not add to the combined bill total.`}
            totalCad={regionIllustration.amountCad ?? 0}
            lines={regionIllustration.lineItems ?? []}
            evidence={evidence}
            simpleLanguage={simpleLanguage}
            kicker="Informational"
          />
        ) : null}

        {marqueeFlags.length > 0 ? (
          <div id="watch">
            <MarqueeFlags flags={marqueeFlags} onOpen={setSelectedFlagId} />
          </div>
        ) : null}

        {data.findings.length > 0 ? (
        <section className="section" id="findings" aria-labelledby="findings-title">
          <div className="section-head">
            <p className="section-kicker">{copy.findingsKicker}</p>
            <h2 id="findings-title">{copy.findingsTitle}</h2>
            <p>{copy.findingsLead}</p>
            <p className="line-meta">
              {data.uiModelHints.flaggedDefinition ??
                'Flagged means this line needs an explanation. It does not mean the money was wasted.'}
            </p>
          </div>
          <div className="filter-row" role="group" aria-label="Finding categories">
            {FINDING_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                aria-pressed={flagTab === tab.id}
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
        ) : null}

        <section className="section" id="gaps" aria-labelledby="gaps-title">
          <div className="section-head">
            <p className="section-kicker">{copy.gapsKicker}</p>
            <h2 id="gaps-title">{copy.gapsTitle}</h2>
            <p>{copy.gapsLead}</p>
          </div>
          <ul className="flag-list">
            {gaps.map((gap) => (
              <li
                key={gap.id}
                id={gap.id}
                className="flag-item severity-watch"
                tabIndex={-1}
              >
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
            <p className="section-kicker">{copy.sourcesKicker}</p>
            <h2 id="sources-title">{copy.sourcesTitle}</h2>
            <p>{copy.sourcesLead}</p>
          </div>

          <div className="source-priority">
            <h3>{copy.startHere}</h3>
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

          <h3 className="source-all-heading">{copy.fullBibliography}</h3>
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
          {onOpenHelp ? (
            <p>
              <button
                type="button"
                className="footer-help-link"
                data-help-trigger="receipt-footer"
                onClick={onOpenHelp}
              >
                {copy.footerHelp}
              </button>
            </p>
          ) : null}
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
