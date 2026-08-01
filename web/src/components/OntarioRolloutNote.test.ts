import { isValidElement, type ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import checkedArtifact from '../../public/registry/ontario-municipal-history.json'
import { validateOntarioMunicipalHistory } from '../lib/ontarioMunicipalHistory'
import OntarioRolloutNote from './OntarioRolloutNote'

function textContent(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textContent).join('')
  if (!isValidElement(node)) return ''
  return textContent((node.props as { children?: ReactNode }).children)
}

function hrefs(node: ReactNode): string[] {
  if (Array.isArray(node)) return node.flatMap(hrefs)
  if (!isValidElement(node)) return []
  const props = node.props as { children?: ReactNode; href?: unknown }
  return [
    ...(typeof props.href === 'string' ? [props.href] : []),
    ...hrefs(props.children ?? null),
  ]
}

describe('Ontario data verification status', () => {
  it('keeps the verified directory record separate from draft receipt previews', () => {
    const registry = validateOntarioMunicipalHistory(checkedArtifact)
    const verificationHref = '/registry/ontario-municipal-history.json'
    const note = OntarioRolloutNote({
      registry,
      receiptPreviewCount: 6,
      verificationHref,
    })
    const content = textContent(note)

    expect(content).toContain('Verified Ontario directory and FIR history')
    expect(content).toContain('6 draft receipt previews')
    expect(content).toContain('444')
    expect(content).toContain('436')
    expect(content).toContain('2026-06-03')
    // Ontario re-exported the 2025 returns on 2026-08-01 (server
    // Last-Modified 00:29 GMT; nine more municipalities filed, adopted in
    // this session's drift review); the note cites the snapshot it was
    // built from.
    expect(content).toContain('2026-08-01')
    expect(content).toContain('2025, 2024, 2023')
    expect(content).toContain('No AI calls and no live government requests')
    expect(content).toContain(
      'Contains information licensed under the Open Government Licence – Ontario.',
    )
    expect(content).not.toContain('Published')

    // The component must not advertise a rollout sequence. Publishing an order
    // commits the project to a queue in public that PURPOSE.md does not promise.
    expect(content).not.toContain('Receipt evidence order')
    for (const scheduled of ['Next evidence target', 'Queued after', 'Wellesley']) {
      expect(content).not.toContain(scheduled)
    }

    expect(hrefs(note)).toContain(verificationHref)
  })
})
