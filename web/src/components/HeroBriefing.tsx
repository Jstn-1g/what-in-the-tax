import { money, pct } from '../lib/format'
import type { HeroBriefingModel } from '../lib/heroBriefing'

function statusCopy(model: HeroBriefingModel) {
  return [
    {
      id: 'review',
      value:
        model.reviewNoteCount === 0
          ? 'No questions flagged'
          : `${model.reviewNoteCount} ${
              model.reviewNoteCount === 1 ? 'question' : 'questions'
            } flagged`,
      detail:
        model.reviewNoteCount === 0
          ? 'No published review notes are attached to this receipt.'
          : 'Questions raised by the record—not conclusions about waste or wrongdoing.',
      href: model.reviewNoteCount > 0 ? '#findings' : undefined,
      tone: model.reviewNoteCount > 0 ? 'review' : 'clear',
    },
    {
      id: 'gaps',
      value:
        model.gapCount === 0
          ? 'No open evidence gaps'
          : `${model.gapCount} open evidence ${
              model.gapCount === 1 ? 'gap' : 'gaps'
            }`,
      detail:
        model.gapCount === 0
          ? 'No open evidence items are listed.'
          : 'Missing information stays visible instead of being guessed.',
      href: '#gaps',
      tone: model.gapCount > 0 ? 'incomplete' : 'clear',
    },
    {
      id: 'citations',
      value:
        model.hardCitationFailureCount > 0
          ? `${model.hardCitationFailureCount} source ${
              model.hardCitationFailureCount === 1 ? 'check' : 'checks'
            } failed`
          : model.weakCitationCount > 0
            ? `${model.weakCitationCount} source ${
                model.weakCitationCount === 1 ? 'check' : 'checks'
              } incomplete`
            : 'Source checks complete',
      detail:
        model.hardCitationFailureCount > 0
          ? 'At least one displayed citation does not support its claim.'
          : model.weakCitationCount > 0
            ? 'Some figures appear in a source without a confirmed label-to-value match.'
            : 'No weak or failed citation matches are listed.',
      href: '#sources',
      tone:
        model.hardCitationFailureCount > 0
          ? 'failed'
          : model.weakCitationCount > 0
            ? 'incomplete'
            : 'clear',
    },
  ]
}

export default function HeroBriefing({
  model,
  onOpenHelp,
}: {
  model: HeroBriefingModel
  onOpenHelp?: () => void
  simpleLanguage?: boolean
}) {
  const statuses = statusCopy(model)

  return (
    <div className="hero-briefing" aria-label="Sample bill overview">
      <div
        className="bill-share-bar"
        role="img"
        aria-label={model.shares
          .map((share) =>
            share.quantitative
              ? `${share.label} ${pct(share.share * 100)}`
              : `${share.label} is not represented in the proportional bar`,
          )
          .join(', ')}
      >
        {model.shares.map((share) =>
          share.quantitative && share.share > 0 ? (
            <span
              key={share.label}
              className={`bill-share-segment tone-${share.tone}`}
              style={{
                width: `${Math.min(Math.max(share.share * 100, 0), 100)}%`,
                minWidth: 0,
              }}
            />
          ) : null,
        )}
      </div>

      <ul className="bill-share-list">
        {model.shares.map((share) => (
          <li key={share.label}>
            <span className={`bill-share-swatch tone-${share.tone}`} aria-hidden="true" />
            <span className="bill-share-name">{share.label}</span>
            <strong>{money(share.amountCad)}</strong>
            <span className="bill-share-percent">
              {share.quantitative
                ? `${pct(share.share * 100)} of total`
                : 'Not represented in the proportional bar'}
            </span>
          </li>
        ))}
      </ul>

      <div className="evidence-summary">
        <div className="evidence-summary-heading">
          <h2>How confident are these numbers?</h2>
          <p>These checks describe our research, not the municipality or its budget.</p>
        </div>
        <ul>
          {statuses.map((status) => {
            const content = (
              <>
                <span
                  className={`evidence-status-icon tone-${status.tone}`}
                  aria-hidden="true"
                />
                <span>
                  <strong>{status.value}</strong>
                  <small>{status.detail}</small>
                </span>
              </>
            )
            return (
              <li key={status.id}>
                {status.href ? (
                  <a href={status.href}>{content}</a>
                ) : (
                  <span className="evidence-status-static">{content}</span>
                )}
              </li>
            )
          })}
        </ul>
        {onOpenHelp ? (
          <button
            type="button"
            className="evidence-help"
            data-help-trigger="receipt-evidence-help"
            onClick={onOpenHelp}
          >
            See how we check the data
          </button>
        ) : null}
      </div>

      <p className="hero-briefing-footnote">{model.footnote}</p>
    </div>
  )
}
