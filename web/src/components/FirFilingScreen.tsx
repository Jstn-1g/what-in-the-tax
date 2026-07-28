import type { FirFiling } from '../lib/firFiling'

export type FirFilingScreenProps = {
  filing: FirFiling
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
