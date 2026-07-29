import { useEffect, useState } from 'react'

import {
  applyTheme,
  DEFAULT_THEME,
  readStoredTheme,
  resolveTheme,
  storeTheme,
  type Theme,
} from '../lib/theme'

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true">
      <circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 2.6v2.2M12 19.2v2.2M4.2 12H2M22 12h-2.2M6.5 6.5 4.9 4.9M19.1 19.1l-1.6-1.6M17.5 6.5l1.6-1.6M4.9 19.1l1.6-1.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true">
      <path
        d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.4 8.4 0 1 0 10.2 10.2Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * Dark reading theme, off by default.
 *
 * A plain button with aria-pressed rather than a switch role: the control has
 * two states, the label says which one, and aria-pressed is the pattern screen
 * readers handle without any of the keyboard contract a switch implies.
 */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(DEFAULT_THEME)

  // The inline script in index.html has already applied the stored theme before
  // first paint. This only catches React up to what the document already says.
  useEffect(() => {
    const stored = resolveTheme(
      readStoredTheme(typeof localStorage === 'undefined' ? null : localStorage),
    )
    setTheme(stored)
    applyTheme(stored, document)
  }, [])

  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      className="site-action site-action-theme"
      aria-pressed={isDark}
      onClick={() => {
        const next: Theme = isDark ? 'light' : 'dark'
        setTheme(next)
        applyTheme(next, document)
        storeTheme(typeof localStorage === 'undefined' ? null : localStorage, next)
      }}
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
      <span>{isDark ? 'Light' : 'Dark'}</span>
    </button>
  )
}
