import { describe, expect, it } from 'vitest'
import {
  DEFAULT_LOCALE,
  money,
  normalizeLocale,
  pct,
} from './format'

function normalizeSpacing(value: string): string {
  return value.replace(/[\u00a0\u202f]/g, ' ')
}

describe('Canadian presentation formatting', () => {
  it('normalizes reviewed English and French locale variants', () => {
    expect(normalizeLocale('fr')).toBe('fr-CA')
    expect(normalizeLocale('fr-CA')).toBe('fr-CA')
    expect(normalizeLocale('en')).toBe('en-CA')
    expect(normalizeLocale('en-CA')).toBe('en-CA')
    expect(normalizeLocale('de-CA')).toBe(DEFAULT_LOCALE)
    expect(normalizeLocale(null)).toBe(DEFAULT_LOCALE)
  })

  it('formats Canadian currency for English and French without AI translation', () => {
    expect(normalizeSpacing(money(1234.5, 'en-CA'))).toBe('$1,234.50')
    expect(normalizeSpacing(money(1234.5, 'fr-CA'))).toBe('1 234,50 $')
  })

  it('formats percentage punctuation and spacing by locale', () => {
    expect(normalizeSpacing(pct(12.34, 'en-CA'))).toBe('12.3%')
    expect(normalizeSpacing(pct(12.34, 'fr-CA'))).toBe('12,3 %')
  })
})
