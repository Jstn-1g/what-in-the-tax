export type SupportedLocale = 'en-CA' | 'fr-CA'

export const DEFAULT_LOCALE: SupportedLocale = 'en-CA'

const currencyFormatters = new Map<SupportedLocale, Intl.NumberFormat>()
const percentFormatters = new Map<SupportedLocale, Intl.NumberFormat>()

/**
 * Keep locale selection deterministic and bounded to the reviewed Canadian
 * message catalogs. Language-only values such as "fr" are accepted so the
 * document language can drive formatting before a full locale picker exists.
 */
export function normalizeLocale(value?: string | null): SupportedLocale {
  return value?.trim().toLowerCase().startsWith('fr') ? 'fr-CA' : DEFAULT_LOCALE
}

export function currentLocale(): SupportedLocale {
  if (typeof document === 'undefined') return DEFAULT_LOCALE
  return normalizeLocale(document.documentElement.lang)
}

function currencyFormatter(locale: SupportedLocale): Intl.NumberFormat {
  const cached = currencyFormatters.get(locale)
  if (cached) return cached
  const formatter = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'CAD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  currencyFormatters.set(locale, formatter)
  return formatter
}

function percentFormatter(locale: SupportedLocale): Intl.NumberFormat {
  const cached = percentFormatters.get(locale)
  if (cached) return cached
  const formatter = new Intl.NumberFormat(locale, {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
  percentFormatters.set(locale, formatter)
  return formatter
}

export function money(amount: number, locale = currentLocale()): string {
  return currencyFormatter(normalizeLocale(locale)).format(amount)
}

/** Format a percentage value expressed as 0–100, preserving the existing API. */
export function pct(value: number, locale = currentLocale()): string {
  return percentFormatter(normalizeLocale(locale)).format(value / 100)
}
