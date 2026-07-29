import { describe, expect, it } from 'vitest'

import {
  applyTheme,
  DEFAULT_THEME,
  readStoredTheme,
  resolveTheme,
  storeTheme,
  THEME_STORAGE_KEY,
  type Theme,
  type ThemeStore,
} from './theme'

function memoryStore(initial: Record<string, string> = {}): ThemeStore {
  const map = new Map(Object.entries(initial))
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => void map.set(key, value),
  }
}

const throwingStore: ThemeStore = {
  getItem() {
    throw new DOMException('storage disabled')
  },
  setItem() {
    throw new DOMException('storage disabled')
  },
}

describe('reading theme', () => {
  it('defaults to light, not to the operating system', () => {
    // The OS preference is deliberately not an input. A reader who has dark mode
    // on everywhere still gets a light page here until they ask for otherwise.
    expect(DEFAULT_THEME).toBe('light')
    expect(resolveTheme(null)).toBe('light')
  })

  it('remembers a choice once made', () => {
    const store = memoryStore()
    storeTheme(store, 'dark')
    expect(store.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(resolveTheme(readStoredTheme(store))).toBe('dark')
  })

  it('ignores a stored value that is not a theme', () => {
    // Anything could be in storage - another script, an old build, a person
    // typing into devtools. Only two strings are themes.
    expect(readStoredTheme(memoryStore({ [THEME_STORAGE_KEY]: 'midnight' }))).toBeNull()
    expect(readStoredTheme(memoryStore())).toBeNull()
    expect(readStoredTheme(null)).toBeNull()
  })

  it('renders a page when storage is unavailable', () => {
    // Private browsing and disabled site data make Storage throw rather than
    // return null. A theme preference is not worth breaking a page over.
    expect(readStoredTheme(throwingStore)).toBeNull()
    expect(() => storeTheme(throwingStore, 'dark')).not.toThrow()
  })
})

describe('applying a theme to the document', () => {
  function fakeDocument() {
    const attributes = new Map<string, string>()
    const meta = { content: '#ffffff' }
    return {
      attributes,
      meta,
      doc: {
        documentElement: {
          setAttribute: (k: string, v: string) => void attributes.set(k, v),
          removeAttribute: (k: string) => void attributes.delete(k),
        },
        querySelector: () => ({
          setAttribute: (_k: string, v: string) => void (meta.content = v),
        }),
      } as unknown as Document,
    }
  }

  it('marks the document when dark and unmarks it when light', () => {
    const { attributes, doc } = fakeDocument()
    applyTheme('dark', doc)
    expect(attributes.get('data-theme')).toBe('dark')
    // Light is the default, so it is the absence of an attribute rather than a
    // second value. One state, one representation.
    applyTheme('light', doc)
    expect(attributes.has('data-theme')).toBe(false)
  })

  it('moves the browser chrome with the page', () => {
    // theme-color paints the mobile address bar, which is the one part of the
    // UI the stylesheet cannot reach. Left behind, it is a white band above a
    // dark page.
    const { meta, doc } = fakeDocument()
    applyTheme('dark', doc)
    expect(meta.content).toBe('#0b1420')
    applyTheme('light', doc)
    expect(meta.content).toBe('#ffffff')
  })

  it('round-trips every theme it claims to support', () => {
    const themes: Theme[] = ['light', 'dark']
    for (const theme of themes) {
      const store = memoryStore()
      storeTheme(store, theme)
      expect(resolveTheme(readStoredTheme(store))).toBe(theme)
    }
  })
})
