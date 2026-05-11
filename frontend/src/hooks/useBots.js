import { useState, useEffect, useCallback } from 'react'
import { useWebSocket } from './useWebSocket'

const POLL_MS = 3000

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
        if (t === 'plan_opened') {
          open_orders = [...open_orders, wsData.data.data || {}]
        } else if (t === 'plan_closed') {
          const planId = wsData.data?.data?.plan_id
          open_orders = open_orders.filter(o => o?.plan_id !== planId)
          closed_orders = [...closed_orders, wsData.data.data || {}].slice(-50)
        }
        return { ...b, events, open_orders, closed_orders }
      }))
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
