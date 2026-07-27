import { describe, expect, it } from 'vitest'
import {
  buildPlaceFinderResults,
  type PlaceFinderResults,
} from './PlaceFinder'
import type { PlaceSearchRecord } from '../lib/placeSearch'

const RECORDS = [
  {
    kind: 'receipt',
    id: 'north-dumfries-on',
    label: 'North Dumfries',
    aliases: ['Ayr'],
    province: 'Ontario',
    typeLabel: 'Township',
    availability: 'available',
    releaseStatus: 'draft',
    currentEvidenceYear: 2026,
    latestFirYear: 2024,
    firYears: [2024, 2023],
  },
  {
    kind: 'receipt',
    id: 'brant-county-on',
    label: 'Paris / Brant County',
    aliases: ['Paris', 'County of Brant'],
    province: 'Ontario',
    typeLabel: 'County',
    availability: 'available',
    releaseStatus: 'draft',
    currentEvidenceYear: 2026,
    latestFirYear: 2024,
    firYears: [2024, 2023],
  },
  {
    kind: 'directory-record',
    id: 'directory-on-1906',
    label: 'Toronto',
    aliases: ['Toronto C', '1906'],
    province: 'Ontario',
    typeLabel: 'City',
    availability: 'directory-record',
    releaseStatus: 'Latest FIR 2025',
    latestFirYear: 2025,
    firYears: [2025, 2024, 2023],
  },
  {
    kind: 'directory-record',
    id: 'directory-on-3024',
    label: 'Wellesley',
    aliases: ['Wellesley Tp', '3024'],
    province: 'Ontario',
    typeLabel: 'Township',
    availability: 'directory-record',
    releaseStatus: 'Next receipt target',
    latestFirYear: 2025,
    firYears: [2025, 2024, 2023],
  },
] satisfies readonly PlaceSearchRecord[]

function ids(result: PlaceFinderResults<PlaceSearchRecord>) {
  return {
    receipts: result.receiptMatches.map((record) => record.id),
    directory: result.directoryMatches.map((record) => record.id),
  }
}

describe('place finder result separation', () => {
  it('shows only receipt previews before a resident starts searching', () => {
    const result = buildPlaceFinderResults(RECORDS, '')

    expect(ids(result)).toEqual({
      receipts: ['north-dumfries-on', 'brant-county-on'],
      directory: [],
    })
    expect(result.directoryTotal).toBe(0)
  })

  it('returns an informational directory record without turning it into a receipt', () => {
    const result = buildPlaceFinderResults(RECORDS, 'Toronto')

    expect(ids(result)).toEqual({
      receipts: [],
      directory: ['directory-on-1906'],
    })
    expect(result.directoryMatches[0]).toMatchObject({
      kind: 'directory-record',
      availability: 'directory-record',
      latestFirYear: 2025,
      firYears: [2025, 2024, 2023],
    })
  })

  it('preserves receipt aliases and the documented next target', () => {
    expect(ids(buildPlaceFinderResults(RECORDS, 'Paris'))).toEqual({
      receipts: ['brant-county-on'],
      directory: [],
    })
    expect(ids(buildPlaceFinderResults(RECORDS, 'Wellesley'))).toEqual({
      receipts: [],
      directory: ['directory-on-3024'],
    })
  })

  it('keeps receipt matches first and caps the combined display at 20', () => {
    const manyDirectory = Array.from({ length: 25 }, (_, index) => ({
      kind: 'directory-record' as const,
      id: `directory-on-${String(index).padStart(4, '0')}`,
      label: `Ontario Place ${index}`,
      province: 'Ontario',
    }))
    const result = buildPlaceFinderResults(
      [RECORDS[0], ...manyDirectory],
      'Ontario',
    )

    expect(result.receiptMatches.map((record) => record.id)).toEqual([
      'north-dumfries-on',
    ])
    expect(result.directoryMatches).toHaveLength(19)
    expect(result.displayedMatches).toBe(20)
    expect(result.receiptTotal + result.directoryTotal).toBe(26)
    expect(result.capped).toBe(true)
  })
})
