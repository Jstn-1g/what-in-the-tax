import { describe, expect, it } from 'vitest'

import registry from '../../public/registry/ontario-municipal-history.json'
import {
  FORMER_MUNICIPALITIES,
  formerNamesNote,
  formerNamesOf,
} from './formerMunicipalities'
import { searchPlaces } from './placeSearch'

// A Scarborough resident searched "Scarborough" and was told no match - which
// reads as a missing city, when Scarborough has been Toronto since 1998. This
// suite pins the fix and, more importantly, pins the rule that keeps the list
// honest: every successor must resolve against the real registry artifact, so
// a dangling or misspelled successor cannot ship.

describe('the crosswalk stays grounded', () => {
  const displayNames = new Set(
    (registry as { records: { displayName: string }[] }).records.map(
      (record) => record.displayName,
    ),
  )

  it('every successor exists in the committed Ontario registry', () => {
    for (const entry of FORMER_MUNICIPALITIES) {
      expect(
        displayNames.has(entry.successor),
        `${entry.name} points at "${entry.successor}", which is not a registry displayName`,
      ).toBe(true)
    }
  })

  it('no former name shadows a current municipality', () => {
    // "Simcoe (town)" is disambiguated precisely because Simcoe County is
    // current. A bare former name that equals a current displayName would
    // make one search result silently claim another's identity.
    for (const entry of FORMER_MUNICIPALITIES) {
      expect(
        displayNames.has(entry.name),
        `${entry.name} is also a current municipality; disambiguate it`,
      ).toBe(false)
    }
  })

  it('every entry carries a plausible amalgamation year', () => {
    for (const entry of FORMER_MUNICIPALITIES) {
      expect(entry.year).toBeGreaterThanOrEqual(1950)
      expect(entry.year).toBeLessThanOrEqual(2010)
    }
  })
})

describe('what a resident actually experiences', () => {
  const toronto = {
    id: 'directory-toronto',
    kind: 'directory-record' as const,
    label: 'Toronto',
    aliases: ['Toronto C', ...formerNamesOf('Toronto')],
    formerNote: formerNamesNote('Toronto') ?? undefined,
  }

  it('searching Scarborough finds Toronto', () => {
    const results = searchPlaces([toronto], 'Scarborough')
    expect(results.matches.map((m) => m.label)).toEqual(['Toronto'])
  })

  it('and the row says why it matched', () => {
    expect(toronto.formerNote).toContain('Scarborough')
    expect(toronto.formerNote).toContain('amalgamated')
  })

  it('Etobicoke, North York and East York find Toronto too', () => {
    for (const query of ['Etobicoke', 'North York', 'East York']) {
      expect(
        searchPlaces([toronto], query).matches.length,
        `${query} should find Toronto`,
      ).toBe(1)
    }
  })

  it('a municipality with no former names gets no note', () => {
    expect(formerNamesNote('Woolwich')).toBeNull()
    expect(formerNamesOf('Woolwich')).toEqual([])
  })
})
