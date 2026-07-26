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
})
