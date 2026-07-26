import {
  useDeferredValue,
  useId,
  useMemo,
  useState,
  type MouseEvent,
} from 'react'
import {
  canonicalPackHref,
  searchPlaces,
  type PlaceSearchRecord,
} from '../lib/placeSearch'

export type PlaceFinderProps<T extends PlaceSearchRecord> = {
  records: readonly T[]
  onSelectPlace: (id: T['id']) => void
  activePlaceId?: string
}

function resultSummary(totalMatches: number, capped: boolean): string {
  if (totalMatches === 0) return 'No matching places'
  if (capped) {
    return `${totalMatches} matching places. Showing the first 20.`
  }
  return `${totalMatches} matching ${totalMatches === 1 ? 'place' : 'places'}`
}

function placeMetadata(place: PlaceSearchRecord): readonly string[] {
  const region = place.province ?? place.territory
  const releaseStatus = (() => {
    if (place.availability === 'blocked') return 'Evidence update required'
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
}: PlaceFinderProps<T>) {
  const inputId = useId()
  const headingId = useId()
  const summaryId = useId()
  const resultsId = useId()
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)
  const result = useMemo(
    () => searchPlaces(records, deferredQuery),
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

  return (
    <section className="place-finder" aria-labelledby={headingId}>
      <div className="place-finder__intro">
        <h2 id={headingId}>Find your municipality</h2>
        <p>
          Search by place name, community type, province, or territory.
        </p>
      </div>

      <div className="place-finder__search">
        <label htmlFor={inputId}>Find your municipality</label>
        <input
          id={inputId}
          type="search"
          value={query}
          placeholder="City, town, township, or municipality"
          autoComplete="off"
          aria-controls={resultsId}
          aria-describedby={summaryId}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      <p
        id={summaryId}
        className="place-finder__summary"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {resultSummary(result.totalMatches, result.capped)}
      </p>

      {result.matches.length > 0 ? (
        <>
          <h3 className="place-finder__results-heading">Available now</h3>
          <ul id={resultsId} className="place-finder__results">
            {result.matches.map((place) => {
              const metadata = placeMetadata(place)
              return (
                <li key={place.id} className="place-finder__result">
                  <a
                    href={canonicalPackHref(place.id)}
                    aria-current={activePlaceId === place.id ? 'page' : undefined}
                    onClick={(event) => handlePlaceClick(event, place.id)}
                  >
                    <span className="place-finder__name">{place.label}</span>
                    {metadata.length > 0 ? (
                      <span className="place-finder__metadata">
                        {metadata.join(' · ')}
                      </span>
                    ) : null}
                  </a>
                </li>
              )
            })}
          </ul>
        </>
      ) : (
        <p id={resultsId} className="place-finder__empty">
          No matching place is available. No place was substituted.
        </p>
      )}
    </section>
  )
}
