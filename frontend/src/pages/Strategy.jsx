import { useState, useEffect } from 'react';
import './Strategy.css';

export default function Strategy() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [strategies, setStrategies] = useState(null);
  const [saving, setSaving] = useState('');  // pattern name currently being saved, '' if idle

  useEffect(() => {
    loadStrategies();
  }, []);

  // `silent` skips the loading-screen swap so a refetch (e.g. after a failed
  // optimistic write) doesn't tear down the cards and reset scroll.
  const loadStrategies = async ({ silent = false } = {}) => {
    try {
      if (!silent) setLoading(true);
      setError(null);
      const response = await fetch('/api/strategies');
      if (!response.ok) throw new Error('Failed to load strategies');
      const data = await response.json();
      setStrategies(data);
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const postUpdate = async (body) => {
    const res = await fetch('/api/strategies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const t = await res.text().catch(() => '');
      throw new Error(t || `HTTP ${res.status}`);
    }
    return res.json();
  };

  // Optimistic mutation — updates local state in place so the toggle feels
  // instant and React doesn't tear down the cards (which used to lose the
  // user's scroll position on every click).
  const handleToggle = async (patternName) => {
    if (saving) return;
    const currentActive = strategies.active_patterns || [];
    const newActive = currentActive.includes(patternName)
      ? currentActive.filter(p => p !== patternName)
      : [...currentActive, patternName];

    setStrategies(prev => ({ ...prev, active_patterns: newActive }))
    setSaving(patternName);
    try {
      await postUpdate({ active: newActive });
    } catch (err) {
      setError(err.message);
      loadStrategies({ silent: true });  // resync without flashing the loading screen
    } finally {
      setSaving('');
    }
  };

  const handleTfToggle = async (patternName, tf) => {
    if (saving) return;
    const meta = strategies.patterns[patternName] || {};
    const current = meta.allowed_tfs || strategies.all_tfs || [];
    const next = current.includes(tf)
      ? current.filter(t => t !== tf)
      : [...current, tf];

    setStrategies(prev => ({
      ...prev,
      patterns: { ...prev.patterns, [patternName]: { ...meta, allowed_tfs: next } },
    }))
    setSaving(patternName + ':' + tf);
    try {
      await postUpdate({ allowed_tfs: { [patternName]: next } });
    } catch (err) {
      setError(err.message);
      loadStrategies();
    } finally {
      setSaving('');
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
  const allTfs = strategies.all_tfs || ['M1', 'M5', 'M15', 'M30', 'H1', 'H4'];

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
            const allowedTfs = meta.allowed_tfs || allTfs;

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
                    disabled={!!saving || !isImplemented}
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

                <div className="strategy-tfs">
                  <div className="strategy-tfs-title">
                    Active on TF
                    <span className="strategy-tfs-count">
                      ({allowedTfs.length}/{allTfs.length})
                    </span>
                  </div>
                  <div className="strategy-tfs-pills">
                    {allTfs.map(tf => {
                      const on = allowedTfs.includes(tf);
                      const busy = saving === patternName + ':' + tf;
                      return (
                        <button
                          key={tf}
                          className={`tf-pill ${on ? 'on' : ''} ${!isActive ? 'dim' : ''}`}
                          onClick={() => handleTfToggle(patternName, tf)}
                          disabled={!!saving || !isImplemented}
                          title={isActive ? `${on ? 'Disable' : 'Enable'} ${tf} for ${patternName}` : 'Pattern is OFF — enable it first'}
                        >
                          {busy ? '…' : tf}
                        </button>
                      );
                    })}
                  </div>
                </div>

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
          <li>Master toggle (top-right) turns the whole strategy ON / OFF</li>
          <li>TF pills under each card pick which timeframes the strategy runs on (Mountain default = M1, M5)</li>
          <li>A bot only fires a strategy if both the master toggle is ON and its TF is in the allow-list</li>
          <li>Changes take effect on the next cycle — no restart needed</li>
        </ul>
      </div>
    </div>
  );
}
