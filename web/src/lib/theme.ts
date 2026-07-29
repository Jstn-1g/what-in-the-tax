/**
 * Reading theme. Light is the default and stays the default.
 *
 * The operating system's prefers-color-scheme is deliberately NOT consulted.
 * This is a page people read carefully, often for the first time, and a dark
 * page arriving unasked is worse for some readers than no dark page at all.
 * Dark is a choice someone makes here, and it is remembered.
 *
 * The one stored value is this preference. It carries no identity, no history
 * and nothing about the reader beyond which of two stylesheets they prefer, and
 * privacy.txt says so plainly rather than leaving it to be discovered.
 */

export type Theme = 'light' | 'dark'

export const DEFAULT_THEME: Theme = 'light'
export const THEME_STORAGE_KEY = 'whatinthetax.theme'

/** Minimal shape of Storage, so callers can be tested without a browser. */
export type ThemeStore = Pick<Storage, 'getItem' | 'setItem'>

function isTheme(value: unknown): value is Theme {
  return value === 'light' || value === 'dark'
}

/**
 * Read a stored preference, or null when there is none.
 *
 * Storage throws rather than returning null in private-browsing modes and when
 * a reader has disabled site data, and a theme preference is not worth breaking
 * a page over.
 */
export function readStoredTheme(store: ThemeStore | null | undefined): Theme | null {
  if (!store) return null
  try {
    const stored = store.getItem(THEME_STORAGE_KEY)
    return isTheme(stored) ? stored : null
  } catch {
    return null
  }
}

export function storeTheme(
  store: ThemeStore | null | undefined,
  theme: Theme,
): void {
  if (!store) return
  try {
    store.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // A preference that cannot be saved is still a preference for this visit.
  }
}

/** Resolve what to render with: the reader's choice, else light. */
export function resolveTheme(stored: Theme | null): Theme {
  return stored ?? DEFAULT_THEME
}

/**
 * Put the theme on the document, and keep the browser chrome in step.
 *
 * data-theme is what styles.css selects on. theme-color is what paints the
 * mobile address bar, and leaving it white behind a dark page is the one bit of
 * the UI a stylesheet cannot reach.
 */
export function applyTheme(theme: Theme, doc: Document): void {
  const root = doc.documentElement
  if (theme === DEFAULT_THEME) {
    root.removeAttribute('data-theme')
  } else {
    root.setAttribute('data-theme', theme)
  }
  const meta = doc.querySelector('meta[name="theme-color"]')
  if (meta) {
    meta.setAttribute('content', theme === 'dark' ? '#0b1420' : '#ffffff')
  }
}
