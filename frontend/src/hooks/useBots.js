import { useState, useEffect, useCallback } from 'react'
import { useWebSocket } from './useWebSocket'

const POLL_MS = 3000

// Prefix-aware trade_id equality — mirrors api_server._trade_ids_match. MT5
// truncates the position comment to 16 chars, so the same trade can arrive
// with the full id from reconcile_pending and a truncated id from
// update_positions; either being a prefix of the other means same trade.
function tradeIdsMatch(a, b) {
  if (!a || !b) return false
  return a === b || a.startsWith(b) || b.startsWith(a)
}

export function useBots() {
  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(true)
  const { data: wsData, isConnected } = useWebSocket()

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/bots')
      if (!res.ok) throw new Error(await res.text())
      const json = await res.json()
      setBots(json.bots || [])
    } catch (err) {
      console.warn('useBots refresh:', err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, POLL_MS)
    return () => clearInterval(t)
  }, [refresh])

  // Apply WebSocket deltas immediately so the user sees state changes
  // without waiting for the next poll tick.
  useEffect(() => {
    if (!wsData) return
    if (wsData.event === 'bot_started' && wsData.bot) {
      setBots(prev => {
        const idx = prev.findIndex(b => b.bot_id === wsData.bot_id)
        if (idx >= 0) {
          const next = [...prev]; next[idx] = wsData.bot; return next
        }
        return [...prev, wsData.bot]
      })
    } else if (wsData.event === 'bot_stopped' && wsData.bot_id) {
      setBots(prev => prev.map(b =>
        b.bot_id === wsData.bot_id ? { ...b, status: 'stopped', bot_pid: null } : b
      ))
    } else if (wsData.event === 'bot_event' && wsData.bot_id) {
      setBots(prev => prev.map(b => {
        if (b.bot_id !== wsData.bot_id) return b
        const events = [...(b.events || []), wsData.data].slice(-200)
        let open_orders = b.open_orders || []
        let closed_orders = b.closed_orders || []
        const t = wsData.data?.type
        const d = wsData.data?.data || {}
        if (t === 'plan_opened') {
          // Dedup by trade_id (prefix-aware) so a re-sent open doesn't double
          // a row. MaiRuay sends 3 plan_opened events (one per entry, distinct
          // trade_id) under one plan_id — all three are kept; the Positions
          // view groups them back into a single plan row at render time.
          if (!open_orders.some(o => tradeIdsMatch(o?.trade_id, d.trade_id))) {
            open_orders = [...open_orders, d]
          }
        } else if (t === 'plan_closed' || t === 'plan_cancelled') {
          // Remove the specific entry by trade_id — NOT plan_id — so closing
          // one MaiRuay entry (or cancelling an unfilled LIMIT) doesn't evict
          // its still-open siblings. Fall back to plan_id only for legacy
          // single-entry events that carry no trade_id.
          open_orders = open_orders.filter(o =>
            d.trade_id ? !tradeIdsMatch(o?.trade_id, d.trade_id) : o?.plan_id !== d.plan_id
          )
          closed_orders = [...closed_orders, d].slice(-50)
        }
        return { ...b, events, open_orders, closed_orders }
      }))
    } else if (wsData.event === 'bot_synced' && wsData.bot_id && wsData.bot) {
      // Reconcile-driven hydration from LocalDB — replace open/closed lists wholesale.
      setBots(prev => prev.map(b => b.bot_id === wsData.bot_id ? wsData.bot : b))
    } else if (wsData.event === 'bot_heartbeat' && wsData.bot_id) {
      // Per-cycle snapshot from main.py — overwrites previous, doesn't add to events.
      setBots(prev => prev.map(b => b.bot_id === wsData.bot_id
        ? { ...b, heartbeat: wsData.data, cycle_count: wsData.cycle_count, last_updated: wsData.data?.ts || b.last_updated }
        : b
      ))
    } else if (wsData.event === 'emergency_stop') {
      // Refresh from server — too many state mutations to track from a single delta.
      refresh()
    }
  }, [wsData, refresh])

  const startBot = async (config) => {
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      const msg = body.detail || `HTTP ${res.status}`
      throw new Error(msg)
    }
    refresh()
    return body  // { bot_id, status, ... }
  }

  const stopBot = async (botId) => {
    const url = botId ? `/api/stop/${encodeURIComponent(botId)}` : '/api/stop'
    const res = await fetch(url, { method: 'POST' })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(body || `HTTP ${res.status}`)
    }
    refresh()
  }

  const emergencyStopAll = async () => {
    if (!confirm('🚨 Emergency Stop ALL bots? Closes every bot immediately.')) return
    await fetch('/api/emergency-stop', { method: 'POST' })
    refresh()
  }

  return { bots, loading, isConnected, startBot, stopBot, emergencyStopAll, refresh }
}
