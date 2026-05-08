import { useEffect } from 'react'
import './TopBar.css'

// Relational map: data source -> selectable symbols
// (label is what user sees; value is what we send to backend — backend maps to provider symbol)
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

// Display label for mode badge (top-left of TopBar)
// Backend still uses paper/micro/live internally; UI just relabels.
const MODE_BADGE = {
  paper: 'SIMULATION',
  micro: 'BROKER • CENT',
  live:  'BROKER • REAL',
}

export default function TopBar({ botState, selection, onSelectionChange, onStart, onStop, onEmergencyStop }) {
  // State lifted to App.jsx so Dashboard's MT5LivePanel sees the same TF/symbol.
  const { tradeKind, accountType, symbol, timeframe, dataSource } = selection
  const setTradeKind   = v => onSelectionChange({ tradeKind: v })
  const setAccountType = v => onSelectionChange({ accountType: v })
  const setSymbol      = v => onSelectionChange({ symbol: v })
  const setTimeframe   = v => onSelectionChange({ timeframe: v })
  const setDataSource  = v => onSelectionChange({ dataSource: v })

  // When data source changes, ensure selected symbol is still valid for that source
  useEffect(() => {
    const allowed = SYMBOL_OPTIONS_BY_SOURCE[dataSource] || []
    if (!allowed.find(o => o.value === symbol)) {
      setSymbol(allowed[0]?.value || 'XAUUSDc')
    }
  }, [dataSource])

  const symbolOptions = SYMBOL_OPTIONS_BY_SOURCE[dataSource] || SYMBOL_OPTIONS_BY_SOURCE.auto

  const statusClass = botState?.status === 'running' ? 'running' : 'stopped'
  const dataSourceClass = botState?.data_source_actual === 'TradingView' ? 'tv' : 'yfinance'

  // Derive backend mode from 2-level UI
  const mode = tradeKind === 'simulation'
    ? 'paper'
    : (accountType === 'cent' ? 'micro' : 'live')

  const handleStart = () => {
    onStart({ tf: timeframe, symbol, mode, data_source: dataSource })
  }

  const handleStop = () => {
    onStop()
  }

  const handleEmergencyStop = () => {
    onEmergencyStop()
  }

  return (
    <div className="topbar">
      <div className="topbar-left">
        <div className="status-group">
          <div className={`status-indicator ${statusClass}`}>
            <span className="status-dot"></span>
            <span className="status-text">
              {botState?.status === 'running' ? 'Running' : 'Stopped'}
            </span>
          </div>

          <div className={`source-badge ${dataSourceClass}`}>
            {botState?.data_source_actual === 'TradingView' ? 'TV' : 'YF'}
          </div>

          <div className="mode-badge">
            {MODE_BADGE[botState?.mode] || MODE_BADGE[mode]}
          </div>
        </div>

        {/* Controls */}
        <div className="controls-group">
          <select
            value={tradeKind}
            onChange={(e) => setTradeKind(e.target.value)}
            disabled={botState?.status === 'running'}
            className="control-select"
            title="Simulation = ไม่ส่งออเดอร์จริง / Broker = ส่งออเดอร์จริง"
          >
            <option value="simulation">Simulation Trade</option>
            <option value="broker">Broker Trade</option>
          </select>

          {tradeKind === 'broker' && (
            <select
              value={accountType}
              onChange={(e) => setAccountType(e.target.value)}
              disabled={botState?.status === 'running'}
              className="control-select"
              title="Cent = บัญชี Cent (เงินน้อย, ทดสอบ) / Real = บัญชีจริง"
            >
              <option value="cent">Cent</option>
              <option value="real">Real</option>
            </select>
          )}

          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            disabled={botState?.status === 'running'}
            className="control-select"
          >
            <option value="M1">M1</option>
            <option value="M5">M5</option>
            <option value="M15">M15</option>
            <option value="M30">M30</option>
            <option value="H1">H1</option>
            <option value="H4">H4</option>
          </select>

          <select
            value={dataSource}
            onChange={(e) => setDataSource(e.target.value)}
            disabled={botState?.status === 'running'}
            className="control-select"
          >
            <option value="auto">Auto</option>
            <option value="mt5">MT5</option>
            <option value="yf">yfinance</option>
            <option value="tv">TradingView</option>
          </select>

          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            disabled={botState?.status === 'running'}
            className="control-select"
          >
            {symbolOptions.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {botState?.status !== 'running' ? (
            <button onClick={handleStart} className="btn btn-start">
              ▶ START
            </button>
          ) : (
            <>
              <button onClick={handleStop} className="btn btn-stop">
                ⏸ STOP
              </button>
              <button onClick={handleEmergencyStop} className="btn btn-emergency">
                🚨 EMERGENCY
              </button>
            </>
          )}
        </div>
      </div>

      <div className="topbar-right">
        <div className="topbar-stats">
          <div className="topbar-stat">
            <span className="stat-label">Price</span>
            <span className="stat-value text-mono">
              ${botState?.current_price?.toFixed(2) || '0.00'}
            </span>
          </div>

          <div className="topbar-stat">
            <span className="stat-label">Balance</span>
            <span className="stat-value text-mono">
              ${botState?.balance?.toFixed(2) || '0.00'}
            </span>
          </div>

          <div className="topbar-stat">
            <span className="stat-label">P/L</span>
            <span className={`stat-value text-mono ${(botState?.total_pnl || 0) >= 0 ? 'profit' : 'loss'}`}>
              {(botState?.total_pnl || 0) >= 0 ? '+' : ''}${botState?.total_pnl?.toFixed(2) || '0.00'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
