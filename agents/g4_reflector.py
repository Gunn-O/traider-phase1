"""
G4d — Reflector Agent (v4.3)

หน้าที่:
- อ่าน trade history ที่ปิดแล้ว (WIN/LOSS only)
- คำนวณ winrate ต่อ technique, session, beauty_score
- สร้าง reflection_summary ≤ 200 ตัวอักษร
- Trigger วันละ 1 ครั้ง (daily reset ตอน 00:00 UTC)

V4.3: เพิ่ม beauty_score analysis (≥90 vs <80)
ต้นทุนเพิ่ม: $0 (Pure Python calculation)
"""

import logging
from typing import Dict, List
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


# ============================================================================
# TRIGGER LOGIC
# ============================================================================

def should_run_daily(last_daily_date, current_date) -> bool:
    """
    รัน Reflector ถ้า:
    - ยังไม่เคยรัน (last_daily_date is None)
    - ผ่านมาแล้ว ≥ 1 วัน

    Args:
        last_daily_date: Last run date (None if never, or date object)
        current_date: Current date (date object)

    Returns:
        True if should run
    """
    if last_daily_date is None:
        return True
    return (current_date - last_daily_date).days >= 1


# ============================================================================
# STATS CALCULATION
# ============================================================================

def calculate_technique_stats(trades: List[Dict]) -> Dict:
    """
    คำนวณ winrate ต่อ technique

    Args:
        trades: list of trade dicts with 'technique', 'result' (WIN/LOSS)

    Returns:
        {
            "twin_candle": {"win": 4, "loss": 1, "winrate": 0.80},
            "breakout_follow": {"win": 1, "loss": 3, "winrate": 0.25},
            ...
        }
    """
    stats = defaultdict(lambda: {"win": 0, "loss": 0, "winrate": 0.0})

    for trade in trades:
        technique = trade.get('technique', 'unknown')
        result = trade.get('result', '')

        if result == 'WIN':
            stats[technique]['win'] += 1
        elif result == 'LOSS':
            stats[technique]['loss'] += 1

    # Calculate winrate
    for technique, data in stats.items():
        total = data['win'] + data['loss']
        if total > 0:
            data['winrate'] = round(data['win'] / total, 2)
        else:
            data['winrate'] = 0.0

    return dict(stats)


def calculate_session_stats(trades: List[Dict]) -> Dict:
    """
    คำนวณ winrate ต่อ session

    Args:
        trades: list of trade dicts with 'session', 'result' (WIN/LOSS)

    Returns:
        {
            "London": {"win": 5, "loss": 1, "winrate": 0.83},
            "NY": {"win": 2, "loss": 3, "winrate": 0.40},
            ...
        }
    """
    stats = defaultdict(lambda: {"win": 0, "loss": 0, "winrate": 0.0})

    for trade in trades:
        session = trade.get('session', 'Unknown')
        result = trade.get('result', '')

        if result == 'WIN':
            stats[session]['win'] += 1
        elif result == 'LOSS':
            stats[session]['loss'] += 1

    # Calculate winrate
    for session, data in stats.items():
        total = data['win'] + data['loss']
        if total > 0:
            data['winrate'] = round(data['win'] / total, 2)
        else:
            data['winrate'] = 0.0

    return dict(stats)


def calculate_current_streak(trades: List[Dict]) -> int:
    """
    คำนวณ streak ปัจจุบัน (นับจาก trade ล่าสุดย้อนหลัง)

    Args:
        trades: list of trade dicts sorted by timestamp (oldest first)

    Returns:
        int: ลบ = loss streak, บวก = win streak
        ตัวอย่าง: -2 = loss 2 ติดกัน, +3 = win 3 ติดกัน
    """
    if not trades:
        return 0

    # Sort by timestamp (newest first for streak calculation)
    sorted_trades = sorted(trades, key=lambda x: x.get('timestamp_close', ''), reverse=True)

    streak = 0
    last_result = None

    for trade in sorted_trades:
        result = trade.get('result', '')
        if result not in ['WIN', 'LOSS']:
            continue

        if last_result is None:
            # First trade
            last_result = result
            streak = 1 if result == 'WIN' else -1
        elif result == last_result:
            # Continue streak
            if result == 'WIN':
                streak += 1
            else:
                streak -= 1
        else:
            # Streak broken
            break

    return streak


def calculate_beauty_stats(trades: List[Dict]) -> Dict:
    """
    คำนวณ winrate ต่อ beauty_score range (V4.3)

    Args:
        trades: list of trade dicts with 'beauty_score_used', 'result'

    Returns:
        {
            "high": {"win": 3, "loss": 0, "total": 3, "winrate": 1.00},  # ≥90
            "mid": {"win": 2, "loss": 1, "total": 3, "winrate": 0.67},   # 80-89
            "low": {"win": 1, "loss": 2, "total": 3, "winrate": 0.33}    # <80
        }
    """
    stats = {
        "high": {"win": 0, "loss": 0, "total": 0, "winrate": 0.0},
        "mid": {"win": 0, "loss": 0, "total": 0, "winrate": 0.0},
        "low": {"win": 0, "loss": 0, "total": 0, "winrate": 0.0}
    }

    for trade in trades:
        beauty = trade.get('beauty_score_used', 100)
        result = trade.get('result', '')

        if result not in ['WIN', 'LOSS']:
            continue

        # Categorize by beauty score
        if beauty >= 90:
            category = "high"
        elif beauty >= 80:
            category = "mid"
        else:
            category = "low"

        # Update stats
        if result == 'WIN':
            stats[category]['win'] += 1
        else:
            stats[category]['loss'] += 1

        stats[category]['total'] += 1

    # Calculate winrate
    for category, data in stats.items():
        if data['total'] > 0:
            data['winrate'] = round(data['win'] / data['total'], 2)

    return stats


# ============================================================================
# REFLECTION SUMMARY GENERATION
# ============================================================================

def build_reflection_summary(technique_stats: Dict, session_stats: Dict,
                             streak: int, date: str, trade_count: int,
                             beauty_stats: Dict = None) -> str:
    """
    สร้าง reflection_summary ≤ 200 ตัวอักษร (V4.3: รองรับ beauty_score)

    Format: "Reflect[วันที่]: [technique ดี] ✅ [technique แย่] ⚠️ [session แย่] 🕐 [beauty insight] [streak]"

    กฎ:
    - technique winrate < 40% → ใส่ ⚠️
    - session winrate < 40% → ใส่ 🕐
    - beauty high (≥90) ชนะบ่อย vs low (<80) แพ้บ่อย → ใส่ 💎
    - ถ้าทุกอย่างดี (winrate > 60%) → "All techniques performing well ✅"
    - ถ้า trade_count < 5 → "Insufficient data — trade normally"
    - ต้องไม่เกิน 200 ตัวอักษรเด็ดขาด

    Args:
        technique_stats: dict from calculate_technique_stats()
        session_stats: dict from calculate_session_stats()
        streak: current streak (int)
        date: date string (e.g., "17Apr")
        trade_count: number of trades used
        beauty_stats: dict from calculate_beauty_stats() (V4.3)

    Returns:
        reflection_summary string (≤ 200 chars)
    """
    if trade_count < 5:
        return "Insufficient data — trade normally"

    # Find techniques with good/bad performance
    good_techniques = []
    bad_techniques = []

    for technique, stats in technique_stats.items():
        total = stats['win'] + stats['loss']
        if total < 2:  # Skip if too few samples
            continue

        winrate = stats['winrate']
        if winrate >= 0.60:
            good_techniques.append(f"{technique} {int(winrate*100)}%")
        elif winrate < 0.40:
            bad_techniques.append(f"{technique} {int(winrate*100)}%")

    # Find sessions with bad performance
    bad_sessions = []
    for session, stats in session_stats.items():
        total = stats['win'] + stats['loss']
        if total < 2:
            continue

        if stats['winrate'] < 0.40:
            bad_sessions.append(f"{session} {int(stats['winrate']*100)}%")

    # V4.3: Check beauty insight
    beauty_insight = None
    if beauty_stats:
        high_wr = beauty_stats['high']['winrate']
        low_wr = beauty_stats['low']['winrate']
        high_total = beauty_stats['high']['total']
        low_total = beauty_stats['low']['total']

        # ถ้ามีข้อมูลเพียงพอ (≥2 ไม้ในแต่ละกลุ่ม)
        if high_total >= 2 and low_total >= 2:
            if high_wr > 0.70 and low_wr < 0.40:
                beauty_insight = f"Beauty matters: {int(high_wr*100)}% vs {int(low_wr*100)}%💎"

    # Build summary
    parts = [f"Reflect[{date}]:"]

    # All good case
    if not bad_techniques and not bad_sessions and streak >= 0:
        parts.append("All techniques performing well ✅")
    else:
        # Add good techniques
        if good_techniques:
            parts.append(f"{good_techniques[0]}✅")

        # Add bad techniques
        if bad_techniques:
            parts.append(f"{bad_techniques[0]}⚠️")

        # Add bad sessions
        if bad_sessions:
            parts.append(f"{bad_sessions[0]}🕐")

    # V4.3: Add beauty insight if significant
    if beauty_insight:
        parts.append(beauty_insight)

    # Add streak
    streak_text = f"streak:{abs(streak)}{'L' if streak < 0 else 'W'}"
    parts.append(streak_text)

    summary = " ".join(parts)

    # Truncate ถ้าเกิน 200 chars
    if len(summary) > 200:
        summary = summary[:197] + "..."

    return summary


# ============================================================================
# MAIN REFLECTOR CLASS
# ============================================================================

class Reflector:
    """
    Reflector Agent — คำนวณ performance reflection จาก trade history

    Usage:
        reflector = Reflector(sheets_logger)
        result = reflector.update()
        # result = {
        #     'reflection_summary': str,
        #     'stats': dict,
        #     'updated_at': str,
        #     'trade_count': int
        # }
    """

    def __init__(self, sheets_logger=None):
        """
        Initialize Reflector

        Args:
            sheets_logger: SheetsLogger instance (optional, for reading trade history)
        """
        self.sheets_logger = sheets_logger
        self.last_update_date = None
        self.cached_reflection = None
        logger.info("Reflector initialized")

    def update(self, trade_history: List[Dict] = None, force: bool = False) -> Dict:
        """
        Update reflection (ควรเรียกวันละ 1 ครั้ง ตอน 00:00 UTC)

        Args:
            trade_history: list of trade dicts (optional, will fetch from Sheets if None)
            force: force update even if already updated today

        Returns:
            {
                'reflection_summary': str,  # ≤ 200 chars
                'stats': dict,              # full stats
                'updated_at': str,          # ISO timestamp
                'trade_count': int          # จำนวน trade ที่ใช้คำนวณ
            }
        """
        today = datetime.now().date()

        # Check if already updated today (skip unless force=True)
        if not force and self.last_update_date == today and self.cached_reflection:
            logger.info(f"Reflection already updated today ({today}), using cache")
            return self.cached_reflection

        # Fetch trade history
        if trade_history is None:
            trade_history = self._fetch_trade_history()

        # Filter: เฉพาะ WIN/LOSS, ย้อนหลังไม่เกิน 30 วันหรือ 50 trades
        filtered_trades = self._filter_trades(trade_history)

        trade_count = len(filtered_trades)
        logger.info(f"Calculating reflection from {trade_count} closed trades")

        # Calculate stats
        technique_stats = calculate_technique_stats(filtered_trades)
        session_stats = calculate_session_stats(filtered_trades)
        streak = calculate_current_streak(filtered_trades)
        beauty_stats = calculate_beauty_stats(filtered_trades)  # V4.3

        # Generate summary
        date_str = today.strftime("%d%b")  # e.g., "17Apr"
        reflection_summary = build_reflection_summary(
            technique_stats, session_stats, streak, date_str, trade_count,
            beauty_stats=beauty_stats  # V4.3
        )

        # Build result
        result = {
            'reflection_summary': reflection_summary,
            'stats': {
                'technique': technique_stats,
                'session': session_stats,
                'streak': streak,
                'beauty': beauty_stats  # V4.3
            },
            'updated_at': datetime.now().isoformat(),
            'trade_count': trade_count
        }

        # Cache result
        self.last_update_date = today
        self.cached_reflection = result

        logger.info(f"✓ Reflection updated: {reflection_summary}")

        # Push agent log to dashboard (Python-only, $0 cost)
        try:
            from api_server import add_agent_log
            add_agent_log("reflector", {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": "REFLECT",
                "reason": reflection_summary[:80],
                "cost_usd": 0.0,  # Python-only
                "tokens": {
                    "input": 0,
                    "output": 0,
                    "cache_read": 0,
                    "cache_write": 0,
                },
                "latency_sec": 0.0,
                "model": "Python",
            })
        except Exception as e:
            logger.debug(f"Failed to push agent log: {e}")

        return result

    def _fetch_trade_history(self) -> List[Dict]:
        """Fetch closed trades from Sheets"""
        if not self.sheets_logger or not self.sheets_logger.enabled:
            logger.warning("Sheets logger not available, returning empty history")
            return []

        try:
            # Get all trades from Sheets
            all_rows = self.sheets_logger.trade_log_ws.get_all_records()

            # Filter: เฉพาะ WIN/LOSS
            closed_trades = [
                r for r in all_rows
                if r.get('result') in ['WIN', 'LOSS']
            ]

            logger.info(f"Fetched {len(closed_trades)} closed trades from Sheets")
            return closed_trades

        except Exception as e:
            logger.error(f"Failed to fetch trade history: {e}")
            return []

    def _filter_trades(self, trades: List[Dict]) -> List[Dict]:
        """
        Filter trades: เฉพาะ WIN/LOSS, ย้อนหลังไม่เกิน 30 วัน หรือ 50 trades

        Args:
            trades: list of trade dicts

        Returns:
            filtered list (sorted by timestamp_close, oldest first)
        """
        # Filter: เฉพาะ WIN/LOSS
        closed = [t for t in trades if t.get('result') in ['WIN', 'LOSS']]

        if not closed:
            return []

        # Sort by timestamp_close (oldest first)
        sorted_trades = sorted(closed, key=lambda x: x.get('timestamp_close', ''))

        # Filter: ย้อนหลังไม่เกิน 30 วัน
        cutoff_date = datetime.now() - timedelta(days=30)
        recent_trades = []

        for trade in sorted_trades:
            close_time_str = trade.get('timestamp_close', '')
            if close_time_str:
                try:
                    # Parse ISO timestamp
                    close_time = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
                    if close_time >= cutoff_date:
                        recent_trades.append(trade)
                except Exception:
                    # If parse fails, include the trade (better safe than sorry)
                    recent_trades.append(trade)
            else:
                recent_trades.append(trade)

        # Limit: ไม่เกิน 50 trades
        limited_trades = recent_trades[-50:] if len(recent_trades) > 50 else recent_trades

        return limited_trades

    def get_current_reflection(self) -> str:
        """
        Get current reflection_summary (ใช้ cache ถ้ามี)

        Returns:
            reflection_summary string or "No history yet — trade normally"
        """
        if self.cached_reflection:
            return self.cached_reflection['reflection_summary']
        else:
            return "No history yet — trade normally"


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("REFLECTOR AGENT TEST")
    print("="*70)

    # Mock trade history (V4.3: with beauty_score_used)
    mock_trades = [
        {"technique": "twin_candle", "result": "WIN", "session": "London", "beauty_score_used": 100, "timestamp_close": "2026-04-17T08:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "beauty_score_used": 90, "timestamp_close": "2026-04-17T10:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "NY", "beauty_score_used": 90, "timestamp_close": "2026-04-17T14:00:00"},
        {"technique": "twin_candle", "result": "WIN", "session": "London", "beauty_score_used": 80, "timestamp_close": "2026-04-17T16:00:00"},
        {"technique": "twin_candle", "result": "LOSS", "session": "Asia", "beauty_score_used": 60, "timestamp_close": "2026-04-18T01:00:00"},
        {"technique": "breakout_follow", "result": "WIN", "session": "NY", "beauty_score_used": 100, "timestamp_close": "2026-04-17T15:00:00"},
        {"technique": "breakout_follow", "result": "LOSS", "session": "NY", "beauty_score_used": 60, "timestamp_close": "2026-04-17T17:00:00"},
        {"technique": "breakout_follow", "result": "LOSS", "session": "NY", "beauty_score_used": 60, "timestamp_close": "2026-04-17T19:00:00"},
        {"technique": "breakout_follow", "result": "LOSS", "session": "Asia", "beauty_score_used": 60, "timestamp_close": "2026-04-18T02:00:00"},
        {"technique": "mai_ruay", "result": "WIN", "session": "London", "beauty_score_used": 90, "timestamp_close": "2026-04-17T11:00:00"},
        {"technique": "mai_ruay", "result": "WIN", "session": "NY", "beauty_score_used": 80, "timestamp_close": "2026-04-17T18:00:00"},
        {"technique": "mai_ruay", "result": "LOSS", "session": "Asia", "beauty_score_used": 60, "timestamp_close": "2026-04-18T03:00:00"},
    ]

    reflector = Reflector()
    result = reflector.update(trade_history=mock_trades, force=True)

    print(f"\n📊 Reflection Summary:")
    print(f"   {result['reflection_summary']}")
    print(f"\n   Trade count: {result['trade_count']}")
    print(f"   Updated at: {result['updated_at']}")

    print(f"\n📈 Technique Stats:")
    for tech, stats in result['stats']['technique'].items():
        print(f"   {tech}: {stats['win']}W-{stats['loss']}L ({int(stats['winrate']*100)}%)")

    print(f"\n🕐 Session Stats:")
    for session, stats in result['stats']['session'].items():
        print(f"   {session}: {stats['win']}W-{stats['loss']}L ({int(stats['winrate']*100)}%)")

    print(f"\n💎 Beauty Stats (V4.3):")
    for category, stats in result['stats']['beauty'].items():
        print(f"   {category}: {stats['win']}W-{stats['loss']}L ({int(stats['winrate']*100)}%)")

    print(f"\n🔥 Current Streak: {result['stats']['streak']}")

    print("\n" + "="*70)
