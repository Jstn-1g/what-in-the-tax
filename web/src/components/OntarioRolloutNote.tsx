import type { OntarioFirRegistry } from '../lib/ontarioFirRegistry'

export type OntarioRolloutNoteProps = {
  registry: OntarioFirRegistry
  receiptAssessmentCodes: ReadonlySet<string>
  receiptPreviewCount: number
}

function targetStatus(
  assessmentCode: string,
  order: number,
  receiptAssessmentCodes: ReadonlySet<string>,
): string {
  if (receiptAssessmentCodes.has(assessmentCode)) return 'Draft preview available'
  if (order === 2) return 'Next evidence target'
  if (order === 3) return 'Queued after Wellesley'
  return 'Identity indexed'
}

export default function OntarioRolloutNote({
  registry,
  receiptAssessmentCodes,
  receiptPreviewCount,
}: OntarioRolloutNoteProps) {
  return (
    <section className="registry-brief" aria-labelledby="registry-brief-heading">
      <div className="registry-brief__copy">
        <p className="registry-brief__eyebrow">Ontario rollout</p>
        <h2 id="registry-brief-heading">
          The directory is broader than the receipt library
        </h2>
        <p>
          Ontario currently posts {registry.coverage.recordsPresent} of{' '}
          {registry.coverage.expectedOntarioReturns} expected 2023 Financial
          Information Returns; we indexed those records so residents can find
          their community. A directory match only confirms a historical
          provincial filing; it does not unlock a receipt.
        </p>
      </div>

      <dl className="registry-brief__stats">
        <div>
          <dt>Directory records</dt>
          <dd>{registry.coverage.recordsPresent}</dd>
        </div>
        <div>
          <dt>Receipt previews</dt>
          <dd>{receiptPreviewCount}</dd>
        </div>
        <div>
          <dt>Runtime AI calls</dt>
          <dd>0</dd>
        </div>
      </dl>

      <div className="registry-brief__rollout">
        <h3>Receipt evidence order</h3>
        <ol>
          {registry.rolloutPlan.cohort.map((target) => (
            <li key={target.assessmentCode}>
              <span>{target.label}</span>
              <small>
                {targetStatus(
                  target.assessmentCode,
                  target.order,
                  receiptAssessmentCodes,
                )}
              </small>
            </li>
          ))}
        </ol>
        <p>
          Wellesley is the next local evidence target, followed by Wilmot.
          Missing evidence stays visible instead of being estimated.
        </p>
      </div>

      <p className="registry-brief__source">
        2023 filing data last updated {registry.source.lastUpdated}. Ontario
        advises that FIR data may be incomplete and previously posted years may
        be revised.{' '}
        <a href={registry.source.officialIndexUrl}>Official FIR index</a>
        {' · '}
        <a href={registry.source.licenceUrl}>Open Government Licence</a>
        <span>{registry.source.licenceAttribution}</span>
      </p>
    </section>
  )
}
