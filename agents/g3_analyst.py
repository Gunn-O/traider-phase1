"""
Agent A — Chart Analyst (v4.3)

หน้าที่:
- วิเคราะห์กราฟ → BUY/SELL/SKIP + Entry/SL/TP
- ใช้ System Prompt V4.3 (XAUUSD_System_PromptV43.md) cached
- Grounding Layer: Python คำนวณก่อนส่ง Claude
- Post-verify: Python ตรวจหลัง Claude ตอบ
- รองรับ beauty_score จาก Twin Candle V4.3

Model: claude-sonnet-4-20250514
Reference: XAUUSD_System_PromptV43.md
"""

import os
import json
import logging
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

import anthropic
from anthropic import RateLimitError, APIStatusError

logger = logging.getLogger(__name__)


# ============================================================================
# GROUNDING LAYER — Python คำนวณค่าสำคัญก่อนส่ง Claude
# ============================================================================

def build_grounding(world_state: dict, balance: float) -> dict:
    """
    Python คำนวณค่าสำคัญทั้งหมดก่อนส่ง Claude
    เพื่อป้องกัน hallucination

    V4.3: เพิ่ม beauty_score และ beauty_warning

    Args:
        world_state: Output จาก G1
        balance: Account balance

    Returns:
        dict with grounding data
    """
    range_55 = world_state["range"]["usd"]
    twin = world_state.get("twin_candle", {})
    technical_price = twin.get("technical_price", 0)
    current_price = world_state["current_price"]
    beauty_score = twin.get("beauty_score", 100)  # Default 100 ถ้าไม่มี

    # Entry constraints
    entry_must_be = technical_price if technical_price > 0 else current_price
    entry_tolerance_pip = 100  # Buffer ±100 pip

    # SL boundaries (5-20% ของ Range)
    sl_min_distance_pip = range_55 * 100 * 0.05  # 5% Range
    sl_max_distance_pip = range_55 * 100 * 0.20  # 20% Range

    # R:R minimum
    rr_minimum = 1.0

    return {
        # ค่าที่ Claude ต้องใช้ — Python หาให้แล้ว
        "technical_price": entry_must_be,
        "range_55_usd": range_55,
        "range_55_pip": world_state["range"]["pip"],

        # SL boundaries
        "sl_min_distance_pip": sl_min_distance_pip,
        "sl_max_distance_pip": sl_max_distance_pip,

        # Entry constraints
        "entry_must_be": entry_must_be,
        "entry_tolerance_pip": entry_tolerance_pip,

        # R:R minimum
        "rr_minimum": rr_minimum,

        # Balance
        "balance": balance,

        # V4.3: Beauty score (Twin Candle Entry)
        "beauty_score": beauty_score,
        "beauty_warning": beauty_score < 80,  # Warning ถ้า < 80
    }


# ============================================================================
# POST-VERIFY — Python ตรวจ output จาก Claude
# ============================================================================

def verify_analyst_decision(decision: dict, grounding: dict) -> list:
    """
    ตรวจ output จาก Agent A
    Returns: list of errors (ว่างถ้าผ่าน)

    Args:
        decision: Decision dict from Claude
        grounding: Grounding data

    Returns:
        List of error messages (empty if passed)
    """
    errors = []
    action = decision.get("action")

    if action == "SKIP":
        return errors  # SKIP ไม่ต้องตรวจ

    entry = decision.get("entry", 0)
    sl = decision.get("sl", 0)
    tp = decision.get("tp", 0)

    # 1. ตรวจ entry ใกล้ technical_price
    if grounding["entry_must_be"] > 0:
        diff = abs(entry - grounding["entry_must_be"])
        diff_pip = diff * 100
        if diff_pip > grounding["entry_tolerance_pip"]:
            errors.append(
                f"Entry {entry:.2f} ห่างจาก technical_price "
                f"{grounding['entry_must_be']:.2f} เกิน "
                f"{grounding['entry_tolerance_pip']} pip "
                f"(diff={diff_pip:.0f}pip)"
            )

    # 2. ตรวจ R:R จริง
    if entry and sl and tp:
        if action == "BUY":
            if sl >= entry:
                errors.append(f"BUY: SL {sl:.2f} ≥ Entry {entry:.2f}")
            if tp <= entry:
                errors.append(f"BUY: TP {tp:.2f} ≤ Entry {entry:.2f}")
            rr = (tp - entry) / (entry - sl) if (entry - sl) > 0 else 0
        else:  # SELL
            if sl <= entry:
                errors.append(f"SELL: SL {sl:.2f} ≤ Entry {entry:.2f}")
            if tp >= entry:
                errors.append(f"SELL: TP {tp:.2f} ≥ Entry {entry:.2f}")
            rr = (entry - tp) / (sl - entry) if (sl - entry) > 0 else 0

        if rr < grounding["rr_minimum"]:
            errors.append(
                f"R:R จริง = {rr:.2f} < {grounding['rr_minimum']} "
                f"(Entry={entry:.2f}, SL={sl:.2f}, TP={tp:.2f})"
            )

    # 3. ตรวจ SL distance
    if entry and sl:
        sl_distance = abs(entry - sl)
        sl_pip = sl_distance * 100

        if sl_pip < grounding["sl_min_distance_pip"]:
            errors.append(
                f"SL แคบเกิน: {sl_pip:.0f}pip < "
                f"{grounding['sl_min_distance_pip']:.0f}pip (5% Range)"
            )
        elif sl_pip > grounding["sl_max_distance_pip"]:
            errors.append(
                f"SL กว้างเกิน: {sl_pip:.0f}pip > "
                f"{grounding['sl_max_distance_pip']:.0f}pip (20% Range)"
            )

    return errors


# ============================================================================
# OUTPUT FORMAT
# ============================================================================

OUTPUT_FORMAT = """
ตอบในรูปแบบ JSON เท่านั้น:
{
  "chart_type": "uptrend|downtrend|sideway_down|sideway_up|mountain|unclear",
  "setup": "twin_candle|breakout_follow|mai_ruay|none",
  "action": "BUY|SELL|SKIP",
  "entry": 0.0,
  "sl": 0.0,
  "tp": 0.0,
  "sl_type": "SL1|SL2|SL3",
  "tp_type": "TP1|TP2|TP3",
  "rr_ratio": 0.0,
  "sl_pip": 0,
  "tp_pip": 0,
  "confidence": 0.0,
  "beauty_score_used": 0,
  "skip_reason": "ถ้า SKIP ≤ 60 ตัวอักษร",
  "reason": "≤ 80 ตัวอักษร"
}

กฎบังคับ:
- ใช้เฉพาะกฎใน Strategy ข้างต้น ห้ามใช้ทฤษฎีอื่น
- RSI เป็น metadata เท่านั้น ไม่ใช้ตัดสิน BUY/SELL
- entry ต้องใช้ technical_price จาก grounding เสมอ
  ห้ามประมาณหรือปัดเป็นเลขกลม
- R:R ต้องได้ ≥ 1.0 เสมอ ถ้าไม่ได้ → SKIP
- ตอบเป็น JSON เท่านั้น ห้ามมีข้อความนอก JSON
"""


# ============================================================================
# AGENT A — ANALYST CLASS
# ============================================================================

class G3AnalystAgent:
    """
    Agent A — Chart Analyst

    Usage:
        analyst = G3AnalystAgent(
            system_prompt_path='strategy/XAUUSD_System_PromptV43.md'
        )
        result = analyst.decide(
            world_state=world_state,
            balance=balance,
            portfolio_state=portfolio_state,
            reflection_summary=reflection_summary,
            grounding=grounding
        )
    """

    def __init__(self, system_prompt_path: str = None,
                 api_key: str = None, config: dict = None):
        """
        Initialize Analyst Agent

        Args:
            system_prompt_path: Path to System Prompt V1 MD file
            api_key: Anthropic API key (optional, reads from env)
            config: Optional config dict
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        self.config = config or {}
        self.verbose = self.config.get('verbose', False)

        # Load System Prompt V4.3
        if not system_prompt_path:
            system_prompt_path = 'strategy/XAUUSD_System_PromptV43.md'

        prompt_path = Path(system_prompt_path)
        if not prompt_path.exists():
            raise FileNotFoundError(f"System Prompt not found: {system_prompt_path}")

        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.system_prompt_content = f.read()

        logger.info(f"✓ System Prompt V1 loaded ({len(self.system_prompt_content)} chars)")

        # Initialize Anthropic client
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def decide(
        self,
        world_state: dict,
        balance: float,
        portfolio_state: dict,
        reflection_summary: str = "No history yet",
        grounding: dict = None
    ) -> dict:
        """
        วิเคราะห์กราฟและตัดสินใจเทรด

        Args:
            world_state: Output from G1
            balance: Account balance
            portfolio_state: Portfolio state dict
            reflection_summary: Performance reflection (from Agent C)
            grounding: Optional pre-computed grounding (if None, will compute)

        Returns:
            {
                'success': bool,
                'decision': dict,
                'llm_log': dict,
                'grounding': dict,
                'verify_errors': list
            }
        """
        # Step 1: Build grounding (if not provided)
        if grounding is None:
            grounding = build_grounding(world_state, balance)

        # Step 2: Build System Prompt (2 blocks)
        system_blocks = self._build_system_prompt_blocks(reflection_summary)

        # Step 3: Build User Prompt
        user_prompt = self._build_user_prompt(world_state, portfolio_state, grounding)

        # Step 4: Call Claude API
        try:
            start_time = datetime.now()
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                temperature=0.0,
                system=system_blocks,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Parse response
            response_text = response.content[0].text
            decision = self._parse_claude_response(response_text)

            # LLM log
            llm_log = self._build_llm_log(response, elapsed_ms)

            # Step 5: Post-verify
            verify_errors = verify_analyst_decision(decision, grounding)

            if verify_errors:
                logger.warning(f"Agent A verify failed: {verify_errors}")
                # Override decision to SKIP
                decision = {
                    "action": "SKIP",
                    "skip_reason": f"Verify failed: {verify_errors[0][:60]}"
                }

            return {
                'success': True,
                'decision': decision,
                'llm_log': llm_log,
                'grounding': grounding,
                'verify_errors': verify_errors
            }

        except Exception as e:
            logger.error(f"Agent A decision failed: {e}")
            return {
                'success': False,
                'decision': {'action': 'SKIP', 'skip_reason': f'Agent A error: {str(e)[:60]}'},
                'llm_log': {'action': 'ERROR', 'error': str(e)},
                'grounding': grounding,
                'verify_errors': [str(e)]
            }

    def _build_system_prompt_blocks(self, reflection_summary: str) -> list:
        """
        Build system prompt blocks (2 blocks)

        Block 1: Strategy content (cached)
        Block 2: Rules + Reflection (not cached)

        Args:
            reflection_summary: Performance reflection text

        Returns:
            List of system message blocks
        """
        # Block 1 — Strategy (cached)
        block1 = {
            "type": "text",
            "text": self.system_prompt_content,
            "cache_control": {"type": "ephemeral"}
        }

        # Block 2 — Rules + Reflection (not cached)
        block2 = {
            "type": "text",
            "text": f"""กฎที่ต้องปฏิบัติเสมอ:
- ใช้เฉพาะกฎใน Strategy ข้างต้น ห้ามใช้ทฤษฎีอื่น
- RSI เป็น metadata เท่านั้น ไม่ใช้ตัดสิน BUY/SELL
- entry ต้องใช้ technical_price จาก grounding เสมอ
  ห้ามประมาณหรือปัดเป็นเลขกลม
- R:R ต้องได้ ≥ 1.0 เสมอ ถ้าไม่ได้ → SKIP
- ตอบเป็น JSON เท่านั้น ห้ามมีข้อความนอก JSON

=== PERFORMANCE REFLECTION ===
{reflection_summary}
=============================="""
        }

        return [block1, block2]

    def _build_user_prompt(
        self,
        world_state: dict,
        portfolio_state: dict,
        grounding: dict
    ) -> str:
        """
        Build user prompt with grounding data

        Args:
            world_state: G1 output
            portfolio_state: Portfolio state
            grounding: Grounding data

        Returns:
            User prompt string
        """
        tf = world_state.get('selected_tf', 'M5')
        chart_type = world_state['chart_type']
        quality = world_state.get('quality', 0.0)
        range_data = world_state['range']
        current_price = world_state['current_price']
        session = world_state.get('session', 'Unknown')

        # Portfolio
        active_plan = portfolio_state.get('active_plan_id', 'ไม่มีแผนที่เปิดอยู่')
        consecutive_loss = portfolio_state.get('consecutive_loss', 0)

        # Twin candle
        twin = world_state.get('twin_candle', {})
        twin_found = twin.get('found', False)
        technical_price = twin.get('technical_price', 0)

        # Build prompt
        prompt = f"""วิเคราะห์กราฟ XAUUSD และตัดสินใจเทรด

=== ข้อมูลกราฟ ===
Timeframe: {tf}
Chart Type: {chart_type}
Quality Score: {quality:.2f}/1.0

Range 55 แท่ง:
- High: {range_data['high']:.2f}
- Low: {range_data['low']:.2f}
- Range: {range_data['usd']:.2f} USD ({range_data['pip']} pip)

ราคาปัจจุบัน: {current_price:.2f}
Session: {session}

=== Grounding Data (Python คำนวณให้แล้ว) ===
Technical Price (จุดเทคนิค): {grounding['technical_price']:.2f}
Entry Tolerance: ±{grounding['entry_tolerance_pip']:.0f} pip
SL Range: {grounding['sl_min_distance_pip']:.0f}-{grounding['sl_max_distance_pip']:.0f} pip
R:R Minimum: {grounding['rr_minimum']:.1f}

=== แท่งคู่ ===
Found: {twin_found}
{'Technical Price: ' + str(technical_price) if twin_found else 'ไม่พบแท่งคู่'}

=== สถานะพอร์ต ===
Balance: {grounding['balance']:.2f} USD
Active Plan: {active_plan}
Consecutive Loss: {consecutive_loss}

=== คำถาม ===
จากข้อมูลทั้งหมดข้างต้น:
1. Chart type นี้ตรงกับ Strategy ข้อไหน?
2. มี Setup ที่เข้าได้ไหม? ถ้ามีคือ Technique อะไร?
3. ถ้าเข้า — Entry, SL, TP อยู่ที่เท่าไหร่? R:R ได้เท่าไหร่?
4. ถ้า SKIP — เหตุผลคืออะไร?

⚠️ CRITICAL — ใช้ technical_price={grounding['technical_price']:.2f} เป็น entry
ห้ามประมาณหรือปัดเป็นเลขกลม

{OUTPUT_FORMAT}"""

        return prompt

    def _parse_claude_response(self, response_text: str) -> dict:
        """
        Parse JSON response from Claude

        Args:
            response_text: Raw response text

        Returns:
            Decision dict

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
            raise ValueError(f"Invalid JSON from Claude: {e}")

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
        # Input: $3.00/MTok, Output: $15.00/MTok, Cache Read: $0.30/MTok
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read_tokens = getattr(usage, 'cache_read_input_tokens', 0)
        cache_creation_tokens = getattr(usage, 'cache_creation_input_tokens', 0)

        # Cost calculation
        input_cost = (input_tokens / 1_000_000) * 3.00
        output_cost = (output_tokens / 1_000_000) * 15.00
        cache_read_cost = (cache_read_tokens / 1_000_000) * 0.30
        cache_create_cost = (cache_creation_tokens / 1_000_000) * 3.00

        total_cost = input_cost + output_cost + cache_read_cost + cache_create_cost

        # Cache hit detection
        cache_hit = cache_read_tokens > 0

        return {
            'action': 'DECISION',
            'model': response.model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cache_read_tokens': cache_read_tokens,
            'cache_creation_tokens': cache_creation_tokens,
            'total_tokens': input_tokens + output_tokens,
            'cache_hit': cache_hit,
            'cost_usd': round(total_cost, 4),
            'elapsed_ms': round(elapsed_ms, 1)
        }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("AGENT A — ANALYST TEST")
    print("="*70)

    # Mock world_state
    mock_world_state = {
        "selected_tf": "M5",
        "chart_type": "uptrend",
        "quality": 0.85,
        "current_price": 3245.60,
        "range": {"high": 3280.0, "low": 3200.0, "usd": 80.0, "pip": 8000},
        "session": "London",
        "twin_candle": {
            "found": True,
            "technical_price": 3238.40
        }
    }

    mock_portfolio = {
        "active_plan_id": "",
        "consecutive_loss": 0
    }

    # Initialize agent
    analyst = G3AnalystAgent()

    # Build grounding
    grounding = build_grounding(mock_world_state, balance=500)
    print(f"\n✓ Grounding built:")
    print(f"  Technical Price: {grounding['technical_price']:.2f}")
    print(f"  SL Range: {grounding['sl_min_distance_pip']:.0f}-{grounding['sl_max_distance_pip']:.0f} pip")

    print("\n✓ Agent A initialized — ready to analyze")
    print("="*70)
