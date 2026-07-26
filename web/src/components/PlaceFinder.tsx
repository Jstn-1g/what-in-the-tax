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
    recordsPresent: number
    expectedOntarioReturns: number
  }
}

export type PlaceFinderResults<T extends PlaceSearchRecord> = {
  receiptMatches: readonly T[]
  firMatches: readonly T[]
  receiptTotal: number
  firTotal: number
  displayedMatches: number
  capped: boolean
  hasQuery: boolean
}

export function buildPlaceFinderResults<T extends PlaceSearchRecord>(
  records: readonly T[],
  query: string,
): PlaceFinderResults<T> {
  const hasQuery = normalizePlaceSearchValue(query).length > 0
  const receipts = records.filter((record) => record.kind !== 'fir-record')
  const firRecords = hasQuery
    ? records.filter((record) => record.kind === 'fir-record')
    : []
  const receiptResult = searchPlaces(receipts, query)
  const firResult = searchPlaces(firRecords, query)
  const remaining = Math.max(
    0,
    MAX_PLACE_RESULTS - receiptResult.matches.length,
  )
  const receiptMatches = receiptResult.matches
  const firMatches = firResult.matches.slice(0, remaining)
  const totalMatches = receiptResult.totalMatches + firResult.totalMatches

  return {
    receiptMatches,
    firMatches,
    receiptTotal: receiptResult.totalMatches,
    firTotal: firResult.totalMatches,
    displayedMatches: receiptMatches.length + firMatches.length,
    capped: totalMatches > receiptMatches.length + firMatches.length,
    hasQuery,
  }
}

function resultSummary(
  receiptMatches: number,
  firMatches: number,
  displayedMatches: number,
  capped: boolean,
  hasQuery: boolean,
): string {
  if (!hasQuery) {
    return `${receiptMatches} receipt ${
      receiptMatches === 1 ? 'preview' : 'previews'
    }`
  }
  const totalMatches = receiptMatches + firMatches
  if (totalMatches === 0) return 'No matching communities'

  const parts = []
  if (receiptMatches > 0) {
    parts.push(
      `${receiptMatches} receipt ${
        receiptMatches === 1 ? 'preview' : 'previews'
      }`,
    )
  }
  if (firMatches > 0) {
    parts.push(
      `${firMatches} Ontario financial-return ${
        firMatches === 1 ? 'record' : 'records'
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
    if (place.kind === 'fir-record') return place.releaseStatus
    if (place.availability === 'blocked') return 'Still checking evidence'
    if (place.releaseStatus === 'draft') return 'Draft preview'
    if (place.releaseStatus === 'preview') return 'Preview'
    if (place.releaseStatus === 'published') return 'Published'
    return place.releaseStatus
  })()
  return [place.typeLabel, region, releaseStatus].filter(
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

  const registryStatus =
    registryState === 'unavailable'
      ? 'The Ontario directory could not be loaded right now. Receipt previews are still available.'
      : registryState === 'ready' && registryCoverage
        ? `Ontario 2023 coverage: ${registryCoverage.recordsPresent} records indexed; ${registryCoverage.expectedOntarioReturns} returns expected.`
        : 'Loading Ontario’s published 2023 financial-return directory…'

  return (
    <section className="place-finder" aria-labelledby={headingId}>
      <div className="place-finder__intro">
        <h2 id={headingId}>Find your community</h2>
        <p>
          Open a receipt preview where one is ready, or check Ontario&apos;s
          published 2023 financial-return directory.
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
          result.firTotal,
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
                    {renderMetadata(place)}
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

        {result.firMatches.length > 0 ? (
          <section
            className="place-finder__group"
            aria-labelledby={`${headingId}-fir`}
          >
            <h3
              id={`${headingId}-fir`}
              className="place-finder__results-heading"
            >
              2023 Ontario financial-return records
            </h3>
            <p className="place-finder__group-note">
              Historical registry data only—not a current tax bill or receipt.
            </p>
            <ul className="place-finder__results">
              {result.firMatches.map((place) => (
                <li key={place.id} className="place-finder__result">
                  <div className="place-finder__result-static">
                    <span className="place-finder__name">{place.label}</span>
                    {renderMetadata(place)}
                    <span className="place-finder__not-ready">
                      No receipt preview yet
                    </span>
                  </div>
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
