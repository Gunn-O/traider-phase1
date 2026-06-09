import { useEffect, useMemo, useState } from 'react'
import { useTicks } from '../hooks/useTicks'
import MT5StatusCard from '../components/MT5StatusCard'
import ChartPanel from '../components/ChartPanel'
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

  // trade_id format is `RT-YYYYMMDD-HHMMSS-XXXXXX-N` (or PT/SM/ prefix in
  // backtest/sim modes), so sorting by trade_id string descending puts the
  // newest order on top AND keeps multi-day history in correct order — which
  // ISO time-only fields can't guarantee when bots run across midnight.
  const _orderKey = (o) =>
    String(o.trade_id || o.plan_id || o.open_time || o.candle_time || '')

  const openOrders = useMemo(() => {
    const all = []
    for (const b of visibleBots) {
      for (const o of (b.open_orders || [])) {
        all.push({ ...o, bot_id: b.bot_id, tf: b.tf })
      }
    }
    return all.sort((a, b) => _orderKey(b).localeCompare(_orderKey(a)))
  }, [visibleBots])

  const closedOrders = useMemo(() => {
    const all = []
    for (const b of visibleBots) {
      for (const o of (b.closed_orders || [])) {
        all.push({ ...o, bot_id: b.bot_id, tf: b.tf })
      }
    }
    return all.sort((a, b) => _orderKey(b).localeCompare(_orderKey(a))).slice(0, 30)
  }, [visibleBots])

  return (
    <div className="dashboard">
      <TickerBar bots={visibleBots} />

      <div className="dashboard-row dashboard-row-split-2-3">
        <MT5StatusCard />
        <ChartPanel bots={visibleBots} />
      </div>

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

      <div className="dashboard-row">
        <PositionsPanel open={openOrders} closed={closedOrders} />
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

// Single unified Positions panel — Open rows on top with PENDING status,
// Closed rows below with WIN/LOSS/CANCELLED, both sorted by open_time desc.
// Body scrolls after ~10 rows; section headers visually separate the two.
function PositionsPanel({ open, closed }) {
  // Both lists already arrive sorted by time desc (Dashboard() useMemo);
  // re-sort closed by OPEN_TIME explicitly so the user's requested ordering
  // ("ปิดแล้วก็เรียงตามเวลาเปิด") holds even if close_time is what came in
  // from plan_closed events.
  const closedByOpenTime = [...closed].sort((a, b) =>
    String(b.open_time || b.plan_id || '')
      .localeCompare(String(a.open_time || a.plan_id || ''))
  )

  return (
    <div className="card">
      <h2 className="card-title">
        Positions{' '}
        <span className="muted-count">
          ({open.length} open · {closedByOpenTime.length} closed)
        </span>
      </h2>
      {open.length === 0 && closedByOpenTime.length === 0 ? (
        <div className="empty-state">No positions yet</div>
      ) : (
        <div className="positions-scroll">
          <table className="orders-table positions-table">
            <thead>
              <tr>
                <th>Open Time</th>
                <th>Bot</th>
                <th>Strategy</th>
                <th>Dir</th>
                <th>Entry</th>
                <th>SL</th>
                <th>TP</th>
                <th>Lot</th>
                <th>Close</th>
                <th>P/L</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {open.length > 0 && (
                <tr className="positions-section">
                  <td colSpan={11}>
                    <span className="positions-section-label">OPEN</span>
                    <span className="positions-section-count">{open.length}</span>
                  </td>
                </tr>
              )}
              {open.map((o, i) => (
                <PositionRow key={`o-${o.trade_id || o.plan_id || i}`} order={o} isOpen />
              ))}
              {closedByOpenTime.length > 0 && (
                <tr className="positions-section">
                  <td colSpan={11}>
                    <span className="positions-section-label">CLOSED</span>
                    <span className="positions-section-count">{closedByOpenTime.length}</span>
                  </td>
                </tr>
              )}
              {closedByOpenTime.map((o, i) => (
                <PositionRow key={`c-${o.trade_id || o.plan_id || i}`} order={o} isOpen={false} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function PositionRow({ order: o, isOpen }) {
  const result = isOpen ? 'PENDING' : (o.result || '—')
  const badgeCls = isOpen
    ? 'warning'
    : result === 'WIN'  ? 'success'
    : result === 'LOSS' ? 'error'
    : 'info'   // CANCELLED / other terminal but non-trade outcomes
  const dirCls = o.action === 'BUY' ? 'success' : 'warning'
  const openTime = fmtDateTime(o.open_time || o.candle_time) || planIdTime(o.plan_id)
  // Hover tooltip with full plan_id + trade_id for debugging; removed
  // the dedicated Plan column because shortPlanId rendered it as time,
  // which duplicated the Open Time column.
  const rowTitle = [
    o.plan_id ? `plan: ${o.plan_id}` : null,
    o.trade_id ? `trade: ${o.trade_id}` : null,
  ].filter(Boolean).join('\n')
  return (
    <tr title={rowTitle}>
      <td className="text-mono text-muted">{openTime}</td>
      <td className="text-mono text-muted">{o.bot_id || '—'}</td>
      <td className="text-mono">{shortPattern(o.pattern || o.chart_type)}</td>
      <td><span className={`badge ${dirCls}`}>{o.action || '—'}</span></td>
      <td className="text-mono">{fmt(o.entry)}</td>
      <td className="text-mono">{fmt(o.sl)}</td>
      <td className="text-mono">{fmt(o.tp)}</td>
      <td className="text-mono">{fmt(o.lot, 2)}</td>
      <td className="text-mono">{isOpen ? '—' : fmt(o.close_price)}</td>
      <td className={`text-mono ${isOpen ? 'text-muted' : ((o.pnl || 0) >= 0 ? 'profit' : 'loss')}`}>
        {isOpen ? '—' : `${(o.pnl || 0) >= 0 ? '+' : ''}${fmt(o.pnl, 2)}`}
      </td>
      <td><span className={`badge ${badgeCls}`}>{result}</span></td>
    </tr>
  )
}

// Short, readable strategy label. Events send the raw signal.pattern
// (`UPTREND_SCANNER`, `DOWNTREND_SCANNER`, `MOUNTAIN`, `MAI_RUAY`); DB
// hydration uses chart_type (`uptrend`, `downtrend`, `mountain`, `mai_ruay`).
// Match prefixes so both forms render identically.
function shortPattern(p) {
  if (!p) return '—'
  const u = String(p).toUpperCase()
  if (u.startsWith('UPTREND'))   return 'Uptrend'
  if (u.startsWith('DOWNTREND')) return 'Downtrend'
  if (u.startsWith('MOUNTAIN'))  return 'Mountain'
  if (u.startsWith('MAI_RUAY') || u.startsWith('MAIRUAY')) return 'MaiRuay'
  return u
}

// Extract HH:MM:SS from a plan_id like "RT-PLAN-20260512-153700-000000"
// when no explicit open_time / close_time is attached to the order.
function planIdTime(id) {
  if (!id) return ''
  const m = String(id).match(/(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/)
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}` : ''
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

// Compact date+time for the Positions panel — sort key is trade_id (which
// encodes the date), but the Open Time column previously showed only HH:MM:SS
// which made multi-day history look out of order to the eye.
function fmtDateTime(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    return `${mm}-${dd} ${hh}:${mi}:${ss}`
  } catch { return iso }
}

function shortPlanId(id) {
  if (!id) return '—'
  // PT-PLAN-20260510-143030-001 → 14:30:30
  const m = String(id).match(/(\d{2})(\d{2})(\d{2})-?(\d+)?$/)
  return m ? `${m[1]}:${m[2]}:${m[3]}` : id.slice(-12)
}
