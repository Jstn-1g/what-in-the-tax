/** Derive the hero "at a glance" briefing from receipt data — no new judgments. */

import type { CitationAudit } from './evidenceLookup'
import type { Finding, Gap, ReceiptLineItem, TaxpayerReceipt } from '../types'
import { money } from './format'

export type BillShare = {
  label: string
  shortLabel: string
  amountCad: number
  share: number
  tone: 'municipal' | 'upper' | 'special' | 'education'
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
  attention: AttentionChip[]
  footnote: string
}

function shortShareLabel(label: string): string {
  const lower = label.toLowerCase()
  if (lower.includes('education')) return 'Education'
  if (lower.includes('hospital')) return 'Hospital'
  if (lower.includes('region')) return 'Region'
  if (lower.includes('township') || lower.includes('north dumfries')) return 'Township'
  if (lower.includes('kitchener') || (lower.includes('city') && !lower.includes('education')))
    return 'City'
  if (lower.includes('county') || lower.includes('brant') || lower.includes('municipal'))
    return 'County'
  const first = label.split(/[(/]/)[0]?.trim() ?? label
  return first.length > 14 ? `${first.slice(0, 12)}…` : first
}

function shareTone(label: string): BillShare['tone'] {
  const lower = label.toLowerCase()
  if (lower.includes('education')) return 'education'
  if (lower.includes('hospital')) return 'special'
  if (lower.includes('region')) return 'upper'
  return 'municipal'
}

function isDestinationLine(line: ReceiptLineItem): boolean {
  if (line.classification === 'reconciling_item') return false
  if (line.classification === 'disclosure_subline') return false
  if (line.classification === 'special_levy') return false
  if (line.amountCad <= 0) return false
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
  if (totalCad == null || totalCad <= 0 || !combined?.components?.length) return null

  const assessmentCad = combined.assessmentCad
  const shares: BillShare[] = combined.components.map((c) => ({
    label: c.label,
    shortLabel: shortShareLabel(c.label),
    amountCad: c.amountCad,
    share: c.amountCad / totalCad,
    tone: shareTone(c.label),
  }))

  const municipalLabel =
    options?.municipalBucketLabel ??
    data.uiModelHints.municipalBucketLabel ??
    profile.township.uiLabel ??
    'Municipal portion'
  const municipalTotal = profile.township.amountCad
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

  return {
    totalCad,
    assessmentCad,
    shares,
    destinations,
    destinationsStatus,
    destinationsBasis,
    ...(destinationsGapId ? { destinationsGapId } : {}),
    ...(destinationsGapTitle ? { destinationsGapTitle } : {}),
    attention,
    footnote: footnoteParts.join(' '),
  }
}
