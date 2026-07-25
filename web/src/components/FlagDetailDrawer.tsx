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

  const citations = flag.citedFactIds.map((id) => resolveCitation(evidence, id))

  return (
    <div className="drawer-root" role="presentation" onClick={onClose}>
      <aside
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
        <p className="drawer-severity">{(flag.opportunitySeverity ?? 'unrated').replace(/_/g, ' ')}</p>
        <p>{flag.evidenceSummary}</p>
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
                    <a href={`#${id}`}>{gap?.title ?? id}</a>
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
