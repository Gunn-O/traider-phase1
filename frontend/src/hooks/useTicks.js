import { useEffect, useState } from 'react'
import { useWebSocket } from './useWebSocket'

/**
 * Latest MT5 tick per symbol — populated by api_server's background poller
 * (api_server.py _tick_poll_loop). Live updates arrive via WebSocket
 * `event: 'tick'`; we also fetch /api/ticks once on mount in case the WS
 * hasn't sent anything yet.
 *
 * Returns: { ticks: { [symbol]: { bid, ask, spread_pip, time, ts } }, isConnected }
 */
export function useTicks() {
  const [ticks, setTicks] = useState({})
  const { data: wsData, isConnected } = useWebSocket()

  // First-load snapshot — covers the gap before the first WS tick arrives.
  useEffect(() => {
    let cancelled = false
    fetch('/api/ticks')
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (!cancelled && j?.ticks) setTicks(j.ticks) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!wsData || wsData.event !== 'tick' || !wsData.symbol) return
    setTicks(prev => ({
      ...prev,
      [wsData.symbol]: {
        bid: wsData.bid,
        ask: wsData.ask,
        spread_pip: wsData.spread_pip,
        time: wsData.time,
        ts: wsData.ts,
      },
    }))
  }, [wsData])

  return { ticks, isConnected }
}
