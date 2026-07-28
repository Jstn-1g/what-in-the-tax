import {
  useDeferredValue,
  useId,
  useMemo,
  useState,
  type MouseEvent,
} from 'react'
import {
  canonicalPackHref,
  MAX_PLACE_RESULTS,
  normalizePlaceSearchValue,
  searchPlaces,
  type PlaceSearchRecord,
} from '../lib/placeSearch'

export type RegistryLoadState = 'loading' | 'ready' | 'unavailable'

export type PlaceFinderProps<T extends PlaceSearchRecord> = {
  records: readonly T[]
  onSelectPlace: (id: T['id']) => void
  activePlaceId?: string
  registryState?: RegistryLoadState
  registryCoverage?: {
    currentMunicipalities: number
    withFirHistory: number
    withoutFirHistory: number
    latest2025: number
  }
}

export type PlaceFinderResults<T extends PlaceSearchRecord> = {
  receiptMatches: readonly T[]
  directoryMatches: readonly T[]
  receiptTotal: number
  directoryTotal: number
  displayedMatches: number
  capped: boolean
  hasQuery: boolean
}

export function buildPlaceFinderResults<T extends PlaceSearchRecord>(
  records: readonly T[],
  query: string,
): PlaceFinderResults<T> {
  const hasQuery = normalizePlaceSearchValue(query).length > 0
  const receipts = records.filter(
    (record) => record.kind !== 'directory-record',
  )
  const directoryRecords = hasQuery
    ? records.filter((record) => record.kind === 'directory-record')
    : []
  const receiptResult = searchPlaces(receipts, query)
  const directoryResult = searchPlaces(directoryRecords, query)
  const remaining = Math.max(
    0,
    MAX_PLACE_RESULTS - receiptResult.matches.length,
  )
  const receiptMatches = receiptResult.matches
  const directoryMatches = directoryResult.matches.slice(0, remaining)
  const totalMatches =
    receiptResult.totalMatches + directoryResult.totalMatches

  return {
    receiptMatches,
    directoryMatches,
    receiptTotal: receiptResult.totalMatches,
    directoryTotal: directoryResult.totalMatches,
    displayedMatches: receiptMatches.length + directoryMatches.length,
    capped:
      totalMatches > receiptMatches.length + directoryMatches.length,
    hasQuery,
  }
}

function resultSummary(
  receiptMatches: number,
  directoryMatches: number,
  displayedMatches: number,
  capped: boolean,
  hasQuery: boolean,
): string {
  if (!hasQuery) {
    // Directory records are query-gated, so with an empty box the count
    // alone told a resident nothing about the 435 places they could
    // actually reach. Say the coverage out loud instead.
    return `${receiptMatches} receipt ${
      receiptMatches === 1 ? 'preview' : 'previews'
    }. Search any Ontario municipality to open its filing.`
  }
  const totalMatches = receiptMatches + directoryMatches
  if (totalMatches === 0) return 'No matching communities'

  const parts = []
  if (receiptMatches > 0) {
    parts.push(
      `${receiptMatches} receipt ${
        receiptMatches === 1 ? 'preview' : 'previews'
      }`,
    )
  }
  if (directoryMatches > 0) {
    parts.push(
      `${directoryMatches} Ontario directory ${
        directoryMatches === 1 ? 'record' : 'records'
      }`,
    )
  }
  const breakdown = parts.join(' and ')
  const matchLabel = totalMatches === 1 ? 'match' : 'matches'
  return capped
    ? `${totalMatches} ${matchLabel}: ${breakdown}. Showing the first ${displayedMatches}.`
    : `${totalMatches} ${matchLabel}: ${breakdown}.`
}

function placeMetadata(place: PlaceSearchRecord): readonly string[] {
  const region = place.province ?? place.territory
  const releaseStatus = (() => {
    if (place.kind === 'directory-record') return place.releaseStatus
    if (place.availability === 'blocked') return 'Still checking evidence'
    if (place.releaseStatus === 'draft') return 'Draft preview'
    if (place.releaseStatus === 'preview') return 'Preview'
    return place.releaseStatus
  })()
  const currentEvidence =
    place.kind === 'receipt' && place.currentEvidenceYear
      ? `${place.currentEvidenceYear} current evidence`
      : null
  return [place.typeLabel, region, currentEvidence, releaseStatus].filter(
    (value): value is string => Boolean(value),
  )
}

export default function PlaceFinder<T extends PlaceSearchRecord>({
  records,
  onSelectPlace,
  activePlaceId,
  registryState = 'loading',
  registryCoverage,
}: PlaceFinderProps<T>) {
  const inputId = useId()
  const headingId = useId()
  const summaryId = useId()
  const registryStatusId = useId()
  const resultsId = useId()
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)

  const result = useMemo(
    () => buildPlaceFinderResults(records, deferredQuery),
    [deferredQuery, records],
  )

  function handlePlaceClick(
    event: MouseEvent<HTMLAnchorElement>,
    id: T['id'],
  ) {
    const target = event.currentTarget.getAttribute('target')
    const isNormalNavigation =
      !event.defaultPrevented &&
      event.button === 0 &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.shiftKey &&
      !event.altKey &&
      (!target || target === '_self')

    if (!isNormalNavigation) return
    event.preventDefault()
    onSelectPlace(id)
  }

  function renderMetadata(place: PlaceSearchRecord) {
    const metadata = placeMetadata(place)
    return metadata.length > 0 ? (
      <span className="place-finder__metadata">{metadata.join(' · ')}</span>
    ) : null
  }

  function renderYearContext(place: PlaceSearchRecord) {
    const firYears = place.firYears ?? []
    if (firYears.length === 0) {
      return place.kind === 'directory-record' ? (
        <span className="place-finder__years">
          No 2023–2025 FIR in the locked bulk files
        </span>
      ) : null
    }
    return (
      <span className="place-finder__years">
        FIR history: {firYears.join(', ')}
      </span>
    )
  }

  const registryStatus =
    registryState === 'unavailable'
      ? 'The Ontario directory could not be loaded right now. Receipt previews are still available.'
      : registryState === 'ready' && registryCoverage
        ? `Current Ontario directory: ${registryCoverage.currentMunicipalities} municipalities. ${registryCoverage.latest2025} use 2025 as their latest FIR; the rest fall back to 2024 or 2023 where available.`
        : 'Loading Ontario’s current municipality directory and 2025–2023 FIR history…'

  return (
    <section className="place-finder" aria-labelledby={headingId}>
      <div className="place-finder__intro">
        <h2 id={headingId}>Find your community</h2>
        <p>
          Start with a 2026 receipt preview where one is ready. Every other
          Ontario municipality has a filing showing where its money went by
          function &mdash; type a name to open it.
        </p>
      </div>

      <div className="place-finder__search">
        <label htmlFor={inputId}>Community name</label>
        <div className="place-finder__input-wrap">
          <svg
            className="place-finder__search-icon"
            viewBox="0 0 24 24"
            width="24"
            height="24"
            aria-hidden="true"
          >
            <circle
              cx="10.5"
              cy="10.5"
              r="6.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
            />
            <path
              d="m15.5 15.5 5 5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
          <input
            id={inputId}
            type="search"
            value={query}
            placeholder="Try Toronto, Woolwich, or Paris"
            autoComplete="off"
            aria-controls={resultsId}
            aria-describedby={`${summaryId} ${registryStatusId}`}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>

      <p
        id={registryStatusId}
        className={`place-finder__registry-status ${
          registryState === 'unavailable' ? 'tone-unavailable' : ''
        }`}
      >
        {registryStatus}
      </p>

      <p
        id={summaryId}
        className="place-finder__summary"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {resultSummary(
          result.receiptTotal,
          result.directoryTotal,
          result.displayedMatches,
          result.capped,
          result.hasQuery,
        )}
      </p>

      <div id={resultsId}>
        {result.receiptMatches.length > 0 ? (
          <section
            className="place-finder__group"
            aria-labelledby={`${headingId}-receipts`}
          >
            <h3
              id={`${headingId}-receipts`}
              className="place-finder__results-heading"
            >
              Receipt previews
            </h3>
            <ul className="place-finder__results">
              {result.receiptMatches.map((place) => (
                <li key={place.id} className="place-finder__result">
                  <a
                    href={canonicalPackHref(place.id)}
                    aria-current={
                      activePlaceId === place.id ? 'page' : undefined
                    }
                    onClick={(event) => handlePlaceClick(event, place.id)}
                  >
                    <span className="place-finder__name">{place.label}</span>
                    <span className="place-finder__result-context">
                      {renderMetadata(place)}
                      {renderYearContext(place)}
                    </span>
                    <svg
                      className="place-finder__arrow"
                      viewBox="0 0 24 24"
                      width="24"
                      height="24"
                      aria-hidden="true"
                    >
                      <path
                        d="M5 12h13m-5-5 5 5-5 5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {result.directoryMatches.length > 0 ? (
          <section
            className="place-finder__group"
            aria-labelledby={`${headingId}-directory`}
          >
            <h3
              id={`${headingId}-directory`}
              className="place-finder__results-heading"
            >
              Ontario municipality directory
            </h3>
            <p className="place-finder__group-note">
              These open the municipality&apos;s own Financial Information
              Return: what it reported spending, by function. A filing is a
              past-year return, not a current tax bill, by-law, or receipt.
            </p>
            <ul className="place-finder__results">
              {result.directoryMatches.map((place) => (
                <li key={place.id} className="place-finder__result">
                  {place.filingHref ? (
                    <a
                      href={place.filingHref}
                      aria-current={
                        activePlaceId === place.id ? 'page' : undefined
                      }
                      onClick={(event) => handlePlaceClick(event, place.id)}
                    >
                      <span className="place-finder__name">{place.label}</span>
                      <span className="place-finder__result-context">
                        {renderMetadata(place)}
                        {renderYearContext(place)}
                      </span>
                      <svg
                        className="place-finder__arrow"
                        viewBox="0 0 24 24"
                        width="24"
                        height="24"
                        aria-hidden="true"
                      >
                        <path
                          d="M5 12h13m-5-5 5 5-5 5"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </a>
                  ) : (
                    <div className="place-finder__result-static">
                      <span className="place-finder__name">{place.label}</span>
                      <span className="place-finder__result-context">
                        {renderMetadata(place)}
                        {renderYearContext(place)}
                      </span>
                      <span className="place-finder__not-ready">
                        No filing published
                      </span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {result.displayedMatches === 0 ? (
          <p className="place-finder__empty">
            No match in the current receipt previews or loaded Ontario records.
            We will not substitute another community&apos;s data.
          </p>
        ) : null}
      </div>
    </section>
  )
}
