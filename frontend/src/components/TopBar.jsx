import { useState } from 'react'
import './TopBar.css'

export default function TopBar({ botState, onStart, onStop, onEmergencyStop }) {
  const [mode, setMode] = useState('paper')
  const [symbol, setSymbol] = useState('XAUUSDm')
  const [timeframe, setTimeframe] = useState('M5')
  const [dataSource, setDataSource] = useState('auto')

  const statusClass = botState?.status === 'running' ? 'running' : 'stopped'
  const dataSourceClass = botState?.data_source_actual === 'TradingView' ? 'tv' : 'yfinance'

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
            {botState?.mode?.toUpperCase() || mode.toUpperCase()}
          </div>
        </div>

        {/* Controls */}
        <div className="controls-group">
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            disabled={botState?.status === 'running'}
            className="control-select"
          >
            <option value="paper">Paper Trade</option>
            <option value="micro">Cent Account</option>
            <option value="live">Real Account</option>
          </select>

          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            disabled={botState?.status === 'running'}
            className="control-select"
          >
            <option value="M5">M5</option>
            <option value="M15">M15</option>
            <option value="M30">M30</option>
            <option value="H1">H1</option>
          </select>

          <select
            value={dataSource}
            onChange={(e) => setDataSource(e.target.value)}
            disabled={botState?.status === 'running'}
            className="control-select"
          >
            <option value="auto">Auto</option>
            <option value="mt5">MT5</option>
            <option value="tv">TradingView</option>
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
