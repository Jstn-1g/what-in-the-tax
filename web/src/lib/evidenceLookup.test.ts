import { describe, expect, it } from 'vitest'
import { buildEvidenceIndex, citationLabel, resolveCitation } from './evidenceLookup'
import kitLedger from '../data/kitchener/evidence-ledger.json'
import kitAudit from '../data/kitchener/citation-audit.json'

describe('resolveCitation', () => {
  it('prefers the department FACT page for Kitchener household DERIVED lines', () => {
    const index = buildEvidenceIndex(
      kitLedger.sources,
      kitLedger.facts,
      kitLedger.derived,
      kitAudit,
    )
    const cite = resolveCitation(index, 'DRV-KIT-DEPT-CSD-2026-HH')
    expect(cite.kind).toBe('DERIVED')
    expect(cite.source?.id).toBe('kit-2026-appendix-b')
    expect(cite.page).toBe(2)
    expect(citationLabel(cite)).toMatch(/Appendix B/i)
  })

  it('fails closed when a fact has no audit row', () => {
    const source = {
      id: 'source-1',
      title: 'Official budget',
      url: 'https://example.test/budget.pdf',
    }
    const fact = {
      id: 'FACT-1',
      sourceId: source.id,
      page: 7,
      label: 'Unreviewed amount',
      amountCad: 100,
    }
    const index = buildEvidenceIndex([source], [fact], [], { results: [] })
    const cite = resolveCitation(index, fact.id)

    expect(cite.href).toBe(source.url)
    expect(cite.matchTier).toBe('weak')
    expect(citationLabel(cite)).toBe('Official budget · document')

    const derivedIndex = buildEvidenceIndex(
      [source],
      [fact],
      [
        {
          id: 'DERIVED-1',
          label: 'Derived from unreviewed amount',
          formula: 'FACT-1',
          inputs: [fact.id],
        },
      ],
      { results: [] },
    )
    const derivedCite = resolveCitation(derivedIndex, 'DERIVED-1')
    expect(derivedCite.href).toBe(source.url)
    expect(derivedCite.matchTier).toBe('weak')
    expect(citationLabel(derivedCite)).toBe('Official budget · document')
  })

  it('only appends a PDF page for an explicitly page-verified tier', () => {
    const source = {
      id: 'source-1',
      title: 'Official budget',
      url: 'https://example.test/budget.pdf',
    }
    const fact = {
      id: 'FACT-1',
      sourceId: source.id,
      page: 7,
      label: 'Reviewed amount',
      amountCad: 100,
    }
    const index = buildEvidenceIndex([source], [fact], [], {
      results: [{ id: fact.id, tier: 'verbatim' }],
    })

    expect(resolveCitation(index, fact.id).href).toBe(`${source.url}#page=7`)
  })
})
