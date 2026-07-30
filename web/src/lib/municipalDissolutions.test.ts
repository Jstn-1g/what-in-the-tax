import { describe, expect, it } from 'vitest'

import dissolutions from '../data/municipal-dissolutions.json'
import { FORMER_MUNICIPALITIES } from './formerMunicipalities'

/**
 * The crosswalk and the official record, held against each other.
 *
 * municipal-dissolutions.json is derived from the hash-locked StatCan
 * interim lists by scripts/build_municipal_dissolutions.py. Inside the
 * machine-verified era both directions must hold: a crosswalk entry the
 * record does not confirm is an invention, and a taxing-municipality
 * dissolution the crosswalk omits strands the dissolved name's residents
 * with "no match".
 */

const coverageStartYear = Number(
  dissolutions.method.coverageStart.slice(0, 4),
)

const strip = (name: string) => name.replace(/\s*\([^)]*\)$/, '')

describe('municipal dissolutions artifact', () => {
  it('derives from every locked interim-list edition with a named reviewer', () => {
    expect(dissolutions.sources.map((s) => s.sourceId)).toEqual([
      'statcan-il-2006-2011-t1',
      'statcan-il-2011-2016-t1',
      'statcan-il-2016-2021',
      'statcan-il-2025',
    ])
    for (const source of dissolutions.sources) {
      expect(source.sha256).toMatch(/^[0-9a-f]{64}$/)
      expect(source.reviewedBy).toBe('Justin Skowyra')
    }
  })

  it('confirms every machine-era crosswalk entry against the official record', () => {
    const recorded = new Set(
      dissolutions.events.map(
        (event) => `${strip(event.dissolved).toLowerCase()}|${event.successor.toLowerCase()}`,
      ),
    )
    for (const entry of FORMER_MUNICIPALITIES) {
      if (entry.year <= coverageStartYear) continue
      expect(
        recorded.has(
          `${strip(entry.name).toLowerCase()}|${entry.successor.toLowerCase()}`,
        ),
        `crosswalk entry "${entry.name}" -> "${entry.successor}" (${entry.year}) ` +
          'is inside the machine-verified era but absent from the official record',
      ).toBe(true)
    }
  })

  it('carries every taxing-municipality dissolution the record holds', () => {
    const crosswalk = new Set(
      FORMER_MUNICIPALITIES.map(
        (entry) => `${strip(entry.name).toLowerCase()}|${entry.successor.toLowerCase()}`,
      ),
    )
    const taxing = dissolutions.events.filter((event) => event.leviedPropertyTax)
    expect(taxing.length).toBeGreaterThan(0)
    for (const event of taxing) {
      expect(
        crosswalk.has(
          `${strip(event.dissolved).toLowerCase()}|${event.successor.toLowerCase()}`,
        ),
        `official dissolution "${event.dissolved}" -> "${event.successor}" ` +
          `(${event.effectiveDate}, ${event.sourceId}:${event.sourceLine}) ` +
          'is missing from the former-municipalities crosswalk',
      ).toBe(true)
    }
  })

  it('cites its source line for every event', () => {
    for (const event of dissolutions.events) {
      expect(event.sourceId).toMatch(/^statcan-il-/)
      expect(event.sourceLine).toBeGreaterThan(0)
      expect(event.effectiveDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    }
  })
})
