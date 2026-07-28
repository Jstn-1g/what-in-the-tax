export const MAX_PLACE_RESULTS = 20

export type PlaceSearchRecord = {
  id: string
  kind?: 'receipt' | 'directory-record'
  label: string
  aliases?: readonly string[]
  province?: string
  territory?: string
  typeLabel?: string
  geographicArea?: string
  releaseStatus?: string
  availability?: string
  availabilityNote?: string
  currentEvidenceYear?: number
  latestFirYear?: number | null
  firYears?: readonly number[]
  /** Set only when a published filing exists for this record. The finder
   *  renders a link when present and stays static when absent, so a
   *  municipality is never offered a page that does not exist. */
  filingHref?: string
}

export type PlaceSearchResults<T extends PlaceSearchRecord> = {
  matches: readonly T[]
  totalMatches: number
  capped: boolean
}

const COMBINING_MARKS = /\p{M}+/gu
const SEARCH_SEPARATORS = /[^\p{L}\p{N}]+/gu

export function normalizePlaceSearchValue(value: string): string {
  return value
    .normalize('NFKD')
    .replace(COMBINING_MARKS, '')
    .toLocaleLowerCase('en-CA')
    .replace(SEARCH_SEPARATORS, ' ')
    .trim()
}

function recordSearchText(record: PlaceSearchRecord): string {
  return [
    record.label,
    ...(record.aliases ?? []),
    record.province,
    record.territory,
    record.typeLabel,
    record.geographicArea,
    record.releaseStatus,
    record.currentEvidenceYear?.toString(),
    record.latestFirYear?.toString(),
    ...(record.firYears?.map(String) ?? []),
  ]
    .filter((value): value is string => Boolean(value))
    .map(normalizePlaceSearchValue)
    .join(' ')
}

/**
 * Deterministic, local-only place search. Each query word may match any
 * supported field, so "township waterloo" can match across type and province.
 */
export function searchPlaces<T extends PlaceSearchRecord>(
  records: readonly T[],
  query: string,
  requestedLimit = MAX_PLACE_RESULTS,
): PlaceSearchResults<T> {
  const normalizedQuery = normalizePlaceSearchValue(query)
  const terms = normalizedQuery ? normalizedQuery.split(' ') : []
  const finiteLimit = Number.isFinite(requestedLimit)
    ? Math.floor(requestedLimit)
    : MAX_PLACE_RESULTS
  const limit = Math.max(0, Math.min(finiteLimit, MAX_PLACE_RESULTS))
  const matches: T[] = []
  let totalMatches = 0

  for (const record of records) {
    const searchText = recordSearchText(record)
    if (!terms.every((term) => searchText.includes(term))) continue

    totalMatches += 1
    if (matches.length < limit) matches.push(record)
  }

  return {
    matches,
    totalMatches,
    capped: totalMatches > matches.length,
  }
}

export function canonicalPackHref(id: string): string {
  return `?pack=${encodeURIComponent(id)}`
}
