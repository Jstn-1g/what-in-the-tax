import { useEffect, useRef } from 'react'
import type { Finding, Gap } from '../types'
import type { EvidenceIndex, ResolvedCitation } from '../lib/evidenceLookup'
import { resolveCitation } from '../lib/evidenceLookup'

type Props = {
  flag: Finding
  evidence: EvidenceIndex
  gapsById: Map<string, Gap>
  onClose: () => void
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) =>
      !element.hasAttribute('hidden') &&
      element.getAttribute('aria-hidden') !== 'true' &&
      !element.closest('[inert]'),
  )
}

export function focusTrapTarget<T>(
  focusable: readonly T[],
  active: T | null,
  backwards: boolean,
): T | null {
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (first == null || last == null) return null
  if (active == null || !focusable.includes(active)) return backwards ? last : first
  if (backwards && active === first) return last
  if (!backwards && active === last) return first
  return null
}

function CitationCard({ citation }: { citation: ResolvedCitation }) {
  return (
    <li className="citation-card">
      <div className="citation-card-top">
        <code className="flag-id">{citation.id}</code>
        <span className="citation-kind">{citation.kind}</span>
      </div>
      <p className="citation-label">{citation.label}</p>
      {citation.excerpt ? <blockquote className="citation-excerpt">{citation.excerpt}</blockquote> : null}
      {citation.formula ? <p className="line-meta">Formula: {citation.formula}</p> : null}
      {citation.note ? <p className="line-meta">{citation.note}</p> : null}
      {citation.source && citation.href ? (
        <a className="source-link" href={citation.href} target="_blank" rel="noreferrer">
          Open {citation.source.title}
          {citation.page != null ? ` · p.${citation.page}` : ''}
        </a>
      ) : citation.source ? (
        <p className="line-meta">{citation.source.title}</p>
      ) : null}
      {citation.inputs && citation.inputs.length > 0 ? (
        <ul className="citation-inputs">
          {citation.inputs.map((input) => (
            <CitationCard key={input.id} citation={input} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

export default function FlagDetailDrawer({ flag, evidence, gapsById, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    const dialogRoot = panelRef.current?.closest<HTMLElement>('.drawer-root') ?? null
    const backgroundSiblings = dialogRoot?.parentElement
      ? Array.from(dialogRoot.parentElement.children).filter(
          (element): element is HTMLElement =>
            element instanceof HTMLElement && element !== dialogRoot,
        )
      : []
    const previousBackgroundState = backgroundSiblings.map((element) => ({
      element,
      inert: element.getAttribute('inert'),
      ariaHidden: element.getAttribute('aria-hidden'),
    }))

    for (const element of backgroundSiblings) {
      element.setAttribute('inert', '')
      element.setAttribute('aria-hidden', 'true')
    }

    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !panelRef.current) return

      const focusable = focusableElements(panelRef.current)
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (!first || !last) {
        event.preventDefault()
        panelRef.current.focus()
        return
      }

      const active =
        document.activeElement instanceof HTMLElement ? document.activeElement : null
      const target = focusTrapTarget(focusable, active, event.shiftKey)
      if (target) {
        event.preventDefault()
        target.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
      for (const { element, inert, ariaHidden } of previousBackgroundState) {
        if (inert == null) element.removeAttribute('inert')
        else element.setAttribute('inert', inert)
        if (ariaHidden == null) element.removeAttribute('aria-hidden')
        else element.setAttribute('aria-hidden', ariaHidden)
      }
      if (previouslyFocused?.isConnected) previouslyFocused.focus()
    }
  }, [onClose])

  const citations = flag.citedFactIds.map((id) => resolveCitation(evidence, id))

  function closeAndNavigateToGap(id: string) {
    onClose()
    window.location.hash = id
    requestAnimationFrame(() => {
      const target = document.getElementById(id)
      if (!(target instanceof HTMLElement)) return
      const focusTarget =
        target instanceof HTMLDetailsElement
          ? target.querySelector<HTMLElement>('summary')
          : target.matches(FOCUSABLE_SELECTOR)
            ? target
            : null
      if (target instanceof HTMLDetailsElement) target.open = true
      if (focusTarget) {
        focusTarget.focus({ preventScroll: true })
      } else {
        target.tabIndex = -1
        target.focus({ preventScroll: true })
      }
      target.scrollIntoView({ block: 'start' })
    })
  }

  return (
    <div className="drawer-root" role="presentation" onClick={onClose}>
      <aside
        ref={panelRef}
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        aria-describedby="drawer-summary"
        tabIndex={-1}
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
        <p className="drawer-severity">{(flag.opportunitySeverity ?? 'unrated').replace(/_/g, ' ')}</p>
        <p id="drawer-summary">{flag.evidenceSummary}</p>
        <p className="drawer-note">
          Bill impact: not allocatable from sources (see gaps). Judgment only.
        </p>

        {citations.length > 0 ? (
          <div>
            <h3>Sources on the record</h3>
            <ul className="citation-list">
              {citations.map((citation) => (
                <CitationCard key={citation.id} citation={citation} />
              ))}
            </ul>
          </div>
        ) : null}

        {flag.gapIds.length > 0 ? (
          <div>
            <h3>Related gaps</h3>
            <ul className="child-list">
              {flag.gapIds.map((id) => {
                const gap = gapsById.get(id)
                return (
                  <li key={id}>
                    <a
                      href={`#${id}`}
                      onClick={(event) => {
                        event.preventDefault()
                        closeAndNavigateToGap(id)
                      }}
                    >
                      {gap?.title ?? id}
                    </a>
                    {gap ? <p className="line-meta">{gap.detail}</p> : null}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}
      </aside>
    </div>
  )
}
