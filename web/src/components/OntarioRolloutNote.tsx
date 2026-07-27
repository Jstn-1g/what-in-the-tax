import type { OntarioMunicipalHistoryRegistry } from '../lib/ontarioMunicipalHistory'

export type OntarioRolloutNoteProps = {
  registry: OntarioMunicipalHistoryRegistry
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
        <p className="registry-brief__eyebrow">Ontario data</p>
        <h2 id="registry-brief-heading">
          Current first. Previous years kept for context.
        </h2>
        <p>
          The directory contains all {registry.coverage.currentMunicipalities}{' '}
          municipalities in Ontario&apos;s current list. For each community, the
          newest locked FIR is selected in 2025 → 2024 → 2023 order, while every
          available year is retained. Current receipt previews stay separate and
          use 2026 tax evidence.
        </p>
      </div>

      <dl className="registry-brief__stats">
        <div>
          <dt>Current municipalities</dt>
          <dd>{registry.coverage.currentMunicipalities}</dd>
        </div>
        <div>
          <dt>Latest FIR is 2025</dt>
          <dd>{registry.coverage.latestFirYearCounts['2025']}</dd>
        </div>
        <div>
          <dt>2026 receipt previews</dt>
          <dd>{receiptPreviewCount}</dd>
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
          Missing evidence stays visible instead of being estimated. Historical
          comparisons will use one common year and basis rather than mixing each
          community&apos;s newest filing.
        </p>
      </div>

      <p className="registry-brief__source">
        Current municipality list updated{' '}
        {registry.sources.currentMunicipalities.lastUpdated}; FIR source
        snapshot {registry.sourceSnapshotDate}. The 2023 baseline remains
        available for broader same-year contrast. Ontario advises that FIR data
        may be incomplete or revised. Runtime AI calls: 0.{' '}
        <a href={registry.sources.currentMunicipalities.dataCatalogueUrl}>
          Current municipality dataset
        </a>
        {' · '}
        <a href={registry.sources.fir.officialIndexUrl}>Official FIR index</a>
        {' · '}
        <a href={registry.sources.licenceUrl}>Open Government Licence</a>
        <span>{registry.sources.licenceAttribution}</span>
      </p>
    </section>
  )
}
