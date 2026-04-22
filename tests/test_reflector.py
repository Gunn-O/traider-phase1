"""
Unit Tests for Reflector Agent (G4d)

Tests:
- calculate_technique_stats()
- calculate_session_stats()
- calculate_current_streak()
- build_reflection_summary()
- Reflector.update()
"""

import pytest
from datetime import datetime, timedelta
from agents.g4_reflector import (
    calculate_technique_stats,
    calculate_session_stats,
    calculate_current_streak,
    build_reflection_summary,
    Reflector
)


# ============================================================================
# TEST CALCULATE_TECHNIQUE_STATS
# ============================================================================

def test_calculate_technique_stats_basic():
    """Test technique winrate calculation — basic case"""
    trades = [
        {"technique": "twin_candle", "result": "WIN"},
        {"technique": "twin_candle", "result": "WIN"},
        {"technique": "twin_candle", "result": "WIN"},
        {"technique": "twin_candle", "result": "WIN"},
        {"technique": "twin_candle", "result": "LOSS"},
        {"technique": "breakout_follow", "result": "WIN"},
        {"technique": "breakout_follow", "result": "LOSS"},
        {"technique": "breakout_follow", "result": "LOSS"},
        {"technique": "breakout_follow", "result": "LOSS"},
    ]

    stats = calculate_technique_stats(trades)

    assert stats['twin_candle']['win'] == 4
    assert stats['twin_candle']['loss'] == 1
    assert stats['twin_candle']['winrate'] == 0.80

    assert stats['breakout_follow']['win'] == 1
    assert stats['breakout_follow']['loss'] == 3
    assert stats['breakout_follow']['winrate'] == 0.25


def test_calculate_technique_stats_no_trades():
    """Test technique stats with empty trade list"""
    stats = calculate_technique_stats([])
    assert stats == {}


def test_calculate_technique_stats_ignore_pending():
    """Test technique stats ignores PENDING trades"""
    trades = [
        {"technique": "twin_candle", "result": "WIN"},
        {"technique": "twin_candle", "result": "PENDING"},  # Should be ignored
        {"technique": "twin_candle", "result": "LOSS"},
    ]

    stats = calculate_technique_stats(trades)

    assert stats['twin_candle']['win'] == 1
    assert stats['twin_candle']['loss'] == 1
    assert stats['twin_candle']['winrate'] == 0.50


# ============================================================================
# TEST CALCULATE_SESSION_STATS
# ============================================================================

def test_calculate_session_stats_basic():
    """Test session winrate calculation — basic case"""
    trades = [
        {"session": "London", "result": "WIN"},
        {"session": "London", "result": "WIN"},
        {"session": "London", "result": "WIN"},
        {"session": "London", "result": "WIN"},
        {"session": "London", "result": "WIN"},
        {"session": "London", "result": "LOSS"},
        {"session": "NY", "result": "WIN"},
        {"session": "NY", "result": "WIN"},
        {"session": "NY", "result": "LOSS"},
        {"session": "NY", "result": "LOSS"},
        {"session": "NY", "result": "LOSS"},
    ]

    stats = calculate_session_stats(trades)

    assert stats['London']['win'] == 5
    assert stats['London']['loss'] == 1
    assert stats['London']['winrate'] == 0.83

    assert stats['NY']['win'] == 2
    assert stats['NY']['loss'] == 3
    assert stats['NY']['winrate'] == 0.40


def test_calculate_session_stats_no_trades():
    """Test session stats with empty trade list"""
    stats = calculate_session_stats([])
    assert stats == {}


# ============================================================================
# TEST CALCULATE_CURRENT_STREAK
# ============================================================================

def test_calculate_current_streak_win_streak():
    """Test streak calculation — win streak"""
    trades = [
        {"result": "LOSS", "timestamp_close": "2026-04-15T10:00:00"},
        {"result": "WIN", "timestamp_close": "2026-04-16T10:00:00"},
        {"result": "WIN", "timestamp_close": "2026-04-17T10:00:00"},
        {"result": "WIN", "timestamp_close": "2026-04-18T10:00:00"},  # Latest
    ]

    streak = calculate_current_streak(trades)
    assert streak == 3  # 3 consecutive wins


def test_calculate_current_streak_loss_streak():
    """Test streak calculation — loss streak"""
    trades = [
        {"result": "WIN", "timestamp_close": "2026-04-15T10:00:00"},
        {"result": "LOSS", "timestamp_close": "2026-04-16T10:00:00"},
        {"result": "LOSS", "timestamp_close": "2026-04-17T10:00:00"},  # Latest
    ]

    streak = calculate_current_streak(trades)
    assert streak == -2  # 2 consecutive losses


def test_calculate_current_streak_no_streak():
    """Test streak calculation — no streak (alternating)"""
    trades = [
        {"result": "WIN", "timestamp_close": "2026-04-17T10:00:00"},
        {"result": "LOSS", "timestamp_close": "2026-04-18T10:00:00"},  # Latest
    ]

    streak = calculate_current_streak(trades)
    assert streak == -1  # 1 loss (last trade)


def test_calculate_current_streak_empty():
    """Test streak calculation — empty trades"""
    streak = calculate_current_streak([])
    assert streak == 0


# ============================================================================
# TEST BUILD_REFLECTION_SUMMARY
# ============================================================================

def test_build_reflection_summary_insufficient_data():
    """Test summary with < 5 trades → Insufficient data"""
    technique_stats = {"twin_candle": {"win": 2, "loss": 1, "winrate": 0.67}}
    session_stats = {"London": {"win": 2, "loss": 1, "winrate": 0.67}}
    streak = 2

    summary = build_reflection_summary(technique_stats, session_stats, streak, "18Apr", trade_count=3)

    assert summary == "Insufficient data — trade normally"


def test_build_reflection_summary_all_good():
    """Test summary when all techniques performing well"""
    technique_stats = {
        "twin_candle": {"win": 8, "loss": 2, "winrate": 0.80},
        "mai_ruay": {"win": 7, "loss": 3, "winrate": 0.70}
    }
    session_stats = {
        "London": {"win": 10, "loss": 2, "winrate": 0.83},
        "NY": {"win": 5, "loss": 3, "winrate": 0.62}
    }
    streak = 3

    summary = build_reflection_summary(technique_stats, session_stats, streak, "18Apr", trade_count=15)

    assert "Reflect[18Apr]:" in summary
    assert "All techniques performing well" in summary or "80%" in summary
    assert "streak:3W" in summary


def test_build_reflection_summary_bad_technique_and_session():
    """Test summary with bad technique and session"""
    technique_stats = {
        "twin_candle": {"win": 4, "loss": 1, "winrate": 0.80},
        "breakout_follow": {"win": 1, "loss": 4, "winrate": 0.20}  # Bad
    }
    session_stats = {
        "London": {"win": 3, "loss": 1, "winrate": 0.75},
        "NY": {"win": 1, "loss": 4, "winrate": 0.20}  # Bad
    }
    streak = -2  # Loss streak

    summary = build_reflection_summary(technique_stats, session_stats, streak, "18Apr", trade_count=10)

    assert "Reflect[18Apr]:" in summary
    assert "breakout_follow" in summary or "20%" in summary
    assert "⚠️" in summary
    assert "NY" in summary or "20%" in summary
    assert "🕐" in summary
    assert "streak:2L" in summary


def test_build_reflection_summary_length_constraint():
    """Test summary respects ≤200 chars constraint"""
    # Create large stats to test truncation
    technique_stats = {
        f"technique_{i}": {"win": 5, "loss": 5, "winrate": 0.50}
        for i in range(10)
    }
    session_stats = {
        f"session_{i}": {"win": 5, "loss": 5, "winrate": 0.50}
        for i in range(5)
    }
    streak = 5

    summary = build_reflection_summary(technique_stats, session_stats, streak, "18Apr", trade_count=100)

    assert len(summary) <= 200


# ============================================================================
# TEST REFLECTOR CLASS
# ============================================================================

def test_reflector_update_basic():
    """Test Reflector.update() with mock data"""
    mock_trades = [
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T08:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T10:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "NY", "timestamp_close": "2026-04-17T14:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T16:00:00"},
        {"technique": "twin_candle", "result": "LOSS", "session": "Asia", "timestamp_close": "2026-04-18T01:00:00"},
        {"technique": "breakout_follow", "result": "LOSS", "session": "NY", "timestamp_close": "2026-04-17T17:00:00"},
    ]

    reflector = Reflector(sheets_logger=None)
    result = reflector.update(trade_history=mock_trades, force=True)

    assert 'reflection_summary' in result
    assert 'stats' in result
    assert 'updated_at' in result
    assert 'trade_count' in result

    assert result['trade_count'] == 6
    assert isinstance(result['reflection_summary'], str)
    assert len(result['reflection_summary']) <= 200


def test_reflector_cache():
    """Test Reflector caches result for same day"""
    mock_trades = [
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T08:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T10:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T11:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T12:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T13:00:00"},
    ]

    reflector = Reflector(sheets_logger=None)

    # First update
    result1 = reflector.update(trade_history=mock_trades, force=True)
    summary1 = result1['reflection_summary']

    # Second update (same day) — should use cache
    result2 = reflector.update(trade_history=mock_trades, force=False)
    summary2 = result2['reflection_summary']

    assert summary1 == summary2
    assert reflector.last_update_date is not None


def test_reflector_filters_pending():
    """Test Reflector ignores PENDING trades"""
    mock_trades = [
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T08:00:00"},
        {"technique": "twin_candle", "result": "PENDING", "session": "London", "timestamp_close": "2026-04-17T09:00:00"},
        {"technique": "twin_candle", "result": "LOSS", "session": "London", "timestamp_close": "2026-04-17T10:00:00"},
        {"technique": "twin_candle", "result": "PENDING", "session": "London", "timestamp_close": "2026-04-17T11:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T12:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T13:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T14:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "timestamp_close": "2026-04-17T15:00:00"},
    ]

    reflector = Reflector(sheets_logger=None)
    result = reflector.update(trade_history=mock_trades, force=True)

    # Should only count 6 trades (exclude 2 PENDING)
    assert result['trade_count'] == 6


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
