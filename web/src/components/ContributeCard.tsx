import { repoBaseUrl } from '../repoLink'

/**
 * The site's primary contribution call-to-action, shown high on the chooser
 * page rather than buried in a footer. Deliberately separate from
 * SupportCard: that one asks for money, this one asks for evidence, and
 * mixing the two would make both reads worse. The wording stays inside the
 * evidence rules - contributions are invited, publication is never promised.
 */
export default function ContributeCard() {
  const repoBase = repoBaseUrl()
  return (
    <aside className="contribute-card" aria-labelledby="contribute-card-heading">
      <div className="contribute-card__body">
        <p className="contribute-card__eyebrow">Open source</p>
        <h2 id="contribute-card-heading">
          Help build the receipt for every community
        </h2>
        <p>
          Every number on this site traces to a public record, and the code,
          evidence, and checks live in a public repository. Coverage grows when
          people contribute official sources &mdash; budgets, by-laws, tax-rate
          schedules &mdash; for the places they know.
        </p>
        <div className="contribute-card__actions">
          <a
            className="button button-primary"
            href={`${repoBase}/blob/main/CONTRIBUTING.md`}
            target="_blank"
            rel="noreferrer"
          >
            Contribute on GitHub
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
          <a
            className="button"
            href={`${repoBase}/issues/new?template=wrong-number.yml`}
            target="_blank"
            rel="noreferrer"
          >
            Report a wrong number
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
          <a
            className="button"
            href={repoBase}
            target="_blank"
            rel="noreferrer"
          >
            Browse the source &amp; data
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
        </div>
        <p className="contribute-card__promise">
          Every contribution passes the same evidence checks before it ships.
          Nothing is published without human review.
        </p>
      </div>
    </aside>
  )
}
