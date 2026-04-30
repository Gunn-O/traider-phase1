import { useState, useEffect } from 'react';

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
      const response = await fetch('http://127.0.0.1:8080/api/strategies');
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

      // Calculate new active list
      const currentActive = strategies.active_patterns || [];
      const newActive = currentActive.includes(patternName)
        ? currentActive.filter(p => p !== patternName)
        : [...currentActive, patternName];

      // Update backend
      const response = await fetch('http://127.0.0.1:8080/api/strategies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: newActive })
      });

      if (!response.ok) throw new Error('Failed to update strategies');

      // Reload to get updated state
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
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-6">Strategy Manager</h1>
        <div className="text-gray-500">Loading strategies...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-6">Strategy Manager</h1>
        <div className="bg-red-50 border border-red-200 rounded p-4 text-red-800">
          <strong>Error:</strong> {error}
        </div>
        <button
          onClick={loadStrategies}
          className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!strategies || !strategies.patterns) {
    return (
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-6">Strategy Manager</h1>
        <div className="text-gray-500">No strategies configured</div>
      </div>
    );
  }

  const patterns = strategies.patterns;
  const activePatterns = strategies.active_patterns || [];

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Strategy Manager</h1>
        <p className="text-gray-600 mt-1">
          Version {strategies.version} • {activePatterns.length} active pattern{activePatterns.length !== 1 ? 's' : ''} • Last updated: {strategies.last_updated}
        </p>
      </div>

      {/* Strategy Patterns Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(patterns)
          .sort((a, b) => {
            // Sort by priority
            const priA = a[1].priority || 99;
            const priB = b[1].priority || 99;
            return priA - priB;
          })
          .map(([patternName, meta]) => {
            const isActive = activePatterns.includes(patternName);
            const isDeprecated = meta.deprecated || false;
            const isImplemented = meta.implemented !== false; // default true

            return (
              <div
                key={patternName}
                className={`border rounded-lg p-4 ${
                  isActive
                    ? 'bg-green-50 border-green-300'
                    : 'bg-gray-50 border-gray-200'
                } ${isDeprecated ? 'opacity-60' : ''}`}
              >
                {/* Header with Toggle */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold text-lg">{meta.name}</h3>
                      {!isImplemented && (
                        <span className="px-2 py-0.5 text-xs bg-yellow-200 text-yellow-800 rounded">
                          Not Implemented
                        </span>
                      )}
                      {isDeprecated && (
                        <span className="px-2 py-0.5 text-xs bg-gray-200 text-gray-600 rounded">
                          Deprecated
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {patternName} • v{meta.version}
                    </div>
                  </div>

                  {/* Toggle Switch */}
                  <button
                    onClick={() => handleToggle(patternName)}
                    disabled={saving || !isImplemented}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      isActive ? 'bg-green-500' : 'bg-gray-300'
                    } ${saving || !isImplemented ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                    aria-label={`Toggle ${patternName}`}
                    title={!isImplemented ? 'Pattern not implemented yet' : ''}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        isActive ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>

                {/* Description */}
                <p className="text-sm text-gray-700 mb-3">
                  {meta.description}
                </p>

                {/* Metadata */}
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Direction:</span>
                    <span
                      className={`font-medium ${
                        meta.direction === 'BUY'
                          ? 'text-green-600'
                          : 'text-red-600'
                      }`}
                    >
                      {meta.direction}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Priority:</span>
                    <span className="font-medium">{meta.priority}</span>
                  </div>
                </div>

                {/* Validations */}
                {meta.validations && meta.validations.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-200">
                    <div className="text-xs font-semibold text-gray-700 mb-1">
                      Validations:
                    </div>
                    <ul className="text-xs text-gray-600 space-y-0.5">
                      {meta.validations.map((validation, idx) => (
                        <li key={idx} className="flex items-start">
                          <span className="mr-1">•</span>
                          <span>{validation}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Status Badge */}
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <span
                    className={`inline-block px-2 py-1 text-xs font-medium rounded ${
                      isActive
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {isActive ? '✓ ACTIVE' : '✗ INACTIVE'}
                  </span>
                </div>
              </div>
            );
          })}
      </div>

      {/* Help Text */}
      <div className="mt-8 p-4 bg-blue-50 border border-blue-200 rounded">
        <h3 className="font-semibold text-blue-900 mb-2">
          💡 How to use Strategy Manager
        </h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• Toggle patterns on/off to control which setups the system will detect</li>
          <li>• Active patterns will be checked by G2 Pre-filter before sending to Claude Reviewer</li>
          <li>• Changes take effect immediately for new candles</li>
          <li>• Priority determines detection order (lower number = higher priority)</li>
        </ul>
      </div>
    </div>
  );
}
