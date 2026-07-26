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
  },
  {
    kind: 'fir-record',
    id: 'fir-on-1906',
    label: 'Toronto',
    aliases: ['Toronto C', '1906'],
    province: 'Ontario',
    typeLabel: 'City',
    availability: 'fir-record',
    releaseStatus: '2023 provincial filing',
  },
  {
    kind: 'fir-record',
    id: 'fir-on-3024',
    label: 'Wellesley',
    aliases: ['Wellesley Tp', '3024'],
    province: 'Ontario',
    typeLabel: 'Township',
    availability: 'fir-record',
    releaseStatus: 'Next receipt target',
  },
] satisfies readonly PlaceSearchRecord[]

function ids(result: PlaceFinderResults<PlaceSearchRecord>) {
  return {
    receipts: result.receiptMatches.map((record) => record.id),
    fir: result.firMatches.map((record) => record.id),
  }
}

describe('place finder result separation', () => {
  it('shows only receipt previews before a resident starts searching', () => {
    const result = buildPlaceFinderResults(RECORDS, '')

    expect(ids(result)).toEqual({
      receipts: ['north-dumfries-on', 'brant-county-on'],
      fir: [],
    })
    expect(result.firTotal).toBe(0)
  })

  it('returns an informational FIR record without turning it into a receipt', () => {
    const result = buildPlaceFinderResults(RECORDS, 'Toronto')

    expect(ids(result)).toEqual({ receipts: [], fir: ['fir-on-1906'] })
    expect(result.firMatches[0]).toMatchObject({
      kind: 'fir-record',
      availability: 'fir-record',
    })
  })

  it('preserves receipt aliases and the documented next target', () => {
    expect(ids(buildPlaceFinderResults(RECORDS, 'Paris'))).toEqual({
      receipts: ['brant-county-on'],
      fir: [],
    })
    expect(ids(buildPlaceFinderResults(RECORDS, 'Wellesley'))).toEqual({
      receipts: [],
      fir: ['fir-on-3024'],
    })
  })

  it('keeps receipt matches first and caps the combined display at 20', () => {
    const manyFir = Array.from({ length: 25 }, (_, index) => ({
      kind: 'fir-record' as const,
      id: `fir-on-${String(index).padStart(4, '0')}`,
      label: `Ontario Place ${index}`,
      province: 'Ontario',
    }))
    const result = buildPlaceFinderResults(
      [RECORDS[0], ...manyFir],
      'Ontario',
    )

    expect(result.receiptMatches.map((record) => record.id)).toEqual([
      'north-dumfries-on',
    ])
    expect(result.firMatches).toHaveLength(19)
    expect(result.displayedMatches).toBe(20)
    expect(result.receiptTotal + result.firTotal).toBe(26)
    expect(result.capped).toBe(true)
  })
})
