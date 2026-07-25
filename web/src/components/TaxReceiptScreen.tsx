import { useEffect, useMemo, useState } from 'react'
import { money, pct } from '../lib/format'
import { scaleReceipt } from '../lib/scaleReceipt'
import {
  loadAssessmentCad,
  loadBillCad,
  saveAssessmentCad,
  saveBillCad,
} from '../lib/storage'
import { buildReceiptSummary } from '../lib/summaryText'
import { readUrlState, writeUrlState } from '../lib/urlState'
import type {
  ForensicFinding,
  LineClassification,
  TaxpayerReceipt,
  UiFilter,
} from '../types'
import AssessmentEstimator from './AssessmentEstimator'
import BaselineCompare from './BaselineCompare'
import BillControls from './BillControls'
import FlagDetailDrawer from './FlagDetailDrawer'
import MarqueeFlags from './MarqueeFlags'
import ShareActions from './ShareActions'

const FLAG_TABS = [
  { id: 'administrativeBloat', label: 'Admin bloat' },
  { id: 'questionableCapitalProjects', label: 'Capital' },
  { id: 'unusualLineItems', label: 'Unusual items' },
] as const

type FlagTab = (typeof FLAG_TABS)[number]['id']

function useCountUp(target: number, durationMs = 1100) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    const safeTarget = Number.isFinite(target) ? Math.max(0, target) : 0
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) {
      setValue(safeTarget)
      return
    }

    let frame = 0
    let start: number | null = null
    let cancelled = false
    setValue(0)

    const tick = (now: number) => {
      if (cancelled) return
      if (start === null) start = now
      const t = Math.min(1, (now - start) / durationMs)
      const eased = 1 - (1 - t) ** 3
      setValue(safeTarget * eased)
      if (t < 1) frame = requestAnimationFrame(tick)
      else setValue(safeTarget)
    }

    frame = requestAnimationFrame(tick)
    return () => {
      cancelled = true
      cancelAnimationFrame(frame)
    }
  }, [target, durationMs])

  return value
}

function classLabel(value: LineClassification): string {
  switch (value) {
    case 'pass_through':
      return 'education'
    case 'flagged_admin':
      return 'flagged · admin'
    case 'flagged_capital':
      return 'flagged · capital'
    case 'flagged_unusual':
      return 'flagged · unusual'
    default:
      return 'necessary'
  }
}

function badgeClass(value: LineClassification): string {
  if (value === 'necessary') return 'badge badge-necessary'
  if (value === 'pass_through') return 'badge badge-pass'
  return 'badge badge-flagged'
}

export default function TaxReceiptScreen({ data }: { data: TaxpayerReceipt }) {
  const [billCad, setBillCad] = useState(() => {
    const fromUrl = readUrlState().billCad
    return fromUrl ?? loadBillCad(data.receiptTotals.billCad)
  })
  const [assessmentCad, setAssessmentCad] = useState(() => {
    const fromUrl = readUrlState().assessmentCad
    return fromUrl ?? loadAssessmentCad(data.jurisdiction.medianAssessmentUsedInTownshipDocs)
  })
  const [filter, setFilter] = useState<UiFilter>('all')
  const [flagTab, setFlagTab] = useState<FlagTab>('administrativeBloat')
  const [selectedFlagId, setSelectedFlagId] = useState<string | null>(null)
  const [highlightLineId, setHighlightLineId] = useState<string | null>(null)
  const view = useMemo(() => scaleReceipt(data, billCad), [data, billCad])
  const summaryText = useMemo(() => buildReceiptSummary(view), [view])
  const animatedTotal = useCountUp(view.receiptTotals.billCad)
  const totals = view.receiptTotals
  const segments = view.uiModelHints.heroMetric.segments

  useEffect(() => {
    saveBillCad(billCad)
  }, [billCad])

  useEffect(() => {
    saveAssessmentCad(assessmentCad)
  }, [assessmentCad])

  useEffect(() => {
    writeUrlState({ billCad, assessmentCad })
  }, [billCad, assessmentCad])

  const allFlags = useMemo(() => {
    const list: ForensicFinding[] = [
      ...view.forensicFindings.administrativeBloat,
      ...view.forensicFindings.questionableCapitalProjects,
      ...view.forensicFindings.unusualLineItems,
    ]
    return new Map(list.map((flag) => [flag.id, flag]))
  }, [view.forensicFindings])

  const marqueeFlags = useMemo(() => {
    return data.uiModelHints.marqueeFlags
      .map((id) => allFlags.get(id))
      .filter((flag): flag is ForensicFinding => Boolean(flag))
  }, [allFlags, data.uiModelHints.marqueeFlags])

  const selectedFlag = selectedFlagId ? allFlags.get(selectedFlagId) ?? null : null

  const linkedLines = useMemo(() => {
    if (!selectedFlagId) return []
    return view.receiptLineItems.filter((line) => line.flagIds.includes(selectedFlagId))
  }, [view.receiptLineItems, selectedFlagId])

  const lines = useMemo(() => {
    const sorted = [...view.receiptLineItems].sort((a, b) => b.amountCad - a.amountCad)
    if (filter === 'all') return sorted
    if (filter === 'flagged') return sorted.filter((line) => line.flagged)
    if (filter === 'pass_through') {
      return sorted.filter((line) => line.classification === 'pass_through')
    }
    return sorted.filter((line) => line.necessary && line.classification !== 'pass_through')
  }, [view.receiptLineItems, filter])

  useEffect(() => {
    if (!highlightLineId) return
    const node = document.getElementById(`line-${highlightLineId}`)
    node?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const timer = window.setTimeout(() => setHighlightLineId(null), 1800)
    return () => window.clearTimeout(timer)
  }, [highlightLineId])

  const necessaryCorePct =
    (totals.necessaryExcludingPassThroughCad / totals.billCad) * 100
  const educationPct = (totals.passThroughCad / totals.billCad) * 100
  const flaggedPct = totals.flaggedShareOfBill * 100

  const openFlag = (flagId: string) => setSelectedFlagId(flagId)
  const openFirstFlagForLine = (flagIds: string[]) => {
    if (flagIds[0]) setSelectedFlagId(flagIds[0])
  }

  return (
    <div className="page">
      <header className="hero">
        <div className="hero-atmosphere" aria-hidden="true" />
        <div className="hero-inner">
          <p className="brand">Taxpayer Receipt</p>
          <h1>Your {money(billCad)} property tax bill, itemized</h1>
          <p className="hero-support">
            North Dumfries + Region of Waterloo · 2026 budget model
          </p>
          <div className="hero-cta-row">
            <a className="cta" href="#bill-controls">
              Set your bill
            </a>
            <a className="cta cta-ghost" href="#findings">
              Jump to flags
            </a>
          </div>
          <p className="hero-amount" aria-live="polite">
            <span className="hero-amount-label">{view.uiModelHints.heroMetric.label}</span>
            <span className="hero-amount-value">{money(animatedTotal)}</span>
          </p>
        </div>
      </header>

      <main>
        <div id="bill-controls">
          <BillControls billCad={billCad} onChange={setBillCad} />
        </div>

        <AssessmentEstimator
          assessment={assessmentCad}
          onAssessmentChange={setAssessmentCad}
          rates={data.methodology.jurisdictionSplit}
          onApplyBill={setBillCad}
        />

        <BaselineCompare
          baseBillCad={data.receiptTotals.billCad}
          currentBillCad={billCad}
          baseFlaggedCad={data.receiptTotals.flaggedCad}
          currentFlaggedCad={totals.flaggedCad}
          onReset={() => setBillCad(data.receiptTotals.billCad)}
        />

        <section className="section mix-section" aria-labelledby="mix-title">
          <div className="section-head">
            <h2 id="mix-title">Necessary vs flagged</h2>
            <p>{totals.uiSummary.headline}</p>
          </div>
          <ShareActions summaryText={summaryText} view={view} />
          <div className="mix-bar" role="img" aria-label="Bill classification mix">
            <span className="mix-seg necessary" style={{ width: `${necessaryCorePct}%` }} />
            <span className="mix-seg pass" style={{ width: `${educationPct}%` }} />
            <span className="mix-seg flagged" style={{ width: `${flaggedPct}%` }} />
          </div>
          <ul className="mix-legend">
            {segments.map((segment) => (
              <li key={segment.key}>
                <span className={`swatch ${segment.colorToken}`} />
                {segment.label} {money(segment.valueCad)}
              </li>
            ))}
          </ul>
        </section>

        <MarqueeFlags flags={marqueeFlags} onOpen={openFlag} />

        <section className="section" aria-labelledby="where-title">
          <div className="section-head">
            <h2 id="where-title">Where the bill goes</h2>
            <p>Township, Region (with police), and provincial education shares.</p>
          </div>
          <ul className="jurisdiction-list">
            {view.jurisdictionBreakdown.map((slice) => (
              <li key={slice.id}>
                <div className="jurisdiction-row">
                  <div>
                    <h3>{slice.label}</h3>
                    {slice.children ? (
                      <ul className="child-list">
                        {slice.children.map((child) => (
                          <li key={child.id}>
                            {child.label}: {money(child.amountCad)}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                  <div className="jurisdiction-figures">
                    <strong>{money(slice.amountCad)}</strong>
                    <span>{pct(slice.shareOfBill * 100)}</span>
                  </div>
                </div>
                <div className="thin-track">
                  <span style={{ width: `${slice.shareOfBill * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="section receipt-section" id="itemized" aria-labelledby="itemized-title">
          <div className="section-head">
            <h2 id="itemized-title">Itemized receipt</h2>
            <p>Every modeled dollar, sorted by size. Tap a flagged line for details.</p>
          </div>

          <div className="filter-row" role="group" aria-label="Filter by classification">
            {(
              [
                ['all', 'all'],
                ['necessary', 'necessary'],
                ['flagged', 'flagged'],
                ['pass_through', 'education'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={filter === key ? 'filter active' : 'filter'}
                onClick={() => setFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="receipt-sheet">
            <div className="perforation" aria-hidden="true" />
            <ol className="receipt-lines">
              {lines.map((line, index) => {
                const interactive = line.flagIds.length > 0
                return (
                  <li
                    key={line.id}
                    id={`line-${line.id}`}
                    className={[
                      'receipt-line',
                      line.flagged ? 'flagged' : line.classification,
                      interactive ? 'interactive' : '',
                      highlightLineId === line.id ? 'pulse' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    style={{ animationDelay: `${index * 35}ms` }}
                  >
                    {interactive ? (
                      <button
                        type="button"
                        className="line-button"
                        onClick={() => openFirstFlagForLine(line.flagIds)}
                      >
                        <LineBody
                          label={line.label}
                          category={line.category}
                          tier={line.tier}
                          classification={line.classification}
                          amountCad={line.amountCad}
                          billCad={totals.billCad}
                        />
                      </button>
                    ) : (
                      <LineBody
                        label={line.label}
                        category={line.category}
                        tier={line.tier}
                        classification={line.classification}
                        amountCad={line.amountCad}
                        billCad={totals.billCad}
                      />
                    )}
                  </li>
                )
              })}
            </ol>
            <div className="receipt-total">
              <span>Total</span>
              <strong>{money(totals.billCad)}</strong>
            </div>
          </div>
        </section>

        <section className="section" id="findings" aria-labelledby="findings-title">
          <div className="section-head">
            <h2 id="findings-title">Forensic findings</h2>
            <p>
              Population basis{' '}
              {view.budgetSnapshots.northDumfries2026Draft.perCapita.populationBasis.toLocaleString()}
              {' · '}
              corporate services ~
              {money(view.budgetSnapshots.northDumfries2026Draft.perCapita.corporateServicesPerCapita)}
              /capita
              {' · '}
              twin-pad project ~
              {money(view.budgetSnapshots.northDumfries2026Draft.perCapita.netZeroArenaProjectPerCapita)}
              /capita
            </p>
          </div>

          <div className="filter-row" role="tablist" aria-label="Finding categories">
            {FLAG_TABS.map((tab) => (
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
            {view.forensicFindings[flagTab].map((flag) => (
              <li key={flag.id} className={`flag-item severity-${flag.opportunitySeverity}`}>
                <button type="button" className="flag-button" onClick={() => openFlag(flag.id)}>
                  <div className="flag-top">
                    <div>
                      <p className="flag-id">{flag.id}</p>
                      <h3>{flag.title}</h3>
                    </div>
                    <span className="flag-impact">{money(flag.estimatedBillImpactCad)}</span>
                  </div>
                  <p>{flag.evidence}</p>
                  <span className="flag-cta">View linked receipt lines</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <footer className="footer">
          <p>{view.purpose}</p>
          <p>Generated {view.generatedAt}</p>
        </footer>
      </main>

      {selectedFlag ? (
        <FlagDetailDrawer
          flag={selectedFlag}
          linkedLines={linkedLines}
          onClose={() => setSelectedFlagId(null)}
          onSelectLine={(lineId) => {
            setSelectedFlagId(null)
            setFilter('all')
            setHighlightLineId(lineId)
          }}
        />
      ) : null}
    </div>
  )
}

function LineBody({
  label,
  category,
  tier,
  classification,
  amountCad,
  billCad,
}: {
  label: string
  category: string
  tier: string
  classification: LineClassification
  amountCad: number
  billCad: number
}) {
  return (
    <div className="line-main">
      <div>
        <p className="line-service">{label}</p>
        <p className="line-meta">
          {category} · {tier}
        </p>
      </div>
      <div className="line-right">
        <span className={badgeClass(classification)}>{classLabel(classification)}</span>
        <strong>{money(amountCad)}</strong>
        <span>{pct((amountCad / billCad) * 100)}</span>
      </div>
    </div>
  )
}
