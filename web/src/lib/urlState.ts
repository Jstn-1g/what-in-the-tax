export type UrlState = {
  billCad?: number
  assessmentCad?: number
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function readUrlState(): UrlState {
  const params = new URLSearchParams(window.location.search)
  const billRaw = params.get('bill')
  const assessmentRaw = params.get('assessment')

  const state: UrlState = {}

  if (billRaw) {
    const billCad = Number(billRaw)
    if (Number.isFinite(billCad)) state.billCad = clamp(Math.round(billCad), 1000, 20000)
  }

  if (assessmentRaw) {
    const assessmentCad = Number(assessmentRaw)
    if (Number.isFinite(assessmentCad)) {
      state.assessmentCad = clamp(Math.round(assessmentCad), 50000, 5000000)
    }
  }

  return state
}

export function writeUrlState(state: { billCad: number; assessmentCad: number }): void {
  const params = new URLSearchParams(window.location.search)
  params.set('bill', String(state.billCad))
  params.set('assessment', String(state.assessmentCad))
  const next = `${window.location.pathname}?${params.toString()}${window.location.hash}`
  window.history.replaceState(null, '', next)
}
