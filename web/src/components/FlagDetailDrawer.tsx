import { useEffect, useRef } from 'react'
import type { Finding } from '../types'

type Props = {
  flag: Finding
  onClose: () => void
}

export default function FlagDetailDrawer({ flag, onClose }: Props) {
  const panelRef = useRef<HTMLElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
      previouslyFocused?.focus()
    }
  }, [onClose])

  return (
    <div className="drawer-root" role="presentation" onClick={onClose}>
      <aside
        ref={panelRef}
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-head">
          <div>
            <p className="flag-id">{flag.id}</p>
            <h2 id="drawer-title">{flag.title}</h2>
          </div>
          <button ref={closeRef} type="button" className="drawer-close" onClick={onClose}>
            Close
          </button>
        </header>
        <p className="drawer-severity">{flag.opportunitySeverity.replace(/_/g, ' ')}</p>
        <p>{flag.evidenceSummary}</p>
        <p className="drawer-note">
          Bill impact: not allocatable from sources (see gaps). Judgment only.
        </p>
        {flag.citedFactIds.length > 0 ? (
          <div>
            <h3>Cited facts</h3>
            <ul className="child-list">
              {flag.citedFactIds.map((id) => (
                <li key={id}>
                  <code>{id}</code>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {flag.gapIds.length > 0 ? (
          <div>
            <h3>Related gaps</h3>
            <ul className="child-list">
              {flag.gapIds.map((id) => (
                <li key={id}>
                  <code>{id}</code>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </aside>
    </div>
  )
}
