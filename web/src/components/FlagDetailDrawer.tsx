import { useEffect, useRef } from 'react'
import { money } from '../lib/format'
import type { ForensicFinding, ReceiptLineItem } from '../types'

type Props = {
  flag: ForensicFinding
  linkedLines: ReceiptLineItem[]
  onClose: () => void
  onSelectLine: (lineId: string) => void
}

export default function FlagDetailDrawer({
  flag,
  linkedLines,
  onClose,
  onSelectLine,
}: Props) {
  const panelRef = useRef<HTMLElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const panel = panelRef.current
    const previouslyFocused = document.activeElement as HTMLElement | null
    closeRef.current?.focus()

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (event.key !== 'Tab' || !panel) return

      const focusable = [
        ...panel.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ].filter((el) => !el.hasAttribute('disabled'))

      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement as HTMLElement | null

      if (event.shiftKey && active === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
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
    <div className="drawer-root" role="presentation">
      <button type="button" className="drawer-backdrop" aria-label="Close flag details" onClick={onClose} />
      <aside
        ref={panelRef}
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="flag-drawer-title"
      >
        <div className="drawer-handle" aria-hidden="true" />
        <header className="drawer-header">
          <div>
            <p className="flag-id">{flag.id}</p>
            <h2 id="flag-drawer-title">{flag.title}</h2>
          </div>
          <button ref={closeRef} type="button" className="drawer-close" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="drawer-body">
          <p className="drawer-impact">
            Estimated bill impact <strong>{money(flag.estimatedBillImpactCad)}</strong>
          </p>
          <p className={`drawer-severity severity-${flag.opportunitySeverity}`}>
            Severity: {flag.opportunitySeverity}
          </p>
          <p className="drawer-evidence">{flag.evidence}</p>
          {flag.uiHint ? <p className="drawer-hint">{flag.uiHint}</p> : null}

          <h3>Linked receipt lines</h3>
          {linkedLines.length === 0 ? (
            <p className="drawer-empty">No receipt lines linked to this flag yet.</p>
          ) : (
            <ul className="drawer-lines">
              {linkedLines.map((line) => (
                <li key={line.id}>
                  <button type="button" onClick={() => onSelectLine(line.id)}>
                    <span>{line.label}</span>
                    <strong>{money(line.amountCad)}</strong>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  )
}
