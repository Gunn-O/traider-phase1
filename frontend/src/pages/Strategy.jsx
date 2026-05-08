import { useState, useEffect } from 'react';
import './Strategy.css';

export default function Strategy() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [strategies, setStrategies] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadStrategies();
  }, []);

  const loadStrategies = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/strategies');
      if (!response.ok) throw new Error('Failed to load strategies');
      const data = await response.json();
      setStrategies(data);
    } catch (err) {
      setError(err.message);
      console.error('Failed to load strategies:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (patternName) => {
    if (saving) return;
    try {
      setSaving(true);
      const currentActive = strategies.active_patterns || [];
      const newActive = currentActive.includes(patternName)
        ? currentActive.filter(p => p !== patternName)
        : [...currentActive, patternName];

      const response = await fetch('/api/strategies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: newActive }),
      });
      if (!response.ok) throw new Error('Failed to update strategies');
      await loadStrategies();
    } catch (err) {
      setError(err.message);
      console.error('Failed to toggle pattern:', err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="strategy-page">
        <div className="strategy-header"><h1>Strategy Manager</h1></div>
        <div className="strategy-loading">Loading strategies...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="strategy-page">
        <div className="strategy-header"><h1>Strategy Manager</h1></div>
        <div className="strategy-error">
          <strong>Error</strong>
          {error}
          <div>
            <button className="strategy-retry-btn" onClick={loadStrategies}>Retry</button>
          </div>
        </div>
      </div>
    );
  }

  if (!strategies || !strategies.patterns) {
    return (
      <div className="strategy-page">
        <div className="strategy-header"><h1>Strategy Manager</h1></div>
        <div className="strategy-empty">No strategies configured</div>
      </div>
    );
  }

  const patterns = strategies.patterns;
  const activePatterns = strategies.active_patterns || [];

  return (
    <div className="strategy-page">
      <div className="strategy-header">
        <h1>Strategy Manager</h1>
        <div className="strategy-meta">
          Version {strategies.version} · {activePatterns.length} active pattern
          {activePatterns.length !== 1 ? 's' : ''} · Last updated: {strategies.last_updated}
        </div>
      </div>

      <div className="strategy-grid">
        {Object.entries(patterns)
          .sort((a, b) => (a[1].priority || 99) - (b[1].priority || 99))
          .map(([patternName, meta]) => {
            const isActive = activePatterns.includes(patternName);
            const isDeprecated = meta.deprecated || false;
            const isImplemented = meta.implemented !== false;
            const dirClass = meta.direction === 'BUY' ? 'buy' : meta.direction === 'SELL' ? 'sell' : '';

            return (
              <div
                key={patternName}
                className={`strategy-card ${isActive ? 'active' : ''} ${isDeprecated ? 'deprecated' : ''}`}
              >
                <div className="strategy-card-head">
                  <div>
                    <div className="strategy-card-title">
                      <span>{meta.name}</span>
                      {!isImplemented && <span className="strategy-badge warn">Not Implemented</span>}
                      {isDeprecated && <span className="strategy-badge muted">Deprecated</span>}
                    </div>
                    <div className="strategy-card-subtitle">
                      {patternName} · v{meta.version}
                    </div>
                  </div>
                  <button
                    onClick={() => handleToggle(patternName)}
                    disabled={saving || !isImplemented}
                    className={`strategy-toggle ${isActive ? 'on' : ''}`}
                    aria-label={`Toggle ${patternName}`}
                    title={!isImplemented ? 'Pattern not implemented yet' : ''}
                  >
                    <span className="strategy-toggle-knob" />
                  </button>
                </div>

                <p className="strategy-desc">{meta.description}</p>

                <div className="strategy-meta-grid">
                  <div className="strategy-meta-row">
                    <span className="label">Direction</span>
                    <span className={`value ${dirClass}`}>{meta.direction}</span>
                  </div>
                  <div className="strategy-meta-row">
                    <span className="label">Priority</span>
                    <span className="value">{meta.priority}</span>
                  </div>
                </div>

                {meta.validations && meta.validations.length > 0 && (
                  <div className="strategy-validations">
                    <div className="strategy-validations-title">Validations</div>
                    <ul>
                      {meta.validations.map((v, i) => <li key={i}>{v}</li>)}
                    </ul>
                  </div>
                )}

                <div className="strategy-status">
                  <span className={`strategy-status-pill ${isActive ? 'active' : 'inactive'}`}>
                    {isActive ? '✓ ACTIVE' : '✗ INACTIVE'}
                  </span>
                </div>
              </div>
            );
          })}
      </div>

      <div className="strategy-help">
        <h3>💡 How to use Strategy Manager</h3>
        <ul>
          <li>Toggle patterns on/off to control which setups the system will detect</li>
          <li>Active patterns are checked by G2 Pre-filter before sending to Claude Reviewer</li>
          <li>Changes take effect immediately for new candles</li>
          <li>Priority determines detection order (lower number = higher priority)</li>
        </ul>
      </div>
    </div>
  );
}
