const PACK_CATALOG_RECORDS = [
  {
    id: 'kitchener-on',
    label: 'Kitchener',
    province: 'Ontario',
    typeLabel: 'City',
    aliases: ['City of Kitchener'],
    banner: 'Preview · pack/kitchener-on · City of Kitchener + Region of Waterloo',
    availability: 'available',
    canDisplay: true,
    releaseStatus: 'draft',
  },
  {
    id: 'waterloo-on',
    label: 'Waterloo',
    province: 'Ontario',
    typeLabel: 'City',
    aliases: ['City of Waterloo'],
    banner: 'Preview · pack/waterloo-on · City of Waterloo + Region of Waterloo',
    availability: 'available',
    canDisplay: true,
    releaseStatus: 'draft',
  },
  {
    id: 'cambridge-on',
    label: 'Cambridge',
    province: 'Ontario',
    typeLabel: 'City',
    aliases: ['City of Cambridge'],
    banner: 'Preview · pack/cambridge-on · City of Cambridge + Region of Waterloo',
    availability: 'available',
    canDisplay: true,
    releaseStatus: 'draft',
  },
  {
    id: 'woolwich-on',
    label: 'Woolwich',
    province: 'Ontario',
    typeLabel: 'Township',
    aliases: ['Township of Woolwich', 'Elmira', 'St. Jacobs'],
    banner:
      'Draft preview · pack/woolwich-on · $354,500 reference scenario, not a Woolwich average',
    availability: 'available',
    canDisplay: true,
    releaseStatus: 'draft',
  },
  {
    id: 'north-dumfries-on',
    label: 'North Dumfries',
    province: 'Ontario',
    typeLabel: 'Township',
    aliases: ['Township of North Dumfries', 'Ayr'],
    banner:
      'Preview · north-dumfries-on · evidence hardening in progress',
    availability: 'available',
    canDisplay: true,
    releaseStatus: 'draft',
  },
  {
    id: 'brant-county-on',
    label: 'Paris / Brant County',
    province: 'Ontario',
    typeLabel: 'Single-tier municipality',
    aliases: ['Paris', 'County of Brant', 'Brant County'],
    banner: 'Preview · pack/brant-county-on · Paris via County of Brant (single-tier)',
    availability: 'available',
    canDisplay: true,
    releaseStatus: 'draft',
  },
] as const

export type PackId = (typeof PACK_CATALOG_RECORDS)[number]['id']
export type PackCatalogEntry = {
  id: PackId
  label: string
  province: string
  typeLabel: string
  aliases: readonly string[]
  banner: string
  canDisplay: boolean
  releaseStatus: 'draft' | 'preview' | 'published' | 'blocked'
} & (
  | { availability: 'available'; availabilityNote?: never }
  | { availability: 'blocked'; availabilityNote: string }
)

// Widen availability to retain fail-closed support even when every currently
// listed preview has a browser-safe public artifact.
export const PACK_CATALOG: readonly PackCatalogEntry[] = PACK_CATALOG_RECORDS
export const PACK_IDS: readonly PackId[] = PACK_CATALOG.map((pack) => pack.id)

const PACK_IDS_SET: ReadonlySet<string> = new Set(PACK_IDS)
const PACK_CATALOG_BY_ID = new Map(PACK_CATALOG.map((pack) => [pack.id, pack]))

export function isPackId(value: string | null | undefined): value is PackId {
  return typeof value === 'string' && PACK_IDS_SET.has(value)
}

export function getPackCatalogEntry(id: PackId): PackCatalogEntry {
  return PACK_CATALOG_BY_ID.get(id)!
}

export type PackRoute =
  | { kind: 'chooser' }
  | { kind: 'pack'; id: PackId }
  | { kind: 'blocked'; id: PackId }
  | { kind: 'unknown'; requested: string }

/**
 * A missing pack is an intentional chooser route. An explicitly invalid pack is
 * retained as an unavailable route so it can never display another municipality.
 */
export function packRouteFromSearch(search: string): PackRoute {
  const params = new URLSearchParams(search)
  if (!params.has('pack')) return { kind: 'chooser' }

  const requested = params.get('pack') ?? ''
  if (!isPackId(requested)) return { kind: 'unknown', requested }
  return getPackCatalogEntry(requested).canDisplay
    ? { kind: 'pack', id: requested }
    : { kind: 'blocked', id: requested }
}
