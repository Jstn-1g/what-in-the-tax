// @vitest-environment jsdom
/**
 * What the "Who levied it" section actually says on the page.
 *
 * The taxation artifacts cover every taxing municipality in Ontario, which
 * means the two shapes below are not edge cases - 167 of the 405 are
 * single-tier, and 30 upper tiers have no taxation receipt at all. Both have to
 * read as facts about the jurisdiction rather than as holes in the evidence,
 * and that is a property of rendered text, not of the model.
 */

import { cleanup, render } from '@testing-library/react'
import axe from 'axe-core'
import { afterEach, describe, expect, it } from 'vitest'

import twoTierFiling from '../../public/fir/2023/3001.json'
import twoTierTaxation from '../../public/fir-taxation/2023/3001.json'
import singleTierFiling from '../../public/fir/2023/3310.json'
import singleTierTaxation from '../../public/fir-taxation/2023/3310.json'
import FirFilingScreen from './FirFilingScreen'
import { validateFirFiling } from '../lib/firFiling'
import { validateFirTaxation } from '../lib/firTaxation'

afterEach(cleanup)

function screenFor(
  filing: unknown,
  taxation: unknown | null,
  taxationAbsent = false,
): { text: string; container: Element } {
  const { container } = render(
    <FirFilingScreen
      filing={validateFirFiling(filing)}
      taxation={taxation ? validateFirTaxation(taxation) : null}
      taxationAbsent={taxationAbsent}
      availableYears={[2023]}
      onSelectYear={() => {}}
      onBack={() => {}}
    />,
  )
  return { text: container.textContent ?? '', container }
}

describe('a two-tier municipality (North Dumfries)', () => {
  it('names all three bodies that levied the tax', () => {
    const { text } = screenFor(twoTierFiling, twoTierTaxation)
    expect(text).toContain('Who levied it')
    expect(text).toContain('This municipality (lower tier)')
    expect(text).toContain('County or region (upper tier)')
    expect(text).toContain('Education (Province of Ontario)')
  })

  it('says these are municipality-wide totals, not one household’s bill', () => {
    // The single most available misreading of this page.
    const { text } = screenFor(twoTierFiling, twoTierTaxation)
    expect(text).toContain('not one household')
  })

  it('shows the education rate checked against the province’s own', () => {
    const { text } = screenFor(twoTierFiling, twoTierTaxation)
    expect(text).toContain('0.1530%')
    expect(text).toContain('does not set')
  })
})

describe('a single-tier municipality (Norfolk County)', () => {
  it('omits the upper tier rather than printing a levy of zero', () => {
    // A zero row reads as "the region took nothing", which is false. There is
    // no region. A shorter bill is a shorter list.
    const { text } = screenFor(singleTierFiling, singleTierTaxation)
    expect(text).toContain('Who levied it')
    expect(text).not.toContain('County or region (upper tier)')
  })

  it('states the absence as a fact about the jurisdiction', () => {
    const { text } = screenFor(singleTierFiling, singleTierTaxation)
    expect(text).toContain('single-tier municipality')
    expect(text).toContain('not a missing figure')
  })
})

describe('a municipality with no taxation receipt', () => {
  it('explains an upper tier rather than reporting a gap', () => {
    const { text } = screenFor(twoTierFiling, null, true)
    expect(text).toContain('Who levied it')
    // The filing fixture is a lower tier, so this exercises the other branch:
    // a municipality that filed no Schedule 26A summary.
    expect(text).toContain('filed no Schedule 26A')
    expect(text).toContain('instead of being estimated')
  })

  it('says nothing at all while the artifact is still loading', () => {
    // Absent and not-yet-known are different. Claiming "no levy" during a
    // pending request would be a claim we cannot support.
    const { text } = screenFor(twoTierFiling, null, false)
    expect(text).not.toContain('Who levied it')
  })
})

describe('accessibility', () => {
  it('renders the levy section without violations', async () => {
    const { container } = screenFor(twoTierFiling, twoTierTaxation)
    const results = await axe.run(container, {
      resultTypes: ['violations'],
      rules: { 'color-contrast': { enabled: false } },
    })
    expect(
      results.violations.map((v) => `${v.id}: ${v.help}`),
    ).toEqual([])
  })
})
