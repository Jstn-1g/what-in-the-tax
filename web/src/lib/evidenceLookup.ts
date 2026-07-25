import type { Derived, Fact, Source } from '../types'

export type EvidenceIndex = {
  sources: Map<string, Source>
  facts: Map<string, Fact>
  derived: Map<string, Derived>
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
  inputs?: ResolvedCitation[]
}

export function buildEvidenceIndex(
  sources: Source[],
  facts: Fact[],
  derived: Derived[],
): EvidenceIndex {
  return {
    sources: new Map(sources.map((s) => [s.id, s])),
    facts: new Map(facts.map((f) => [f.id, f])),
    derived: new Map(derived.map((d) => [d.id, d])),
  }
}

/** Append #page=N for PDF viewers when the URL looks like a PDF. */
export function sourceHref(source: Source, page?: number): string {
  if (!source.url) return ''
  if (page == null || page <= 0) return source.url
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
    const href = source
      ? sourceHref(source, fact.page)
      : fact.url
    return {
      id: fact.id,
      kind: 'FACT',
      label: fact.label,
      excerpt: fact.excerpt,
      note: fact.note,
      page: fact.page,
      source,
      href: href || undefined,
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
    const pageBit = citation.page != null ? ` · p.${citation.page}` : ''
    return `${citation.source.title}${pageBit}`
  }
  if (citation.kind === 'DERIVED' && citation.formula) {
    return `Derived · ${citation.formula}`
  }
  return citation.label
}
