"""
Strategy Loader — V65 Strategy Manager
Loads and manages active pattern configurations from config/strategies.json
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "strategies.json"


def load_config() -> dict:
    """
    Load strategy configuration from config/strategies.json

    Returns:
        dict: Full strategy configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is invalid JSON
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Strategy config not found: {CONFIG_PATH}")

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    logger.debug(f"Loaded strategy config v{config.get('version', '?')}")
    return config


def get_active_patterns() -> List[str]:
    """
    Get list of active pattern names

    Returns:
        List[str]: Pattern names where active=true

    Example:
        ['MOUNTAIN', 'MOUNTAIN_R2']
    """
    config = load_config()
    patterns = config.get('patterns', {})

    active = [
        name for name, meta in patterns.items()
        if meta.get('active', False)
    ]

    logger.debug(f"Active patterns: {active}")
    return active


def is_pattern_active(pattern_name: str) -> bool:
    """
    Check if a specific pattern is active

    Args:
        pattern_name: Pattern name (e.g., 'MOUNTAIN', 'DOWNTREND_IMPULSE')

    Returns:
        bool: True if pattern is active, False otherwise
    """
    config = load_config()
    patterns = config.get('patterns', {})

    if pattern_name not in patterns:
        logger.warning(f"Pattern '{pattern_name}' not found in config")
        return False

    return patterns[pattern_name].get('active', False)


def get_pattern_metadata(pattern_name: str) -> Optional[dict]:
    """
    Get metadata for a specific pattern

    Args:
        pattern_name: Pattern name

    Returns:
        dict or None: Pattern metadata if found
    """
    config = load_config()
    patterns = config.get('patterns', {})
    return patterns.get(pattern_name)


def save_active(active_patterns: List[str]) -> None:
    """
    Save updated active pattern list to config file

    Args:
        active_patterns: List of pattern names to activate (all others will be deactivated)

    Example:
        save_active(['MOUNTAIN', 'MOUNTAIN_R2'])
    """
    config = load_config()
    patterns = config.get('patterns', {})

    # Update active status for all patterns
    for name in patterns:
        patterns[name]['active'] = name in active_patterns

    config['last_updated'] = __import__('datetime').datetime.now().strftime("%Y-%m-%d")

    # Write back to file
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    logger.info(f"Updated active patterns: {active_patterns}")


def get_global_settings() -> dict:
    """
    Get global strategy settings

    Returns:
        dict: Global settings (risk, filters, etc.)
    """
    config = load_config()
    return config.get('global_settings', {})


def get_patterns_by_priority() -> List[tuple]:
    """
    Get all patterns sorted by priority (lower number = higher priority)
    Only returns active patterns

    Returns:
        List[tuple]: [(priority, pattern_name), ...] sorted by priority

    Example:
        [(1, 'MOUNTAIN_R2'), (2, 'MOUNTAIN')]
    """
    config = load_config()
    patterns = config.get('patterns', {})

    active_with_priority = [
        (meta.get('priority', 99), name)
        for name, meta in patterns.items()
        if meta.get('active', False)
    ]

    active_with_priority.sort()  # Sort by priority (ascending)
    return active_with_priority


# ═══════════════════════════════════════════════════════════════════
# CLI Test
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== Strategy Loader Test ===\n")

    print("1. Load config:")
    config = load_config()
    print(f"   Version: {config.get('version')}")
    print(f"   Last updated: {config.get('last_updated')}")

    print("\n2. Active patterns:")
    active = get_active_patterns()
    for p in active:
        print(f"   - {p}")

    print("\n3. Pattern priorities:")
    for pri, name in get_patterns_by_priority():
        print(f"   [{pri}] {name}")

    print("\n4. Check specific patterns:")
    for pattern in ['MOUNTAIN', 'DOWNTREND', 'UPTREND_IMPULSE']:
        status = "✓ ACTIVE" if is_pattern_active(pattern) else "✗ INACTIVE"
        print(f"   {pattern}: {status}")

    print("\n5. Global settings:")
    settings = get_global_settings()
    print(f"   Min R:R: {settings.get('min_rr_ratio')}")
    print(f"   Risk per plan: {settings.get('risk_per_plan_pct')*100}%")
    print(f"   Time filter: {settings.get('time_filter', {}).get('enabled')}")
