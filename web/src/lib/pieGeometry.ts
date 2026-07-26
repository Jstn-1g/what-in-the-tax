/** Pure SVG pie/donut geometry — no React. Shares must sum ≈ 1. */

export type PieSliceInput = {
  id: string
  share: number
}

export type PieSliceGeom = PieSliceInput & {
  startAngle: number
  endAngle: number
  /** SVG path for the annular sector (donut) or full sector. */
  path: string
}

const TAU = Math.PI * 2

function polar(cx: number, cy: number, r: number, angle: number): { x: number; y: number } {
  // Angle 0 at 12 o'clock, clockwise (screen coords: y grows down).
  const a = angle - Math.PI / 2
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
}

function annularSectorPath(
  cx: number,
  cy: number,
  innerR: number,
  outerR: number,
  start: number,
  end: number,
): string {
  const large = end - start > Math.PI ? 1 : 0
  const o0 = polar(cx, cy, outerR, start)
  const o1 = polar(cx, cy, outerR, end)
  const i0 = polar(cx, cy, innerR, end)
  const i1 = polar(cx, cy, innerR, start)
  if (innerR <= 0) {
    return [
      `M ${cx} ${cy}`,
      `L ${o0.x} ${o0.y}`,
      `A ${outerR} ${outerR} 0 ${large} 1 ${o1.x} ${o1.y}`,
      'Z',
    ].join(' ')
  }
  return [
    `M ${o0.x} ${o0.y}`,
    `A ${outerR} ${outerR} 0 ${large} 1 ${o1.x} ${o1.y}`,
    `L ${i0.x} ${i0.y}`,
    `A ${innerR} ${innerR} 0 ${large} 0 ${i1.x} ${i1.y}`,
    'Z',
  ].join(' ')
}

/** Build donut slices. Tiny shares are still drawn (min visual share optional via caller). */
export function buildPieSlices(
  inputs: PieSliceInput[],
  options?: { size?: number; innerRatio?: number },
): PieSliceGeom[] {
  const size = options?.size ?? 160
  const innerRatio = options?.innerRatio ?? 0.58
  const cx = size / 2
  const cy = size / 2
  const outerR = size / 2 - 1
  const innerR = outerR * innerRatio

  const positive = inputs.filter((s) => s.share > 0)
  const total = positive.reduce((sum, s) => sum + s.share, 0)
  if (total <= 0) return []

  let angle = 0
  return positive.map((slice) => {
    const sweep = (slice.share / total) * TAU
    // Full circle as one slice needs a near-full arc (SVG A struggles with exact 360°).
    const startAngle = angle
    const endAngle = angle + Math.min(sweep, TAU * 0.9999)
    angle += sweep
    return {
      ...slice,
      startAngle,
      endAngle,
      path: annularSectorPath(cx, cy, innerR, outerR, startAngle, endAngle),
    }
  })
}
