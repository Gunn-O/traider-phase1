"""
Agent B — Risk Manager (v4.3)

หน้าที่:
- Approve lot + ปรับตาม performance context
- รับ decision จาก Agent A + balance + risk_context
- Output: approved + lot + reason
- V4.3: รองรับ beauty_adjustment (ลด lot ถ้า beauty_score < 80)

Model: claude-haiku-4-5-20251001 (ประหยัด cost)
Reference: TRAIDER_MASTER_PLAN_v2.1.md Section 2
"""

import os
import json
import logging
from typing import Dict
from datetime import datetime

import anthropic

from config import calc_lot, RISK_CONFIG

logger = logging.getLogger(__name__)


# ============================================================================
# RISK CONTEXT BUILDER — Python คำนวณก่อนส่ง Haiku
# ============================================================================

def build_risk_context(
    decision: dict,
    balance: float,
    portfolio_state: dict,
    weekly_stats: dict = None
) -> dict:
    """
    Python คำนวณ risk context ก่อนส่ง Haiku

    V4.3: เพิ่ม beauty_adjustment logic

    Args:
        decision: Decision from Agent A
        balance: Account balance
        portfolio_state: Portfolio state dict
        weekly_stats: Weekly stats from Agent C (optional)

    Returns:
        Risk context dict
    """
    if weekly_stats is None:
        weekly_stats = {}

    sl_pip = decision.get("sl_pip", 0)
    base_lot = round((balance * 0.10) / sl_pip, 2) if sl_pip > 0 else 0.01

    # คำนวณ max loss
    max_loss_usd = balance * RISK_CONFIG['risk_per_plan_pct']  # 10%

    # สถานะปัจจุบัน
    consecutive_loss = portfolio_state.get("consecutive_loss", 0)
    daily_pnl = portfolio_state.get("realized_pnl_usd", 0)
    total_loss_pct = portfolio_state.get("total_loss_pct", 0)

    # Weekly stats
    overall_winrate = weekly_stats.get("overall_winrate", 0.5)
    technique = decision.get("setup", "")
    technique_winrate = weekly_stats.get("by_technique", {}).get(technique, {}).get("winrate", 0.5)

    # V4.3: Beauty adjustment
    beauty = decision.get("beauty_score_used", 100)
    beauty_adj = (
        1.0 if beauty >= 90 else
        0.8 if beauty >= 80 else
        0.6  # beauty < 80
    )

    return {
        "balance": balance,
        "base_lot": base_lot,
        "sl_pip": sl_pip,
        "max_loss_usd": max_loss_usd,

        # สถานะปัจจุบัน
        "consecutive_loss": consecutive_loss,
        "daily_pnl": daily_pnl,
        "drawdown_pct": total_loss_pct,

        # Weekly stats
        "weekly_winrate": overall_winrate,
        "technique_winrate": technique_winrate,

        # V4.3: Beauty score
        "beauty_score": beauty,
        "beauty_adjustment": beauty_adj,

        # Rules (ส่งให้ Haiku ทำตาม)
        "rules": [
            "consecutive_loss ≥ 3 → approved=false (hard stop)",
            "consecutive_loss = 2 → lot = base_lot × 0.5",
            "weekly_winrate < 0.40 → lot = base_lot × 0.7",
            "drawdown_pct > 0.30 → approved=false (hard stop)",
            "technique_winrate < 0.35 → lot = base_lot × 0.6",
            "beauty_score < 80 → lot = base_lot × beauty_adjustment",
            "lot ต้องไม่เกิน base_lot เว้นแต่ approved เต็ม",
            "lot ขั้นต่ำ = 0.01",
        ]
    }


# ============================================================================
# POST-VERIFY — Python ตรวจ lot จาก Haiku
# ============================================================================

def verify_risk_decision(risk_decision: dict, base_lot: float) -> dict:
    """
    Python verify lot จาก Haiku
    ป้องกัน Haiku hallucinate lot ใหญ่เกิน

    Args:
        risk_decision: Decision from Haiku
        base_lot: Base lot from risk context

    Returns:
        Verified (and possibly adjusted) risk decision
    """
    lot = risk_decision.get("lot", 0.01)
    adjusted = False

    # lot ต้องไม่เกิน base_lot × 1.05 (tolerance 5%)
    if lot > base_lot * 1.05:
        lot = base_lot
        adjusted = True
        logger.warning(f"Haiku lot {risk_decision['lot']:.2f} > base_lot×1.05 → adjusted to {lot:.2f}")

    # lot ขั้นต่ำ
    if lot < 0.01:
        lot = 0.01
        adjusted = True

    risk_decision["lot"] = lot
    risk_decision["adjusted"] = adjusted

    return risk_decision


# ============================================================================
# AGENT B — RISK MANAGER CLASS
# ============================================================================

class G3RiskManagerAgent:
    """
    Agent B — Risk Manager

    Usage:
        risk_mgr = G3RiskManagerAgent()
        result = risk_mgr.approve(
            decision=decision,
            risk_context=risk_context
        )
    """

    def __init__(self, api_key: str = None, config: dict = None):
        """
        Initialize Risk Manager Agent

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

        logger.info("✓ Agent B (Risk Manager) initialized")

    def approve(
        self,
        decision: dict,
        risk_context: dict
    ) -> dict:
        """
        Approve และคำนวณ lot

        Args:
            decision: Decision from Agent A
            risk_context: Risk context dict (from build_risk_context)

        Returns:
            {
                'approved': bool,
                'lot': float,
                'reason': str,
                'llm_log': dict
            }
        """
        # Check if decision is SKIP
        if decision.get('action') == 'SKIP':
            return {
                'approved': False,
                'lot': 0.0,
                'reason': 'Decision is SKIP',
                'llm_log': {'action': 'SKIP'}
            }

        # Build prompt
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(decision, risk_context)

        # Call Haiku
        try:
            start_time = datetime.now()
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                temperature=0.0,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Parse response
            response_text = response.content[0].text
            risk_decision = self._parse_haiku_response(response_text)

            # Post-verify
            risk_decision = verify_risk_decision(risk_decision, risk_context["base_lot"])

            # LLM log
            llm_log = self._build_llm_log(response, elapsed_ms)

            return {
                'approved': risk_decision.get('approved', False),
                'lot': risk_decision.get('lot', 0.01),
                'reason': risk_decision.get('reason', ''),
                'adjusted': risk_decision.get('adjusted', False),
                'llm_log': llm_log
            }

        except Exception as e:
            logger.error(f"Agent B approval failed: {e}")
            return {
                'approved': False,
                'lot': 0.0,
                'reason': f'Agent B error: {str(e)[:60]}',
                'llm_log': {'action': 'ERROR', 'error': str(e)}
            }

    def _build_system_prompt(self) -> str:
        """
        Build system prompt for Haiku

        Returns:
            System prompt string
        """
        return """คุณคือ Risk Manager สำหรับระบบเทรด XAUUSD

หน้าที่ของคุณคือ approve และคำนวณ lot size ตามกฎที่กำหนด

กฎเคร่งครัด:
- ต้องทำตาม rules ที่ระบุในข้อมูล 100%
- ห้ามคิดนอกกรอบหรือใช้ judgment อื่น
- ตอบเป็น JSON เท่านั้น
- lot ต้องไม่เกิน base_lot เว้นแต่ approved เต็ม
- lot ขั้นต่ำ = 0.01

Output Format:
{
  "approved": true/false,
  "lot": 0.0,
  "reason": "≤ 60 ตัวอักษร"
}"""

    def _build_user_prompt(self, decision: dict, risk_context: dict) -> str:
        """
        Build user prompt with risk context

        Args:
            decision: Decision from Agent A
            risk_context: Risk context dict

        Returns:
            User prompt string
        """
        return f"""วิเคราะห์และ approve lot size

=== Decision from Agent A ===
Action: {decision.get('action')}
Setup: {decision.get('setup')}
Entry: {decision.get('entry', 0):.2f}
SL: {decision.get('sl', 0):.2f} ({risk_context['sl_pip']} pip)
TP: {decision.get('tp', 0):.2f}
R:R: {decision.get('rr_ratio', 0):.2f}

=== Risk Context ===
Balance: ${risk_context['balance']:.2f}
Base Lot (10%/{risk_context['sl_pip']}pip): {risk_context['base_lot']:.2f}
Max Loss: ${risk_context['max_loss_usd']:.2f}

สถานะปัจจุบัน:
- Consecutive Loss: {risk_context['consecutive_loss']}
- Daily P&L: ${risk_context['daily_pnl']:.2f}
- Drawdown: {risk_context['drawdown_pct']:.1%}

Performance:
- Weekly Win Rate: {risk_context['weekly_winrate']:.1%}
- Technique Win Rate: {risk_context['technique_winrate']:.1%}

=== Rules (ต้องทำตามทุกข้อ) ===
{chr(10).join('- ' + rule for rule in risk_context['rules'])}

=== คำถาม ===
1. approve หรือไม่? (ตาม rules)
2. lot เท่าไหร่? (คำนวณตาม rules)
3. เหตุผล (≤ 60 ตัวอักษร)

ตอบเป็น JSON เท่านั้น"""

    def _parse_haiku_response(self, response_text: str) -> dict:
        """
        Parse JSON response from Haiku

        Args:
            response_text: Raw response text

        Returns:
            Risk decision dict

        Raises:
            ValueError: If JSON parse fails
        """
        try:
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            decision = json.loads(response_text.strip())
            return decision

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            logger.error(f"Raw response: {response_text[:500]}")
            raise ValueError(f"Invalid JSON from Haiku: {e}")

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

        # Calculate cost (Haiku pricing)
        # Input: $1.00/MTok, Output: $5.00/MTok
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens

        input_cost = (input_tokens / 1_000_000) * 1.00
        output_cost = (output_tokens / 1_000_000) * 5.00
        total_cost = input_cost + output_cost

        return {
            'action': 'RISK_APPROVAL',
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
    print("AGENT B — RISK MANAGER TEST")
    print("="*70)

    # Mock decision from Agent A
    mock_decision = {
        "action": "BUY",
        "setup": "twin_candle",
        "entry": 3245.60,
        "sl": 3230.00,
        "tp": 3275.00,
        "rr_ratio": 1.88,
        "sl_pip": 1560
    }

    # Build risk context
    mock_portfolio = {
        "consecutive_loss": 1,
        "realized_pnl_usd": -10.0,
        "total_loss_pct": 0.05
    }

    mock_weekly_stats = {
        "overall_winrate": 0.55,
        "by_technique": {
            "twin_candle": {"winrate": 0.60}
        }
    }

    risk_context = build_risk_context(
        mock_decision,
        balance=500,
        portfolio_state=mock_portfolio,
        weekly_stats=mock_weekly_stats
    )

    print(f"\n✓ Risk Context built:")
    print(f"  Base Lot: {risk_context['base_lot']:.2f}")
    print(f"  Consecutive Loss: {risk_context['consecutive_loss']}")
    print(f"  Weekly Win Rate: {risk_context['weekly_winrate']:.1%}")

    # Initialize agent
    risk_mgr = G3RiskManagerAgent()
    print("\n✓ Agent B initialized — ready to approve")
    print("="*70)
