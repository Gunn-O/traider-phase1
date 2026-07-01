import { useEffect, useState } from 'react'
import { OFFICE_AGENTS } from './agents'

// useAgents — overlays LIVE status/metrics/log onto the static office roster.
// Pipeline agents read from the running bots (passed in); off-cycle + infra
// agents poll their REST endpoints. Everything degrades gracefully to the
// static defaults / STANDBY when no data is available.
export function useAgents(bots = []) {
  const [aux, setAux] = useState({ logs: {}, costs: {}, mt5: null })

  useEffect(() => {
    let alive = true
    const load = async () => {
      const out = { logs: {}, costs: {}, mt5: null }
      try {
        const r = await fetch('/api/agent-logs'); if (r.ok) out.logs = await r.json()
      } catch { /* ignore */ }
      try {
        const r = await fetch('/api/agent-costs'); if (r.ok) out.costs = await r.json()
      } catch { /* ignore */ }
      try {
        const r = await fetch('/api/mt5-status'); if (r.ok) out.mt5 = await r.json()
      } catch { /* ignore */ }
      if (alive) setAux(out)
    }
    load()
    const t = setInterval(load, 15000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const running = bots.filter((b) => b.status === 'running')
  const cycles = bots.reduce((s, b) => s + (b.cycle_count || 0), 0)
  const mode = running[0]?.mode || '—'

  // Most recent heartbeat across running bots (for Signal Engine state).
  const hb = running
    .map((b) => b.heartbeat)
    .filter(Boolean)
    .sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || '')))[0] || {}

  const signalCount = bots.reduce(
    (s, b) => s + (b.events || []).filter((e) => e.type === 'signal_detected').length, 0
  )

  const lastLog = (key) => {
    const arr = aux.logs?.[key]
    if (Array.isArray(arr) && arr.length) {
      const l = arr[arr.length - 1]
      return { ts: l.timestamp || l.ts || '', count: arr.length, msg: l.message || l.summary || '' }
    }
    return { ts: '', count: 0, msg: '' }
  }
  const cost = (key) => {
    const c = aux.costs?.[key]
    return c ? `$${Number(c.total_cost || 0).toFixed(2)}` : '$0'
  }

  const agents = OFFICE_AGENTS.map((base) => {
    const a = { ...base, metrics: base.metrics.map((m) => ({ ...m })) }
    const anyRunning = running.length > 0

    if (base.live === 'pipeline') {
      if (base.id === 'supervisor') {
        a.status = anyRunning ? 'active' : 'idle'
        a.metrics[0].v = String(running.length)
        a.metrics[1].v = String(cycles)
        a.metrics[2].v = mode
        a.log = anyRunning ? `DISPATCH · ${running.length} bot(s) · mode ${mode}` : 'STANDBY · ยังไม่มีบอททำงาน'
      } else if (base.id === 'analyst') {
        a.status = anyRunning ? 'active' : 'idle'
        a.metrics[0].v = hb.signal_pattern || '—'
        a.metrics[1].v = String(signalCount)
        a.metrics[2].v = hb.signal_rr ? Number(hb.signal_rr).toFixed(2) : '—'
        a.log = hb.signal_pattern
          ? `${hb.signal_pattern} ${hb.signal_direction || ''} @ ${hb.candle_close ?? '—'}`
          : (anyRunning ? `SCAN · ${hb.session || 'session'} · R55 ${hb.R55_pip ?? '—'}` : 'STANDBY · รอ candle ปิด')
      } else if (base.id === 'risk_manager') {
        a.status = anyRunning ? 'active' : 'idle'
        a.log = anyRunning ? 'ALLOW · Python guardian active' : 'STANDBY · Python rules'
      } else if (base.id === 'notify') {
        const liveMode = running.some((b) => b.mode === 'live' || b.mode === 'micro')
        a.status = anyRunning ? 'active' : 'idle'
        a.metrics[2].v = liveMode ? 'ON' : 'SIM'
        a.log = anyRunning ? `LINE dispatch · ${mode}` : 'STANDBY · LINE_NOTIFY ตาม .env'
      }
    } else if (base.live === 'offcycle') {
      const key = base.id === 'weekly' ? 'weekly' : 'monthly'
      const l = lastLog(key)
      a.status = l.count > 0 ? 'review' : 'idle'
      a.metrics[0].v = l.ts ? new Date(l.ts).toLocaleDateString() : '—'
      a.metrics[1].v = String(l.count)
      a.metrics[2].v = cost(key)
      a.log = l.msg ? `${l.msg}`.slice(0, 80) : base.log
    } else if (base.live === 'infra') {
      const m = aux.mt5
      const up = m?.connected
      a.status = up ? 'active' : 'idle'
      a.metrics[0].v = up ? 'UP' : 'DOWN'
      a.metrics[1].v = m?.account?.equity != null ? `$${Math.round(m.account.equity)}` : '—'
      a.metrics[2].v = String(m?.account?.positions_count ?? 0)
      a.log = up
        ? `OK · MT5 build ${m?.terminal?.build ?? '—'} · ${m?.symbol?.name || ''} ${m?.symbol?.bid ?? ''}`
        : (m?.error ? `DOWN · ${m.error}` : 'STANDBY · checking MT5…')
    } else {
      // disabled — always STANDBY (news_agent reviewer / reflector off-cycle)
      a.status = 'idle'
    }
    return a
  })

  return agents
}

export default useAgents
