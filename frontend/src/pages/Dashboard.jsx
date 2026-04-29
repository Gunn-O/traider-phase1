import './Dashboard.css'

export default function Dashboard({ botState }) {
  return (
    <div className="dashboard">
      <div className="dashboard-grid">
        {/* Portfolio Stats */}
        <div className="card stats-card">
          <h2 className="card-title">Portfolio</h2>
          <div className="stats-grid">
            <div className="stat-item">
              <div className="stat-label">Balance</div>
              <div className="stat-value text-mono">${botState?.balance?.toFixed(2) || '0.00'}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Daily P/L</div>
              <div className="stat-value text-mono">${botState?.daily_pnl?.toFixed(2) || '0.00'}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Total P/L</div>
              <div className={`stat-value text-mono ${botState.portfolio?.total_pnl >= 0 ? 'profit' : 'loss'}`}>
                {botState.portfolio?.total_pnl >= 0 ? '+' : ''}${botState.portfolio?.total_pnl?.toFixed(2) || '0.00'}
              </div>
            </div>
            <div className="stat-item">
              <div className="stat-label">P/L %</div>
              <div className={`stat-value text-mono ${botState.portfolio?.total_pnl_pct >= 0 ? 'profit' : 'loss'}`}>
                {botState.portfolio?.total_pnl_pct >= 0 ? '+' : ''}{botState.portfolio?.total_pnl_pct?.toFixed(2) || '0.00'}%
              </div>
            </div>
          </div>
        </div>

        {/* Risk Metrics */}
        <div className="card stats-card">
          <h2 className="card-title">Risk Metrics</h2>
          <div className="stats-grid">
            <div className="stat-item">
              <div className="stat-label">Open Positions</div>
              <div className="stat-value text-mono">{botState.portfolio?.open_positions || 0}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Consecutive Loss</div>
              <div className="stat-value text-mono">{botState.portfolio?.consecutive_loss || 0}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Active Plan</div>
              <div className="stat-value text-mono">
                {botState.portfolio?.active_plan_id ? 'Yes' : 'No'}
              </div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Max DD</div>
              <div className="stat-value text-mono loss">{botState.max_dd?.toFixed(2) || '0.00'}%</div>
            </div>
          </div>
        </div>

        {/* Performance */}
        <div className="card stats-card">
          <h2 className="card-title">Performance</h2>
          <div className="stats-grid">
            <div className="stat-item">
              <div className="stat-label">Total Trades</div>
              <div className="stat-value text-mono">{botState.total_trades || 0}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Win Rate</div>
              <div className="stat-value text-mono profit">{botState.win_rate?.toFixed(1) || '0.0'}%</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Avg R:R</div>
              <div className="stat-value text-mono">{botState.avg_rr?.toFixed(2) || '0.00'}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Sharpe</div>
              <div className="stat-value text-mono">{botState.sharpe?.toFixed(2) || '0.00'}</div>
            </div>
          </div>
        </div>

        {/* Market State */}
        <div className="card world-botState-card">
          <h2 className="card-title">Market State</h2>
          <div className="world-botState-grid">
            <div className="world-botState-item">
              <span className="ws-label">Trend:</span>
              <span className={`ws-value badge ${getTrendClass(botState.world_botState?.trend)}`}>
                {botState.world_botState?.trend || 'unclear'}
              </span>
            </div>
            <div className="world-botState-item">
              <span className="ws-label">Quality:</span>
              <span className="ws-value text-mono">
                {((botState.world_botState?.chart_quality || 0) * 100).toFixed(0)}%
              </span>
            </div>
            <div className="world-botState-item">
              <span className="ws-label">Twin Candle:</span>
              <span className={`ws-value badge ${botState.world_botState?.twin_candle ? 'success' : 'error'}`}>
                {botState.world_botState?.twin_candle ? 'Yes' : 'No'}
              </span>
            </div>
            <div className="world-botState-item">
              <span className="ws-label">Breakout Box:</span>
              <span className={`ws-value badge ${botState.world_botState?.breakout_box ? 'success' : 'error'}`}>
                {botState.world_botState?.breakout_box ? 'Yes' : 'No'}
              </span>
            </div>
            <div className="world-botState-item">
              <span className="ws-label">Mountain:</span>
              <span className={`ws-value badge ${botState.world_botState?.mountain_detected ? 'success' : 'error'}`}>
                {botState.world_botState?.mountain_detected ? 'Yes' : 'No'}
              </span>
            </div>
            <div className="world-botState-item">
              <span className="ws-label">Technique:</span>
              <span className="ws-value text-mono">
                {botState.world_botState?.technique_candidate || 'None'}
              </span>
            </div>
          </div>
        </div>

        {/* Recent Trades */}
        <div className="card recent-trades-card">
          <h2 className="card-title">Recent Trades</h2>
          <div className="trades-list">
            {botState.recent_trades && botState.recent_trades.length > 0 ? (
              botState.recent_trades.slice(0, 5).map((trade, index) => (
                <div key={index} className="trade-item">
                  <div className="trade-header">
                    <span className={`trade-type badge ${trade.type === 'BUY' ? 'success' : 'warning'}`}>
                      {trade.type}
                    </span>
                    <span className="trade-time text-muted text-mono">{trade.time}</span>
                  </div>
                  <div className="trade-details">
                    <span className="text-mono">Entry: ${trade.entry?.toFixed(2)}</span>
                    <span className="text-mono">SL: ${trade.sl?.toFixed(2)}</span>
                    <span className="text-mono">TP: ${trade.tp?.toFixed(2)}</span>
                    <span className={`text-mono ${trade.pnl >= 0 ? 'profit' : 'loss'}`}>
                      P/L: {trade.pnl >= 0 ? '+' : ''}${trade.pnl?.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div className="empty-botState text-muted">No trades yet</div>
            )}
          </div>
        </div>

        {/* Last Decision */}
        {botState.last_decision && (
          <div className="card last-decision-card">
            <h2 className="card-title">Last Decision</h2>
            <div className="decision-content">
              <div className="decision-header">
                <span className={`decision-action badge ${botState.last_decision.action === 'SKIP' ? 'error' : 'success'}`}>
                  {botState.last_decision.action}
                </span>
                <span className="decision-confidence text-mono">
                  {(botState.last_decision.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <div className="decision-reason text-muted">
                {botState.last_decision.reason}
              </div>
              {botState.last_decision.technique && (
                <div className="decision-technique">
                  <span className="badge info">{botState.last_decision.technique}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function getTrendClass(trend) {
  if (trend === 'uptrend') return 'success'
  if (trend === 'downtrend') return 'warning'
  if (trend === 'mountain') return 'info'
  return 'error'
}
