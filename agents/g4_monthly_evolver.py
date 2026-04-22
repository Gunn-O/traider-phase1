"""
Agent D — Strategy Evolver (v3.0)

หน้าที่:
- วิเคราะห์ trade 30 วัน
- Propose กฎใหม่ให้ human approve
- ⚠️ ไม่แก้ strategy อัตโนมัติ — human approve เสมอ

Model: claude-sonnet-4-20250514
Trigger: ทุกวันที่ 1 ของเดือน หรือ manual
Cost: ~$0.10/ครั้ง
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

def aggregate_monthly_stats(trade_history: list) -> dict:
    """
    Python คำนวณ stats ทั้งหมดก่อนส่ง Claude
    สำหรับ 30 วันข้อมูล

    Args:
        trade_history: List of closed trades (30 days)

    Returns:
        Aggregated stats dict
    """
    # Filter closed trades
    closed = [t for t in trade_history
              if t.get("result") in ["WIN", "LOSS"]]

    if len(closed) < 15:
        return {
            "insufficient_data": True,
            "count": len(closed),
            "message": "Need at least 15 trades for monthly analysis"
        }

    # คำนวณต่อ technique (with more detail)
    by_technique = {}
    for t in closed:
        tech = t.get("technique", "unknown")
        if tech not in by_technique:
            by_technique[tech] = {
                "win": 0,
                "loss": 0,
                "pnl": 0.0,
                "avg_rr": [],
                "avg_sl_pip": [],
                "win_reasons": [],
                "loss_reasons": []
            }

        if t["result"] == "WIN":
            by_technique[tech]["win"] += 1
            by_technique[tech]["win_reasons"].append(t.get("close_reason", ""))
        else:
            by_technique[tech]["loss"] += 1
            by_technique[tech]["loss_reasons"].append(t.get("close_reason", ""))

        by_technique[tech]["pnl"] += t.get("pnl_usd", 0)
        by_technique[tech]["avg_rr"].append(t.get("rr_ratio", 0))
        by_technique[tech]["avg_sl_pip"].append(t.get("sl_pip", 0))

    for tech, s in by_technique.items():
        total = s["win"] + s["loss"]
        s["winrate"] = round(s["win"] / total, 2) if total > 0 else 0
        s["total"] = total
        s["pnl"] = round(s["pnl"], 2)
        s["avg_rr"] = round(sum(s["avg_rr"]) / len(s["avg_rr"]), 2) if s["avg_rr"] else 0
        s["avg_sl_pip"] = round(sum(s["avg_sl_pip"]) / len(s["avg_sl_pip"]), 0) if s["avg_sl_pip"] else 0

        # Reason frequency
        s["sl_hit_count"] = s["loss_reasons"].count("SL_HIT")
        s["tp_hit_count"] = s["win_reasons"].count("TP_HIT")

    # คำนวณต่อ chart_type
    by_chart = {}
    for t in closed:
        ct = t.get("chart_type", "unknown")
        if ct not in by_chart:
            by_chart[ct] = {"win": 0, "loss": 0, "pnl": 0.0}

        if t["result"] == "WIN":
            by_chart[ct]["win"] += 1
        else:
            by_chart[ct]["loss"] += 1

        by_chart[ct]["pnl"] += t.get("pnl_usd", 0)

    for ct, v in by_chart.items():
        total = v["win"] + v["loss"]
        v["winrate"] = round(v["win"] / total, 2) if total > 0 else 0
        v["total"] = total
        v["pnl"] = round(v["pnl"], 2)

    # คำนวณต่อ timeframe
    by_tf = {}
    for t in closed:
        tf = t.get("timeframe", "unknown")
        if tf not in by_tf:
            by_tf[tf] = {"win": 0, "loss": 0}

        if t["result"] == "WIN":
            by_tf[tf]["win"] += 1
        else:
            by_tf[tf]["loss"] += 1

    for tf, v in by_tf.items():
        total = v["win"] + v["loss"]
        v["winrate"] = round(v["win"] / total, 2) if total > 0 else 0
        v["total"] = total

    # overall
    total = len(closed)
    wins = sum(1 for t in closed if t["result"] == "WIN")
    overall_winrate = round(wins / total, 2) if total > 0 else 0
    total_pnl = sum(t.get("pnl_usd", 0) for t in closed)

    # Avg R:R
    all_rr = [t.get("rr_ratio", 0) for t in closed if t.get("rr_ratio", 0) > 0]
    avg_rr = round(sum(all_rr) / len(all_rr), 2) if all_rr else 0

    return {
        "period_trades": total,
        "overall_winrate": overall_winrate,
        "total_pnl": round(total_pnl, 2),
        "avg_rr": avg_rr,
        "by_technique": by_technique,
        "by_chart_type": by_chart,
        "by_timeframe": by_tf,
    }


# ============================================================================
# TRIGGER LOGIC
# ============================================================================

def should_run_monthly(
    last_monthly_date: date,
    current_date: date
) -> bool:
    """
    รัน Agent D ถ้า:
    - ยังไม่เคยรัน
    - เป็นวันที่ 1 ของเดือน

    Args:
        last_monthly_date: Last run date (None if never)
        current_date: Current date

    Returns:
        True if should run
    """
    if last_monthly_date is None:
        return True

    # ตรวจเดือนต่างกัน + เป็นวันที่ 1-7 ของเดือน
    different_month = (
        current_date.year != last_monthly_date.year or
        current_date.month != last_monthly_date.month
    )
    early_in_month = current_date.day <= 7

    return different_month and early_in_month


# ============================================================================
# AGENT D — MONTHLY EVOLVER CLASS
# ============================================================================

class G4MonthlyEvolver:
    """
    Agent D — Strategy Evolver

    Usage:
        monthly = G4MonthlyEvolver()
        result = monthly.analyze(monthly_stats)
    """

    MONTHLY_SYSTEM = """คุณคือ Strategy Evolution Analyst
หน้าที่: วิเคราะห์ผลเทรด 30 วัน
       → เสนอกฎใหม่ให้ human approve

⚠️ CRITICAL — ห้ามแก้ strategy อัตโนมัติ
Human ต้อง approve ก่อนทุกครั้ง

กฎเคร่งครัด:
- วิเคราะห์จากตัวเลขที่ให้มาเท่านั้น
- เสนอเฉพาะกฎที่มีหลักฐานสนับสนุนชัดเจน
- ระบุ sample size และ confidence
- ตอบเป็น JSON เท่านั้น"""

    MONTHLY_OUTPUT_FORMAT = """
{
  "proposals": [
    {
      "rule_target": "section ใน strategy เช่น Branch A SL",
      "current_rule": "กฎปัจจุบัน",
      "proposed_change": "กฎที่เสนอ",
      "evidence": {
        "sample_size": 0,
        "supporting_stat": "ตัวเลขที่สนับสนุน"
      },
      "confidence": 0.0,
      "priority": "high|medium|low"
    }
  ],
  "do_not_change": ["สิ่งที่ทำได้ดีอยู่แล้ว"],
  "beauty_score_insight": "วิเคราะห์ beauty_score (≥90 vs <80) vs winrate (≤ 150 ตัวอักษร)",
  "summary": "string ≤ 150 ตัวอักษร"
}

⚠️ proposals ต้องผ่าน human approve ก่อน merge เสมอ
ไม่มี auto-update strategy MD"""

    def __init__(self, api_key: str = None, config: dict = None):
        """
        Initialize Monthly Evolver

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
        self.last_proposals = []

        logger.info("✓ Agent D (Monthly Evolver) initialized")

    def analyze(self, monthly_stats: dict) -> dict:
        """
        วิเคราะห์ monthly stats → propose กฎใหม่

        Args:
            monthly_stats: Aggregated stats (from aggregate_monthly_stats)

        Returns:
            {
                'success': bool,
                'proposals': list,
                'do_not_change': list,
                'summary': str,
                'llm_log': dict
            }
        """
        # Check insufficient data
        if monthly_stats.get("insufficient_data"):
            logger.info("Monthly analysis skipped: insufficient data")
            return {
                'success': True,
                'proposals': [],
                'do_not_change': [],
                'summary': 'Insufficient data for monthly analysis',
                'llm_log': {'action': 'SKIP_INSUFFICIENT_DATA'}
            }

        # Build prompt
        user_prompt = self._build_user_prompt(monthly_stats)

        # Call Sonnet
        try:
            start_time = datetime.now()
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                temperature=0.0,
                system=self.MONTHLY_SYSTEM,
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
            self.last_proposals = analysis.get("proposals", [])

            # LLM log
            llm_log = self._build_llm_log(response, elapsed_ms)

            # Save proposals (for human review)
            self._save_proposals(analysis)

            # Push agent log to dashboard
            try:
                from api_server import add_agent_log
                add_agent_log("monthly", {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action": "EVOLVE",
                    "reason": f"{len(analysis.get('proposals', []))} proposals"[:80],
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
                'proposals': analysis.get("proposals", []),
                'do_not_change': analysis.get("do_not_change", []),
                'summary': analysis.get("summary", ""),
                'llm_log': llm_log
            }

        except Exception as e:
            logger.error(f"Agent D analysis failed: {e}")
            return {
                'success': False,
                'proposals': [],
                'do_not_change': [],
                'summary': f'Analysis error: {str(e)[:100]}',
                'llm_log': {'action': 'ERROR', 'error': str(e)}
            }

    def get_last_proposals(self) -> list:
        """
        Get cached proposals (for human review)

        Returns:
            List of proposals
        """
        return self.last_proposals

    def _build_user_prompt(self, monthly_stats: dict) -> str:
        """
        Build user prompt with aggregated stats

        Args:
            monthly_stats: Aggregated stats dict

        Returns:
            User prompt string
        """
        by_tech = monthly_stats.get("by_technique", {})
        by_chart = monthly_stats.get("by_chart_type", {})
        by_tf = monthly_stats.get("by_timeframe", {})

        return f"""วิเคราะห์ผลเทรด 30 วันที่ผ่านมา → เสนอกฎใหม่

=== Overall (30 วัน) ===
Total Trades: {monthly_stats.get('period_trades', 0)}
Overall Win Rate: {monthly_stats.get('overall_winrate', 0):.1%}
Total P&L: ${monthly_stats.get('total_pnl', 0):.2f}
Average R:R: {monthly_stats.get('avg_rr', 0):.2f}

=== By Technique ===
{self._format_technique_stats(by_tech)}

=== By Chart Type ===
{self._format_stats(by_chart)}

=== By Timeframe ===
{self._format_stats(by_tf)}

=== คำถาม ===
1. Technique ไหนควรปรับกฎ? (เช่น SL กว้างเกิน/แคบเกิน)
2. Chart type ไหนควรหลีกเลี่ยงหรือชอบ?
3. Timeframe ไหนควรเปลี่ยน?
4. มีกฎอะไรที่ทำได้ดีอยู่แล้ว (do not change)?

เสนอเฉพาะกฎที่มีหลักฐานชัดเจน
Sample size ≥ 10 trades per proposal

{self.MONTHLY_OUTPUT_FORMAT}"""

    def _format_technique_stats(self, stats_dict: dict) -> str:
        """
        Format technique stats with detail

        Args:
            stats_dict: Technique stats dictionary

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
            avg_rr = val.get("avg_rr", 0)
            avg_sl = val.get("avg_sl_pip", 0)
            sl_hit = val.get("sl_hit_count", 0)
            tp_hit = val.get("tp_hit_count", 0)

            lines.append(
                f"  {key}: {wr:.0%} ({val['win']}/{total}) | "
                f"P&L: ${pnl:.2f} | "
                f"Avg R:R: {avg_rr:.2f} | "
                f"Avg SL: {avg_sl}pip | "
                f"SL hits: {sl_hit}/{total} | "
                f"TP hits: {tp_hit}/{total}"
            )

        return "\n".join(lines)

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
                lines.append(f"  {key}: {wr:.0%} ({val.get('win', 0)}/{total}) | P&L: ${pnl:.2f}")
            else:
                lines.append(f"  {key}: {wr:.0%} ({val.get('win', 0)}/{total})")

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

    def _save_proposals(self, analysis: dict):
        """
        Save proposals to file (for human review)

        Args:
            analysis: Analysis dict with proposals
        """
        try:
            from pathlib import Path

            proposals_dir = Path("strategy/proposals")
            proposals_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = proposals_dir / f"proposals_{timestamp}.json"

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)

            logger.info(f"✓ Proposals saved: {filename}")

        except Exception as e:
            logger.error(f"Failed to save proposals: {e}")

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
            'action': 'MONTHLY_ANALYSIS',
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
    print("AGENT D — MONTHLY EVOLVER TEST")
    print("="*70)

    # Mock monthly stats
    mock_stats = {
        "period_trades": 25,
        "overall_winrate": 0.56,
        "total_pnl": 125.50,
        "avg_rr": 1.35,
        "by_technique": {
            "twin_candle": {
                "winrate": 0.65,
                "total": 15,
                "win": 10,
                "loss": 5,
                "pnl": 85.0,
                "avg_rr": 1.50,
                "avg_sl_pip": 1200,
                "sl_hit_count": 4,
                "tp_hit_count": 9
            },
            "mai_ruay": {
                "winrate": 0.30,
                "total": 10,
                "win": 3,
                "loss": 7,
                "pnl": -45.0,
                "avg_rr": 0.95,
                "avg_sl_pip": 800,
                "sl_hit_count": 6,
                "tp_hit_count": 2
            }
        }
    }

    # Initialize agent
    monthly = G4MonthlyEvolver()
    print("\n✓ Agent D initialized — ready to analyze")
    print("="*70)
