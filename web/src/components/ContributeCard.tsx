import { repoBaseUrl } from '../repoLink'
import { normalizeSupportUrl } from './SupportCard'

function StarIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        d="m12 3.6 2.5 5.2 5.7.7-4.2 3.9 1.1 5.6-5.1-2.8-5.1 2.8 1.1-5.6-4.2-3.9 5.7-.7Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * The site's primary contribution call-to-action, shown high on the chooser
 * page rather than buried in a footer. Evidence remains the headline ask;
 * the donate action rides along by owner decision, env-gated through the same
 * normalizer as SupportCard so a test-mode or non-Stripe URL can never render.
 * The wording stays inside the evidence rules - contributions are invited,
 * publication is never promised.
 */
export default function ContributeCard() {
  const repoBase = repoBaseUrl()
  const donateUrl = normalizeSupportUrl(import.meta.env.VITE_SUPPORT_ONCE_URL)
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
            href={repoBase}
            target="_blank"
            rel="noreferrer"
          >
            <StarIcon />
            Star on GitHub
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
          {donateUrl ? (
            <a
              className="button"
              href={donateUrl}
              target="_blank"
              rel="noreferrer"
            >
              Donate
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          ) : null}
          <a
            className="button"
            href={`${repoBase}/issues/new?template=wrong-number.yml`}
            target="_blank"
            rel="noreferrer"
          >
            Report a wrong number
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
