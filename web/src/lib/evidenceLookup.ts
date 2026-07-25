import type { Derived, Fact, Source } from '../types'

export type CitationAudit = {
  counts?: Record<string, number>
  results?: { id?: string; tier?: string }[]
}

export type EvidenceIndex = {
  sources: Map<string, Source>
  facts: Map<string, Fact>
  derived: Map<string, Derived>
  /** factId -> safe for #page= deep link */
  pageVerified: Map<string, boolean>
}

export type ResolvedCitation = {
  id: string
  kind: 'FACT' | 'DERIVED' | 'UNKNOWN'
  label: string
  excerpt?: string
  formula?: string
  note?: string
  page?: number
  source?: Source
  href?: string
  matchTier?: string
  inputs?: ResolvedCitation[]
}

/** Tiers that are safe for #page= deep links (PUBLISH.md / Phase 0 item 3). */
export const PAGE_LINK_TIERS = new Set([
  'verbatim',
  'normalized',
  'alnum',
  'row-bound',
])

export function buildEvidenceIndex(
  sources: Source[],
  facts: Fact[],
  derived: Derived[],
  audit?: CitationAudit | null,
): EvidenceIndex {
  const pageVerified = new Map<string, boolean>()
  for (const row of audit?.results ?? []) {
    if (!row.id || !row.tier) continue
    if (row.tier === 'unverifiable' || row.tier === 'no-excerpt') continue
    pageVerified.set(row.id, PAGE_LINK_TIERS.has(row.tier))
  }
  return {
    sources: new Map(sources.map((s) => [s.id, s])),
    facts: new Map(facts.map((f) => [f.id, f])),
    derived: new Map(derived.map((d) => [d.id, d])),
    pageVerified,
  }
}

/** Append #page=N for PDF viewers only when the cite is page-verified. */
export function sourceHref(
  source: Source,
  page?: number,
  opts?: { pageVerified?: boolean },
): string {
  if (!source.url) return ''
  if (page == null || page <= 0) return source.url
  if (opts && opts.pageVerified === false) return source.url
  const base = source.url.split('#')[0]
  if (/\.pdf($|\?)/i.test(base) || base.toLowerCase().includes('.pdf')) {
    return `${base}#page=${page}`
  }
  return source.url
}

export function resolveCitation(
  index: EvidenceIndex,
  id: string,
  depth = 0,
): ResolvedCitation {
  const fact = index.facts.get(id)
  if (fact) {
    const source = index.sources.get(fact.sourceId)
    const verified = index.pageVerified.get(fact.id)
    const href = source
      ? sourceHref(source, fact.page, {
          pageVerified: verified === undefined ? undefined : verified,
        })
      : fact.url
    const auditRow = verified === undefined ? undefined : verified
    return {
      id: fact.id,
      kind: 'FACT',
      label: fact.label,
      excerpt: fact.excerpt,
      note: fact.note,
      page: fact.page,
      source,
      href: href || undefined,
      matchTier: auditRow === false ? 'weak' : auditRow === true ? 'page-verified' : undefined,
    }
  }

  const derived = index.derived.get(id)
  if (derived) {
    const inputs =
      depth < 2
        ? (derived.inputs ?? []).map((inputId) => resolveCitation(index, inputId, depth + 1))
        : []
    const primary = inputs.find((c) => c.href)
    return {
      id: derived.id,
      kind: 'DERIVED',
      label: derived.label,
      formula: derived.formula,
      note: derived.note,
      source: primary?.source,
      href: primary?.href,
      page: primary?.page,
      excerpt: primary?.excerpt,
      inputs,
    }
  }

  return { id, kind: 'UNKNOWN', label: id }
}

export function citationLabel(citation: ResolvedCitation): string {
  if (citation.source) {
    const pageBit =
      citation.page != null && citation.matchTier !== 'weak'
        ? ` · p.${citation.page}`
        : citation.page != null
          ? ' · document'
          : ''
    return `${citation.source.title}${pageBit}`
  }
  if (citation.kind === 'DERIVED' && citation.formula) {
    return `Derived · ${citation.formula}`
  }
  return citation.label
}
