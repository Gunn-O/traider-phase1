import { useState, useEffect, useMemo, useCallback, Fragment } from 'react'
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell,
} from 'recharts'

const API = 'http://127.0.0.1:8080'

// Command Deck cyberpunk palette — real hex (NOT CSS var()) because recharts
// renders stroke/fill as SVG presentation attributes, where var() is invalid.
// Values mirror command-deck.css :root tokens so the page matches the theme.
const COLOR = {
  bg:       '#05080f',                    // --bg
  card:     '#0c1322',                    // --panel-2
  hover:    '#0e1526',                    // panel hover
  border:   'rgba(120,160,220,0.14)',     // --line
  text:     '#d6e3f7',                    // --text
  muted:    '#6f819f',                    // --muted
  green:    '#34e5a3',                    // --c-green
  red:      '#ff5274',                    // --c-red
  yellow:   '#f5c451',                    // --c-gold
  blue:     '#22d8ee',                    // --c-cyan
  pink:     '#ff2e9a',                    // --c-magenta
}

const todayIso = () => new Date().toISOString().slice(0, 10)
const daysAgoIso = (d) => new Date(Date.now() - d * 86400000).toISOString().slice(0, 10)

const fmt = (v, n = 2) => {
  if (v === null || v === undefined || v === '') return '—'
  const x = Number(v)
  return Number.isFinite(x) ? x.toFixed(n) : '—'
}

const fmtSignedUsd = (v) => {
  if (v === null || v === undefined) return '—'
  const x = Number(v)
  if (!Number.isFinite(x)) return '—'
  return `${x >= 0 ? '+' : ''}$${x.toFixed(2)}`
}

const fmtTime = (iso) => {
  if (!iso) return '—'
  return String(iso).slice(0, 16).replace('T', ' ')
}

const resultColor = (r) => r === 'WIN' ? COLOR.green : r === 'LOSS' ? COLOR.red : COLOR.muted

export default function TradeHistory() {
  // ── Filters ─────────────────────────────────────────
  const [from, setFrom] = useState(daysAgoIso(30))
  const [to,   setTo]   = useState(todayIso())
  const [mode, setMode] = useState('all')
  const [pattern, setPattern] = useState('all')

  // ── Data ────────────────────────────────────────────
  const [trades, setTrades] = useState([])
  const [stats,  setStats]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const qs = new URLSearchParams({ from, to, mode, pattern }).toString()
      const [tRes, sRes] = await Promise.all([
        fetch(`${API}/api/trades?${qs}`),
        fetch(`${API}/api/trades/stats?${qs}`),
      ])
      if (!tRes.ok || !sRes.ok) throw new Error(`HTTP ${tRes.status}/${sRes.status}`)
      const tJson = await tRes.json()
      const sJson = await sRes.json()
      setTrades(tJson.trades || [])
      setStats(sJson)
    } catch (e) {
      setError(e.message || String(e))
      setTrades([])
      setStats(null)
    } finally {
      setLoading(false)
    }
  }, [from, to, mode, pattern])

  useEffect(() => { fetchAll() }, [fetchAll, refreshKey])

  const applyPreset = (label) => {
    const now = todayIso()
    if (label === 'Today')      { setFrom(now); setTo(now) }
    if (label === 'This Week')  { setFrom(daysAgoIso(7));  setTo(now) }
    if (label === 'This Month') { setFrom(daysAgoIso(30)); setTo(now) }
    if (label === 'All Time')   { setFrom('2020-01-01');   setTo(now) }
  }

  const exportCsv = () => {
    if (!trades.length) return
    const cols = ['trade_id','plan_id','open_time','close_time','symbol','timeframe',
                  'direction','pattern','lot','entry_price','sl_price','tp_price',
                  'close_price','result','pnl_usd','pnl_pip','rr_actual','rr_planned',
                  'session','mode','mae_pip','mfe_pip','r55_pip_at_open','claude_confidence']
    const csv = [cols.join(',')]
    for (const t of trades) {
      csv.push(cols.map(c => {
        const v = t[c]
        if (v === null || v === undefined) return ''
        const s = String(v).replace(/"/g, '""')
        return /[,"\n]/.test(s) ? `"${s}"` : s
      }).join(','))
    }
    const blob = new Blob([csv.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trades_${from}_${to}_${mode}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ padding: 24, maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600 }}>📊 Trade History</h1>
        <span style={{ color: COLOR.muted, fontSize: 12, fontFamily: 'monospace' }}>
          {loading ? 'loading…' : `${trades.length} trades`}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button onClick={() => setRefreshKey(k => k + 1)}
            style={btnSecondary}>↻ Refresh</button>
          <button onClick={exportCsv} disabled={!trades.length}
            style={{ ...btnSecondary, opacity: trades.length ? 1 : 0.4 }}>
            ⬇ Export CSV
          </button>
        </div>
      </div>

      <FiltersBar
        from={from} to={to} mode={mode} pattern={pattern}
        setFrom={setFrom} setTo={setTo} setMode={setMode} setPattern={setPattern}
        applyPreset={applyPreset} applyFilters={() => setRefreshKey(k => k + 1)}
      />

      {error && <ErrorBox message={error} />}

      {loading && !stats ? (
        <SkeletonGrid />
      ) : !stats || stats.total_trades === 0 ? (
        <EmptyState from={from} to={to} mode={mode} />
      ) : (
        <>
          <SummaryGrid stats={stats} />
          <RiskPanel stats={stats} />
          <ChartRow stats={stats} />
          <PatternBreakdown stats={stats} />
          <TradeTable trades={trades} />
        </>
      )}
    </div>
  )
}

// ─── Filters ──────────────────────────────────────────────────────
const inputStyle = {
  background: COLOR.hover, border: `1px solid ${COLOR.border}`,
  borderRadius: 6, padding: '8px 12px', color: COLOR.text, fontSize: 13,
}
const btnSecondary = {
  background: COLOR.hover, border: `1px solid ${COLOR.border}`,
  borderRadius: 6, padding: '6px 14px', color: COLOR.text, fontSize: 13,
  cursor: 'pointer', fontFamily: 'inherit',
}

function FiltersBar({ from, to, mode, pattern, setFrom, setTo, setMode, setPattern, applyPreset, applyFilters }) {
  return (
    <div style={{
      background: COLOR.card, border: `1px solid ${COLOR.border}`,
      borderRadius: 12, padding: 16, marginBottom: 20,
      display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap',
    }}>
      <FilterField label="From">
        <input type="date" value={from} onChange={e => setFrom(e.target.value)} style={inputStyle} />
      </FilterField>
      <FilterField label="To">
        <input type="date" value={to} onChange={e => setTo(e.target.value)} style={inputStyle} />
      </FilterField>
      <FilterField label="Mode">
        <select value={mode} onChange={e => setMode(e.target.value)} style={inputStyle}>
          <option value="all">All</option>
          <option value="paper">Paper</option>
          <option value="micro">Micro (Cent)</option>
          <option value="live">Live</option>
        </select>
      </FilterField>
      <FilterField label="Pattern">
        <select value={pattern} onChange={e => setPattern(e.target.value)} style={inputStyle}>
          <option value="all">All</option>
          <option value="mountain">Mountain</option>
          <option value="mai_ruay">MaiRuay</option>
          <option value="uptrend">Uptrend Scanner</option>
          <option value="downtrend">Downtrend Scanner</option>
        </select>
      </FilterField>

      <FilterField label="Quick">
        <div style={{ display: 'flex', gap: 6 }}>
          {['Today', 'This Week', 'This Month', 'All Time'].map(p => (
            <button key={p} onClick={() => applyPreset(p)} style={btnSecondary}>{p}</button>
          ))}
        </div>
      </FilterField>

      <button onClick={applyFilters}
        style={{
          background: COLOR.green, color: '#04070e', border: 'none',
          padding: '9px 22px', borderRadius: 6, fontSize: 13,
          fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
        }}>
        Apply
      </button>
    </div>
  )
}

function FilterField({ label, children }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: COLOR.muted, marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  )
}

// ─── Summary Cards ─────────────────────────────────────────────────
function SummaryGrid({ stats }) {
  const cards = [
    {
      title: 'Total / Win Rate',
      a: { label: 'Trades',   value: stats.total_trades, sub: `${stats.closed_trades} closed` },
      b: { label: 'Win Rate', value: `${fmt(stats.wr_pct, 1)}%`,
           color: stats.wr_pct >= 60 ? COLOR.green : stats.wr_pct >= 45 ? COLOR.yellow : COLOR.red,
           sub: `${stats.wins}W / ${stats.losses}L` },
    },
    {
      title: 'Net P&L',
      a: { label: 'USD', value: fmtSignedUsd(stats.total_pnl_usd),
           color: stats.total_pnl_usd >= 0 ? COLOR.green : COLOR.red },
      b: { label: 'Pip', value: `${stats.total_pnl_pip >= 0 ? '+' : ''}${fmt(stats.total_pnl_pip, 0)}`,
           color: stats.total_pnl_pip >= 0 ? COLOR.green : COLOR.red },
    },
    {
      title: 'Best / Worst',
      a: { label: 'Best',  value: stats.best_trade  ? fmtSignedUsd(stats.best_trade.pnl_usd)  : '—',
           color: COLOR.green, sub: stats.best_trade?.pattern || '' },
      b: { label: 'Worst', value: stats.worst_trade ? fmtSignedUsd(stats.worst_trade.pnl_usd) : '—',
           color: COLOR.red, sub: stats.worst_trade?.pattern || '' },
    },
    {
      title: 'Avg R:R',
      a: { label: 'Actual',  value: fmt(stats.avg_rr_actual,  2),
           color: stats.avg_rr_actual >= 1.5 ? COLOR.green : stats.avg_rr_actual >= 1.0 ? COLOR.yellow : COLOR.red,
           sub: 'wins only' },
      b: { label: 'Planned', value: fmt(stats.avg_rr_planned, 2),
           color: COLOR.blue, sub: 'all closed' },
    },
    {
      title: 'Max Drawdown',
      a: { label: '%',   value: `-${fmt(stats.max_drawdown_pct, 1)}%`,
           color: stats.max_drawdown_pct >= 30 ? COLOR.red : stats.max_drawdown_pct >= 15 ? COLOR.yellow : COLOR.muted },
      b: { label: 'USD', value: `-$${fmt(stats.max_drawdown_usd, 2)}`,
           color: stats.max_drawdown_pct >= 30 ? COLOR.red : stats.max_drawdown_pct >= 15 ? COLOR.yellow : COLOR.muted },
    },
    {
      title: 'Streaks',
      a: { label: 'Max Win',  value: stats.max_win_streak,  color: COLOR.green },
      b: { label: 'Max Loss', value: stats.max_loss_streak,
           color: stats.max_loss_streak >= 3 ? COLOR.red : stats.max_loss_streak >= 2 ? COLOR.yellow : COLOR.muted },
    },
  ]
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
      gap: 12, marginBottom: 20,
    }}>
      {cards.map(c => <DoubleCard key={c.title} {...c} />)}
    </div>
  )
}

function DoubleCard({ title, a, b }) {
  return (
    <div style={{
      background: COLOR.card, border: `1px solid ${COLOR.border}`,
      borderRadius: 12, padding: 16,
    }}>
      <div style={{
        fontSize: 11, color: COLOR.muted, letterSpacing: 1.5,
        textTransform: 'uppercase', marginBottom: 12,
      }}>
        {title}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <MiniStat {...a} />
        <MiniStat {...b} />
      </div>
    </div>
  )
}

function MiniStat({ label, value, sub, color }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: COLOR.muted, marginBottom: 4 }}>{label}</div>
      <div style={{
        fontSize: 20, fontWeight: 700, color: color || COLOR.text,
        fontFamily: 'monospace', lineHeight: 1.1,
      }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 10, color: COLOR.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

// ─── Risk Panel ────────────────────────────────────────────────────
function RiskPanel({ stats }) {
  const lossFromPeak = stats.peak_balance > 0
    ? (stats.peak_balance - stats.current_balance) / stats.peak_balance * 100
    : 0
  const lossClass = lossFromPeak >= 30 ? COLOR.red
                  : lossFromPeak >= 20 ? COLOR.yellow : COLOR.green
  const streakClass = stats.max_loss_streak >= 3 ? COLOR.red
                    : stats.max_loss_streak >= 2 ? COLOR.yellow : COLOR.muted

  const balanceDelta = stats.current_balance - stats.starting_balance
  const balanceClass = balanceDelta >= 0 ? COLOR.green : COLOR.red

  return (
    <div style={{
      background: COLOR.card, border: `1px solid ${COLOR.border}`,
      borderRadius: 12, padding: 16, marginBottom: 20,
    }}>
      <div style={{
        fontSize: 11, color: COLOR.muted, letterSpacing: 1.5,
        textTransform: 'uppercase', marginBottom: 14,
      }}>
        Risk Metrics
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16,
      }}>
        <RiskRow label="Current Balance" value={`$${fmt(stats.current_balance, 2)}`} sub={`Start $${fmt(stats.starting_balance, 0)}`} color={balanceClass} />
        <RiskRow label="P&L" value={fmtSignedUsd(balanceDelta)} sub={`${fmt(balanceDelta / stats.starting_balance * 100, 1)}%`} color={balanceClass} />
        <RiskRow label="Loss from Peak" value={`-${fmt(lossFromPeak, 1)}%`} sub={`Peak $${fmt(stats.peak_balance, 2)}`} color={lossClass} />
        <RiskRow label="Max Consec Loss" value={stats.max_loss_streak} sub="circuit @ 3" color={streakClass} />
        <RiskRow label="Max Drawdown" value={`-${fmt(stats.max_drawdown_pct, 1)}%`} sub={`-$${fmt(stats.max_drawdown_usd, 2)}`} color={stats.max_drawdown_pct >= 30 ? COLOR.red : COLOR.muted} />
      </div>
    </div>
  )
}

function RiskRow({ label, value, sub, color }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: COLOR.muted, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: color || COLOR.text, fontFamily: 'monospace' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: COLOR.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

// ─── Equity + Drawdown ──────────────────────────────────────────────
function ChartRow({ stats }) {
  const data = stats.equity_curve || []
  const minBal = Math.min(...data.map(d => d.balance), stats.starting_balance)
  const maxBal = Math.max(...data.map(d => d.balance), stats.starting_balance)
  const minDd  = Math.min(...data.map(d => d.drawdown_pct))

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
      gap: 16, marginBottom: 20,
    }}>
      <ChartCard title="Equity Curve">
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data}>
            <XAxis dataKey="t" hide />
            <YAxis
              domain={[minBal * 0.98, maxBal * 1.02]}
              tickFormatter={v => `$${Math.round(v)}`}
              tick={{ fill: COLOR.muted, fontSize: 11 }} width={70} />
            <Tooltip
              labelFormatter={fmtTime}
              formatter={(v, name) => name === 'balance' ? [`$${Number(v).toFixed(2)}`, 'Balance'] : [v, name]}
              contentStyle={{ background: COLOR.card, border: `1px solid ${COLOR.border}`, borderRadius: 6, fontSize: 12 }} />
            <ReferenceLine y={stats.starting_balance} stroke={COLOR.border} strokeDasharray="4 4" />
            <Line type="monotone" dataKey="balance" stroke={COLOR.green} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="Drawdown %">
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data}>
            <XAxis dataKey="t" hide />
            <YAxis
              domain={[Math.min(minDd, -50), 0]}
              tickFormatter={v => `${v.toFixed(0)}%`}
              tick={{ fill: COLOR.muted, fontSize: 11 }} width={50} />
            <Tooltip
              labelFormatter={fmtTime}
              formatter={(v) => [`${Number(v).toFixed(2)}%`, 'Drawdown']}
              contentStyle={{ background: COLOR.card, border: `1px solid ${COLOR.border}`, borderRadius: 6, fontSize: 12 }} />
            <ReferenceLine y={-30} stroke={COLOR.yellow} strokeDasharray="4 4"
              label={{ value: '-30% warn', fill: COLOR.yellow, fontSize: 10, position: 'insideTopLeft' }} />
            <ReferenceLine y={-50} stroke={COLOR.red}    strokeDasharray="4 4"
              label={{ value: '-50% stop', fill: COLOR.red, fontSize: 10, position: 'insideBottomLeft' }} />
            <Area type="monotone" dataKey="drawdown_pct" stroke={COLOR.red} fill={COLOR.red} fillOpacity={0.15} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  )
}

function ChartCard({ title, children }) {
  return (
    <div style={{
      background: COLOR.card, border: `1px solid ${COLOR.border}`,
      borderRadius: 12, padding: 16,
    }}>
      <div style={{
        fontSize: 11, color: COLOR.muted, letterSpacing: 1.5,
        textTransform: 'uppercase', marginBottom: 12,
      }}>
        {title}
      </div>
      {children}
    </div>
  )
}

// ─── Pattern breakdown (bar) ────────────────────────────────────────
function PatternBreakdown({ stats }) {
  const data = (stats.pattern_breakdown || []).map(d => ({
    pattern: d.pattern,
    wr: d.wr_pct,
    total: d.total,
    wins: d.wins,
    losses: d.losses,
    net: d.net_usd,
  }))
  if (!data.length) return null
  return (
    <div style={{
      background: COLOR.card, border: `1px solid ${COLOR.border}`,
      borderRadius: 12, padding: 16, marginBottom: 20,
    }}>
      <div style={{
        fontSize: 11, color: COLOR.muted, letterSpacing: 1.5,
        textTransform: 'uppercase', marginBottom: 12,
      }}>
        Pattern Breakdown
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) 1.5fr',
        gap: 16, alignItems: 'stretch',
      }}>
        <ResponsiveContainer width="100%" height={Math.max(160, data.length * 38)}>
          <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
            <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fill: COLOR.muted, fontSize: 11 }} />
            <YAxis type="category" dataKey="pattern" tick={{ fill: COLOR.text, fontSize: 12 }} width={100} />
            <Tooltip
              formatter={(v) => [`${Number(v).toFixed(1)}%`, 'Win Rate']}
              contentStyle={{ background: COLOR.card, border: `1px solid ${COLOR.border}`, borderRadius: 6, fontSize: 12 }} />
            <Bar dataKey="wr" radius={[0, 4, 4, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.wr >= 60 ? COLOR.green : d.wr >= 45 ? COLOR.yellow : COLOR.red} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${COLOR.border}` }}>
              {['Pattern', 'Total', 'W', 'L', 'WR%', 'Net USD'].map(h => (
                <th key={h} style={{
                  padding: '8px 10px', textAlign: h === 'Pattern' ? 'left' : 'right',
                  fontSize: 11, color: COLOR.muted, fontWeight: 500,
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map(d => (
              <tr key={d.pattern} style={{ borderBottom: `1px solid ${COLOR.border}` }}>
                <td style={{ padding: '10px', color: COLOR.text }}>{d.pattern}</td>
                <td style={{ padding: '10px', textAlign: 'right', color: COLOR.muted }}>{d.total}</td>
                <td style={{ padding: '10px', textAlign: 'right', color: COLOR.green }}>{d.wins}</td>
                <td style={{ padding: '10px', textAlign: 'right', color: COLOR.red }}>{d.losses}</td>
                <td style={{
                  padding: '10px', textAlign: 'right', fontWeight: 600,
                  color: d.wr >= 60 ? COLOR.green : d.wr >= 45 ? COLOR.yellow : COLOR.red,
                }}>{fmt(d.wr, 1)}%</td>
                <td style={{
                  padding: '10px', textAlign: 'right', fontFamily: 'monospace',
                  color: d.net >= 0 ? COLOR.green : COLOR.red,
                }}>{fmtSignedUsd(d.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Trade Table ────────────────────────────────────────────────────
const PAGE_SIZE = 20

function TradeTable({ trades }) {
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState(null)
  const [sortDir, setSortDir] = useState('desc') // newest first

  const sorted = useMemo(() => {
    const arr = [...trades]
    arr.sort((a, b) => {
      const av = a.open_time || ''
      const bv = b.open_time || ''
      return sortDir === 'desc' ? bv.localeCompare(av) : av.localeCompare(bv)
    })
    return arr
  }, [trades, sortDir])

  const pages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const view = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  // Clamp page when filters change underneath us
  useEffect(() => { setPage(p => Math.min(p, pages)) }, [pages])

  return (
    <div style={{
      background: COLOR.card, border: `1px solid ${COLOR.border}`,
      borderRadius: 12, padding: 16, marginBottom: 20,
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 12,
      }}>
        <div style={{
          fontSize: 11, color: COLOR.muted, letterSpacing: 1.5, textTransform: 'uppercase',
        }}>
          Trade History ({sorted.length})
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12, color: COLOR.muted }}>
          <button onClick={() => setSortDir(d => d === 'desc' ? 'asc' : 'desc')}
            style={btnSecondary}>
            Time {sortDir === 'desc' ? '↓' : '↑'}
          </button>
          <span>Page {page} / {pages}</span>
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} style={btnSecondary}>‹</button>
          <button onClick={() => setPage(p => Math.min(pages, p + 1))} disabled={page >= pages} style={btnSecondary}>›</button>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${COLOR.border}` }}>
              {['#', 'Open', 'Close', 'Dir', 'Pattern', 'TF', 'Lot', 'Entry', 'SL', 'TP', 'Close', 'P&L USD', 'P&L pip', 'R:R', 'Result', 'Conf']
                .map(h => (
                  <th key={h} style={{
                    padding: '8px 8px', textAlign: 'left',
                    fontSize: 10, color: COLOR.muted, fontWeight: 500, letterSpacing: 0.5,
                    whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
            </tr>
          </thead>
          <tbody>
            {view.map((t, i) => {
              const rowIdx = (page - 1) * PAGE_SIZE + i + 1
              const isOpen = expanded === t.trade_id
              const tint = t.result === 'WIN'
                ? 'rgba(52,229,163,0.05)'
                : t.result === 'LOSS' ? 'rgba(255,82,116,0.05)' : 'transparent'
              return (
                <Fragment key={t.trade_id || i}>
                  <tr
                    onClick={() => setExpanded(isOpen ? null : t.trade_id)}
                    style={{
                      borderBottom: `1px solid ${COLOR.border}`,
                      background: tint,
                      cursor: 'pointer',
                    }}>
                    <td style={cellMuted}>{rowIdx}</td>
                    <td style={cellMono}>{fmtTime(t.open_time)}</td>
                    <td style={cellMono}>{fmtTime(t.close_time)}</td>
                    <td>
                      <span style={{
                        ...badgeStyle,
                        background: t.direction === 'BUY' ? 'rgba(52,229,163,0.16)' : 'rgba(245,196,81,0.16)',
                        color:      t.direction === 'BUY' ? COLOR.green : COLOR.yellow,
                      }}>{t.direction || '—'}</span>
                    </td>
                    <td style={cellMuted}>{t.pattern || '—'}</td>
                    <td style={cellMuted}>{t.timeframe || '—'}</td>
                    <td style={cellMono}>{fmt(t.lot, 2)}</td>
                    <td style={cellMono}>{fmt(t.entry_price, 2)}</td>
                    <td style={{ ...cellMono, color: COLOR.red }}>{fmt(t.sl_price, 2)}</td>
                    <td style={{ ...cellMono, color: COLOR.green }}>{fmt(t.tp_price, 2)}</td>
                    <td style={cellMono}>{fmt(t.close_price, 2)}</td>
                    <td style={{ ...cellMono, color: (t.pnl_usd || 0) >= 0 ? COLOR.green : COLOR.red, fontWeight: 600 }}>
                      {t.result === 'PENDING' ? '—' : fmtSignedUsd(t.pnl_usd)}
                    </td>
                    <td style={{ ...cellMono, color: (t.pnl_pip || 0) >= 0 ? COLOR.green : COLOR.red }}>
                      {t.result === 'PENDING' ? '—' : `${t.pnl_pip >= 0 ? '+' : ''}${fmt(t.pnl_pip, 0)}`}
                    </td>
                    <td style={cellMono}>{fmt(t.rr_actual, 2)}</td>
                    <td>
                      <span style={{
                        ...badgeStyle,
                        background: t.result === 'WIN'  ? 'rgba(52,229,163,0.16)'
                                  : t.result === 'LOSS' ? 'rgba(255,82,116,0.16)' : 'rgba(111,129,159,0.16)',
                        color: resultColor(t.result),
                      }}>
                        {t.result === 'WIN' ? '🟢 WIN' : t.result === 'LOSS' ? '🔴 LOSS' : `⚪ ${t.result || '—'}`}
                      </span>
                    </td>
                    <td style={cellMono}>{fmt(t.claude_confidence, 2)}</td>
                  </tr>
                  {isOpen && <ExpandedRow t={t} />}
                </Fragment>
              )
            })}
            {!view.length && (
              <tr><td colSpan={16} style={{ padding: 40, color: COLOR.muted, textAlign: 'center' }}>
                No trades match these filters
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ExpandedRow({ t }) {
  return (
    <tr>
      <td colSpan={16} style={{ background: '#070b16', padding: 14, borderBottom: `1px solid ${COLOR.border}` }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          <Detail label="Plan ID"    value={t.plan_id} mono />
          <Detail label="Trade ID"   value={t.trade_id} mono />
          <Detail label="Bot"        value={t.bot_id} mono />
          <Detail label="Symbol"     value={t.symbol} />
          <Detail label="Session"    value={t.session} />
          <Detail label="Mode"       value={t.mode} />
          <Detail label="MAE pip"    value={fmt(t.mae_pip, 1)} mono />
          <Detail label="MFE pip"    value={fmt(t.mfe_pip, 1)} mono />
          <Detail label="R55 @ open" value={fmt(t.r55_pip_at_open, 0)} mono />
          <Detail label="R:R planned" value={fmt(t.rr_planned, 2)} mono />
          <Detail label="Close reason" value={t.close_reason} />
          <Detail label="Source DB" value={t.source_db} mono />
        </div>
        {t.claude_reason && (
          <div style={{ marginTop: 10, padding: 10, background: '#05080f', borderRadius: 6 }}>
            <div style={{ fontSize: 10, color: COLOR.muted, marginBottom: 4 }}>REASON</div>
            <div style={{ fontSize: 12, color: COLOR.text, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
              {t.claude_reason}
            </div>
          </div>
        )}
      </td>
    </tr>
  )
}

function Detail({ label, value, mono }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: COLOR.muted, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 12, color: COLOR.text, fontFamily: mono ? 'monospace' : 'inherit' }}>
        {value || '—'}
      </div>
    </div>
  )
}

const cellMono = { padding: '8px 8px', fontFamily: 'monospace', color: COLOR.text, whiteSpace: 'nowrap' }
const cellMuted = { padding: '8px 8px', color: COLOR.muted, whiteSpace: 'nowrap' }
const badgeStyle = {
  display: 'inline-block', padding: '2px 8px', borderRadius: 4,
  fontSize: 10, fontWeight: 600, letterSpacing: 0.5,
}

// ─── States ─────────────────────────────────────────────────────────
function SkeletonGrid() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} style={{
          background: COLOR.card, border: `1px solid ${COLOR.border}`,
          borderRadius: 12, padding: 16, height: 110,
          animation: 'pulse 1.4s ease-in-out infinite',
        }} />
      ))}
      <style>{`@keyframes pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.5 } }`}</style>
    </div>
  )
}

function EmptyState({ from, to, mode }) {
  return (
    <div style={{
      background: COLOR.card, border: `1px solid ${COLOR.border}`,
      borderRadius: 12, padding: 60, textAlign: 'center',
    }}>
      <div style={{ fontSize: 14, color: COLOR.muted, fontFamily: 'monospace' }}>
        No trades in {from} → {to} (mode: {mode})
      </div>
      <div style={{ fontSize: 12, color: COLOR.muted, marginTop: 8 }}>
        Try expanding the date range, or pick "All Time"
      </div>
    </div>
  )
}

function ErrorBox({ message }) {
  return (
    <div style={{
      background: 'rgba(255,82,116,0.1)', border: `1px solid ${COLOR.red}`,
      borderRadius: 8, padding: 12, marginBottom: 16,
      color: COLOR.red, fontSize: 13,
    }}>
      ⚠ {message}
    </div>
  )
}
