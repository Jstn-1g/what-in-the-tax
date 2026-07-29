// @vitest-environment jsdom
/**
 * What a single-tier municipality's receipt actually says.
 *
 * The declared-bill model landed with a model, a builder, a projector and an
 * artifact, and no test ever rendered the one pack that uses it - which is how
 * a schema that refused that artifact reached the site. So this renders both
 * shapes and reads the page: a single-tier bill that must not show a phantom
 * upper tier, and a two-tier bill that must still show a real one.
 *
 * Assertions are on rendered text rather than on the model, because every
 * defect this file exists to catch was invisible in the model and obvious on
 * the page.
 */

import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import brantPack from '../../public/packs/brant-county-on.json'
import northDumfriesPack from '../../public/packs/north-dumfries-on.json'
import TaxReceiptScreen from './TaxReceiptScreen'
import type { CitationAudit } from '../lib/evidenceLookup'
import type { Derived, Fact, Gap, Source, TaxpayerReceipt } from '../types'

afterEach(cleanup)

function renderPack(pack: typeof brantPack | typeof northDumfriesPack): string {
  const evidence = pack.evidence as unknown as {
    gaps: Gap[]
    evidencePolicy: { rules: string[] }
    sources: Source[]
    facts: Fact[]
    derived: Derived[]
  }
  const { container } = render(
    <TaxReceiptScreen
      data={pack.receipt as unknown as TaxpayerReceipt}
      gaps={evidence.gaps}
      evidenceRules={evidence.evidencePolicy.rules}
      sources={evidence.sources}
      facts={evidence.facts}
      derived={evidence.derived}
      citationAudit={pack.audit as unknown as CitationAudit}
      bannerText="Draft — source checks pending."
    />,
  )
  return container.textContent ?? ''
}

describe('a single-tier bill (County of Brant)', () => {
  it('says why there is no upper tier, in the builder’s own words', () => {
    expect(renderPack(brantPack)).toContain(
      'County of Brant is a single-tier municipality',
    )
  })

  it('states it as a fact about the place, not as missing evidence', () => {
    const text = renderPack(brantPack)
    expect(text).toContain('rather than evidence we are missing')
  })

  it('never prints a placeholder upper tier', () => {
    // uiModelHints.regionBucketLabel is still 'Upper-tier (n/a)' in the
    // artifact. Nothing may render it: a reader seeing "n/a" reads a hole.
    const text = renderPack(brantPack)
    expect(text).not.toMatch(/n\/a/i)
    expect(text).not.toContain('Upper-tier (')
  })

  it('still says where the missing tier’s services are paid for', () => {
    // The declared reason explains the absence; it must not displace the note
    // that tells a reader policing and paramedics are inside the County lines.
    expect(renderPack(brantPack)).toContain(
      'Policing (OPP), paramedics, and related costs appear inside the County levy lines',
    )
  })

  it('shows the hospital special levy as its own charge', () => {
    // $78.04 folded into the municipal portion is a levy the reader is
    // entitled to see, and the reason the bill became a list.
    const text = renderPack(brantPack)
    expect(text).toContain('Hospital special levy')
    expect(text).toContain('$78.04')
  })
})

describe('a two-tier bill (Township of North Dumfries)', () => {
  it('still shows the upper tier', () => {
    // The control. North Dumfries declares no bodies yet, so it exercises the
    // legacy path; if this breaks, the single-tier work broke everyone else.
    const text = renderPack(northDumfriesPack)
    expect(text).toContain('Region of Waterloo')
  })

  it('does not claim a tier is inapplicable', () => {
    expect(renderPack(northDumfriesPack)).not.toContain('single-tier municipality')
  })
})
