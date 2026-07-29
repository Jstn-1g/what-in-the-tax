/**
 * Former Ontario municipalities, mapped to where their records live now.
 *
 * A Scarborough resident who searches "Scarborough" was told "no match... we
 * will not substitute another community's data" - which reads as a missing
 * city, when the truth is that Scarborough has not been a municipality since
 * 1998 and its taxes are Toronto's. Roughly 630,000 people live under that one
 * dissolved name; the amalgamations of the 1990s and 2000s created dozens
 * more. The finder should say where the records went, not shrug.
 *
 * Rules for this list, and for anyone extending it:
 *
 *  - Dissolved LEGAL municipalities only - places that once levied their own
 *    property tax and were amalgamated away. Neighbourhoods that were never
 *    municipalities do not belong here.
 *  - The successor must resolve against the Ontario registry artifact by
 *    display name. A test loads the real registry and fails on any entry that
 *    does not - a dangling successor cannot ship.
 *  - This is a navigation aid, not evidence. Nothing here reaches a ledger,
 *    a receipt, or a published figure; it only makes the successor's existing
 *    record findable under the name a resident actually uses.
 *  - The list is deliberately not exhaustive. It carries the widely-searched
 *    names; additions are welcome by pull request under the same rules.
 */

export type FormerMunicipality = {
  /** The dissolved municipality's common name, as a resident would type it. */
  name: string
  /** Registry displayName of the municipality that holds its records now. */
  successor: string
  /** Year the amalgamation took effect. */
  year: number
}

export const FORMER_MUNICIPALITIES: readonly FormerMunicipality[] = [
  // Metropolitan Toronto's six, amalgamated into the City of Toronto in 1998.
  { name: 'Scarborough', successor: 'Toronto', year: 1998 },
  { name: 'North York', successor: 'Toronto', year: 1998 },
  { name: 'Etobicoke', successor: 'Toronto', year: 1998 },
  { name: 'East York', successor: 'Toronto', year: 1998 },
  { name: 'York (borough)', successor: 'Toronto', year: 1998 },
  { name: 'Metropolitan Toronto', successor: 'Toronto', year: 1998 },
  // Ottawa-Carleton's municipalities, amalgamated into Ottawa in 2001.
  { name: 'Nepean', successor: 'Ottawa', year: 2001 },
  { name: 'Kanata', successor: 'Ottawa', year: 2001 },
  { name: 'Gloucester', successor: 'Ottawa', year: 2001 },
  { name: 'Vanier', successor: 'Ottawa', year: 2001 },
  { name: 'Cumberland', successor: 'Ottawa', year: 2001 },
  { name: 'Rockcliffe Park', successor: 'Ottawa', year: 2001 },
  // Hamilton-Wentworth's municipalities, amalgamated into Hamilton in 2001.
  { name: 'Stoney Creek', successor: 'Hamilton', year: 2001 },
  { name: 'Dundas (town)', successor: 'Hamilton', year: 2001 },
  { name: 'Ancaster', successor: 'Hamilton', year: 2001 },
  { name: 'Flamborough', successor: 'Hamilton', year: 2001 },
  { name: 'Glanbrook', successor: 'Hamilton', year: 2001 },
  // Galt, Preston and Hespeler formed Cambridge in 1973.
  { name: 'Galt', successor: 'Cambridge', year: 1973 },
  { name: 'Preston', successor: 'Cambridge', year: 1973 },
  { name: 'Hespeler', successor: 'Cambridge', year: 1973 },
  // Fort William and Port Arthur formed Thunder Bay in 1970.
  { name: 'Fort William', successor: 'Thunder Bay', year: 1970 },
  { name: 'Port Arthur', successor: 'Thunder Bay', year: 1970 },
  // The Sudbury region towns, amalgamated into Greater Sudbury in 2001.
  { name: 'Valley East', successor: 'Greater Sudbury', year: 2001 },
  { name: 'Rayside-Balfour', successor: 'Greater Sudbury', year: 2001 },
  { name: 'Nickel Centre', successor: 'Greater Sudbury', year: 2001 },
  { name: 'Walden', successor: 'Greater Sudbury', year: 2001 },
  { name: 'Capreol', successor: 'Greater Sudbury', year: 2001 },
  { name: 'Onaping Falls', successor: 'Greater Sudbury', year: 2001 },
  // Kent County's municipalities, amalgamated into Chatham-Kent in 1998.
  { name: 'Chatham', successor: 'Chatham-Kent', year: 1998 },
  { name: 'Wallaceburg', successor: 'Chatham-Kent', year: 1998 },
  { name: 'Tilbury', successor: 'Chatham-Kent', year: 1998 },
  { name: 'Dresden', successor: 'Chatham-Kent', year: 1998 },
  // Victoria County became Kawartha Lakes in 2001.
  { name: 'Lindsay', successor: 'Kawartha Lakes', year: 2001 },
  { name: 'Bobcaygeon', successor: 'Kawartha Lakes', year: 2001 },
  { name: 'Fenelon Falls', successor: 'Kawartha Lakes', year: 2001 },
  // Trenton amalgamated into Quinte West in 1998.
  { name: 'Trenton', successor: 'Quinte West', year: 1998 },
  // New Liskeard and Haileybury formed Temiskaming Shores in 2004.
  { name: 'New Liskeard', successor: 'Temiskaming Shores', year: 2004 },
  { name: 'Haileybury', successor: 'Temiskaming Shores', year: 2004 },
  // The town of Simcoe dissolved into Norfolk County in 2001. (Distinct from
  // Simcoe County, which is current and matches on its own.)
  { name: 'Simcoe (town)', successor: 'Norfolk County', year: 2001 },
  // Caledonia, Dunnville and Hagersville dissolved into Haldimand County in 2001.
  { name: 'Caledonia', successor: 'Haldimand County', year: 2001 },
  { name: 'Dunnville', successor: 'Haldimand County', year: 2001 },
  { name: 'Hagersville', successor: 'Haldimand County', year: 2001 },
  // The Town of Newcastle was renamed Clarington in 1993; Bowmanville had
  // already been folded into it in 1974.
  { name: 'Bowmanville', successor: 'Clarington', year: 1974 },
  { name: 'Newcastle (town)', successor: 'Clarington', year: 1993 },
  // Port Credit and Streetsville amalgamated into Mississauga in 1974.
  { name: 'Port Credit', successor: 'Mississauga', year: 1974 },
  { name: 'Streetsville', successor: 'Mississauga', year: 1974 },
  // Napanee and its neighbours formed Greater Napanee in 1998.
  { name: 'Napanee', successor: 'Greater Napanee', year: 1998 },
  // Picton dissolved into the single-tier Prince Edward County in 1998.
  { name: 'Picton', successor: 'Prince Edward', year: 1998 },
  // Geraldton and Longlac formed Greenstone in 2001.
  { name: 'Geraldton', successor: 'Greenstone', year: 2001 },
  { name: 'Longlac', successor: 'Greenstone', year: 2001 },
]

const bySuccessor = new Map<string, FormerMunicipality[]>()
for (const entry of FORMER_MUNICIPALITIES) {
  const key = entry.successor.toLocaleLowerCase('en-CA')
  const list = bySuccessor.get(key) ?? []
  list.push(entry)
  bySuccessor.set(key, list)
}

/** Former names to fold into a successor's search aliases. */
export function formerNamesOf(displayName: string): string[] {
  return (bySuccessor.get(displayName.toLocaleLowerCase('en-CA')) ?? []).map(
    (entry) => entry.name,
  )
}

/**
 * One line for the finder row, so a Scarborough searcher who is shown
 * "Toronto" is told why rather than left to wonder.
 */
export function formerNamesNote(displayName: string): string | null {
  const entries = bySuccessor.get(displayName.toLocaleLowerCase('en-CA'))
  if (!entries || entries.length === 0) return null
  const names = entries.map((entry) => entry.name.replace(/\s*\([^)]*\)$/, ''))
  return `Includes the former ${names.length === 1 ? 'municipality' : 'municipalities'} ${names.join(', ')} (amalgamated).`
}
