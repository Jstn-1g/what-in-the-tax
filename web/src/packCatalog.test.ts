import { describe, expect, it } from 'vitest'
import {
  getPackCatalogEntry,
  isPackId,
  PACK_CATALOG,
  packRouteFromSearch,
} from './packCatalog'

describe('pack catalog routing', () => {
  it('uses the chooser when no pack was requested', () => {
    expect(packRouteFromSearch('')).toEqual({ kind: 'chooser' })
    expect(packRouteFromSearch('?view=summary')).toEqual({ kind: 'chooser' })
  })

  it('preserves a valid deep link', () => {
    expect(packRouteFromSearch('?pack=north-dumfries-on')).toEqual({
      kind: 'pack',
      id: 'north-dumfries-on',
    })
  })

  it('fails closed for unknown and blank pack parameters', () => {
    expect(packRouteFromSearch('?pack=not-a-place')).toEqual({
      kind: 'unknown',
      requested: 'not-a-place',
    })
    expect(packRouteFromSearch('?pack=')).toEqual({
      kind: 'unknown',
      requested: '',
    })
  })

  it('keeps a known blocked pack unavailable without substituting another pack', () => {
    expect(packRouteFromSearch('?pack=woolwich-on')).toEqual({
      kind: 'blocked',
      id: 'woolwich-on',
    })
  })

  it('has one unique catalog record for every supported pack', () => {
    const ids = PACK_CATALOG.map((pack) => pack.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const id of ids) {
      expect(isPackId(id)).toBe(true)
      expect(getPackCatalogEntry(id).id).toBe(id)
    }
    expect(isPackId('kitchener')).toBe(false)
  })
})
