import { useEffect, useState } from 'react'
import './TopBar.css'

const SYMBOL_OPTIONS_BY_SOURCE = {
  auto: [
    { value: 'XAUUSDc', label: 'XAUUSDc (Cent)' },
    { value: 'XAUUSDm', label: 'XAUUSDm (Micro)' },
    { value: 'XAUUSD',  label: 'XAUUSD (Standard)' },
  ],
  mt5: [
    { value: 'XAUUSDc', label: 'XAUUSDc (Cent)' },
    { value: 'XAUUSDm', label: 'XAUUSDm (Micro)' },
    { value: 'XAUUSD',  label: 'XAUUSD (Standard)' },
  ],
  yf: [
    { value: 'XAUUSD', label: 'Gold Futures (GC=F)' },
  ],
  tv: [
    { value: 'XAUUSD', label: 'XAUUSD (OANDA)' },
  ],
}

const TF_TABS = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4']

export default function TopBar({ bots, selection, onSelectionChange, onAddBot, onEmergencyStop }) {
  const { tradeKind, accountType, symbol, timeframe, dataSource } = selection
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const setTradeKind   = v => onSelectionChange({ tradeKind: v })
  const setAccountType = v => onSelectionChange({ accountType: v })
  const setSymbol      = v => onSelectionChange({ symbol: v })
  const setTimeframe   = v => onSelectionChange({ timeframe: v })
  const setDataSource  = v => onSelectionChange({ dataSource: v })

  useEffect(() => {
    const allowed = SYMBOL_OPTIONS_BY_SOURCE[dataSource] || []
    if (!allowed.find(o => o.value === symbol)) {
      setSymbol(allowed[0]?.value || 'XAUUSDc')
    }
  }, [dataSource])

  const symbolOptions = SYMBOL_OPTIONS_BY_SOURCE[dataSource] || SYMBOL_OPTIONS_BY_SOURCE.auto
  const mode = tradeKind === 'simulation'
    ? 'paper'
    : (accountType === 'cent' ? 'micro' : 'live')

  const candidateBotId = `${timeframe}-${symbol}-${mode}`
  const alreadyRunning = bots.some(b => b.bot_id === candidateBotId && b.status === 'running')
  const runningCount = bots.filter(b => b.status === 'running').length

  const handleAdd = async () => {
    setError('')
    setBusy(true)
    try {
      await onAddBot({ tf: timeframe, symbol, mode, data_source: dataSource })
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="topbar">
      <div className="topbar-left">
        <div className="status-group">
          <div className={`status-indicator ${runningCount > 0 ? 'running' : 'stopped'}`}>
            <span className="status-dot"></span>
            <span className="status-text">{runningCount} running</span>
          </div>
        </div>

        <div className="tf-tabs">
          {TF_TABS.map(tf => {
            const hasBot = bots.some(b => b.tf === tf && b.status === 'running')
            return (
              <button
                key={tf}
                className={`tf-tab ${timeframe === tf ? 'active' : ''} ${hasBot ? 'has-bot' : ''}`}
                onClick={() => setTimeframe(tf)}
                title={hasBot ? `${tf} bot is running` : `Select ${tf}`}
              >
                {tf}{hasBot ? ' ●' : ''}
              </button>
            )
          })}
        </div>

        <div className="controls-group">
          <select value={tradeKind} onChange={e => setTradeKind(e.target.value)} className="control-select">
            <option value="simulation">Simulation</option>
            <option value="broker">Broker</option>
          </select>

          {tradeKind === 'broker' && (
            <select value={accountType} onChange={e => setAccountType(e.target.value)} className="control-select">
              <option value="cent">Cent</option>
              <option value="real">Real</option>
            </select>
          )}

          <select value={dataSource} onChange={e => setDataSource(e.target.value)} className="control-select">
            <option value="auto">Auto</option>
            <option value="mt5">MT5</option>
            <option value="yf">yfinance</option>
            <option value="tv">TradingView</option>
          </select>

          <select value={symbol} onChange={e => setSymbol(e.target.value)} className="control-select">
            {symbolOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>

          <button
            onClick={handleAdd}
            className="btn btn-start"
            disabled={busy || alreadyRunning}
            title={alreadyRunning ? `${candidateBotId} already running` : 'Start a bot with this config'}
          >
            {busy ? '…' : alreadyRunning ? '✓ Running' : '+ Add Bot'}
          </button>

          {runningCount > 0 && (
            <button onClick={onEmergencyStop} className="btn btn-emergency" title="Stop ALL bots immediately">
              🚨 Stop All
            </button>
          )}
        </div>

        {error && <div className="topbar-error">{error}</div>}
      </div>
    </div>
  )
}
