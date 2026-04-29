"""
Agent C — Weekly Strategist (v3.0)

หน้าที่:
- วิเคราะห์ trade history 7 วัน
- สร้าง weekly_stats + performance_context
- Performance context ส่งให้ Agent A (≤ 200 ตัวอักษร)

Model: claude-sonnet-4-20250514
Trigger: ทุก 7 วัน หรือ manual
Cost: ~$0.05/ครั้ง
"""

import os
import json
import logging
from typing import Dict, List
from datetime import datetime, date

import anthropic

logger = logging.getLogger(__name__)


# ============================================================================
# PRE-AGGREGATE — Python คำนวณก่อนส่ง Sonnet
# ============================================================================

def aggregate_weekly_stats(trade_history: list) -> dict:
    """
    Python คำนวณ stats ทั้งหมดก่อนส่ง Claude
    ห้ามส่ง raw history — ส่งเฉพาะ aggregated stats

    Args:
        trade_history: List of closed trades

    Returns:
        Aggregated stats dict
    """
    # Filter closed trades
    closed = [t for t in trade_history
              if t.get("result") in ["WIN", "LOSS"]]

    if len(closed) < 5:
        return {
            "insufficient_data": True,
            "count": len(closed),
            "message": "Need at least 5 trades for analysis"
        }

    # คำนวณต่อ technique
    by_technique = {}
    for t in closed:
        tech = t.get("technique", "unknown")
        if tech not in by_technique:
            by_technique[tech] = {"win": 0, "loss": 0, "pnl": 0.0}

        if t["result"] == "WIN":
            by_technique[tech]["win"] += 1
        else:
            by_technique[tech]["loss"] += 1

        by_technique[tech]["pnl"] += t.get("pnl_usd", 0)

    for tech, s in by_technique.items():
        total = s["win"] + s["loss"]
        s["winrate"] = round(s["win"] / total, 2) if total > 0 else 0
        s["total"] = total
        s["pnl"] = round(s["pnl"], 2)

    # คำนวณต่อ session
    by_session = {}
    for t in closed:
        session = t.get("session", "unknown")
        if session not in by_session:
            by_session[session] = {"win": 0, "loss": 0}

        if t["result"] == "WIN":
            by_session[session]["win"] += 1
        else:
            by_session[session]["loss"] += 1

    for s, v in by_session.items():
        total = v["win"] + v["loss"]
        v["winrate"] = round(v["win"] / total, 2) if total > 0 else 0
        v["total"] = total

    # คำนวณต่อ chart_type
    by_chart = {}
    for t in closed:
        ct = t.get("chart_type", "unknown")
        if ct not in by_chart:
            by_chart[ct] = {"win": 0, "loss": 0}

        if t["result"] == "WIN":
            by_chart[ct]["win"] += 1
        else:
            by_chart[ct]["loss"] += 1

    for ct, v in by_chart.items():
        total = v["win"] + v["loss"]
        v["winrate"] = round(v["win"] / total, 2) if total > 0 else 0
        v["total"] = total

    # V4.3: คำนวณต่อ beauty_score
    by_beauty = {"high": [], "mid": [], "low": []}
    for t in closed:
        beauty = t.get("beauty_score_used", 100)
        if beauty >= 90:
            by_beauty["high"].append(t)
        elif beauty >= 80:
            by_beauty["mid"].append(t)
        else:
            by_beauty["low"].append(t)

    def calc_stats(trades):
        if not trades:
            return {"win": 0, "loss": 0, "total": 0, "winrate": 0}
        wins = sum(1 for t in trades if t["result"] == "WIN")
        total = len(trades)
        return {
            "win": wins,
            "loss": total - wins,
            "total": total,
            "winrate": round(wins / total, 2) if total > 0 else 0
        }

    by_beauty_stats = {
        k: calc_stats(v) for k, v in by_beauty.items()
    }

    # overall
    total = len(closed)
    wins = sum(1 for t in closed if t["result"] == "WIN")
    overall_winrate = round(wins / total, 2) if total > 0 else 0
    total_pnl = sum(t.get("pnl_usd", 0) for t in closed)

    return {
        "period_trades": total,
        "overall_winrate": overall_winrate,
        "total_pnl": round(total_pnl, 2),
        "by_technique": by_technique,
        "by_session": by_session,
        "by_chart_type": by_chart,
        "by_beauty": by_beauty_stats,  # V4.3
    }


# ============================================================================
# TRIGGER LOGIC
# ============================================================================

def should_run_weekly(
    last_weekly_date: date,
    current_date: date
) -> bool:
    """
    รัน Agent C ถ้า:
    - ยังไม่เคยรัน
    - ผ่านมาแล้ว ≥ 7 วัน

    Args:
        last_weekly_date: Last run date (None if never)
        current_date: Current date

    Returns:
        True if should run
    """
    if last_weekly_date is None:
        return True
    return (current_date - last_weekly_date).days >= 7


# ============================================================================
# AGENT C — WEEKLY STRATEGIST CLASS
# ============================================================================

class G4WeeklyStrategist:
    """
    Agent C — Weekly Strategist

    Usage:
        weekly = G4WeeklyStrategist()
        result = weekly.analyze(weekly_stats)
    """

    WEEKLY_SYSTEM = """คุณคือ Trading Coach
หน้าที่: วิเคราะห์ผลเทรดสัปดาห์ที่ผ่านมา
       → สร้าง performance_context สั้นๆ
       ที่จะแนบใน prompt ของ Analyst Agent

กฎเคร่งครัด:
- วิเคราะห์จากตัวเลขที่ให้มาเท่านั้น
- ห้ามอ้างอิงข้อมูลที่ไม่ได้ให้มา
- ตอบเป็น JSON เท่านั้น"""

    WEEKLY_OUTPUT_FORMAT = """
{
  "performance_context": "string ≤ 200 ตัวอักษร สำหรับแนบใน prompt",
  "weak_techniques": ["technique ที่ winrate < 40%"],
  "weak_sessions": ["session ที่ winrate < 40%"],
  "strong_techniques": ["technique ที่ winrate > 70%"],
  "beauty_insight": "insight จาก beauty_score vs winrate (≤ 100 ตัวอักษร)",
  "overall_assessment": "good|neutral|poor",
  "recommendation": "string ≤ 100 ตัวอักษร"
}"""

    def __init__(self, api_key: str = None, config: dict = None):
        """
        Initialize Weekly Strategist

        Args:
            api_key: Anthropic API key (optional, reads from env)
            config: Optional config dict
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        self.config = config or {}
        self.verbose = self.config.get('verbose', False)

        # Initialize Anthropic client
        self.client = anthropic.Anthropic(api_key=self.api_key)

        # Cache
        self.last_analysis_date = None
        self.current_reflection = "No history yet — trade normally"

        logger.info("✓ Agent C (Weekly Strategist) initialized")

    def analyze(self, weekly_stats: dict) -> dict:
        """
        วิเคราะห์ weekly stats

        Args:
            weekly_stats: Aggregated stats (from aggregate_weekly_stats)

        Returns:
            {
                'success': bool,
                'performance_context': str,
                'weak_techniques': list,
                'strong_techniques': list,
                'overall_assessment': str,
                'llm_log': dict
            }
        """
        # Check insufficient data
        if weekly_stats.get("insufficient_data"):
            logger.info("Weekly analysis skipped: insufficient data")
            return {
                'success': True,
                'performance_context': "No history yet — trade normally",
                'weak_techniques': [],
                'strong_techniques': [],
                'overall_assessment': 'neutral',
                'llm_log': {'action': 'SKIP_INSUFFICIENT_DATA'}
            }

        # Build prompt
        user_prompt = self._build_user_prompt(weekly_stats)

        # Call Sonnet
        try:
            start_time = datetime.now()
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                temperature=0.0,
                system=self.WEEKLY_SYSTEM,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Parse response
            response_text = response.content[0].text
            analysis = self._parse_response(response_text)

            # Cache
            self.last_analysis_date = datetime.now().date()
            self.current_reflection = analysis.get("performance_context", "No history yet")

            # LLM log
            llm_log = self._build_llm_log(response, elapsed_ms)

            # Push agent log to dashboard
            try:
                from api_server import add_agent_log
                add_agent_log("weekly", {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action": "ANALYZE",
                    "reason": analysis.get("overall_assessment", "neutral")[:80],
                    "cost_usd": llm_log.get("cost_usd", 0),
                    "tokens": {
                        "input": llm_log.get("input_tokens", 0),
                        "output": llm_log.get("output_tokens", 0),
                        "cache_read": llm_log.get("cache_read_tokens", 0),
                        "cache_write": llm_log.get("cache_creation_tokens", 0),
                    },
                    "latency_sec": round(elapsed_ms / 1000, 2),
                    "model": "claude-sonnet-4-20250514",
                })
            except Exception as e:
                logger.debug(f"Failed to push agent log: {e}")

            return {
                'success': True,
                'performance_context': analysis.get("performance_context", ""),
                'weak_techniques': analysis.get("weak_techniques", []),
                'weak_sessions': analysis.get("weak_sessions", []),
                'strong_techniques': analysis.get("strong_techniques", []),
                'overall_assessment': analysis.get("overall_assessment", "neutral"),
                'recommendation': analysis.get("recommendation", ""),
                'llm_log': llm_log
            }

        except Exception as e:
            logger.error(f"Agent C analysis failed: {e}")
            return {
                'success': False,
                'performance_context': "Analysis error — trade normally",
                'weak_techniques': [],
                'strong_techniques': [],
                'overall_assessment': 'neutral',
                'llm_log': {'action': 'ERROR', 'error': str(e)}
            }

    def get_current_reflection(self) -> str:
        """
        Get cached reflection (ใช้เมื่อยังไม่ถึง 7 วัน)

        Returns:
            Current performance context string
        """
        return self.current_reflection

    def _build_user_prompt(self, weekly_stats: dict) -> str:
        """
        Build user prompt with aggregated stats

        Args:
            weekly_stats: Aggregated stats dict

        Returns:
            User prompt string
        """
        by_tech = weekly_stats.get("by_technique", {})
        by_session = weekly_stats.get("by_session", {})
        by_chart = weekly_stats.get("by_chart_type", {})
        by_beauty = weekly_stats.get("by_beauty", {})

        return f"""วิเคราะห์ผลเทรด 7 วันที่ผ่านมา

=== Overall ===
Total Trades: {weekly_stats.get('period_trades', 0)}
Overall Win Rate: {weekly_stats.get('overall_winrate', 0):.1%}
Total P&L: ${weekly_stats.get('total_pnl', 0):.2f}

=== By Technique ===
{self._format_stats(by_tech)}

=== By Session ===
{self._format_stats(by_session)}

=== By Chart Type ===
{self._format_stats(by_chart)}

=== By Beauty Score (V4.3) ===
{self._format_stats(by_beauty)}

=== คำถาม ===
1. Technique ไหนแพ้บ่อย (< 40%)? ควรหลีกเลี่ยงหรือไม่?
2. Session ไหนแพ้บ่อย (< 40%)? ควรระวังหรือไม่?
3. Technique ไหนชนะบ่อย (> 70%)? ควรชอบหรือไม่?
4. Beauty score สูง (≥90) vs ต่ำ (<80) ส่งผลต่อ winrate อย่างไร?
5. Overall assessment: good|neutral|poor?
6. Recommendation สำหรับ Analyst Agent (≤ 100 ตัวอักษร)?

สร้าง performance_context สั้นๆ (≤ 200 ตัวอักษร) สำหรับแนบใน prompt

{self.WEEKLY_OUTPUT_FORMAT}"""

    def _format_stats(self, stats_dict: dict) -> str:
        """
        Format stats dict to readable text

        Args:
            stats_dict: Stats dictionary

        Returns:
            Formatted string
        """
        if not stats_dict:
            return "  (no data)"

        lines = []
        for key, val in stats_dict.items():
            wr = val.get("winrate", 0)
            total = val.get("total", 0)
            pnl = val.get("pnl", 0)

            if pnl != 0:
                lines.append(f"  {key}: {wr:.0%} ({val['win']}/{total}) | P&L: ${pnl:.2f}")
            else:
                lines.append(f"  {key}: {wr:.0%} ({val['win']}/{total})")

        return "\n".join(lines)

    def _parse_response(self, response_text: str) -> dict:
        """
        Parse JSON response

        Args:
            response_text: Raw response text

        Returns:
            Analysis dict

        Raises:
            ValueError: If JSON parse fails
        """
        try:
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            analysis = json.loads(response_text.strip())
            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            logger.error(f"Raw response: {response_text[:500]}")
            raise ValueError(f"Invalid JSON from Sonnet: {e}")

    def _build_llm_log(self, response, elapsed_ms: float) -> dict:
        """
        Build LLM usage log

        Args:
            response: Anthropic API response
            elapsed_ms: Elapsed time in milliseconds

        Returns:
            LLM log dict
        """
        usage = response.usage

        # Calculate cost (Sonnet 4 pricing)
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens

        input_cost = (input_tokens / 1_000_000) * 3.00
        output_cost = (output_tokens / 1_000_000) * 15.00
        total_cost = input_cost + output_cost

        return {
            'action': 'WEEKLY_ANALYSIS',
            'model': response.model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'cost_usd': round(total_cost, 4),
            'elapsed_ms': round(elapsed_ms, 1)
        }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("AGENT C — WEEKLY STRATEGIST TEST")
    print("="*70)

    # Mock trade history
    mock_history = [
        {"result": "WIN", "technique": "twin_candle", "session": "London", "chart_type": "uptrend", "pnl_usd": 15.0},
        {"result": "LOSS", "technique": "twin_candle", "session": "London", "chart_type": "uptrend", "pnl_usd": -10.0},
        {"result": "WIN", "technique": "breakout_follow", "session": "NY", "chart_type": "downtrend", "pnl_usd": 20.0},
        {"result": "WIN", "technique": "twin_candle", "session": "Asia", "chart_type": "uptrend", "pnl_usd": 12.0},
        {"result": "LOSS", "technique": "mai_ruay", "session": "London", "chart_type": "unclear", "pnl_usd": -8.0},
        {"result": "WIN", "technique": "twin_candle", "session": "London", "chart_type": "uptrend", "pnl_usd": 18.0},
    ]

    # Aggregate stats
    stats = aggregate_weekly_stats(mock_history)
    print(f"\n✓ Aggregated stats:")
    print(f"  Total Trades: {stats['period_trades']}")
    print(f"  Overall Win Rate: {stats['overall_winrate']:.1%}")
    print(f"  Total P&L: ${stats['total_pnl']:.2f}")

    # Initialize agent
    weekly = G4WeeklyStrategist()
    print("\n✓ Agent C initialized — ready to analyze")
    print("="*70)
