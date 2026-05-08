import { useEffect, useState } from 'react'

/**
 * MT5LivePanel — Shows live MT5 connectivity + latest candles.
 * Polls /api/mt5-status every 3s and /api/candles every 5s.
 * Confirms data is actually flowing from MT5 Desktop → api_server → UI.
 */
export default function MT5LivePanel({ symbol = 'XAUUSDc', timeframe = 'M1' }) {
  const [mt5, setMt5] = useState(null)
  const [candles, setCandles] = useState([])
  const [lastFetched, setLastFetched] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true

    const pollStatus = async () => {
      try {
        const r = await fetch('/api/mt5-status')
        const j = await r.json()
        if (!alive) return
        setMt5(j)
        setError(j.connected ? null : (j.error || 'not connected'))
      } catch (e) {
        if (!alive) return
        setError(`fetch failed: ${e.message}`)
      }
    }

    const pollCandles = async () => {
      try {
        const r = await fetch(`/api/candles?tf=${timeframe}&limit=10&symbol=${symbol}`)
        const j = await r.json()
        if (!alive) return
        if (Array.isArray(j) && j.length > 0) {
          setCandles(j)
          setLastFetched(new Date())
        }
      } catch (e) {
        // silent — pollStatus shows the error
      }
    }

    pollStatus()
    pollCandles()
    const t1 = setInterval(pollStatus, 3000)
    const t2 = setInterval(pollCandles, 5000)
    return () => { alive = false; clearInterval(t1); clearInterval(t2) }
  }, [symbol, timeframe])

  const ok = mt5?.connected
  const dotStyle = {
    display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
    background: ok ? '#4ade80' : '#ef4444',
    marginRight: 8, animation: ok ? 'pulse 2s infinite' : 'none',
  }

  const fmtTime = ts => new Date(ts * 1000).toLocaleTimeString()
  const fmtTimeShort = ts => {
    const d = new Date(ts * 1000)
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
  }

  return (
    <div className="card" style={{ gridColumn: 'span 2' }}>
      <h2 className="card-title">
        <span style={dotStyle}></span>
        MT5 Live Data
        <span style={{ marginLeft: 12, fontSize: '0.75em', fontWeight: 'normal', color: '#9aa0aa' }}>
          {symbol} · {timeframe}
        </span>
      </h2>

      {error && (
        <div style={{ color: '#f87171', marginBottom: 12, fontSize: 13 }}>
          ⚠️ {error}
        </div>
      )}

      {/* Account + tick info */}
      {mt5?.connected && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
          <div className="stat-item">
            <div className="stat-label">Account</div>
            <div className="stat-value text-mono" style={{ fontSize: 14 }}>
              {mt5.account?.login}
            </div>
          </div>
          <div className="stat-item">
            <div className="stat-label">Balance</div>
            <div className="stat-value text-mono" style={{ fontSize: 14 }}>
              {mt5.account?.balance?.toFixed(2)} {mt5.account?.currency}
            </div>
          </div>
          <div className="stat-item">
            <div className="stat-label">Bid / Ask</div>
            <div className="stat-value text-mono" style={{ fontSize: 14 }}>
              {mt5.symbol?.bid?.toFixed(2)} / {mt5.symbol?.ask?.toFixed(2)}
            </div>
          </div>
          <div className="stat-item">
            <div className="stat-label">Spread</div>
            <div className="stat-value text-mono" style={{ fontSize: 14 }}>
              {mt5.symbol?.spread_pip} pip
            </div>
          </div>
        </div>
      )}

      {/* Recent candles table */}
      {candles.length > 0 ? (
        <>
          <div style={{ fontSize: 12, color: '#9aa0aa', marginBottom: 6 }}>
            Last {candles.length} candles · fetched {lastFetched?.toLocaleTimeString()}
          </div>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #2b2f3a', color: '#9aa0aa' }}>
                <th style={{ textAlign: 'left',  padding: '4px 8px' }}>Time</th>
                <th style={{ textAlign: 'right', padding: '4px 8px' }}>Open</th>
                <th style={{ textAlign: 'right', padding: '4px 8px' }}>High</th>
                <th style={{ textAlign: 'right', padding: '4px 8px' }}>Low</th>
                <th style={{ textAlign: 'right', padding: '4px 8px' }}>Close</th>
                <th style={{ textAlign: 'right', padding: '4px 8px' }}>Δ</th>
              </tr>
            </thead>
            <tbody>
              {[...candles].reverse().map((c, i) => {
                const delta = c.close - c.open
                const color = delta >= 0 ? '#4ade80' : '#f87171'
                return (
                  <tr key={c.time} style={{ borderBottom: '1px solid #1a1d24' }}>
                    <td style={{ padding: '4px 8px', fontFamily: 'monospace' }}>{fmtTimeShort(c.time)}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: 'monospace' }}>{c.open.toFixed(2)}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: 'monospace' }}>{c.high.toFixed(2)}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: 'monospace' }}>{c.low.toFixed(2)}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: 'monospace' }}>{c.close.toFixed(2)}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: 'monospace', color }}>
                      {delta >= 0 ? '+' : ''}{delta.toFixed(2)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </>
      ) : (
        <div style={{ color: '#9aa0aa', fontSize: 13 }}>No candle data yet…</div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%      { opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}
