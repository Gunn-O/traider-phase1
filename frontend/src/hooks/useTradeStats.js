import { useEffect, useState } from 'react'

// useTradeStats — aggregate trade statistics + equity curve from LocalDB.
// Backs the Command Center stat tiles and equity chart.
export function useTradeStats(filters = {}, pollMs = 15000) {
  const [stats, setStats] = useState(null)
  const qs = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v != null && v !== '')
  ).toString()

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await fetch(`/api/trades/stats${qs ? `?${qs}` : ''}`)
        if (!r.ok) return
        const j = await r.json()
        if (alive) setStats(j)
      } catch { /* ignore */ }
    }
    load()
    const t = setInterval(load, pollMs)
    return () => { alive = false; clearInterval(t) }
  }, [qs, pollMs])

  return stats
}

export default useTradeStats
