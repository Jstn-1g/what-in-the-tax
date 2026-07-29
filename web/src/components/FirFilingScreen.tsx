import type { FirFiling } from '../lib/firFiling'
import {
  PROVINCIAL_EDUCATION_RATE,
  type FirTaxationReceipt,
} from '../lib/firTaxation'

export type FirFilingScreenProps = {
  filing: FirFiling
  /** Schedule 26A, if this municipality has one. Null while loading or absent. */
  taxation?: FirTaxationReceipt | null
  /** True only when the artifact resolved as genuinely absent, never on error. */
  taxationAbsent?: boolean
  /** Every year this municipality has a published filing for, newest first. */
  availableYears: readonly number[]
  onSelectYear: (year: number) => void
  onBack: () => void
}

const money = new Intl.NumberFormat('en-CA', {
  style: 'currency',
  currency: 'CAD',
  maximumFractionDigits: 0,
})

const percent = new Intl.NumberFormat('en-CA', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

const count = new Intl.NumberFormat('en-CA')

const FALLBACK_SHARES_NOTE =
  'Percentages are withheld for this filing, because a share of its reported ' +
  "total would misread. The dollar amounts below are the filing's own and are " +
  'unaffected.'

export default function FirFilingScreen({
  filing,
  taxation = null,
  taxationAbsent = false,
  availableYears,
  onSelectYear,
  onBack,
}: FirFilingScreenProps) {
  const { totals, comparability } = filing
  const hasOther = filing.other.amountCad !== 0 || filing.other.components.length > 0
  // Two different situations both arrive here as a note, and only one of them
  // also drops the column. A filing with a negative line keeps its shares and
  // gains an explanation; a filing whose total stopped working as a denominator
  // loses the column entirely. When it does, drop the column rather than print
  // a stack of em-dashes - an empty column invites the reader to wonder what is
  // being hidden, and the caption says plainly what happened and why.
  const showShares = totals.sharesReported
  const columnCount = showShares ? 3 : 2
  // A missing column must never be unexplained. Artifacts built before the
  // builder emitted this field carry no note, so supply one rather than leave
  // the reader looking at a gap.
  const sharesNote =
    totals.sharesNote ?? (showShares ? null : FALLBACK_SHARES_NOTE)
  // Other carries a real amount, so it carries a real share. Showing an amount
  // while withholding its share is what made the visible column fall short of
  // the stated total. It can be negative where a filing records recoveries.
  const otherShare =
    showShares && totals.grandTotalCad !== 0
      ? filing.other.amountCad / totals.grandTotalCad
      : null

  return (
    <main className="fir-filing" aria-labelledby="fir-filing-heading">
      <button type="button" className="fir-filing__back" onClick={onBack}>
        ← All places
      </button>

      <header className="fir-filing__header">
        <p className="fir-filing__grade">{filing.badge}</p>
        <h1 id="fir-filing-heading">
          {filing.name} — {filing.fiscalYear} filing
        </h1>
        <p className="fir-filing__subtitle">
          What this {filing.tier} municipality reported spending, by function, in
          its own Financial Information Return. This is a filing, not a tax bill.
        </p>

        {availableYears.length > 1 ? (
          <nav className="fir-filing__years" aria-label="Filing year">
            <span className="fir-filing__years-label">Filing year</span>
            {availableYears.map((year) => (
              <a
                key={year}
                href={`?filing=${filing.assessmentCode}&year=${year}`}
                className="fir-filing__year"
                aria-current={year === filing.fiscalYear ? 'page' : undefined}
                onClick={(event) => {
                  if (
                    event.defaultPrevented ||
                    event.button !== 0 ||
                    event.metaKey ||
                    event.ctrlKey ||
                    event.shiftKey ||
                    event.altKey
                  ) {
                    return
                  }
                  event.preventDefault()
                  onSelectYear(year)
                }}
              >
                {year}
              </a>
            ))}
            <span className="fir-filing__years-note">
              Ontario municipalities file on their own schedule, so the newest
              available year differs by place. Comparing one year against
              another is a different question than this page answers.
            </span>
          </nav>
        ) : null}
      </header>

      <dl className="fir-filing__totals">
        <div>
          <dt>Total expenses</dt>
          <dd>{money.format(totals.grandTotalCad)}</dd>
        </div>
        {totals.populationFir !== null ? (
          <div>
            <dt>FIR population</dt>
            <dd>{count.format(totals.populationFir)}</dd>
          </div>
        ) : null}
        {totals.perCapitaCad !== null ? (
          <div>
            <dt>Per person</dt>
            <dd>{money.format(totals.perCapitaCad)}</dd>
          </div>
        ) : null}
      </dl>

      {taxation ? (
        <section className="fir-filing__taxation" aria-labelledby="fir-taxation-heading">
          <h2 id="fir-taxation-heading">Who levied it</h2>
          <p className="fir-filing__caption">
            Residential property taxes for {taxation.fiscalYear}, as filed on
            Schedule 26A, split between the bodies that levied them. These are
            the municipality&rsquo;s totals across every residential property,
            not one household&rsquo;s bill.
          </p>
          <table>
            <thead>
              <tr>
                <th scope="col">Levied by</th>
                <th scope="col">Amount</th>
                <th scope="col">Share</th>
              </tr>
            </thead>
            <tbody>
              {[
                {
                  key: 'local',
                  label:
                    taxation.tier === 'ST'
                      ? 'This municipality'
                      : 'This municipality (lower tier)',
                  amount: taxation.residential.municipalLowerOrSingleTierCad,
                  share: taxation.residential.shares.municipalLowerOrSingleTier,
                },
                {
                  key: 'upper',
                  label: 'County or region (upper tier)',
                  amount: taxation.residential.municipalUpperTierCad,
                  share: taxation.residential.shares.municipalUpperTier,
                },
                {
                  key: 'education',
                  label: 'Education (Province of Ontario)',
                  amount: taxation.residential.educationCad,
                  share: taxation.residential.shares.education,
                },
              ]
                // A single-tier municipality has no upper tier. A shorter bill
                // is a shorter list; a zero row would read as a levy of nothing
                // rather than as a body that does not exist here.
                .filter((row) => row.key !== 'upper' || row.amount !== 0)
                .map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.label}</th>
                    <td>{money.format(row.amount)}</td>
                    <td>{row.share === null ? '—' : percent.format(row.share)}</td>
                  </tr>
                ))}
              <tr className="fir-filing__row-total">
                <th scope="row">Total residential taxes</th>
                <td>{money.format(taxation.residential.totalTaxesCad)}</td>
                <td>{percent.format(1)}</td>
              </tr>
            </tbody>
          </table>
          <p className="fir-filing__caption">
            {taxation.tier === 'ST'
              ? 'This is a single-tier municipality, so no county or region levies a share here. That is a fact about the jurisdiction, not a missing figure. '
              : ''}
            Education is levied at Ontario&rsquo;s province-wide residential
            rate. This filing reports{' '}
            {(taxation.residential.educationRate * 100).toFixed(4)}% against the
            province&rsquo;s {(PROVINCIAL_EDUCATION_RATE * 100).toFixed(4)}% —
            checked here, in your browser, against a rate the municipality does
            not set.
          </p>
        </section>
      ) : taxationAbsent ? (
        <section className="fir-filing__taxation" aria-labelledby="fir-taxation-heading">
          <h2 id="fir-taxation-heading">Who levied it</h2>
          <p className="fir-filing__caption">
            {filing.tier.toLowerCase().includes('upper')
              ? 'An upper-tier municipality does not levy on assessment directly. Its share is apportioned through its member municipalities and already appears inside each of their receipts, so there is no separate levy to show here.'
              : 'This municipality filed no Schedule 26A taxation summary for this year, so we have nothing to show. Missing evidence stays visible instead of being estimated.'}
          </p>
        </section>
      ) : null}

      <section className="fir-filing__functions" aria-label="Spending by function">
        <table>
          <caption className="fir-filing__caption">
            Every figure below is a line the municipality filed. Components are
            shown under the function they roll up into, and the parts add to the
            total.{' '}
            {showShares
              ? 'Shares are rounded to one decimal place, so they may not read as exactly 100%; the dollar amounts are the authority.'
              : null}
            {sharesNote ? (
              <span className="fir-filing__shares-withheld">{sharesNote}</span>
            ) : null}
          </caption>
          <thead>
            <tr>
              <th scope="col">Function</th>
              <th scope="col" className="fir-filing__num">
                Amount
              </th>
              {showShares ? (
                <th scope="col" className="fir-filing__num">
                  Share
                </th>
              ) : null}
            </tr>
          </thead>
          {filing.functions.map((fn) => (
            <tbody key={fn.code} className="fir-filing__group">
              <tr className="fir-filing__group-row">
                <th scope="rowgroup">{fn.label}</th>
                <td className="fir-filing__num">{money.format(fn.amountCad)}</td>
                {showShares ? (
                  <td className="fir-filing__num">
                    {fn.shareOfTotal !== null
                      ? percent.format(fn.shareOfTotal)
                      : '—'}
                  </td>
                ) : null}
              </tr>
              {fn.components.map((component) => (
                <tr key={component.code} className="fir-filing__component-row">
                  <td>
                    <span className="fir-filing__component-label">
                      {component.label}
                    </span>
                    <span className="fir-filing__slc">{component.slc}</span>
                  </td>
                  <td className="fir-filing__num">
                    {money.format(component.amountCad)}
                  </td>
                  {showShares ? <td /> : null}
                </tr>
              ))}
            </tbody>
          ))}
          {hasOther ? (
            <tbody className="fir-filing__group">
              <tr className="fir-filing__group-row">
                <th scope="rowgroup">{filing.other.label}</th>
                <td className="fir-filing__num">
                  {money.format(filing.other.amountCad)}
                </td>
                {showShares ? (
                  <td className="fir-filing__num">
                    {otherShare !== null ? percent.format(otherShare) : '—'}
                  </td>
                ) : null}
              </tr>
              <tr className="fir-filing__component-row">
                <td colSpan={columnCount} className="fir-filing__other-note">
                  {filing.other.note}
                </td>
              </tr>
            </tbody>
          ) : null}
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              <td className="fir-filing__num">{money.format(totals.grandTotalCad)}</td>
              {showShares ? (
                <td className="fir-filing__num">{percent.format(1)}</td>
              ) : null}
            </tr>
          </tfoot>
        </table>
      </section>

      <section className="fir-filing__refusal" aria-label="Comparison limits">
        <h2>Why this cannot be compared with another municipality</h2>
        <p>{comparability.reason}.</p>
        <ul>
          {comparability.blockers.map((blocker) => (
            <li key={blocker.code}>{blocker.detail}</li>
          ))}
        </ul>
        <p className="fir-filing__refusal-note">{comparability.note}</p>
      </section>

      <section className="fir-filing__source" aria-label="Source">
        <h2>Where this came from</h2>
        <p>
          {filing.source.title} — {filing.source.schedule}. Figures are{' '}
          {filing.source.measure}.
        </p>
        <p>
          <a href={filing.source.url}>Official source file</a>{' '}
          <span className="fir-filing__hash">
            sha256 {filing.source.localZipSha256.slice(0, 16)}…
          </span>
        </p>
        <p className="fir-filing__note">{filing.source.note}</p>
        <p className="fir-filing__disclaimer">{filing.disclaimer}</p>
      </section>
    </main>
  )
}
