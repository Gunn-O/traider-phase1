import { useEffect, useMemo, useState } from 'react'
import {
  ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'

const TF_OPTIONS = ['M1', 'M5', 'M15', 'M30']
const DEFAULT_TF = 'M5'
const DEFAULT_SYMBOL = 'XAUUSDc'
const BARS = 55

const BULL_COLOR = '#26a69a'
const BEAR_COLOR = '#ef5350'

/**
 * 55-bar candlestick chart for the symbol/tf the bots are watching.
 *
 * Implementation note: recharts has no native candlestick, so each bar is
 * drawn with a custom SVG `shape` that uses the row's full OHLC payload:
 * one vertical line for the wick (low..high) + one centered rect for the
 * body (open..close). The Bar's `dataKey="range"` array `[low, high]` only
 * gives recharts the y-bounds so it can pick the axis scale.
 *
 * Polls /api/candles?limit=55. Default tf/symbol come from the first
 * running bot; user can override via the dropdown/buttons.
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
    const intervalMs = tf === 'M1' ? 30000 : 60000
    const t = setInterval(poll, intervalMs)
    return () => { alive = false; clearInterval(t) }
  }, [tf, symbol])

  const symbols = useMemo(() => {
    const s = new Set(runningBots.map(b => b.symbol))
    s.add(symbol)
    return Array.from(s)
  }, [runningBots, symbol])

  // Use a sequential index for x so weekends/gaps don't visually distort spacing.
  // We still expose the original unix `time` for the tooltip/axis label.
  const data = useMemo(() => candles.map((c, i) => ({
    idx: i,
    time: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    range: [c.low, c.high],
  })), [candles])

  const lastClose = candles.length > 0 ? candles[candles.length - 1].close : null
  const tickFormatterIdx = (i) => {
    const c = data[i]
    return c ? fmtTimeShort(c.time) : ''
  }

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
                dataKey="idx"
                type="number"
                domain={[-0.5, data.length - 0.5]}
                tick={{ fill: '#9aa0aa', fontSize: 10 }}
                tickFormatter={tickFormatterIdx}
                interval={Math.max(0, Math.floor(BARS / 8))}
                allowDecimals={false}
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
              <Bar
                dataKey="range"
                shape={<CandleShape />}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

/**
 * Custom SVG candle:
 *   - x/y/width/height come from recharts (y/height map the [low, high] range
 *     into the y-axis scale of the chart, so y = pixel y of `high`, y+height
 *     = pixel y of `low`).
 *   - Wick: single vertical line at the bar's horizontal center, spanning the
 *     full y..y+height (= high..low).
 *   - Body: rect centered on the wick, from open's y-pixel to close's y-pixel.
 *     Uses linear interpolation within [low, high] → [y, y+height].
 */
function CandleShape(props) {
  const { x, y, width, height, payload } = props
  if (!payload || width <= 0 || height <= 0) return null
  const { open, high, low, close } = payload
  if (!Number.isFinite(open) || !Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) return null

  const range = high - low
  if (range <= 0) return null

  const xCenter = x + width / 2
  // Map a price (between low and high) to its pixel y. Higher price → smaller y.
  const yFor = (price) => y + ((high - price) / range) * height

  const openY = yFor(open)
  const closeY = yFor(close)
  const bodyTop = Math.min(openY, closeY)
  const bodyBottom = Math.max(openY, closeY)
  const bodyHeight = Math.max(1, bodyBottom - bodyTop)
  const bodyWidth = Math.max(2, width * 0.7)

  const isBull = close >= open
  const color = isBull ? BULL_COLOR : BEAR_COLOR

  return (
    <g>
      {/* Wick: full high-to-low vertical line */}
      <line
        x1={xCenter}
        x2={xCenter}
        y1={y}
        y2={y + height}
        stroke={color}
        strokeWidth={1}
      />
      {/* Body: open-to-close rect centered on the wick */}
      <rect
        x={xCenter - bodyWidth / 2}
        y={bodyTop}
        width={bodyWidth}
        height={bodyHeight}
        fill={color}
      />
    </g>
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
