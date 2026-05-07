"""
strategies/ — Trading strategy modules

Each strategy exposes find_signal(bars, portfolio) -> Optional[Signal] and a
PATTERN_NAME constant matching the key in config/strategies.json.

The active set is read from config/strategies.json at runtime via
utils.strategy_loader.is_pattern_active(); inactive strategies are skipped
by signal_engine before any computation.
"""
