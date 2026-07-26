import { buildPieSlices } from '../lib/pieGeometry'

export type SharePieSlice = {
  id: string
  label: string
  share: number
  color: string
  title?: string
}

const SIZE = 168

export default function SharePie({
  slices,
  centerLabel,
  centerValue,
  ariaLabel,
}: {
  slices: SharePieSlice[]
  centerLabel?: string
  centerValue?: string
  ariaLabel: string
}) {
  const geom = buildPieSlices(
    slices.map((s) => ({ id: s.id, share: s.share })),
    { size: SIZE, innerRatio: 0.58 },
  )
  const colorById = new Map(slices.map((s) => [s.id, s]))

  return (
    <div className="share-pie" role="img" aria-label={ariaLabel}>
      <svg
        className="share-pie-svg"
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        width={SIZE}
        height={SIZE}
        aria-hidden="true"
      >
        {geom.map((slice, index) => {
          const meta = colorById.get(slice.id)
          return (
            <path
              key={slice.id}
              d={slice.path}
              fill={meta?.color ?? '#8fa3b0'}
              className="share-pie-slice"
              style={{ animationDelay: `${0.12 + index * 0.07}s` }}
            >
              {meta?.title ? <title>{meta.title}</title> : null}
            </path>
          )
        })}
      </svg>
      {centerLabel || centerValue ? (
        <div className="share-pie-center">
          {centerLabel ? <span className="share-pie-center-label">{centerLabel}</span> : null}
          {centerValue ? <strong className="share-pie-center-value">{centerValue}</strong> : null}
        </div>
      ) : null}
    </div>
  )
}

/** Palette for bill-share tones — matches hero legend dots. */
export function toneColor(tone: string): string {
  switch (tone) {
    case 'municipal':
      return '#d8ebe3'
    case 'upper':
      return '#7eb8a8'
    case 'special':
      return '#e2b46a'
    case 'education':
      return '#8fa3b0'
    default:
      return '#a8b8c0'
  }
}

/** Sequential greens/slates for local destination slices. */
const DEST_COLORS = ['#d8ebe3', '#9ec4b6', '#6f9e8f', '#4f7a6d', '#3d5f56', '#8fa3b0']

export function destinationColor(index: number, isRemainder: boolean): string {
  if (isRemainder) return 'rgba(244, 248, 250, 0.28)'
  return DEST_COLORS[index % DEST_COLORS.length] ?? '#8fa3b0'
}
