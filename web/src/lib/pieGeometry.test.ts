import { describe, expect, it } from 'vitest'
import { buildPieSlices } from './pieGeometry'

describe('buildPieSlices', () => {
  it('returns empty for zero shares', () => {
    expect(buildPieSlices([{ id: 'a', share: 0 }])).toEqual([])
  })

  it('covers a full turn across slices', () => {
    const slices = buildPieSlices([
      { id: 'a', share: 0.5 },
      { id: 'b', share: 0.3 },
      { id: 'c', share: 0.2 },
    ])
    expect(slices).toHaveLength(3)
    expect(slices[0].startAngle).toBe(0)
    const last = slices[slices.length - 1]
    expect(last.endAngle).toBeCloseTo(Math.PI * 2, 5)
    for (const slice of slices) {
      expect(slice.path).toMatch(/^M /)
      expect(slice.path).toContain('A ')
    }
  })

  it('normalizes shares that do not sum to 1', () => {
    const slices = buildPieSlices([
      { id: 'a', share: 2 },
      { id: 'b', share: 2 },
    ])
    expect(slices[0].endAngle - slices[0].startAngle).toBeCloseTo(Math.PI, 5)
  })
})
