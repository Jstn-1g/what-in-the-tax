/** Simple-language (ELI5) copy remaps — UI strings only; never invents numbers. */

export const ELI5_STORAGE_KEY = 'taxpayer-receipt:simple-language'

export function readSimpleLanguagePreference(): boolean {
  try {
    return window.localStorage.getItem(ELI5_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function writeSimpleLanguagePreference(on: boolean): void {
  try {
    window.localStorage.setItem(ELI5_STORAGE_KEY, on ? '1' : '0')
  } catch {
    /* private mode / blocked storage */
  }
}

/** Evidence / badge status → plain words. Keeps FACT/DERIVED/GAP rules intact. */
export function badgeLabel(status: string, simple: boolean): string {
  if (!simple) return status
  switch (status) {
    case 'FACT':
      return 'From the official document'
    case 'DERIVED':
      return 'We calculated this'
    case 'GAP':
      return "We don't know yet"
    case 'JUDGMENT':
      return 'Needs an explanation'
    case 'ROUNDING':
      return 'Tiny math fix'
    default:
      if (/watch/i.test(status)) return 'Needs an explanation'
      return status
  }
}

/** Bill-stack / share short labels (Township, County, Region, Education…). */
export function simplifyShareLabel(label: string, simple: boolean): string {
  if (!simple) return label
  const lower = label.toLowerCase()
  if (lower.includes('education') || lower === 'schools') return 'Schools'
  if (lower.includes('hospital')) return 'Hospital'
  if (lower.includes('region')) return 'Bigger region'
  if (lower.includes('township') || lower.includes('north dumfries')) return 'Your town'
  if (lower.includes('kitchener') || lower === 'city') return 'Your city'
  if (lower.includes('county') || lower.includes('brant') || lower.includes('municipal'))
    return 'Your county'
  return label
}

/** Section / bucket titles like "Township portion", "County portion". */
export function simplifyBucketLabel(label: string, simple: boolean): string {
  if (!simple) return label
  const lower = label.toLowerCase()
  if (lower.includes('education')) return 'Schools'
  if (lower.includes('township')) return "Your town's share"
  if (lower.includes('city')) return "Your city's share"
  if (lower.includes('county')) return "Your county's share"
  if (lower.includes('region') || lower.includes('upper-tier')) return "The region's share"
  if (lower.includes('municipal')) return 'Local government share'
  return label
}

/** Combined-bill component titles (full labels on the stack). */
export function simplifyComponentLabel(label: string, simple: boolean): string {
  if (!simple) return label
  const lower = label.toLowerCase()
  if (lower.includes('education')) return 'Schools (province sets the rate)'
  if (lower.includes('hospital')) return 'Hospital special charge'
  if (lower.includes('region')) return 'Region of Waterloo'
  if (lower.includes('township') || lower.includes('north dumfries')) return 'Township of North Dumfries'
  if (lower.includes('kitchener')) return 'City of Kitchener'
  if (lower.includes('county') || lower.includes('brant')) return 'County of Brant'
  return label
}

export type UiCopy = {
  heroHeadlineAfterAmount: string
  heroSupport: string
  atAGlance: string
  ofThisBill: string
  ofThisBillSub: string
  localDollar: string
  evidenceState: string
  evidenceStateSub: string
  whatDoTheseMean: string
  fullReceiptJump: string
  yourBillCta: string
  sourcesCta: string
  gapsCta: string
  helpCta: string
  combinedKicker: string
  combinedTitle: string
  onTheBill: string
  publishedTotal: string
  combinedTotalLabel: string
  findingsKicker: string
  findingsTitle: string
  findingsLead: string
  gapsKicker: string
  gapsTitle: string
  gapsLead: string
  sourcesKicker: string
  sourcesTitle: string
  sourcesLead: string
  startHere: string
  fullBibliography: string
  footerHelp: string
  navWatch: string
  navFindings: string
  navGaps: string
  navSources: string
  navHelp: string
}

const STANDARD: UiCopy = {
  heroHeadlineAfterAmount: 'assessment — where this tax goes',
  heroSupport:
    'Skim At a glance, then the bill stack. Every dollar stays cited — or marked as a gap.',
  atAGlance: 'At a glance',
  ofThisBill: 'Of this bill',
  ofThisBillSub: 'Who levies what · same assessment',
  localDollar: 'Where the local dollar goes',
  evidenceState: 'Evidence state',
  evidenceStateSub: 'Not a grade of the budget — a grade of our proof',
  whatDoTheseMean: 'What do these mean?',
  fullReceiptJump: 'Full itemized receipt ↓',
  yourBillCta: 'Your bill',
  sourcesCta: 'Sources',
  gapsCta: 'Gaps',
  helpCta: 'Help & glossary',
  combinedKicker: '1 · Combined receipt',
  combinedTitle: 'How the total is built',
  onTheBill: 'On the bill',
  publishedTotal: 'Published / allocated total',
  combinedTotalLabel: 'Combined total',
  findingsKicker: '2 · Needs explanation',
  findingsTitle: 'Findings',
  findingsLead: 'Cited to facts; bill dollars stay null until a formula is approved.',
  gapsKicker: '3 · Still missing',
  gapsTitle: 'Evidence gaps',
  gapsLead: 'Missing proof is listed — not filled with invented numbers.',
  sourcesKicker: 'References',
  sourcesTitle: 'Direct sources',
  sourcesLead: 'Open the published documents behind this receipt.',
  startHere: 'Start here',
  fullBibliography: 'Full bibliography',
  footerHelp: 'Help & glossary — what FACT, DERIVED, GAP mean',
  navWatch: 'Watch',
  navFindings: 'Findings',
  navGaps: 'Gaps',
  navSources: 'Sources',
  navHelp: 'Help',
}

const SIMPLE: UiCopy = {
  heroHeadlineAfterAmount: 'home value — where your tax money goes',
  heroSupport:
    'Look at the picture below, then scroll to see the full bill. Money we can prove stays linked; money we cannot stays marked missing.',
  atAGlance: 'Quick look',
  ofThisBill: 'Who gets your tax money',
  ofThisBillSub: 'Same house value · different pockets',
  localDollar: 'Biggest pieces of your local share',
  evidenceState: 'How sure are we?',
  evidenceStateSub: 'This grades our proof — not the budget itself',
  whatDoTheseMean: 'What do these labels mean?',
  fullReceiptJump: 'See every line item ↓',
  yourBillCta: 'Your bill',
  sourcesCta: 'Source papers',
  gapsCta: "What's missing",
  helpCta: 'Help & glossary',
  combinedKicker: '1 · The whole bill',
  combinedTitle: 'How the total adds up',
  onTheBill: 'On your bill',
  publishedTotal: 'Total for this part',
  combinedTotalLabel: 'All together',
  findingsKicker: '2 · Needs a closer look',
  findingsTitle: 'Things to check',
  findingsLead: 'Each item points at documents. We do not invent a dollar amount until the math is approved.',
  gapsKicker: '3 · Still missing',
  gapsTitle: "What we don't know yet",
  gapsLead: 'If proof is missing, we list the hole — we never fill it with a guess.',
  sourcesKicker: 'Where this came from',
  sourcesTitle: 'Official documents',
  sourcesLead: 'Open the real papers this receipt is built from.',
  startHere: 'Start here',
  fullBibliography: 'All documents',
  footerHelp: 'Help — plain words for the evidence labels',
  navWatch: 'Watch',
  navFindings: 'To check',
  navGaps: 'Missing',
  navSources: 'Sources',
  navHelp: 'Help',
}

export function uiCopy(simple: boolean): UiCopy {
  return simple ? SIMPLE : STANDARD
}
