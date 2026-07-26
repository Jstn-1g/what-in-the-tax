import { describe, expect, it } from 'vitest'
import {
  badgeLabel,
  simplifyBucketLabel,
  simplifyComponentLabel,
  simplifyShareLabel,
  uiCopy,
} from './eli5'

describe('eli5 copy remaps', () => {
  it('leaves technical badge labels alone when simple language is off', () => {
    expect(badgeLabel('FACT', false)).toBe('FACT')
    expect(badgeLabel('DERIVED', false)).toBe('DERIVED')
    expect(badgeLabel('GAP', false)).toBe('GAP')
    expect(badgeLabel('ROUNDING', false)).toBe('ROUNDING')
  })

  it('maps evidence badges to plain language when on', () => {
    expect(badgeLabel('FACT', true)).toBe('From the official document')
    expect(badgeLabel('DERIVED', true)).toBe('We calculated this')
    expect(badgeLabel('GAP', true)).toBe("We don't know yet")
    expect(badgeLabel('JUDGMENT', true)).toBe('Needs an explanation')
    expect(badgeLabel('ROUNDING', true)).toBe('Tiny math fix')
    expect(badgeLabel('0 Watch', true)).toBe('Needs an explanation')
  })

  it('simplifies jurisdiction share and bucket labels for ND and Brant', () => {
    expect(simplifyShareLabel('Township', true)).toBe('Your town')
    expect(simplifyShareLabel('County', true)).toBe('Your county')
    expect(simplifyShareLabel('Region', true)).toBe('Bigger region')
    expect(simplifyShareLabel('Education', true)).toBe('Schools')
    expect(simplifyBucketLabel('Township portion', true)).toBe("Your town's share")
    expect(simplifyBucketLabel('County portion', true)).toBe("Your county's share")
    expect(simplifyBucketLabel('Region portion', true)).toBe("The region's share")
    expect(simplifyComponentLabel('Education (Province of Ontario)', true)).toMatch(/Schools/)
    expect(simplifyComponentLabel('County of Brant (municipal)', true)).toBe('County of Brant')
  })

  it('swaps hero/briefing titles used with the denser masthead', () => {
    const simple = uiCopy(true)
    const standard = uiCopy(false)
    expect(standard.heroHeadlineAfterAmount).toMatch(/assessment/)
    expect(simple.heroHeadlineAfterAmount).toMatch(/home value/)
    expect(simple.ofThisBill).toBe('Who gets your tax money')
    expect(simple.localDollar).toBe('Biggest pieces of your local share')
    expect(simple.evidenceState).toBe('How sure are we?')
    expect(standard.ofThisBill).toBe('Of this bill')
  })
})
