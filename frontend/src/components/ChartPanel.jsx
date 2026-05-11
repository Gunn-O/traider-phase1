import { useEffect, useMemo, useState } from 'react'
import {
  ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'

const TF_OPTIONS = ['M1', 'M5', 'M15', 'M30']
const DEFAULT_TF = 'M5'
const DEFAULT_SYMBOL = 'XAUUSDc'
const BARS = 55

/**
 * 55-bar candlestick chart (recharts ComposedChart with a custom Shape per bar
 * — no extra dep). Polls /api/candles?limit=55. Default tf/symbol come from
 * the first running bot, but the user can override via the dropdowns.
 */
export default function ChartPanel({ bots = [] }) {
  const runningBots = useMemo(() => bots.filter(b => b.status === 'running'), [bots])
  const initialTf = runningBots[0]?.tf || DEFAULT_TF
  const initialSym = runningBots[0]?.symbol || DEFAULT_SYMBOL

  const [tf, setTf] = useState(initialTf)
  const [symbol, setSymbol] = useState(initialSym)
  const [candles, setCandles] = useState([])
  const [lastFetch, setLastFetch] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const r = await fetch(`/api/candles?tf=${tf}&limit=${BARS}&symbol=${symbol}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const j = await r.json()
        if (!alive) return
        setCandles(Array.isArray(j) ? j : [])
        setLastFetch(new Date())
        setErr(null)
      } catch (e) {
        if (!alive) return
        setErr(e.message)
      }
    }
    poll()
    // M1 → 30s, M5+ → 60s. Cache TTL on backend handles dedup across UI clients.
    const intervalMs = tf === 'M1' ? 30000 : 60000
    const t = setInterval(poll, intervalMs)
    return () => { alive = false; clearInterval(t) }
  }, [tf, symbol])

  // Symbols from running bots (so user can pick what each bot is watching)
  const symbols = useMemo(() => {
    const s = new Set(runningBots.map(b => b.symbol))
    s.add(symbol)
    return Array.from(s)
  }, [runningBots, symbol])

  // Pre-compute series for recharts: keep raw OHLC and add helper fields
  // for the bar shape. recharts needs a numeric "value" array for the bar.
  const data = useMemo(() => candles.map(c => ({
    time: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    range: [c.low, c.high],   // wick range
    body: [Math.min(c.open, c.close), Math.max(c.open, c.close)],
    bullish: c.close >= c.open,
  })), [candles])

  const lastClose = candles.length > 0 ? candles[candles.length - 1].close : null

  return (
    <div className="card chart-card">
      <div className="card-header">
        <h2 className="card-title">
          Chart · last {BARS} bars
          {lastClose != null && (
            <span className="text-muted text-mono" style={{ marginLeft: 12, fontSize: 13 }}>
              close {lastClose.toFixed(2)}
            </span>
          )}
        </h2>
        <div className="chart-controls">
          <select className="filter-pill" value={symbol} onChange={e => setSymbol(e.target.value)}>
            {symbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          {TF_OPTIONS.map(t => (
            <button
              key={t}
              className={`filter-pill ${tf === t ? 'active' : ''}`}
              onClick={() => setTf(t)}
            >{t}</button>
          ))}
          {lastFetch && (
            <span className="text-muted text-mono" style={{ fontSize: 11 }}>
              {lastFetch.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
        </div>
      </div>

      {err && <div className="mt5-error">⚠️ {err}</div>}

      {data.length === 0 ? (
        <div className="empty-state">No candle data — waiting for MT5…</div>
      ) : (
        <div style={{ width: '100%', height: 320 }}>
          <ResponsiveContainer>
            <ComposedChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="time"
                tickFormatter={t => fmtTimeShort(t)}
                tick={{ fill: '#9aa0aa', fontSize: 10 }}
                interval={Math.max(0, Math.floor(BARS / 8))}
              />
              <YAxis
                domain={['dataMin - 0.5', 'dataMax + 0.5']}
                tick={{ fill: '#9aa0aa', fontSize: 10 }}
                tickFormatter={v => v.toFixed(2)}
                width={60}
                orientation="right"
              />
              <Tooltip
                content={<CandleTooltip />}
                cursor={{ stroke: 'rgba(255,255,255,0.2)' }}
              />
              {lastClose != null && (
                <ReferenceLine y={lastClose} stroke="rgba(150,150,255,0.4)" strokeDasharray="3 3" />
              )}
              {/* Wick: thin range bar */}
              <Bar dataKey="range" barSize={1} isAnimationActive={false}>
                {data.map((d, i) => (
                  <Cell key={`wick-${i}`} fill={d.bullish ? '#26a69a' : '#ef5350'} />
                ))}
              </Bar>
              {/* Body: thicker open-close bar */}
              <Bar dataKey="body" barSize={6} isAnimationActive={false}>
                {data.map((d, i) => (
                  <Cell key={`body-${i}`} fill={d.bullish ? '#26a69a' : '#ef5350'} />
                ))}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

function CandleTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const d = payload[0].payload
  if (!d) return null
  const delta = d.close - d.open
  const cls = delta >= 0 ? 'profit' : 'loss'
  return (
    <div className="chart-tooltip">
      <div className="text-mono text-muted">{fmtTime(d.time)}</div>
      <div className="text-mono">O <span>{d.open.toFixed(2)}</span></div>
      <div className="text-mono">H <span>{d.high.toFixed(2)}</span></div>
      <div className="text-mono">L <span>{d.low.toFixed(2)}</span></div>
      <div className="text-mono">C <span>{d.close.toFixed(2)}</span></div>
      <div className={`text-mono ${cls}`}>Δ {delta >= 0 ? '+' : ''}{delta.toFixed(2)}</div>
    </div>
  )
}

function fmtTime(ts) {
  const d = new Date(ts * 1000)
  return d.toLocaleString([], { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function fmtTimeShort(ts) {
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
