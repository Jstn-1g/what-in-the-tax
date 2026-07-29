// @vitest-environment jsdom
/**
 * Automated accessibility checks over the rendered screens.
 *
 * The manual screen-reader pass is still the thing that finds the defects that
 * matter, and this does not replace it. What it does is stop a regression from
 * waiting for the next manual pass to be noticed.
 *
 * One rule is switched off deliberately. jsdom does no layout and computes no
 * colours, so axe cannot evaluate colour-contrast here; leaving it on would
 * report "incomplete" and read like a pass. Contrast is checked instead in
 * contrast.test.ts, against the declared tokens, where it can actually be
 * measured.
 */

import { cleanup, render } from '@testing-library/react'
import axe from 'axe-core'
import { afterEach, describe, expect, it } from 'vitest'

import pack from '../public/packs/north-dumfries-on.json'
import singleTierPack from '../public/packs/brant-county-on.json'
import filing from '../public/fir/2023/3001.json'
import FirFilingScreen from './components/FirFilingScreen'
import HelpGuide from './components/HelpGuide'
import TaxReceiptScreen from './components/TaxReceiptScreen'
import { validateFirFiling } from './lib/firFiling'
import type { CitationAudit } from './lib/evidenceLookup'
import type { Derived, Fact, Gap, Source, TaxpayerReceipt } from './types'

const RULES_OFF = new Set(['color-contrast'])

async function violationsIn(container: Element): Promise<string[]> {
  const results = await axe.run(container, {
    resultTypes: ['violations'],
    rules: Object.fromEntries(
      [...RULES_OFF].map((rule) => [rule, { enabled: false }]),
    ),
  })
  return results.violations.map(
    (violation) =>
      `${violation.id} (${violation.impact}): ${violation.help} — ` +
      violation.nodes.map((node) => node.target.join(' ')).join('; '),
  )
}

afterEach(cleanup)

describe('the checker itself', () => {
  it('reports a defect it is supposed to catch', async () => {
    // A test that has never failed has not been shown to work. Three screens
    // passing on the first run is only good news if a violation would have been
    // reported, so plant two and check.
    const { container } = render(
      <div>
        <img src="chart.png" />
        <input type="text" />
      </div>,
    )
    const found = await violationsIn(container)
    expect(found.some((line) => line.startsWith('image-alt'))).toBe(true)
    expect(found.some((line) => line.startsWith('label'))).toBe(true)
  })
})

describe('rendered screens', () => {
  it('renders the receipt without accessibility violations', async () => {
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
    expect(await violationsIn(container)).toEqual([])
  })

  it('renders a single-tier receipt without accessibility violations', async () => {
    // A single-tier bill renders a different tree: no upper-tier section, an
    // extra special-area charge, and a declared reason in place of a row. It
    // had never been rendered here, so it had never been checked.
    const evidence = singleTierPack.evidence as unknown as {
      gaps: Gap[]
      evidencePolicy: { rules: string[] }
      sources: Source[]
      facts: Fact[]
      derived: Derived[]
    }
    const { container } = render(
      <TaxReceiptScreen
        data={singleTierPack.receipt as unknown as TaxpayerReceipt}
        gaps={evidence.gaps}
        evidenceRules={evidence.evidencePolicy.rules}
        sources={evidence.sources}
        facts={evidence.facts}
        derived={evidence.derived}
        citationAudit={singleTierPack.audit as unknown as CitationAudit}
        bannerText="Draft — source checks pending."
      />,
    )
    expect(await violationsIn(container)).toEqual([])
  })

  it('renders a FIR filing without accessibility violations', async () => {
    const { container } = render(
      <FirFilingScreen
        filing={validateFirFiling(filing)}
        availableYears={[2025, 2024, 2023]}
        onSelectYear={() => {}}
        onBack={() => {}}
      />,
    )
    expect(await violationsIn(container)).toEqual([])
  })

  it('renders the help guide without accessibility violations', async () => {
    const { container } = render(
      <HelpGuide onBack={() => {}} onNavigate={() => {}} />,
    )
    expect(await violationsIn(container)).toEqual([])
  })
})
