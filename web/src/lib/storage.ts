const BILL_KEY = 'taxpayer-receipt:billCad'
const ASSESSMENT_KEY = 'taxpayer-receipt:assessmentCad'

function readNumber(key: string): number | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const value = Number(raw)
    return Number.isFinite(value) ? value : null
  } catch {
    return null
  }
}

export function loadBillCad(fallback: number): number {
  const stored = readNumber(BILL_KEY)
  if (stored === null) return fallback
  return Math.min(20000, Math.max(1000, Math.round(stored)))
}

export function saveBillCad(value: number): void {
  try {
    localStorage.setItem(BILL_KEY, String(value))
  } catch {
    // ignore quota / private mode failures
  }
}

export function loadAssessmentCad(fallback: number): number {
  const stored = readNumber(ASSESSMENT_KEY)
  if (stored === null) return fallback
  return Math.min(5000000, Math.max(50000, Math.round(stored)))
}

export function saveAssessmentCad(value: number): void {
  try {
    localStorage.setItem(ASSESSMENT_KEY, String(value))
  } catch {
    // ignore quota / private mode failures
  }
}
