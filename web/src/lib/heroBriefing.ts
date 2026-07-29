/** Derive the hero "at a glance" briefing from receipt data — no new judgments. */

import type { CitationAudit } from './evidenceLookup'
import type { Finding, Gap, ReceiptLineItem, TaxpayerReceipt , TaxingBodyRole } from '../types'
import { money } from './format'

export type BillShare = {
  label: string
  shortLabel: string
  amountCad: number
  share: number
  role: BillComponentRole
  roleBasis: BillComponentRoleBasis
  quantitative: boolean
  tone: 'municipal' | 'upper' | 'special' | 'education' | 'unclassified'
}

export type BillComponentRole =
  | 'municipal'
  | 'upper-tier'
  | 'special-levy'
  | 'education'
  | 'unclassified'

export type BillComponentRoleBasis =
  | 'explicit'
  | 'bucket-amount'
  | 'component-order'
  | 'unclassified'

/** The declared taxing-body roles, in this module's vocabulary. */
const DECLARED_ROLE_TO_BILL_ROLE: Record<TaxingBodyRole, BillComponentRole> = {
  local: 'municipal',
  'upper-tier': 'upper-tier',
  'special-area': 'special-levy',
  education: 'education',
}

export type Destination = {
  id: string
  label: string
  amountCad: number
  shareOfMunicipal: number
}

export type DestinationsStatus = 'allocated' | 'gap'

export type AttentionChip = {
  id: string
  label: string
  detail: string
  /** Omit when the chip should not navigate (e.g. 0 Watch with no target). */
  href?: string
  tone: 'watch' | 'gap' | 'cite-ok' | 'cite-weak' | 'cite-fail' | 'clear'
}

export type HeroBriefingModel = {
  totalCad: number
  assessmentCad: number
  shares: BillShare[]
  destinations: Destination[]
  /** Real department split vs open evidence hole — never silently omit. */
  destinationsStatus: DestinationsStatus
  destinationsBasis: string
  destinationsGapId?: string
  destinationsGapTitle?: string
  reviewNoteCount: number
  gapCount: number
  weakCitationCount: number
  hardCitationFailureCount: number
  attention: AttentionChip[]
  footnote: string
}

function shortShareLabel(label: string): string {
  const firstWord = label.trim().split(/\s+/u)[0]
  if (!firstWord) return 'Identity unavailable'
  return firstWord.length > 14 ? `${firstWord.slice(0, 12)}…` : firstWord
}

function normalizeExplicitRole(value: unknown): BillComponentRole | null {
  if (typeof value !== 'string') return null
  switch (value.trim().toLowerCase()) {
    case 'municipal':
    case 'local':
    case 'lower-tier':
    case 'single-tier':
      return 'municipal'
    case 'regional':
    case 'region':
    case 'upper-tier':
      return 'upper-tier'
    case 'special':
    case 'special-levy':
      return 'special-levy'
    case 'education':
    case 'school':
    case 'school-board':
      return 'education'
    case 'unclassified':
      return 'unclassified'
    default:
      return null
  }
}

function amountsMatch(left: unknown, right: unknown): boolean {
  return (
    typeof left === 'number' &&
    Number.isFinite(left) &&
    typeof right === 'number' &&
    Number.isFinite(right) &&
    Math.abs(left - right) < 0.005
  )
}

/**
 * Component labels are presentation text, not a national classification system.
 * Prefer a structured role when a newer pack provides one. Legacy packs are
 * classified deterministically from their bucket amounts and documented component
 * order so French or other localized labels are never interpreted as English.
 */
export function deriveBillComponentRole(
  component: TaxpayerReceipt['profiles']['supportedAverageHousehold']['combinedAtAssessment'] extends
    | { components: (infer T)[] }
    | undefined
    ? T
    : never,
  index: number,
  componentCount: number,
  profile: TaxpayerReceipt['profiles']['supportedAverageHousehold'],
  jurisdictionLevel?: string,
): { role: BillComponentRole; basis: BillComponentRoleBasis } {
  const extended = component as typeof component & {
    role?: unknown
    componentRole?: unknown
    governingBodyRole?: unknown
  }
  const explicit = normalizeExplicitRole(
    extended.governingBodyRole ?? extended.componentRole ?? extended.role,
  )
  if (explicit) return { role: explicit, basis: 'explicit' }

  if (amountsMatch(component.amountCad, profile.education.amountCad)) {
    return { role: 'education', basis: 'bucket-amount' }
  }
  if (amountsMatch(component.amountCad, profile.region.amountCad)) {
    return { role: 'upper-tier', basis: 'bucket-amount' }
  }

  // Legacy pack contract: the base local levy is first. Lower-tier receipts
  // place their upper-tier levy second. This uses structured jurisdiction
  // metadata plus reviewed component order, never a display-label guess.
  if (componentCount > 0 && index === 0) {
    return { role: 'municipal', basis: 'component-order' }
  }
  if (jurisdictionLevel === 'lower-tier' && componentCount > 2 && index === 1) {
    return { role: 'upper-tier', basis: 'component-order' }
  }
  if (
    componentCount > 1 &&
    index === componentCount - 1 &&
    (typeof profile.education.amountCad !== 'number' ||
      !Number.isFinite(profile.education.amountCad))
  ) {
    return { role: 'education', basis: 'component-order' }
  }
  if (componentCount > 1) {
    return { role: 'special-levy', basis: 'component-order' }
  }
  return { role: 'unclassified', basis: 'unclassified' }
}

function shareTone(role: BillComponentRole): BillShare['tone'] {
  if (role === 'education') return 'education'
  if (role === 'special-levy') return 'special'
  if (role === 'upper-tier') return 'upper'
  if (role === 'municipal') return 'municipal'
  return 'unclassified'
}

function isDestinationLine(line: ReceiptLineItem): boolean {
  if (line.classification === 'reconciling_item') return false
  if (line.classification === 'disclosure_subline') return false
  if (line.classification === 'special_levy') return false
  if (
    typeof line.amountCad !== 'number' ||
    !Number.isFinite(line.amountCad) ||
    line.amountCad <= 0
  )
    return false
  return true
}

/** Single combined rate×assessment blob — not a real department split. */
export function isUnallocatedCombinedLine(line: ReceiptLineItem): boolean {
  if (/unallocated/i.test(line.classification)) return true
  if (line.gapId && /DEPT-SCHEDULE/i.test(line.gapId)) return true
  const lower = line.label.toLowerCase()
  if (lower.includes('combined') && (lower.includes('rate') || lower.includes('assessment'))) {
    return true
  }
  return false
}

export function findDeptScheduleGap(gaps: Gap[]): Gap | undefined {
  return gaps.find(
    (g) =>
      /DEPT-SCHEDULE/i.test(g.id) ||
      /department.*(allocat|schedule|split)/i.test(g.title) ||
      /service.*(allocat|split)/i.test(g.title) ||
      /household allocation/i.test(g.title),
  )
}

export function buildHeroBriefing(
  data: TaxpayerReceipt,
  gaps: Gap[],
  citationAudit?: CitationAudit | null,
  options?: { municipalBucketLabel?: string },
): HeroBriefingModel | null {
  const profile = data.profiles.supportedAverageHousehold
  const combined = profile.combinedAtAssessment
  const totalCad = combined?.totalCad ?? profile.combinedTotalCad
  const assessmentCad = combined?.assessmentCad
  const municipalTotal = profile.township.amountCad
  if (
    typeof totalCad !== 'number' ||
    !Number.isFinite(totalCad) ||
    totalCad <= 0 ||
    typeof assessmentCad !== 'number' ||
    !Number.isFinite(assessmentCad) ||
    assessmentCad <= 0 ||
    typeof municipalTotal !== 'number' ||
    !Number.isFinite(municipalTotal) ||
    municipalTotal < 0 ||
    !combined?.components?.length ||
    combined.components.some(
      (component) =>
        typeof component.amountCad !== 'number' || !Number.isFinite(component.amountCad),
    )
  )
    return null

  // A pack that declares taxingBodies[] has already said what each line is, and
  // the bodies were built from these same components keyed on sourceFactId, so
  // the join is exact rather than a label match. Preferring the declaration
  // keeps the hero's bar and the bill list below it from categorising the same
  // line two different ways - which they would, since one was reading declared
  // roles and the other was inferring from position.
  const declaredRoles = new Map<string, BillComponentRole>()
  for (const body of profile.taxingBodies ?? []) {
    if (!body.sourceFactId) continue
    declaredRoles.set(body.sourceFactId, DECLARED_ROLE_TO_BILL_ROLE[body.role])
  }

  const shares: BillShare[] = combined.components.map((component, index) => {
    const declared =
      typeof component.sourceFactId === 'string'
        ? declaredRoles.get(component.sourceFactId)
        : undefined
    const { role, basis } = declared
      ? { role: declared, basis: 'explicit' as const }
      : deriveBillComponentRole(
          component,
          index,
          combined.components.length,
          profile,
          data.jurisdiction?.level,
        )
    const quantitative = component.amountCad >= 0
    const componentLabel =
      typeof component.label === 'string' && component.label.trim()
        ? component.label
        : 'Component identity unavailable'
    return {
      label: componentLabel,
      shortLabel: shortShareLabel(componentLabel),
      amountCad: component.amountCad,
      share: quantitative ? component.amountCad / totalCad : 0,
      role,
      roleBasis: basis,
      quantitative,
      tone: shareTone(role),
    }
  })

  const municipalLabel =
    options?.municipalBucketLabel?.trim() ||
    data.uiModelHints.municipalBucketLabel?.trim() ||
    profile.township.uiLabel?.trim() ||
    'Municipal identity unavailable'
  const lines = (profile.township.lineItems ?? []).filter(isDestinationLine)
  const onlyCombinedBlob =
    lines.length === 1 && lines[0] != null && isUnallocatedCombinedLine(lines[0])
  const townshipDeptGap =
    profile.township.gapId && /DEPT-SCHEDULE/i.test(profile.township.gapId)
      ? profile.township.gapId
      : lines.find((l) => l.gapId && /DEPT-SCHEDULE/i.test(l.gapId))?.gapId
  const deptGapFromLedger = findDeptScheduleGap(gaps)
  const hasNoRealSplit = lines.length === 0 || onlyCombinedBlob || Boolean(townshipDeptGap)

  let destinations: Destination[] = []
  let destinationsStatus: DestinationsStatus = 'allocated'
  let destinationsGapId: string | undefined
  let destinationsGapTitle: string | undefined
  let destinationsBasis = `Largest lines inside the ${municipalLabel.toLowerCase()} (pro-rata of published levy)`

  if (hasNoRealSplit) {
    destinationsStatus = 'gap'
    destinations = []
    destinationsGapId =
      deptGapFromLedger?.id ??
      townshipDeptGap ??
      (onlyCombinedBlob ? lines[0]?.gapId : undefined)
    destinationsGapTitle =
      deptGapFromLedger?.title ??
      (destinationsGapId
        ? 'Local department / service allocation not yet bound'
        : 'Published department allocation not yet bound for this pack')
    destinationsBasis =
      'No published department / service allocation is bound yet — listed as a gap, not invented'
  } else {
    const ranked = [...lines].sort((a, b) => b.amountCad - a.amountCad)
    const topDestinations = ranked.slice(0, 5)
    destinations = topDestinations.map((line) => ({
      id: line.id,
      label: line.label,
      amountCad: line.amountCad,
      shareOfMunicipal:
        municipalTotal && municipalTotal > 0 ? line.amountCad / municipalTotal : 0,
    }))
    const shownSum = topDestinations.reduce((sum, line) => sum + line.amountCad, 0)
    const remainderCad =
      municipalTotal && municipalTotal > 0 ? municipalTotal - shownSum : 0
    // Surface the rest as one bar when leftover is material (>2% of municipal).
    if (
      remainderCad > 0 &&
      municipalTotal &&
      remainderCad / municipalTotal > 0.02 &&
      ranked.length > topDestinations.length
    ) {
      destinations.push({
        id: 'dest-remainder',
        label: 'Everything else',
        amountCad: remainderCad,
        shareOfMunicipal: remainderCad / municipalTotal,
      })
    }
  }

  const publishedIds = new Set(data.uiModelHints.publishedFindingIds ?? [])
  const watchFindings: Finding[] = data.findings.filter(
    (f) => !f.belowMateriality && (publishedIds.size === 0 || publishedIds.has(f.id)),
  )
  // Prefer marquee set when present — that's what the UI already promotes.
  const marqueeIds = new Set(data.uiModelHints.marqueeFindings ?? [])
  const watchCount =
    marqueeIds.size > 0
      ? watchFindings.filter((f) => marqueeIds.has(f.id)).length
      : watchFindings.length

  const counts = citationAudit?.counts ?? {}
  const hardFails =
    (counts['not-found'] ?? 0) + (counts['wrong-page'] ?? 0) + (counts['bad-page-number'] ?? 0)
  const weakCitations =
    (counts['numbers-only'] ?? 0) +
    (counts['unverifiable'] ?? 0) +
    (counts['no-excerpt'] ?? 0)

  const gapsDetail =
    destinationsStatus === 'gap' && destinationsGapId
      ? `Department allocation still open (${destinationsGapId}) — listed under Gaps, not invented`
      : gaps.length === 0
        ? 'No open evidence gaps listed'
        : 'Missing proof is listed, not filled with invented dollars'

  const attention: AttentionChip[] = [
    {
      id: 'watch',
      label: watchCount === 0 ? '0 Watch' : `${watchCount} Watch`,
      detail:
        watchCount === 0
          ? 'No published findings needing explanation'
          : 'Open findings that need an explanation — not a verdict of waste',
      ...(watchCount > 0 ? { href: '#watch' } : {}),
      tone: watchCount > 0 ? 'watch' : 'clear',
    },
    {
      id: 'gaps',
      label: gaps.length === 0 ? '0 Gaps' : `${gaps.length} Gaps`,
      detail: gapsDetail,
      href: '#gaps',
      tone: gaps.length > 0 ? 'gap' : 'clear',
    },
    {
      id: 'cite',
      label:
        hardFails > 0
          ? `${hardFails} Cite fails`
          : weakCitations > 0
            ? `${weakCitations} Cite weak`
            : 'Cite OK',
      detail:
        hardFails > 0
          ? 'Some cited pages do not support the claim — treat figures with caution'
          : weakCitations > 0
            ? 'Some values appear in a source without a verified label-to-value match'
            : 'Citation audit found no weak or hard-failure matches',
      href: '#sources',
      tone: hardFails > 0 ? 'cite-fail' : weakCitations > 0 ? 'cite-weak' : 'cite-ok',
    },
  ]

  const ayr = combined.ayrUrbanVariant
  const footnoteParts = [
    destinationsStatus === 'gap'
      ? 'Shares follow published rates. Local department destinations stay blank until a published schedule is bound.'
      : 'Shares follow published rates. Destinations are a model over the levy — not a per-household schedule the municipality prints.',
  ]
  if (ayr) {
    const sar =
      typeof ayr.specialAreaRateCad === 'number' ? ` (+${money(ayr.specialAreaRateCad)})` : ''
    footnoteParts.push(
      `Rural combined total shown; Ayr urban properties also pay a Special Area Rate${sar}.`,
    )
  }
  if (shares.some((share) => share.roleBasis === 'component-order')) {
    footnoteParts.push(
      'Component categories follow the reviewed receipt order until each pack includes explicit role fields. Display names are never used to guess a role.',
    )
  }

  return {
    totalCad,
    assessmentCad,
    shares,
    destinations,
    destinationsStatus,
    destinationsBasis,
    ...(destinationsGapId ? { destinationsGapId } : {}),
    ...(destinationsGapTitle ? { destinationsGapTitle } : {}),
    reviewNoteCount: watchCount,
    gapCount: gaps.length,
    weakCitationCount: weakCitations,
    hardCitationFailureCount: hardFails,
    attention,
    footnote: footnoteParts.join(' '),
  }
}
