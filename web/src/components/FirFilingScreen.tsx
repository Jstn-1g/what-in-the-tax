import type { FirFiling } from '../lib/firFiling'

export type FirFilingScreenProps = {
  filing: FirFiling
  onBack: () => void
}

const money = new Intl.NumberFormat('en-CA', {
  style: 'currency',
  currency: 'CAD',
  maximumFractionDigits: 0,
})

const percent = new Intl.NumberFormat('en-CA', {
  style: 'percent',
  maximumFractionDigits: 1,
})

const count = new Intl.NumberFormat('en-CA')

export default function FirFilingScreen({ filing, onBack }: FirFilingScreenProps) {
  const { totals, comparability } = filing
  const hasOther = filing.other.amountCad !== 0 || filing.other.components.length > 0

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
            total.
          </caption>
          <thead>
            <tr>
              <th scope="col">Function</th>
              <th scope="col" className="fir-filing__num">
                Amount
              </th>
              <th scope="col" className="fir-filing__num">
                {totals.sharesReported ? 'Share' : ''}
              </th>
            </tr>
          </thead>
          {filing.functions.map((fn) => (
            <tbody key={fn.code} className="fir-filing__group">
              <tr className="fir-filing__group-row">
                <th scope="rowgroup">{fn.label}</th>
                <td className="fir-filing__num">{money.format(fn.amountCad)}</td>
                <td className="fir-filing__num">
                  {totals.sharesReported && fn.shareOfTotal !== null
                    ? percent.format(fn.shareOfTotal)
                    : '—'}
                </td>
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
                  <td />
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
                <td className="fir-filing__num">—</td>
              </tr>
              <tr className="fir-filing__component-row">
                <td colSpan={3} className="fir-filing__other-note">
                  {filing.other.note}
                </td>
              </tr>
            </tbody>
          ) : null}
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              <td className="fir-filing__num">{money.format(totals.grandTotalCad)}</td>
              <td className="fir-filing__num">
                {totals.sharesReported ? percent.format(1) : '—'}
              </td>
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
