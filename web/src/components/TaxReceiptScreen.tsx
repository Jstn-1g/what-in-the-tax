import { useMemo, useState, type ReactNode } from 'react'
import { money, pct } from '../lib/format'
import { repoBaseUrl } from '../repoLink'
import RepoLinks from './RepoLinks'
import {
  buildEvidenceIndex,
  citationLabel,
  resolveCitation,
  type CitationAudit,
  type EvidenceIndex,
  type ResolvedCitation,
} from '../lib/evidenceLookup'
import {
  simplifyBucketLabel,
  uiCopy,
} from '../lib/eli5'
import type {
  Derived,
  Fact,
  Gap,
  ReceiptLineItem,
  Source,
  TaxpayerReceipt,
} from '../types'
import FlagDetailDrawer from './FlagDetailDrawer'
import HeroBriefing from './HeroBriefing'
import { buildHeroBriefing } from '../lib/heroBriefing'
import { declaredBillFor } from '../lib/taxingBodies'

function isFiniteAmount(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function availableMoney(value: unknown): string {
  return isFiniteAmount(value) ? money(value) : 'Unavailable'
}

function hasPublishedBinding(citation: ResolvedCitation): boolean {
  if (citation.kind === 'FACT') return Boolean(citation.source || citation.href)
  if (citation.kind !== 'DERIVED' || !citation.inputs?.length) return false
  return citation.inputs.some(hasPublishedBinding)
}

function hasFullyVerifiedBinding(citation: ResolvedCitation): boolean {
  if (citation.kind === 'FACT') {
    return Boolean(citation.source || citation.href) && citation.matchTier === 'page-verified'
  }
  if (citation.kind !== 'DERIVED' || !citation.inputs?.length) return false
  return citation.inputs.every(hasFullyVerifiedBinding)
}

function lineTone(line: ReceiptLineItem, evidence: EvidenceIndex) {
  if (line.classification === 'reconciling_item') {
    return {
      row: 'pass_through',
      badge: 'badge-pass',
      label: 'Rounding adjustment',
    }
  }
  if (line.evidenceStatus === 'GAP') {
    return { row: 'flagged', badge: 'badge-flagged', label: 'Evidence missing' }
  }
  const citation = line.sourceFactId
    ? resolveCitation(evidence, line.sourceFactId)
    : null
  const hasCitationBinding = citation != null && hasPublishedBinding(citation)
  const hasVerifiedBinding = citation != null && hasFullyVerifiedBinding(citation)
  if (line.evidenceStatus === 'FACT') {
    return hasVerifiedBinding
      ? {
          row: 'necessary',
          badge: 'badge-fact',
          label: 'From a verified published source',
        }
      : {
          row: 'flagged',
          badge: 'badge-flagged',
          label: hasCitationBinding
            ? 'Source check incomplete'
            : 'Primary source binding unavailable',
        }
  }
  if (line.evidenceStatus === 'DERIVED') {
    return hasVerifiedBinding
      ? {
          row: 'necessary',
          badge: 'badge-derived',
          label: 'Calculated from verified published sources',
        }
      : {
          row: 'flagged',
          badge: 'badge-flagged',
          label: hasCitationBinding
            ? 'Calculation source check incomplete'
            : 'Calculation source binding unavailable',
        }
  }
  return { row: 'necessary', badge: 'badge-necessary', label: 'Review note' }
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
      {citation.source ? citation.source.title : 'Open source'}
      {pageLabel}
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  )
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
  totalCad: number | null
  lines: ReceiptLineItem[]
  evidence: EvidenceIndex
  simpleLanguage?: boolean
  kicker?: string
}) {
  const sorted = [...lines].sort((a, b) => {
    const left = isFiniteAmount(a.amountCad) ? Math.abs(a.amountCad) : -1
    const right = isFiniteAmount(b.amountCad) ? Math.abs(b.amountCad) : -1
    return right - left
  })
  const copy = uiCopy(simpleLanguage)
  const barBase = isFiniteAmount(totalCad) && totalCad > 0 ? totalCad : null
  return (
    <section className="section receipt-section" id={id} aria-labelledby={`${id}-title`}>
      <div className="section-head">
        {kicker ? <p className="section-kicker">{kicker}</p> : null}
        <h2 id={`${id}-title`}>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <div className="receipt-sheet">
        <ol className="receipt-lines">
          {sorted.map((line, index) => {
            const tone = lineTone(line, evidence)
            const status = tone.label
            const share =
              barBase != null && isFiniteAmount(line.amountCad) && line.amountCad > 0
                ? line.amountCad / barBase
                : null
            const showBar =
              share != null &&
              share > 0 &&
              line.classification !== 'reconciling_item' &&
              line.classification !== 'disclosure_subline'
            const nonQuantitative =
              isFiniteAmount(line.amountCad) &&
              line.amountCad <= 0 &&
              line.classification !== 'reconciling_item'
            const detailParts = [
              showBar && share != null
                ? `${pct(share * 100)} of this share`
                : null,
              nonQuantitative
                ? 'Not represented in the proportional bar'
                : null,
              line.note ?? null,
            ].filter((part): part is string => Boolean(part))
            return (
              <li
                key={line.id}
                className={['receipt-line', tone.row].join(' ')}
                style={{ animationDelay: `${index * 25}ms` }}
              >
                <div className="line-main">
                  <p className="line-service">{line.label}</p>
                  <strong className="line-amount">
                    {availableMoney(line.amountCad)}
                  </strong>
                  <div className="line-details">
                    {detailParts.length > 0 ? (
                      <p className="line-meta">{detailParts.join(' · ')}</p>
                    ) : null}
                    <SourceAnchor evidence={evidence} factId={line.sourceFactId} />
                  </div>
                  <span className={`badge line-status ${tone.badge}`}>
                    {status}
                  </span>
                </div>
                {showBar && share != null ? (
                  <div
                    className="line-share-track"
                    role="img"
                    aria-label={`${line.label}: ${pct(share * 100)} of ${title}`}
                  >
                    <span
                      className="line-share-fill"
                      style={{
                        width: `${Math.min(Math.max(share * 100, 0), 100)}%`,
                        minWidth: 0,
                      }}
                    />
                  </div>
                ) : null}
              </li>
            )
          })}
        </ol>
        <div className="receipt-total">
          <span>{copy.publishedTotal}</span>
          <strong>{availableMoney(totalCad)}</strong>
        </div>
      </div>
    </section>
  )
}

export type FirHistoryState = 'loading' | 'ready' | 'unavailable'

export function receiptYearContext(
  receiptYear: number,
  firYears: readonly number[] | undefined,
  firHistoryState: FirHistoryState,
): string {
  const current = `current tax evidence ${receiptYear}`
  if (firHistoryState === 'loading') {
    return `${current} · loading earlier FIR context.`
  }
  if (firHistoryState === 'unavailable' || firYears === undefined) {
    return `${current} · earlier FIR context is temporarily unavailable.`
  }
  if (firYears.length === 0) {
    return `${current} · no 2023–2025 FIR history available. FIR years stay separate from this receipt calculation.`
  }
  return `${current} · FIR history ${firYears.join(', ')}. FIR years stay separate from this receipt calculation.`
}

export default function TaxReceiptScreen({
  data,
  firYears,
  firHistoryState = 'loading',
  gaps,
  evidenceRules,
  sources,
  facts,
  derived,
  citationAudit,
  bannerText,
  appHeader,
  onOpenHelp,
  simpleLanguage = false,
}: {
  data: TaxpayerReceipt
  firYears?: readonly number[]
  firHistoryState?: FirHistoryState
  gaps: Gap[]
  evidenceRules: string[]
  sources: Source[]
  facts: Fact[]
  derived: Derived[]
  citationAudit?: CitationAudit | null
  bannerText?: string
  appHeader?: ReactNode
  onOpenHelp?: () => void
  simpleLanguage?: boolean
}) {
  const profile = data.profiles.supportedAverageHousehold
  const combined = profile.combinedAtAssessment
  const [selectedFlagId, setSelectedFlagId] = useState<string | null>(null)

  const evidence = useMemo(
    () => buildEvidenceIndex(sources, facts, derived, citationAudit),
    [sources, facts, derived, citationAudit],
  )

  const findingsById = useMemo(() => {
    return new Map(data.findings.map((finding) => [finding.id, finding]))
  }, [data.findings])

  const gapsById = useMemo(() => new Map(gaps.map((gap) => [gap.id, gap])), [gaps])

  const heroBriefing = useMemo(
    () =>
      buildHeroBriefing(data, gaps, citationAudit, {
        municipalBucketLabel:
          data.uiModelHints.municipalBucketLabel ?? profile.township.uiLabel,
      }),
    [data, gaps, citationAudit, profile.township.uiLabel],
  )

  const visibleFindings = useMemo(
    () => data.findings.filter((finding) => !finding.belowMateriality),
    [data.findings],
  )

  const selectedFlag = selectedFlagId ? findingsById.get(selectedFlagId) ?? null : null
  const townshipLines = profile.township.lineItems ?? []
  const regionLines = profile.region.lineItems ?? []

  // The bill as its builder declared it, or null for a pack not yet migrated.
  // Only the questions that are *about roles* are answered from here; the
  // amounts and line items still come from the buckets, because the declared
  // bodies do not carry line items and their amounts measure something else.
  const bill = useMemo(
    () => declaredBillFor(profile, data.jurisdiction?.slug),
    [profile, data.jurisdiction?.slug],
  )
  const declaredUpperTier =
    bill?.bodies.find((body) => body.role === 'upper-tier') ?? null
  const upperTierNotApplicable =
    bill?.inapplicable.find((entry) => entry.role === 'upper-tier') ?? null

  // With a declared bill, "is there an upper tier" is a stated fact about the
  // jurisdiction. Without one it has to be inferred from whether the bucket
  // happens to carry a usable amount - which is exactly the inference the
  // declaration exists to retire, and which cannot tell a single-tier
  // municipality apart from a two-tier one whose evidence is missing.
  const hasRegionBucket = bill
    ? declaredUpperTier !== null
    : isFiniteAmount(profile.region.amountCad) &&
      (regionLines.length > 0 || profile.region.evidenceStatus !== 'GAP')
  const regionIllustration = profile.regionIllustrationAt354500
  const assessmentCad =
    combined?.assessmentCad ?? profile.township.assessmentCad ?? null
  const receiptTotalCad = combined?.totalCad ?? profile.combinedTotalCad
  const municipalAmountCad = profile.township.amountCad
  const displayName = data.jurisdiction?.displayName?.trim() || null
  const receiptYear = data.fiscalYear.toString()
  const rawMunicipalLabel =
    data.uiModelHints.municipalBucketLabel?.trim() ||
    profile.township.uiLabel?.trim() ||
    null
  const municipalLabel = rawMunicipalLabel
    ? simplifyBucketLabel(rawMunicipalLabel, simpleLanguage)
    : 'Municipal identity unavailable'
  const regionLabel = simplifyBucketLabel(
    // A declared body names itself. The uiModelHints fallback is how a pack
    // that has not declared one still gets a heading - and it is also how
    // "Upper-tier (n/a)" survived into a single-tier receipt, so a declared
    // body has to win.
    declaredUpperTier?.uiLabel ??
      declaredUpperTier?.label ??
      data.uiModelHints.regionBucketLabel ??
      profile.region.uiLabel ??
      'Other governing-body portion',
    simpleLanguage,
  )
  const municipalShareName = municipalLabel
    .replace(/ portion$/i, '')
    .replace(/'s share$/i, '')
  const regionShareName = regionLabel
    .replace(/ portion$/i, '')
    .replace(/'s share$/i, '')

  const citedSources = useMemo(() => {
    const candidateFactIds = [
      ...(combined?.components ?? []).map((component) => component.sourceFactId),
      profile.township.sourceFactId,
      ...townshipLines.map((line) => line.sourceFactId),
      profile.region.sourceFactId,
      ...regionLines.map((line) => line.sourceFactId),
    ]
    const sourceIds = new Set(
      candidateFactIds
        .filter((id): id is string => Boolean(id))
        .map((id) => resolveCitation(evidence, id).source?.id)
        .filter((id): id is string => Boolean(id)),
    )
    return sources.filter((source) => sourceIds.has(source.id))
  }, [
    combined?.components,
    evidence,
    profile.region.sourceFactId,
    profile.township.sourceFactId,
    regionLines,
    sources,
    townshipLines,
  ])

  const unavailableFields = [
    !displayName ? 'Municipal identity' : null,
    !rawMunicipalLabel ? 'Municipal component identity' : null,
    !isFiniteAmount(assessmentCad) || assessmentCad <= 0
      ? 'Reference assessment'
      : null,
    !isFiniteAmount(receiptTotalCad) || receiptTotalCad <= 0
      ? 'Estimated bill total'
      : null,
    !isFiniteAmount(municipalAmountCad) || municipalAmountCad < 0
      ? 'Municipal amount'
      : null,
  ].filter((field): field is string => field != null)

  if (unavailableFields.length > 0) {
    return (
      <div className="page">
        <a className="skip-link" href="#main-content">
          Skip to receipt availability
        </a>
        {appHeader}
        <section
          className="hero"
          id="receipt-hero"
          tabIndex={-1}
          aria-labelledby="receipt-unavailable-title"
        >
          <div className="hero-inner">
            <p className="hero-context">
              <span className="hero-place">
                {displayName ?? 'Municipal identity unavailable'}
              </span>
            </p>
            <h1 id="receipt-unavailable-title">Receipt unavailable</h1>
            <p className="hero-support">
              We will not display a receipt when a required identity or amount
              is missing.
            </p>
          </div>
        </section>
        <main id="main-content" tabIndex={-1}>
          <section
            className="section"
            aria-labelledby="receipt-unavailable-fields-title"
          >
            <div className="section-head">
              <h2 id="receipt-unavailable-fields-title">Evidence update required</h2>
              <p>The following required fields are unavailable:</p>
            </div>
            <ul className="child-list">
              {unavailableFields.map((field) => (
                <li key={field}>{field}: Unavailable</li>
              ))}
            </ul>
          </section>
        </main>
      </div>
    )
  }

  // The fail-closed branch above narrows these values for the complete receipt.
  const availableAssessmentCad = assessmentCad as number
  const availableReceiptTotalCad = receiptTotalCad as number
  const availableMunicipalAmountCad = municipalAmountCad as number
  const availableDisplayName = displayName as string

  return (
    <div className="page">
      <a className="skip-link" href="#main-content">
        Skip to sample receipt
      </a>
      {appHeader}
      <section
        className="hero"
        id="receipt-hero"
        tabIndex={-1}
        aria-labelledby="receipt-title"
      >
        <div className="hero-inner">
          <div className="hero-heading-row">
            <div className="hero-copy-block">
              <p className="hero-context">
                <span className="hero-place">{availableDisplayName}</span>
                {receiptYear ? (
                  <>
                    <span className="hero-context-sep" aria-hidden="true">
                      ·
                    </span>
                    <span className="hero-year">
                      {receiptYear} current evidence
                    </span>
                  </>
                ) : null}
              </p>
              <h1 id="receipt-title">
                Where a sample property-tax bill for {availableDisplayName} goes
              </h1>
              <p className="hero-support">
                Based on a {money(availableAssessmentCad)} reference assessment. This is an
                illustration, not your bill.
              </p>
              <p className="hero-scenario-note">
                <strong>Reference used:</strong> {profile.description}
              </p>
              <p className="hero-year-context">
                <strong>Year context:</strong>{' '}
                {receiptYearContext(
                  data.fiscalYear,
                  firYears,
                  firHistoryState,
                )}
              </p>
            </div>
            <p className="hero-amount">
              <span className="hero-amount-label">
                Estimated {receiptYear ? `${receiptYear} ` : ''}property-tax bill
              </span>
              <span className="hero-amount-value">
                {money(availableReceiptTotalCad)}
              </span>
            </p>
          </div>
          {heroBriefing ? (
            <HeroBriefing
              model={heroBriefing}
              onOpenHelp={onOpenHelp}
              simpleLanguage={simpleLanguage}
            />
          ) : null}
          <div className="hero-status-row">
            <p>
              {bannerText ??
                'Draft preview — source checks are not currently available.'}
            </p>
            <a className="button button-primary" href="#bill">
              See the full breakdown
              <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                <path
                  d="m6 3 5 5-5 5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </a>
          </div>
        </div>
      </section>

      <nav className="page-nav" aria-label="On this page">
        <a className="page-nav-overview" href="#receipt-hero">
          Overview
        </a>
        <a href="#bill">Bill breakdown</a>
        <a href="#gaps">Evidence</a>
        <a href="#sources">Sources</a>
      </nav>

      <main id="main-content" tabIndex={-1}>
        <section className="section bill-section" id="bill" aria-labelledby="bill-title">
          <div className="section-head">
            <h2 id="bill-title">How the bill is built</h2>
            <p>
              The same {money(availableAssessmentCad)} assessment is applied to each
              published {receiptYear ?? ''} rate.
            </p>
          </div>

          <ol className="bill-stack">
            {(combined?.components ?? []).map((component, index) => {
              const billTotal = availableReceiptTotalCad
              const shareOfBill =
                isFiniteAmount(component.amountCad) && component.amountCad > 0
                  ? component.amountCad / billTotal
                  : null
              const shareModel = heroBriefing?.shares[index]
              const tone = shareModel?.tone ?? 'unclassified'
              const quantitative = isFiniteAmount(component.amountCad) && component.amountCad >= 0
              return (
                <li key={component.label} className="bill-stack-row">
                  <div className="bill-stack-body">
                    <div className="bill-stack-copy">
                      <h3>{component.label || 'Component identity unavailable'}</h3>
                      <p className="line-meta">
                        {isFiniteAmount(component.rate)
                          ? `Rate ${component.rate.toFixed(8)}`
                          : 'Rate unavailable'}{' '}
                        × {money(availableAssessmentCad)}
                        {shareOfBill != null
                          ? ` · ${pct(shareOfBill * 100)} of bill`
                          : ' · Not represented in the proportional bar'}
                      </p>
                      <SourceAnchor evidence={evidence} factId={component.sourceFactId} />
                    </div>
                    <strong className="bill-stack-amount">
                      {availableMoney(component.amountCad)}
                    </strong>
                  </div>
                  {quantitative && shareOfBill != null && shareOfBill > 0 ? (
                    <div
                      className="bill-stack-track"
                      role="img"
                      aria-label={`${component.label}: ${pct(
                        shareOfBill * 100,
                      )} of combined bill`}
                    >
                      <span
                        className={`bill-stack-fill tone-${tone}`}
                        style={{
                          width: `${Math.min(
                            Math.max(shareOfBill * 100, 0),
                            100,
                          )}%`,
                          minWidth: 0,
                        }}
                      />
                    </div>
                  ) : null}
                </li>
              )
            })}
          </ol>

          <div className="bill-stack-total">
            <span>Estimated total</span>
            <strong>{money(availableReceiptTotalCad)}</strong>
          </div>

          <p className="bill-note">{profile.combinedTotalNote}</p>

          <details className="fold">
            <summary>How this calculation works</summary>
            <ul className="child-list">
              <li>
                {combined?.basis ??
                  (bill
                    ? // Name the bodies this bill actually has. The two fixed
                      // sentences below assume an education body exists, which
                      // is true in Ontario and not true everywhere.
                      `${bill.bodies
                        .map((body) => body.uiLabel ?? body.label)
                        .join(' + ')} at one assessment.`
                    : hasRegionBucket
                      ? `${municipalLabel} + ${regionLabel} + education at one assessment.`
                      : `${municipalLabel} + education at one assessment.`)}
              </li>
              {profile.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
              <li>
                {municipalLabel} @ {money(availableAssessmentCad)}:{' '}
                {money(availableMunicipalAmountCad)}
              </li>
              {hasRegionBucket ? (
                <li>
                  {regionLabel} @{' '}
                  {availableMoney(
                    profile.region.assessmentCad ?? availableAssessmentCad,
                  )}
                  : {availableMoney(profile.region.amountCad)} — already included in the combined total
                  above at this household assessment
                </li>
              ) : (
                // A declared absence states why the tier does not exist here.
                // The bucket note is a fallback for packs that have not
                // declared one, and it describes missing evidence rather than
                // a fact about the jurisdiction - the two must not read alike.
                <li>
                  {[
                    upperTierNotApplicable?.reason ??
                      profile.region.note ??
                      profile.region.basis,
                    // The declaration says the tier does not exist; the bucket
                    // note says where those services are actually paid for.
                    // Different questions, so keep both rather than letting the
                    // new field quietly delete the older answer.
                    upperTierNotApplicable ? profile.region.note : null,
                  ]
                    .filter(Boolean)
                    .join(' ')}
                </li>
              )}
              {regionIllustration ? (
                <li>
                  Region illustration @{' '}
                  {availableMoney(regionIllustration.assessmentCad)}:{' '}
                  {availableMoney(regionIllustration.amountCad)} — different assessment base; do not
                  add to the combined total above
                </li>
              ) : null}
              <li>{data.profiles.hypothetical5000.message}</li>
            </ul>
          </details>
        </section>

        <LineList
          id="township"
          title={`What the ${municipalShareName} portion supports`}
          subtitle={`A proportional model based on published totals. ${profile.township.basis}`}
          totalCad={availableMunicipalAmountCad}
          lines={townshipLines}
          evidence={evidence}
          simpleLanguage={simpleLanguage}
        />

        {hasRegionBucket ? (
          <LineList
            id="region"
            title={`What the ${regionShareName} portion supports`}
            subtitle={`A proportional model based on published totals. ${profile.region.basis}`}
            totalCad={profile.region.amountCad}
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
              `Region schedule @ ${availableMoney(regionIllustration.assessmentCad)}`
            }
            subtitle={`${
              regionIllustration.description ?? regionIllustration.basis
            } Different assessment — informational only; do not add to the combined bill total.`}
            totalCad={regionIllustration.amountCad}
            lines={regionIllustration.lineItems ?? []}
            evidence={evidence}
            simpleLanguage={simpleLanguage}
            kicker="Informational"
          />
        ) : null}

        {visibleFindings.length > 0 ? (
        <section className="section" id="findings" aria-labelledby="findings-title">
          <div className="section-head">
            <h2 id="findings-title">Review notes</h2>
            <p>
              Questions raised by the published record. These are review notes,
              not conclusions about waste or wrongdoing.
            </p>
          </div>
          <ul className="flag-list">
            {visibleFindings.map((flag) => {
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
                    <span className="flag-cta">Review sources</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
        ) : null}

        <section className="section" id="gaps" aria-labelledby="gaps-title">
          <div className="section-head">
            <h2 id="gaps-title">Open evidence items</h2>
            <p>What is still missing, why it matters, and what evidence is needed.</p>
          </div>
          {gaps.length > 0 ? (
            <ul className="gap-list">
              {gaps.map((gap) => (
                <li key={gap.id}>
                  <details id={gap.id} className="gap-item">
                    <summary>
                      <span>
                        <strong>{gap.title}</strong>
                        <small>Missing information stays visible instead of being guessed.</small>
                      </span>
                      <span className="gap-state">Open</span>
                    </summary>
                    <div className="gap-detail">
                      <p>{gap.detail}</p>
                      {gap.neededEvidence.length > 0 ? (
                        <p>
                          <strong>Evidence needed:</strong>{' '}
                          {gap.neededEvidence.join(' · ')}
                        </p>
                      ) : null}
                      <p className="technical-id">Evidence reference: {gap.id}</p>
                    </div>
                  </details>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">No open evidence items are listed for this receipt.</p>
          )}
          <details className="fold">
            <summary>Read the evidence policy</summary>
            <ul className="child-list">
              {evidenceRules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          </details>
        </section>

        <section className="section sources-section" id="sources" aria-labelledby="sources-title">
          <div className="section-head">
            <h2 id="sources-title">Official source documents</h2>
            <p>
              Public budgets, tax-rate schedules, and by-laws used for this sample receipt.
            </p>
          </div>

          <div className="source-priority">
            <h3>Start with these documents</h3>
            {citedSources.length > 0 ? (
              <ul className="source-list">
                {citedSources.map((source) => (
                  <li key={source.id}>
                    <a className="source-card" href={source.url} target="_blank" rel="noreferrer">
                      <span className="source-auth">{source.authority ?? 'source'}</span>
                      <strong>{source.title}</strong>
                      <span className="source-open">
                        Open document
                        <span className="visually-hidden"> in a new tab</span>
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-state">
                No primary source binding is available for this receipt.
              </p>
            )}
          </div>

          <h3 className="source-all-heading">All source documents</h3>
          <ul className="source-list source-list-compact">
            {sources.map((source) => (
              <li key={source.id}>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.title}
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </a>
                {source.asOf ? <span className="line-meta"> · as of {source.asOf}</span> : null}
                {source.note ? <p className="line-meta">{source.note}</p> : null}
              </li>
            ))}
          </ul>
        </section>

        <aside className="contribute-callout">
          <p>
            <strong>Spot a number that looks wrong?</strong> This receipt is
            open source. <a
              href={`${repoBaseUrl()}/issues/new?template=wrong-number.yml`}
              target="_blank"
              rel="noreferrer"
            >
              Report it
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>{' '}
            and it gets checked against the record &mdash; or{' '}
            <a
              href={`${repoBaseUrl()}/blob/main/CONTRIBUTING.md`}
              target="_blank"
              rel="noreferrer"
            >
              contribute evidence
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>{' '}
            for a community you know.
          </p>
        </aside>

        <footer className="footer">
          <p>
            Independent public-information project. Not affiliated with any
            government. Not an official bill, formal audit, or tax advice.
            Open source: every number on this receipt, and the checks behind
            it, can be inspected and re-run from the repository.
          </p>
          <p className="technical-id">
            {data.status} · {data.evidencePolicyRef}
          </p>
          {onOpenHelp ? (
            <p>
              <button
                type="button"
                className="footer-help-link"
                data-help-trigger="receipt-footer"
                onClick={onOpenHelp}
              >
                How What in the Tax? works
              </button>
            </p>
          ) : null}
          <nav className="product-footer__links" aria-label="Project links">
            <a href="#help/about">About this site</a>
            <a href={`${import.meta.env.BASE_URL}privacy.txt`}>Privacy</a>
            <RepoLinks />
          </nav>
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
