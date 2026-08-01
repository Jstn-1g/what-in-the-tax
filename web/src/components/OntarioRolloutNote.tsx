import { repoBaseUrl } from '../repoLink'
import type { OntarioMunicipalHistoryRegistry } from '../lib/ontarioMunicipalHistory'

export type OntarioRolloutNoteProps = {
  registry: OntarioMunicipalHistoryRegistry
  receiptPreviewCount: number
  verificationHref: string
}

export default function OntarioRolloutNote({
  registry,
  receiptPreviewCount,
  verificationHref,
}: OntarioRolloutNoteProps) {
  const firYears = registry.sources.fir.releases
    .map((release) => release.fiscalYear)
    .join(', ')
  const receiptPreviewLabel = `${receiptPreviewCount} draft receipt ${
    receiptPreviewCount === 1 ? 'preview' : 'previews'
  }`

  return (
    <section
      id="data-verification"
      className="registry-brief"
      aria-labelledby="registry-brief-heading"
    >
      <div className="registry-brief__copy">
        <p className="registry-brief__eyebrow">Data verification</p>
        <h2 id="registry-brief-heading">
          Verified Ontario directory and FIR history
        </h2>
        <p>
          This checked record covers Ontario&apos;s current municipality directory and
          historical Financial Information Return (FIR) files. It is separate
          from the {receiptPreviewLabel}, which use 2026 tax evidence and are
          not official bills.
        </p>
      </div>

      <dl className="registry-brief__stats">
        <div>
          <dt>Ontario municipalities</dt>
          <dd>{registry.coverage.currentMunicipalities}</dd>
        </div>
        <div>
          <dt>With FIR history</dt>
          <dd>{registry.coverage.withFirHistory}</dd>
        </div>
        <div>
          <dt>Draft 2026 previews</dt>
          <dd>{receiptPreviewCount}</dd>
        </div>
      </dl>

      <div className="registry-brief__details">
        <h3>What is checked</h3>
        <ul className="registry-brief__checks">
          <li>
            <strong>Source snapshots</strong>
            <span>
              Directory updated {registry.sources.currentMunicipalities.lastUpdated};
              FIR snapshot {registry.sourceSnapshotDate} for {firYears}.
            </span>
          </li>
          <li>
            <strong>Coverage</strong>
            <span>
              {registry.coverage.withFirHistory} municipalities have one or more
              FIR years; {registry.coverage.withoutFirHistory} have directory
              identity only.
            </span>
          </li>
          <li>
            <strong>Runtime</strong>
            <span>
              No AI calls and no live government requests are needed to use this
              record.
            </span>
          </li>
        </ul>
      </div>

      <div className="registry-brief__rollout">
        <p>
          Missing evidence stays visible instead of being estimated. Historical
          comparisons use one common year and basis rather than mixing each
          community&apos;s newest filing.
        </p>
        <p>
          This record is built in the open. Anyone can{' '}
          <a
            href={`${repoBaseUrl()}/blob/main/CONTRIBUTING.md`}
            target="_blank"
            rel="noreferrer"
          >
            contribute official sources and evidence
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>{' '}
          or{' '}
          <a
            href={`${repoBaseUrl()}/issues/new?template=wrong-number.yml`}
            target="_blank"
            rel="noreferrer"
          >
            report a wrong number
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
          ; every contribution passes the same checks before it ships.
        </p>
      </div>

      <div className="registry-brief__source">
        <p>
          Source: {registry.sources.currentMunicipalities.publisher}.{' '}
          <a href={registry.sources.currentMunicipalities.dataCatalogueUrl}>
            Current municipality dataset
          </a>
          {' · '}
          <a href={registry.sources.fir.officialIndexUrl}>Official FIR index</a>
          {' · '}
          <a href={registry.sources.licenceUrl}>Open Government Licence</a>
        </p>
        <p>{registry.sources.licenceAttribution}</p>
        <a className="registry-brief__manifest" href={verificationHref}>
          Open the public verification record (JSON)
        </a>
      </div>
    </section>
  )
}
