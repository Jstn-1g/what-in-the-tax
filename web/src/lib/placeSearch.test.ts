import { describe, expect, it } from 'vitest'
import {
  canonicalPackHref,
  MAX_PLACE_RESULTS,
  normalizePlaceSearchValue,
  searchPlaces,
  type PlaceSearchRecord,
} from './placeSearch'

const PLACES = [
  {
    id: 'quebec-qc',
    label: 'Québec',
    aliases: ['Quebec City'],
    province: 'Québec',
    typeLabel: 'City',
    releaseStatus: 'Available',
  },
  {
    id: 'woolwich-on',
    label: 'Woolwich',
    aliases: ['Elmira', 'St. Jacobs'],
    province: 'Ontario',
    typeLabel: 'Township',
  },
  {
    id: 'whitehorse-yt',
    label: 'Whitehorse',
    territory: 'Yukon',
    typeLabel: 'City',
  },
] satisfies readonly PlaceSearchRecord[]

describe('place search', () => {
  it('normalizes case, accents, and punctuation', () => {
    expect(normalizePlaceSearchValue('  Île-d’Orléans  ')).toBe(
      'ile d orleans',
    )
    expect(searchPlaces(PLACES, 'QUEBEC').matches.map((place) => place.id)).toEqual([
      'quebec-qc',
    ])
  })

  it('searches aliases and combines words from different fields', () => {
    expect(searchPlaces(PLACES, 'st jacobs').matches[0]?.id).toBe('woolwich-on')
    expect(searchPlaces(PLACES, 'township Ontario').matches[0]?.id).toBe(
      'woolwich-on',
    )
  })

  it('searches province, territory, type, and release status fields', () => {
    expect(searchPlaces(PLACES, 'available').matches[0]?.id).toBe('quebec-qc')
    expect(searchPlaces(PLACES, 'yukon city').matches[0]?.id).toBe(
      'whitehorse-yt',
    )
  })

  it('returns an honest empty result without falling back to another place', () => {
    expect(searchPlaces(PLACES, 'not a real municipality')).toEqual({
      matches: [],
      totalMatches: 0,
      capped: false,
    })
  })

  it('hard-caps results at 20 while retaining the full match count', () => {
    const records = Array.from({ length: 27 }, (_, index) => ({
      id: `place-${index}`,
      label: `Place ${index}`,
    }))
    const result = searchPlaces(records, '', 999)

    expect(result.matches).toHaveLength(MAX_PLACE_RESULTS)
    expect(result.totalMatches).toBe(27)
    expect(result.capped).toBe(true)
    expect(result.matches[0]?.id).toBe('place-0')
    expect(result.matches.at(-1)?.id).toBe('place-19')
  })

  it('supports a smaller caller limit without mutating catalog order', () => {
    const result = searchPlaces(PLACES, '', 2)
    expect(result.matches.map((place) => place.id)).toEqual([
      'quebec-qc',
      'woolwich-on',
    ])
    expect(result.capped).toBe(true)
    expect(PLACES.map((place) => place.id)).toEqual([
      'quebec-qc',
      'woolwich-on',
      'whitehorse-yt',
    ])
  })

  it('builds an encoded canonical pack link', () => {
    expect(canonicalPackHref('saint-john’s nb')).toBe(
      '?pack=saint-john%E2%80%99s%20nb',
    )
  })
})
