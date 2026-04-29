export default function Settings({ botState }) {
  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <div className="settings-section">
        <h3>Bot Configuration</h3>
        <div className="setting-row">
          <span>Default TF</span>
          <span className="mono">
            {botState?.trading_tf || 'M5'}
          </span>
        </div>
        <div className="setting-row">
          <span>Default Symbol</span>
          <span className="mono">
            {botState?.symbol || 'XAUUSDm'}
          </span>
        </div>
        <div className="setting-row">
          <span>Data Source</span>
          <span className="mono">
            {botState?.data_source_actual || 'Auto'}
          </span>
        </div>
      </div>

      <div className="settings-section">
        <h3>Risk Management</h3>
        <div className="setting-row">
          <span>Risk per plan</span>
          <span className="mono">10%</span>
        </div>
        <div className="setting-row">
          <span>Min R:R</span>
          <span className="mono">1.0</span>
        </div>
        <div className="setting-row">
          <span>Max consecutive loss</span>
          <span className="mono">3</span>
        </div>
      </div>

      <div className="settings-section">
        <h3>System</h3>
        <div className="setting-row">
          <span>Backend</span>
          <span className={`conn-status ${
            botState?.status !== 'error'
              ? 'online' : 'offline'
          }`}>
            http://127.0.0.1:8080
          </span>
        </div>
        <div className="setting-row">
          <span>Version</span>
          <span className="mono">Phase I v2.1</span>
        </div>
      </div>
    </div>
  )
}
