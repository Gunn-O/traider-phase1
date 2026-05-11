import { useEffect, useMemo, useState } from 'react'
import { useTicks } from '../hooks/useTicks'
import './Dashboard.css'

export default function Dashboard({ bots, onStop }) {
  const [filterBotId, setFilterBotId] = useState('') // '' = all bots

  const visibleBots = useMemo(
    () => filterBotId ? bots.filter(b => b.bot_id === filterBotId) : bots,
    [bots, filterBotId]
  )

  // Aggregate signal events across the visible bots, newest first
  const signalEvents = useMemo(() => {
    const all = []
    for (const b of visibleBots) {
      for (const e of (b.events || [])) {
        if (e.type === 'signal_detected' || e.type === 'signal_skipped') {
          all.push({ ...e, bot_id: b.bot_id, tf: b.tf })
        }
      }
    }
    return all.sort((a, b) => (b.ts || '').localeCompare(a.ts || '')).slice(0, 30)
  }, [visibleBots])

  const openOrders = useMemo(() => {
    const all = []
    for (const b of visibleBots) {
      for (const o of (b.open_orders || [])) {
        all.push({ ...o, bot_id: b.bot_id, tf: b.tf })
      }
    }
    return all
  }, [visibleBots])

  const closedOrders = useMemo(() => {
    const all = []
    for (const b of visibleBots) {
      for (const o of (b.closed_orders || [])) {
        all.push({ ...o, bot_id: b.bot_id, tf: b.tf })
      }
    }
    return all.slice(-30).reverse()
  }, [visibleBots])

  return (
    <div className="dashboard">
      <TickerBar bots={visibleBots} />

      <RunningBotsTable
        bots={bots}
        onStop={onStop}
        filterBotId={filterBotId}
        onFilterChange={setFilterBotId}
      />

      <div className="dashboard-row">
        <LiveSnapshotPanel bots={visibleBots} />
      </div>

      <div className="dashboard-row">
        <SignalEventsPanel events={signalEvents} />
      </div>

      <div className="dashboard-row dashboard-row-split">
        <OpenOrdersPanel orders={openOrders} />
        <ClosedOrdersPanel orders={closedOrders} />
      </div>
    </div>
  )
}

function RunningBotsTable({ bots, onStop, filterBotId, onFilterChange }) {
  const [busyId, setBusyId] = useState('')

  const handleStop = async (botId) => {
    if (!confirm(`Stop bot ${botId}?`)) return
    setBusyId(botId)
    try { await onStop(botId) } finally { setBusyId('') }
  }

  const sorted = [...bots].sort((a, b) => {
    if (a.status !== b.status) return a.status === 'running' ? -1 : 1
    return (a.bot_id || '').localeCompare(b.bot_id || '')
  })

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Bots</h2>
        {bots.length > 0 && (
          <div className="filter-pills">
            <button
              className={`filter-pill ${filterBotId === '' ? 'active' : ''}`}
              onClick={() => onFilterChange('')}
            >
              All ({bots.length})
            </button>
            {bots.map(b => (
              <button
                key={b.bot_id}
                className={`filter-pill ${filterBotId === b.bot_id ? 'active' : ''}`}
                onClick={() => onFilterChange(b.bot_id)}
              >
                {b.bot_id}
              </button>
            ))}
          </div>
        )}
      </div>

      {bots.length === 0 ? (
        <div className="empty-state">No bots — pick a TF and click + Add Bot</div>
      ) : (
        <table className="bots-table">
          <thead>
            <tr>
              <th>Bot</th>
              <th>TF</th>
              <th>Mode</th>
              <th>Symbol</th>
              <th>Status</th>
              <th>PID</th>
              <th>Started</th>
              <th>Last cycle</th>
              <th>Cycles</th>
              <th>Open</th>
              <th>Closed</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(b => (
              <tr key={b.bot_id} className={`bot-row ${b.status}`}>
                <td className="text-mono">{b.bot_id}</td>
                <td>{b.tf}</td>
                <td>{b.mode}</td>
                <td>{b.symbol}</td>
                <td>
                  <span className={`badge ${b.status === 'running' ? 'success' : 'error'}`}>
                    {b.status}
                  </span>
                </td>
                <td className="text-mono text-muted">{b.bot_pid ?? '—'}</td>
                <td className="text-mono text-muted">{fmtTime(b.started_at)}</td>
                <td className="text-mono"><AgoBadge ts={b.heartbeat?.ts || b.last_updated} /></td>
                <td className="text-mono">{b.cycle_count ?? 0}</td>
                <td className="text-mono">{(b.open_orders || []).length}</td>
                <td className="text-mono">{(b.closed_orders || []).length}</td>
                <td>
                  {b.status === 'running' && (
                    <button
                      className="btn-tiny btn-tiny-stop"
                      onClick={() => handleStop(b.bot_id)}
                      disabled={busyId === b.bot_id}
                    >
                      {busyId === b.bot_id ? '…' : 'Stop'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function TickerBar({ bots }) {
  // Re-render every 1s so "X seconds ago" stays fresh between WS ticks.
  const [, setNowTick] = useState(0)
  useTick(() => setNowTick(n => n + 1), 1000)

  const { ticks, isConnected } = useTicks()
  const symbols = useMemo(
    () => Array.from(new Set(bots.filter(b => b.status === 'running').map(b => b.symbol))),
    [bots]
  )
  if (symbols.length === 0) return null

  return (
    <div className="ticker-bar">
      <span className="ticker-label">📡 Live</span>
      {symbols.map(sym => {
        const t = ticks[sym]
        if (!t) return (
          <span key={sym} className="ticker-cell ticker-empty">
            <span className="ticker-symbol">{sym}</span>
            <span className="text-muted">waiting…</span>
          </span>
        )
        const ageSec = Math.max(0, Math.floor((Date.now() - new Date(t.ts).getTime()) / 1000))
        const ageClass = ageSec < 5 ? 'profit' : ageSec < 15 ? 'warning' : 'loss'
        return (
          <span key={sym} className="ticker-cell">
            <span className="ticker-symbol">{sym}</span>
            <span className="ticker-bid">bid <strong>{fmt(t.bid, 2)}</strong></span>
            <span className="ticker-ask">ask <strong>{fmt(t.ask, 2)}</strong></span>
            <span className="ticker-spread text-muted">sp {fmt(t.spread_pip, 1)}p</span>
            <span className={`ticker-age ${ageClass}`}>{ageSec}s</span>
          </span>
        )
      })}
      {!isConnected && <span className="ticker-disconnected">⚠️ WS off</span>}
    </div>
  )
}

function LiveSnapshotPanel({ bots }) {
  // Re-render every 2s so AgoBadge / "X seconds ago" stays fresh even when no
  // new heartbeat arrived. Cheap — just a state bump.
  const [, setNowTick] = useState(0)
  useTick(() => setNowTick(n => n + 1), 2000)

  const runningBots = bots.filter(b => b.status === 'running')
  return (
    <div className="card">
      <h2 className="card-title">
        Live Snapshot {runningBots.length > 0 && <span className="muted-count">({runningBots.length})</span>}
      </h2>
      {runningBots.length === 0 ? (
        <div className="empty-state">No running bots</div>
      ) : (
        <table className="orders-table">
          <thead>
            <tr>
              <th>Bot</th>
              <th>Last cycle</th>
              <th>Candle</th>
              <th>Close</th>
              <th>R55 (pip)</th>
              <th>Session</th>
              <th>State</th>
              <th>Active plan</th>
            </tr>
          </thead>
          <tbody>
            {runningBots.map(b => {
              const hb = b.heartbeat || {}
              const state = hb.signal_pattern
                ? `${hb.signal_pattern} ${hb.signal_direction || ''}${hb.signal_rr ? ` R:R=${fmt(hb.signal_rr, 2)}` : ''}`
                : (hb.skip_reason || hb.chart_type || '—')
              const stateClass = hb.signal_pattern ? 'success' : (hb.chart_type === 'unclear' ? 'text-muted' : 'warning')
              const skipReasons = hb.skip_reasons || {}
              const skipPairs = Object.entries(skipReasons)
              return (
                <tr key={b.bot_id}>
                  <td className="text-mono">{b.bot_id}</td>
                  <td><AgoBadge ts={hb.ts || b.last_updated} /></td>
                  <td className="text-mono text-muted">{fmtTime(hb.candle_time)}</td>
                  <td className="text-mono">{fmt(hb.candle_close)}</td>
                  <td className="text-mono">{fmt(hb.R55_pip, 0)}</td>
                  <td className="text-mono text-muted">{hb.session || '—'}</td>
                  <td className={stateClass}>
                    {state}
                    {skipPairs.length > 0 && (
                      <div className="skip-reasons">
                        {skipPairs.map(([pat, reason]) => (
                          <div key={pat} className="skip-reason-row">
                            <span className="skip-pattern text-muted">{pat}:</span>{' '}
                            <span className="skip-text">{reason}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="text-mono text-muted">{shortPlanId(hb.active_plan) || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

function AgoBadge({ ts }) {
  if (!ts) return <span className="text-muted">—</span>
  const now = Date.now()
  const then = new Date(ts).getTime()
  if (!Number.isFinite(then)) return <span className="text-muted">—</span>
  const sec = Math.max(0, Math.floor((now - then) / 1000))
  let label, cls
  if (sec < 5) { label = 'just now'; cls = 'profit' }
  else if (sec < 90) { label = `${sec}s ago`; cls = 'profit' }
  else if (sec < 300) { label = `${Math.floor(sec / 60)}m ago`; cls = 'warning' }
  else { label = `${Math.floor(sec / 60)}m ago`; cls = 'loss' }
  return <span className={cls}>{label}</span>
}

// Stable interval hook so panels can self-tick without props
function useTick(callback, ms) {
  useEffect(() => {
    const t = setInterval(callback, ms)
    return () => clearInterval(t)
  }, [ms, callback])
}

function SignalEventsPanel({ events }) {
  return (
    <div className="card">
      <h2 className="card-title">Signal Events {events.length > 0 && <span className="muted-count">({events.length})</span>}</h2>
      {events.length === 0 ? (
        <div className="empty-state">No signals yet — bots will report SIGNAL/SKIP here</div>
      ) : (
        <div className="event-list">
          {events.map((e, i) => (
            <div key={i} className={`event-item event-${e.type}`}>
              <span className="event-time text-mono text-muted">{fmtTime(e.ts)}</span>
              <span className="event-bot text-mono">{e.bot_id}</span>
              <span className={`event-type badge ${e.type === 'signal_detected' ? 'success' : 'warning'}`}>
                {e.type === 'signal_detected' ? 'SIGNAL' : 'SKIP'}
              </span>
              <span className="event-msg">{e.msg}</span>
              {e.type === 'signal_detected' && e.data && (
                <span className="event-extra text-mono text-muted">
                  {e.data.direction} entry={fmt(e.data.entry)} sl={fmt(e.data.sl)} tp={fmt(e.data.tp)} R:R={fmt(e.data.rr, 2)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function OpenOrdersPanel({ orders }) {
  return (
    <div className="card">
      <h2 className="card-title">Open Positions {orders.length > 0 && <span className="muted-count">({orders.length})</span>}</h2>
      {orders.length === 0 ? (
        <div className="empty-state">No open positions</div>
      ) : (
        <table className="orders-table">
          <thead>
            <tr>
              <th>Bot</th>
              <th>Plan</th>
              <th>Action</th>
              <th>Entry</th>
              <th>SL</th>
              <th>TP</th>
              <th>Lot</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o, i) => (
              <tr key={i}>
                <td className="text-mono text-muted">{o.bot_id}</td>
                <td className="text-mono text-muted">{shortPlanId(o.plan_id)}</td>
                <td>
                  <span className={`badge ${o.action === 'BUY' ? 'success' : 'warning'}`}>{o.action}</span>
                </td>
                <td className="text-mono">{fmt(o.entry)}</td>
                <td className="text-mono">{fmt(o.sl)}</td>
                <td className="text-mono">{fmt(o.tp)}</td>
                <td className="text-mono">{o.lot}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function ClosedOrdersPanel({ orders }) {
  return (
    <div className="card">
      <h2 className="card-title">Recently Closed {orders.length > 0 && <span className="muted-count">({orders.length})</span>}</h2>
      {orders.length === 0 ? (
        <div className="empty-state">No closed positions yet</div>
      ) : (
        <table className="orders-table">
          <thead>
            <tr>
              <th>Bot</th>
              <th>Plan</th>
              <th>Result</th>
              <th>Reason</th>
              <th>Close</th>
              <th>P/L</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o, i) => (
              <tr key={i}>
                <td className="text-mono text-muted">{o.bot_id}</td>
                <td className="text-mono text-muted">{shortPlanId(o.plan_id)}</td>
                <td>
                  <span className={`badge ${o.result === 'WIN' ? 'success' : 'error'}`}>{o.result}</span>
                </td>
                <td className="text-muted">{o.close_reason}</td>
                <td className="text-mono">{fmt(o.close_price)}</td>
                <td className={`text-mono ${(o.pnl || 0) >= 0 ? 'profit' : 'loss'}`}>
                  {(o.pnl || 0) >= 0 ? '+' : ''}{fmt(o.pnl, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function fmt(v, digits = 2) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function fmtTime(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return iso }
}

function shortPlanId(id) {
  if (!id) return '—'
  // PT-PLAN-20260510-143030-001 → 14:30:30
  const m = String(id).match(/(\d{2})(\d{2})(\d{2})-?(\d+)?$/)
  return m ? `${m[1]}:${m[2]}:${m[3]}` : id.slice(-12)
}
