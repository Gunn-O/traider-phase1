import { useEffect, useState } from 'react'

/**
 * Compact MT5 connection + portfolio panel.
 * Polls /api/mt5-status every 5s. Renders connection dot, account login,
 * balance / equity / floating P/L / margin, plus number of open positions
 * reported by MT5 itself (not the bot's view).
 */
export default function MT5StatusCard() {
  const [data, setData] = useState(null)
  const [lastFetch, setLastFetch] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const r = await fetch('/api/mt5-status')
        const j = await r.json()
        if (!alive) return
        setData(j)
        setLastFetch(new Date())
        setError(j.connected ? null : (j.error || 'not connected'))
      } catch (e) {
        if (!alive) return
        setError(`fetch failed: ${e.message}`)
      }
    }
    poll()
    const t = setInterval(poll, 5000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const ok = data?.connected
  const acc = data?.account
  const sym = data?.symbol

  return (
    <div className="card mt5-card">
      <div className="card-header">
        <h2 className="card-title">
          <span className={`status-dot ${ok ? 'status-ok' : 'status-err'}`}></span>
          MT5 {ok ? 'Connected' : 'Disconnected'}
        </h2>
        {lastFetch && (
          <span className="text-muted text-mono" style={{ fontSize: 11 }}>
            {lastFetch.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        )}
      </div>

      {error && <div className="mt5-error">⚠️ {error}</div>}

      {ok && acc && (
        <div className="mt5-grid">
          <Stat label="Account" value={`${acc.login}`} sub={acc.server} />
          <Stat label="Mode" value={acc.trade_mode === 2 ? 'REAL' : acc.trade_mode === 0 ? 'Demo' : 'Contest'} sub={`${acc.leverage}:1`} />
          <Stat label="Balance" value={`${fmt(acc.balance)}`} sub={acc.currency} />
          <Stat label="Equity" value={`${fmt(acc.equity)}`} sub={fmtPnl(acc.profit)} pnlClass={acc.profit} />
          <Stat label="Margin used" value={`${fmt(acc.margin)}`} sub={acc.margin_level != null ? `${acc.margin_level.toFixed(0)}%` : '—'} />
          <Stat label="Free margin" value={`${fmt(acc.margin_free)}`} sub={`${acc.positions_count ?? '—'} pos`} />
        </div>
      )}

      {ok && sym && (
        <div className="mt5-symbol-line">
          <span className="text-muted">{sym.name}</span>
          <span className="text-mono">bid <strong className="loss">{fmt(sym.bid)}</strong></span>
          <span className="text-mono">ask <strong className="profit">{fmt(sym.ask)}</strong></span>
          <span className="text-mono text-muted">sp {sym.spread_pip}p</span>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, sub, pnlClass }) {
  let subClass = 'text-muted'
  if (pnlClass != null && Number.isFinite(pnlClass)) {
    subClass = pnlClass > 0 ? 'profit' : pnlClass < 0 ? 'loss' : 'text-muted'
  }
  return (
    <div className="stat-item">
      <div className="stat-label">{label}</div>
      <div className="stat-value text-mono">{value ?? '—'}</div>
      {sub != null && <div className={`stat-sub ${subClass}`}>{sub}</div>}
    </div>
  )
}

function fmt(v) {
  if (v === null || v === undefined) return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(2)
}

function fmtPnl(v) {
  if (v === null || v === undefined) return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}
