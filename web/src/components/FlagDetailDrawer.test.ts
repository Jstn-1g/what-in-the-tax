import { describe, expect, it } from 'vitest'
import { focusTrapTarget } from './FlagDetailDrawer'

describe('evidence drawer focus containment', () => {
  const controls = ['close', 'source', 'related-gap'] as const

  it('wraps forward and backward focus at the drawer boundaries', () => {
    expect(focusTrapTarget(controls, 'related-gap', false)).toBe('close')
    expect(focusTrapTarget(controls, 'close', true)).toBe('related-gap')
  })

  it('pulls focus back into the drawer if it starts outside', () => {
    expect(focusTrapTarget(controls, null, false)).toBe('close')
    expect(focusTrapTarget(controls, null, true)).toBe('related-gap')
    expect(focusTrapTarget(controls, 'source', false)).toBeNull()
  })
})
