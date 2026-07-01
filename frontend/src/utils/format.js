// format.js — number/currency formatters shared across the Command Deck UI.
// Mirrors the design bundle's FMT helper.

const abs = Math.abs

export const FMT = {
  usd: (n, dp = 2) => {
    const v = Number(n)
    if (!Number.isFinite(v)) return '—'
    return (v < 0 ? '-' : '') + '$' + abs(v).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })
  },
  num: (n, dp = 2) => {
    const v = Number(n)
    if (!Number.isFinite(v)) return '—'
    return v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })
  },
  signed: (n, dp = 2) => {
    const v = Number(n)
    if (!Number.isFinite(v)) return '—'
    return (v >= 0 ? '+' : '-') + abs(v).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })
  },
  pct: (n, dp = 1) => {
    const v = Number(n)
    if (!Number.isFinite(v)) return '—'
    return (v >= 0 ? '+' : '') + v.toFixed(dp) + '%'
  },
  px: (n, dp = 2) => {
    const v = Number(n)
    return Number.isFinite(v) ? v.toFixed(dp) : '—'
  },
}

export function fmtTime(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return iso }
}

export function fmtDateTime(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    return `${mm}-${dd} ${hh}:${mi}`
  } catch { return iso }
}

export default FMT
