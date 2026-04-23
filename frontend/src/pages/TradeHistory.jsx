import { useState, useEffect } from 'react'

export default function TradeHistory() {
  const [trades, setTrades] = useState([])
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/history?limit=50')
      .then(r => r.json())
      .then(data => {
        setTrades(data.trades || [])
        setSource(data.source || '')
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Trade History</h1>
        <span className={`source-badge ${
          source === 'google_sheets'
            ? 'sheets' : 'memory'
        }`}>
          {source === 'google_sheets'
            ? '📊 Google Sheets'
            : '💾 In-Memory'}
        </span>
      </div>

      {loading ? (
        <div className="loading">Loading...</div>
      ) : trades.length === 0 ? (
        <div className="empty-state">
          No trades yet
        </div>
      ) : (
        <table className="trade-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Lot</th>
              <th>Entry</th>
              <th>SL</th>
              <th>TP</th>
              <th>P&L</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i}>
                <td className="mono">
                  {t.timestamp_open || t.time || '—'}
                </td>
                <td className={`action ${
                  t.action?.toLowerCase()
                }`}>
                  {t.action}
                </td>
                <td className="mono">{t.lot}</td>
                <td className="mono">{t.entry}</td>
                <td className="mono">{t.sl}</td>
                <td className="mono">{t.tp}</td>
                <td className={`pnl ${
                  t.pnl > 0 ? 'win'
                  : t.pnl < 0 ? 'loss' : ''
                }`}>
                  {t.pnl > 0 ? '+' : ''}
                  {t.pnl?.toFixed(2) || '—'}
                </td>
                <td className={t.result?.toLowerCase()}>
                  {t.result === 'WIN' ? '✅'
                   : t.result === 'LOSS' ? '❌'
                   : '⏳'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
