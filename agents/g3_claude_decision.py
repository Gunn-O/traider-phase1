"""
G3a — Claude Decision Agent

หน้าที่:
- รับ world_state จาก G1 (ผ่าน G2 pre-filter)
- อ่าน Strategy MD (XAUUSD_AI_Trading_System_v2.1.md)
- ส่ง prompt ไปยัง Claude API
- ตัดสินใจ BUY / SELL / SKIP ตาม strategy rules
- คำนวณ Entry / SL / TP

Reference: claude_prompt_template.md v1.0
"""

import os
import json
import logging
import time
from typing import Dict, Optional
from pathlib import Path
from datetime import datetime

import anthropic
from anthropic import RateLimitError, APIStatusError

from config import calc_lot

# Setup logging
logger = logging.getLogger(__name__)


# ============================================================================
# PROMPT BUILDERS
# ============================================================================

# REMOVED: build_system_prompt() - now constructed inline in call_claude_decision()
# to support prompt caching with cache_control
# Old function kept commented for reference:
#
# def build_system_prompt(strategy_content: str) -> str:
#     """
#     สร้าง System Prompt สำหรับ Claude
#     Args:
#         strategy_content: เนื้อหาจาก XAUUSD_AI_Trading_System_v2.1.md
#     Returns:
#         system prompt string
#     """
#     return f"""คุณคือ XAUUSD Trading Analyst ที่มีประสบการณ์สูง
#     ...
#     (See call_claude_decision() for current system prompt)
#     """


def build_user_prompt(world_state: Dict, balance: float,
                      portfolio_state: Dict) -> str:
    """
    สร้าง User Prompt จาก world_state

    Args:
        world_state: output จาก G1
        balance: Account balance (USD)
        portfolio_state: {
            'active_plan_id': str,
            'open_orders_count': int,
            'consecutive_loss': int,
            ...
        }

    Returns:
        user prompt string
    """
    tf = world_state.get('selected_tf', world_state.get('timeframe', 'M5'))
    chart_type = world_state['chart_type']
    quality = world_state.get('quality', 0.0)
    technique = world_state.get('technique_candidate', 'skip')
    range_data = world_state['range']
    current_price = world_state['current_price']
    session = world_state.get('session', 'Unknown')

    # Chart detail
    chart_detail_text = format_chart_detail(chart_type, world_state.get('chart_detail', {}))

    # Twin candle
    twin_text = format_twin_candle(world_state.get('twin_candle', {'found': False}))

    # Father candle
    father_text = format_father_candle(world_state.get('father_candle', {'found': False}))

    # OHLC table
    ohlc_table = format_ohlc_table(world_state.get('ohlc_last_10', []), tf)

    # TF selection reason
    tf_reason = format_tf_selection_reason(
        world_state.get('tf_results', {}),
        tf
    )

    # RSI
    rsi_value = world_state.get('metadata', {}).get('rsi_14', 50.0)

    # Portfolio state
    active_plan = portfolio_state.get('active_plan_id', 'ไม่มีแผนที่เปิดอยู่')
    consecutive_loss = portfolio_state.get('consecutive_loss', 0)

    output_format = get_output_format_json()
    few_shot_examples = get_few_shot_examples()
    chart_specific_instruction = get_chart_specific_instruction(chart_type)

    prompt = f"""วิเคราะห์กราฟ XAUUSD และตัดสินใจเทรด

{few_shot_examples}

=== ข้อมูลกราฟ ===
Timeframe ที่เลือก: {tf}
เหตุผลที่เลือก TF นี้: {tf_reason}

Chart Type ที่ตรวจพบ: {chart_type}
Chart Quality Score: {quality:.2f}/1.0
Technique Candidate: {technique}

Range 55 แท่ง:
- High: {range_data['high']:.2f}
- Low: {range_data['low']:.2f}
- Range: {range_data['usd']:.2f} USD ({range_data['pip']} pip)

ราคาปัจจุบัน: {current_price:.2f}
Session: {session}

=== รายละเอียด Chart Pattern ===
{chart_detail_text}

{chart_specific_instruction}

=== แท่งคู่ (จุดเทคนิค) ===
{twin_text}

=== แท่งพ่อ (ถ้ามี) ===
{father_text}

=== OHLC ล่าสุด 10 แท่ง ({tf}) ===
{ohlc_table}

=== ข้อมูล Metadata (อ้างอิงเท่านั้น) ===
RSI(14): {rsi_value:.1f}

=== สถานะพอร์ต ===
Balance: {balance:.2f} USD
Current Plan: {active_plan}
Consecutive Loss: {consecutive_loss}

=== คำถาม ===
จากข้อมูลทั้งหมดข้างต้น:
1. Chart type นี้ตรงกับ Strategy ข้อไหน?
2. มี Setup ที่เข้าได้ไหม? ถ้ามีคือ Technique อะไร?
3. ถ้าเข้า — Entry, SL, TP อยู่ที่เท่าไหร่? R:R ได้เท่าไหร่?
4. ถ้า SKIP — เหตุผลคืออะไร?

⚠️ กฎ Entry Price (สำคัญมาก):
- ใช้ technical_price จากแท่งคู่ที่ระบุข้างต้นเป็น entry เสมอ
- ห้ามประมาณหรือปัดเป็นเลขกลม (เช่น 4700.00, 4750.00)
- ถ้าไม่มี technical_price → ใช้ current_price แทน
- entry ต้องตรงกับราคาที่ระบุใน world_state (มีทศนิยม)
- ตัวอย่าง: technical_price=4728.36 → ใช้ entry=4728.36 (ไม่ใช่ 4728 หรือ 4730)

ตอบในรูปแบบ JSON ตามนี้เท่านั้น:
{output_format}"""

    return prompt


def get_output_format_json() -> str:
    """Return JSON schema example with constraints"""
    return """{
  "chart_type": "uptrend|downtrend|sideway_down|sideway_up|mountain|unclear",
  "technique": "twin_candle|breakout_follow|mai_ruay|support_bounce|none",
  "action": "BUY|SELL|SKIP",
  "confidence": 0.85,
  "entry": 3245.50,
  "sl": 3230.00,
  "tp": 3261.00,
  "rr_ratio": 1.03,
  "sl_pip": 1550,
  "tp_pip": 1550,
  "skip_reason": "สรุปสั้นๆ ≤ 60 ตัวอักษร เช่น: ไม่พบแท่งคู่ กรอบตามเจ้าใหญ่เกิน 35%",
  "reason": "สรุปสั้นๆ ≤ 80 ตัวอักษร เช่น: H1 uptrend ชัด 46° พบแท่งคู่ 3238 R:R=2.0 BUY"
}

⚠️ CONSTRAINTS (ต้องปฏิบัติเสมอ):
- R:R ≥ 1.0 (ถ้าไม่ได้ → SKIP)
- สูตร R:R = (TP - Entry) / (Entry - SL) สำหรับ BUY
- สูตร R:R = (Entry - TP) / (SL - Entry) สำหรับ SELL
- SL และ TP ต้องอยู่คนละด้านของ Entry
- confidence ต้องอยู่ระหว่าง 0.0-1.0
- ถ้า action=SKIP ต้องใส่ skip_reason (≤ 60 ตัวอักษร)
- ถ้า action=BUY/SELL ต้องระบุ entry, sl, tp, technique และ reason (≤ 80 ตัวอักษร)
- technique ต้องตรงกับ setup ที่เห็นจริง (ห้ามใส่ technique ที่ไม่เจอ)"""


# ============================================================================
# FEW-SHOT EXAMPLES
# ============================================================================

def get_few_shot_examples() -> str:
    """Few-shot examples สำหรับ Claude"""
    return """
=== FEW-SHOT EXAMPLES ===

Example 1: Uptrend + Twin Candle (BUY)
Input: H1 uptrend, angle=46.2°, HH/HL=4/4, Twin Candle พบที่ idx 48-49 (near Left Base), Technical Price=3238.5, Current=3241.0
Decision: {
  "chart_type": "uptrend",
  "technique": "twin_candle",
  "action": "BUY",
  "confidence": 0.82,
  "entry": 3242.00,
  "sl": 3232.00,
  "tp": 3272.00,
  "rr_ratio": 3.00,
  "sl_pip": 1000,
  "tp_pip": 3000,
  "reason": "Uptrend ชัดเจนด้วย HH/HL ต่อเนื่อง 4 ครั้ง ความชัน 46.2° ใกล้มาตรฐาน พบแท่งคู่ใกล้ Left Base เหมาะสำหรับ BUY ตามเทรน"
}

Example 2: Downtrend + No Setup (SKIP)
Input: M30 downtrend, angle=42.1°, LH/LL=3/3, ไม่พบแท่งคู่, ไม่พบกรอบเล็ก, Current=3215.0
Decision: {
  "chart_type": "downtrend",
  "technique": "none",
  "action": "SKIP",
  "skip_reason": "ไม่พบ Setup ที่ใช้ได้ทั้งแท่งคู่และกรอบตามเจ้า",
  "reason": "แม้เป็น downtrend ชัดเจน แต่ไม่พบจุดเข้าที่เหมาะสม ควรรอ Setup ที่ดีกว่า"
}

Example 3: Uptrend + R:R ต่ำ (SKIP)
Input: H4 uptrend, Twin Candle พบ แต่ TP ใกล้เกิน → R:R = 0.8
Decision: {
  "chart_type": "uptrend",
  "technique": "twin_candle",
  "action": "SKIP",
  "skip_reason": "R:R = 0.8 ต่ำกว่า 1.0",
  "reason": "พบแท่งคู่ แต่ Right Top ใกล้เกิน ทำให้ R:R ไม่ผ่านเกณฑ์ ไม่คุ้มค่าเสี่ยง"
}

=== END EXAMPLES ===
"""


# ============================================================================
# CHART-SPECIFIC INSTRUCTIONS
# ============================================================================

def get_chart_specific_instruction(chart_type: str) -> str:
    """
    ให้คำแนะนำเฉพาะตาม chart type

    Args:
        chart_type: uptrend, downtrend, sideway_down, sideway_up, mountain, unclear

    Returns:
        Instruction string สำหรับ chart type นั้น
    """
    instructions = {
        'uptrend': """📈 UPTREND SETUP:
- มองหา Twin Candle กรอบสดใหม่ใกล้ Left Base (Lower Low)
- หรือ Breakout Follow จากกรอบเล็กๆ ตามเจ้า
- Entry: เหนือ Technical Price
- SL: ใต้ Left Base
- TP: ใกล้ Right Top (Higher High)
- ต้องมี HH/HL ต่อเนื่อง + ความชัน 45-50°""",

        'downtrend': """📉 DOWNTREND SETUP:
- มองหา Twin Candle กรอบสดใหม่ใกล้ Left Base (Higher High)
- หรือ Breakout Follow จากกรอบเล็กๆ ตามเจ้า
- Entry: ใต้ Technical Price
- SL: เหนือ Left Base
- TP: ใกล้ Right Bottom (Lower Low)
- ต้องมี LH/LL ต่อเนื่อง + ความชัน 45-50°""",

        'sideway_down': """📊 SIDEWAY DOWN (Press Down) SETUP:
- รอราคาย่อขึ้นมาใกล้ Box Top
- มองหา Twin Candle ใกล้ขอบบน
- Entry: SELL ใต้ Technical Price
- SL: เหนือ Box Top
- TP: ใกล้ Box Bottom
- ระวัง False Breakout ขอบบน""",

        'sideway_up': """📊 SIDEWAY UP (Press Up) SETUP:
- รอราคาย่อลงมาใกล้ Box Bottom
- มองหา Twin Candle ใกล้ขอบล่าง
- Entry: BUY เหนือ Technical Price
- SL: ใต้ Box Bottom
- TP: ใกล้ Box Top
- ระวัง False Breakout ขอบล่าง""",

        'mountain': """⛰️ MOUNTAIN SETUP (BUY เท่านั้น):
- เงื่อนไขขั้นต่ำ: ความสูงภูเขา > 50% ของ Range (เช่น 51%, 60%, 70% ผ่านทั้งหมด)
- มองหา Peak (ยอดภูเขา) และ Left Base (ฐานซ้าย = แท่งคู่หนา)
- รอราคาลงมาถึง Right Base (ฐานด้านขวา ≈ ฐานซ้าย ±5% หรือ ±300 pip)
- Entry: BUY เมื่อราคาลงถึงฐานด้านขวา (ใกล้ Left Base)
- SL: ใต้ฐาน
- TP: 1/3, 1/2, หรือเกือบถึงยอดภูเขา
- ต้องยืนยันว่าราคาวกกลับมาถึงฐานภายใน 55 แท่ง (สวย ≤ 40 แท่ง)""",

        'unclear': """❌ UNCLEAR → SKIP
- กราฟไม่ชัด ไม่มี pattern ที่เห็นได้ชัดเจน
- ไม่ควรเข้าเทรด
- รอโอกาสที่ดีกว่า"""
    }

    return instructions.get(chart_type, instructions['unclear'])


# ============================================================================
# FORMAT HELPERS
# ============================================================================

def format_chart_detail(chart_type: str, chart_detail: Dict) -> str:
    """Format chart detail text ตาม chart type"""

    if chart_type == 'uptrend':
        hh_hl = chart_detail.get('hh_hl', {})
        return f"""Uptrend ที่ตรวจพบ:
- ความชัน: {chart_detail.get('slope_angle', 0):.1f}° (อ้างอิง: 45-50°)
- Higher High พบ: {hh_hl.get('hh_count', 0)} ครั้ง
- Higher Low พบ: {hh_hl.get('hl_count', 0)} ครั้ง
- ต่อเนื่องไม่มีสวนทิศ: {'Yes' if hh_hl.get('consecutive') else 'No'}"""

    elif chart_type == 'downtrend':
        lh_ll = chart_detail.get('lh_ll', {})
        return f"""Downtrend ที่ตรวจพบ:
- ความชัน: {chart_detail.get('slope_angle', 0):.1f}° (อ้างอิง: 45-50°)
- Lower High พบ: {lh_ll.get('lh_count', 0)} ครั้ง
- Lower Low พบ: {lh_ll.get('ll_count', 0)} ครั้ง
- ต่อเนื่องไม่มีสวนทิศ: {'Yes' if lh_ll.get('consecutive') else 'No'}"""

    elif chart_type in ['sideway_down', 'sideway_up']:
        impulse_pct = chart_detail.get('impulse_pct', 0) * 100
        box_pct = chart_detail.get('box_pct', 0) * 100
        return f"""{chart_type.replace('_', ' ').title()} ที่ตรวจพบ:
- ขาพุ่ง: {chart_detail.get('impulse_candles', 0)} แท่ง = {impulse_pct:.0f}% ของ Range
- กรอบ Sideway: {chart_detail.get('box_low', 0):.2f} - {chart_detail.get('box_high', 0):.2f} ({box_pct:.0f}% ของ Range)
- ตำแหน่งราคาปัจจุบัน: {chart_detail.get('current_position', 'middle')}"""

    elif chart_type == 'mountain':
        return f"""ภูเขาที่ตรวจพบ:
- ยอดภูเขา: {chart_detail.get('peak_price', 0):.2f}
- ฐานซ้าย: {chart_detail.get('left_base_price', 0):.2f}
- ความสูง: {chart_detail.get('height_usd', 0):.2f} USD = {chart_detail.get('height_pct', 0)*100:.0f}% ของ Range
- แท่งที่วกกลับฐาน: {chart_detail.get('return_candles', 0)} แท่ง (ดี ≤ 40)
- Tolerance: ±{chart_detail.get('tolerance_usd', 0):.2f} USD"""

    elif chart_type == 'unclear':
        return "กราฟไม่ชัด — ไม่มี pattern ที่ชัดเจน"

    return "ไม่พบ pattern"


def format_twin_candle(twin: Dict) -> str:
    """Format twin candle info"""
    if not twin.get('found'):
        return "ไม่พบแท่งคู่ในบริเวณที่ค้นหา"

    return f"""พบแท่งคู่:
- จุดเทคนิค (Technical Price): {twin.get('technical_price', 0):.2f}
- ขนาดเนื้อเทียน: {twin.get('body_pct', 0)*100:.1f}% ของ Range
- ตำแหน่ง: แท่งที่ {twin.get('candle1_idx', 0)} และ {twin.get('candle2_idx', 0)}"""


def format_father_candle(father: Dict) -> str:
    """Format father candle info"""
    if not father.get('found'):
        return "ไม่พบแท่งพ่อ"

    mother = father.get('mother_candle', {})
    dir_th = "ลง" if father['direction'] == 'down' else "ขึ้น"
    play_th = "BUY" if father['direction'] == 'down' else "SELL"

    result = f"""พบแท่งพ่อ:
- ทิศทาง: พุ่ง{dir_th} → เตรียมเล่น {play_th}
- ขนาด: {father.get('pct_range', 0)*100:.0f}% ของ Range ({father.get('candle_count', 0)} แท่ง)
- Quality: {father.get('quality', 0):.2f}"""

    if mother.get('found'):
        result += f"""
แท่งแม่:
- ขนาดเนื้อเทียน: {mother.get('body_ratio', 0)*100:.1f}% ของพ่อ ({mother.get('beauty', 'unknown')})
- ปิดสวนทิศ: {'✅' if mother.get('reversed_close') else '❌'}
- จุดเทคนิค: {mother.get('technical_price', 0):.2f}
- ใช้ได้: {'✅' if mother.get('valid') else '❌'}"""
    else:
        result += "\nแท่งแม่: ยังไม่เกิด (รอแท่งถัดไป)"

    return result


def format_ohlc_table(candles: list, tf: str) -> str:
    """สร้างตาราง OHLC ล่าสุด 10 แท่ง"""
    if not candles:
        return "ไม่มีข้อมูล OHLC"

    header = f"{'แท่ง':>4} | {'Open':>8} | {'High':>8} | {'Low':>8} | {'Close':>8} | {'Dir':>5}"
    lines = [header, "-" * 55]

    recent = candles[-10:] if len(candles) >= 10 else candles
    for i, c in enumerate(recent):
        n = i - len(recent) + 1  # -9 ถึง 0
        direction = "▲" if c.get('close', 0) >= c.get('open', 0) else "▼"
        lines.append(
            f"{n:>4} | {c.get('open', 0):>8.2f} | {c.get('high', 0):>8.2f} | "
            f"{c.get('low', 0):>8.2f} | {c.get('close', 0):>8.2f} | {direction:>5}"
        )

    return "\n".join(lines)


def format_tf_selection_reason(tf_results: Dict, selected_tf: str) -> str:
    """อธิบายเหตุผลที่เลือก TF นี้"""
    if not tf_results or selected_tf not in tf_results:
        return f"เลือก {selected_tf} (default)"

    selected = tf_results[selected_tf]
    others = {tf: r for tf, r in tf_results.items()
              if tf != selected_tf and r.get('chart_type') != 'unclear'}

    reason = (
        f"เลือก {selected_tf} เพราะ Chart Type '{selected.get('chart_type', 'unclear')}' "
        f"มี Quality {selected.get('quality', 0):.2f}"
    )

    if others:
        other_summary = ", ".join(
            f"{tf}={r.get('chart_type', 'unclear')}({r.get('quality', 0):.2f})"
            for tf, r in list(others.items())[:3]  # แสดงแค่ 3 TF
        )
        reason += f"\nTF อื่นที่พบ: {other_summary}"

    return reason


# Continue in next message...

# ============================================================================
# CLAUDE API CALL
# ============================================================================

def call_claude_decision(world_state: Dict, balance: float,
                          portfolio_state: Dict, strategy_content: str,
                          api_key: str) -> Dict:
    """
    เรียก Claude API เพื่อตัดสินใจ

    Args:
        world_state: output จาก G1
        balance: Account balance
        portfolio_state: Portfolio state dict
        strategy_content: เนื้อหา Strategy MD
        api_key: Anthropic API key

    Returns:
        {
            'decision': dict (JSON ที่ Claude ตอบ),
            'll

m_log': dict (tokens, cost, latency),
            'success': bool
        }
    """
    client = anthropic.Anthropic(api_key=api_key)

    # Build user prompt
    user_prompt = build_user_prompt(world_state, balance, portfolio_state)

    start_time = time.time()

    # System prompt with cache_control (split into 2 blocks for optimal caching)
    # Block 1: Strategy content (cached) - large, rarely changes
    # Block 2: Instructions (not cached) - small, can change
    system_blocks = [
        {
            "type": "text",
            "text": f"""คุณคือ XAUUSD Trading Analyst ที่มีประสบการณ์สูง

หน้าที่ของคุณ:
1. อ่าน Strategy Document ด้านล่างให้เข้าใจ
2. วิเคราะห์ข้อมูลกราฟที่ได้รับ
3. ตัดสินใจ BUY / SELL / SKIP พร้อมระบุ Entry, SL, TP และเหตุผล

=== STRATEGY DOCUMENT ===
{strategy_content}
=== END STRATEGY ===""",
            "cache_control": {"type": "ephemeral"}
        },
        {
            "type": "text",
            "text": """กฎที่ต้องปฏิบัติเสมอ:
- ตัดสินใจตาม Strategy ข้างต้นเท่านั้น ห้ามใช้ทฤษฎีอื่น
- RSI และ indicators เป็นข้อมูลประกอบเท่านั้น ไม่ใช้ตัดสิน BUY/SELL
- R:R ต้องได้ ≥ 1.0 เสมอ ถ้าไม่ได้ → SKIP
- ถ้าไม่แน่ใจ → SKIP ดีกว่าเข้าผิด
- ตอบเป็น JSON เท่านั้น ห้ามมีข้อความนอก JSON"""
        }
    ]

    # Retry logic for rate limits and overloaded errors
    response = None
    last_error = None

    for attempt in range(3):
        try:
            # Model: claude-sonnet-4-20250514
            # Note: Verify this model supports prompt caching
            # Alternative models with confirmed caching support:
            #   - claude-3-5-sonnet-20241022
            #   - claude-3-opus-20240229
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": user_prompt}],
                system=system_blocks
            )
            break  # Success - exit retry loop

        except RateLimitError as e:
            last_error = e
            if attempt < 2:  # Don't sleep on last attempt
                wait_time = 60 if attempt == 0 else 120
                logger.warning(f"Rate limit hit (attempt {attempt + 1}/3), waiting {wait_time}s...")
                time.sleep(wait_time)
            # Don't re-raise - let it fall through to handlers below

        except APIStatusError as e:
            last_error = e
            if e.status_code == 529 and attempt < 2:  # Overloaded
                logger.warning(f"API overloaded (attempt {attempt + 1}/3), waiting 30s...")
                time.sleep(30)
            # Don't re-raise - let it fall through to handlers below

        except Exception as e:
            last_error = e
            # For other exceptions, don't retry - let it fall through

    # If we failed to get a response after retries, handle the error gracefully
    if response is None:
        if last_error is not None:
            # Handle specific error types
            error_msg = str(last_error).lower()

            # Credit exhausted
            if "credit" in error_msg or "balance is too low" in error_msg:
                logger.error("❌ Anthropic credit exhausted — backtest stopped")
                logger.error("   Go to console.anthropic.com to add credits")
                return {
                    'decision': {'action': 'SKIP', 'skip_reason': 'API credit exhausted'},
                    'llm_log': {'action': 'CREDIT_EXHAUSTED', 'cost_usd': 0},
                    'success': False
                }

            # Rate limit
            elif isinstance(last_error, RateLimitError):
                logger.error("❌ Rate limit exceeded after 3 retries")
                return {
                    'decision': {'action': 'SKIP', 'skip_reason': 'API rate limit exceeded'},
                    'llm_log': {'action': 'RATE_LIMIT', 'cost_usd': 0},
                    'success': False
                }

            # Other API errors
            elif isinstance(last_error, APIStatusError):
                logger.error(f"❌ API error ({last_error.status_code}): {last_error}")
                return {
                    'decision': {'action': 'SKIP', 'skip_reason': f'API error: {last_error.status_code}'},
                    'llm_log': {'action': 'API_ERROR', 'cost_usd': 0},
                    'success': False
                }

            # Unknown error
            else:
                logger.error(f"❌ Unexpected error: {last_error}")
                return {
                    'decision': {'action': 'SKIP', 'skip_reason': 'Unexpected API error'},
                    'llm_log': {'action': 'ERROR', 'cost_usd': 0},
                    'success': False
                }
        else:
            logger.error("❌ Failed to get response (no error captured)")
            return {
                'decision': {'action': 'SKIP', 'skip_reason': 'Unknown API failure'},
                'llm_log': {'action': 'ERROR', 'cost_usd': 0},
                'success': False
            }

    try:
        latency = round(time.time() - start_time, 2)

        # DEBUG: Log raw usage to verify cache fields
        logger.debug(f"API Response Usage: {response.usage}")
        logger.debug(f"Has cache_creation_input_tokens? {hasattr(response.usage, 'cache_creation_input_tokens')}")
        logger.debug(f"Has cache_read_input_tokens? {hasattr(response.usage, 'cache_read_input_tokens')}")

        # Parse JSON
        raw_text = response.content[0].text.strip()

        # ลบ markdown code block ถ้ามี
        if raw_text.startswith("```"):
            parts = raw_text.split("```")
            if len(parts) >= 2:
                raw_text = parts[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]

        decision = json.loads(raw_text.strip())

        # LLM Log
        llm_log = {
            'timestamp': datetime.now().isoformat(),
            'model': 'claude-sonnet-4-20250514',
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'cache_creation_tokens': getattr(response.usage, 'cache_creation_input_tokens', 0) or 0,
            'cache_read_tokens': getattr(response.usage, 'cache_read_input_tokens', 0) or 0,

            # total ที่ถูกต้อง = รวมทุกอย่างที่มีค่าใช้จ่าย
            'total_tokens': (
                response.usage.input_tokens +
                response.usage.output_tokens +
                (getattr(response.usage, 'cache_creation_input_tokens', 0) or 0)
            ),

            'cache_hit': (getattr(response.usage, 'cache_read_input_tokens', 0) or 0) > 0,
            'cost_usd': calc_cost(response.usage),
            'latency_sec': latency,
            'action': decision.get('action'),
            'confidence': decision.get('confidence'),
            'reason': decision.get('reason', '')[:100]  # ตัดถ้ายาวเกิน
        }

        # Log with full breakdown
        logger.info(
            f"💰 Tokens: in={llm_log['input_tokens']:,} | "
            f"out={llm_log['output_tokens']:,} | "
            f"cache_write={llm_log['cache_creation_tokens']:,} | "
            f"cache_read={llm_log['cache_read_tokens']:,} | "
            f"cost=${llm_log['cost_usd']:.4f} | "
            f"cache={'✅HIT' if llm_log['cache_hit'] else '❌MISS'}"
        )

        return {'decision': decision, 'llm_log': llm_log, 'success': True}

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return {
            'decision': {'action': 'SKIP', 'skip_reason': f'JSON parse error: {e}'},
            'llm_log': {'action': 'ERROR', 'latency_sec': round(time.time() - start_time, 2), 'cost_usd': 0},
            'success': False
        }
    except anthropic.RateLimitError as e:
        logger.error(f"❌ Rate limit error: {e}")
        return {
            'decision': {'action': 'SKIP', 'skip_reason': 'API rate limit - try again later'},
            'llm_log': {'action': 'RATE_LIMIT', 'cost_usd': 0},
            'success': False
        }
    except anthropic.APIStatusError as e:
        # Check for specific error types
        error_msg = str(e).lower()

        # Credit exhausted (400 with "credit" in message)
        if "credit" in error_msg or "balance is too low" in error_msg:
            logger.error(f"❌ Anthropic credit exhausted — backtest stopped")
            logger.error(f"   Go to console.anthropic.com to add credits")
            return {
                'decision': {'action': 'SKIP', 'skip_reason': 'API credit exhausted'},
                'llm_log': {'action': 'CREDIT_EXHAUSTED', 'cost_usd': 0},
                'success': False
            }

        # Overloaded (529)
        elif e.status_code == 529:
            logger.warning(f"API overloaded (529) - system busy")
            return {
                'decision': {'action': 'SKIP', 'skip_reason': 'API overloaded'},
                'llm_log': {'action': 'OVERLOADED', 'cost_usd': 0},
                'success': False
            }

        # Other API errors
        else:
            logger.error(f"API status error ({e.status_code}): {e}")
            return {
                'decision': {'action': 'SKIP', 'skip_reason': f'API error: {e.status_code}'},
                'llm_log': {'action': 'API_ERROR', 'cost_usd': 0},
                'success': False
            }

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            'decision': {'action': 'SKIP', 'skip_reason': 'Unexpected error'},
            'llm_log': {'action': 'ERROR', 'cost_usd': 0},
            'success': False
        }


def calc_cost(usage) -> float:
    """
    คำนวณต้นทุน API call พร้อม Prompt Caching
    claude-sonnet-4-20250514 pricing:
    - Input: $3/MTok
    - Output: $15/MTok
    - Cache Write: $3.75/MTok
    - Cache Read: $0.30/MTok (90% discount!)
    """
    # Regular tokens
    input_cost = (usage.input_tokens / 1_000_000) * 3.0
    output_cost = (usage.output_tokens / 1_000_000) * 15.0

    # Cache tokens (if exists)
    cache_creation_cost = 0.0
    cache_read_cost = 0.0

    if hasattr(usage, 'cache_creation_input_tokens') and usage.cache_creation_input_tokens:
        cache_creation_cost = (usage.cache_creation_input_tokens / 1_000_000) * 3.75

    if hasattr(usage, 'cache_read_input_tokens') and usage.cache_read_input_tokens:
        cache_read_cost = (usage.cache_read_input_tokens / 1_000_000) * 0.30

    total = input_cost + output_cost + cache_creation_cost + cache_read_cost
    return round(total, 6)


def validate_decision(decision: Dict, world_state: Dict, balance: float) -> Dict:
    """
    ตรวจ output จาก Claude ก่อนส่งต่อ

    Returns:
        {'valid': bool, 'errors': list}
    """
    errors = []
    action = decision.get('action')

    if action not in ['BUY', 'SELL', 'SKIP']:
        errors.append(f"action ไม่ถูกต้อง: {action}")
        return {'valid': False, 'errors': errors}

    if action == 'SKIP':
        if not decision.get('skip_reason'):
            errors.append("SKIP ต้องมี skip_reason")
        return {'valid': len(errors) == 0, 'errors': errors}

    # ตรวจ BUY/SELL
    required = ['entry', 'sl', 'tp', 'rr_ratio']
    for field in required:
        if decision.get(field) is None:
            errors.append(f"ขาด field: {field}")

    entry = decision.get('entry', 0)
    sl = decision.get('sl', 0)
    tp = decision.get('tp', 0)

    # Note: ไม่ reject เลขกลม เพราะบางครั้ง technical_price อาจเป็นเลขกลมได้จริง
    # แค่ prompt instruction ให้ Claude ใช้ technical_price ก็พอ

    if entry and sl and tp:
        if action == 'BUY':
            if sl >= entry:
                errors.append(f"BUY: SL ({sl}) ต้องต่ำกว่า Entry ({entry})")
            if tp <= entry:
                errors.append(f"BUY: TP ({tp}) ต้องสูงกว่า Entry ({entry})")
        elif action == 'SELL':
            if sl <= entry:
                errors.append(f"SELL: SL ({sl}) ต้องสูงกว่า Entry ({entry})")
            if tp >= entry:
                errors.append(f"SELL: TP ({tp}) ต้องต่ำกว่า Entry ({entry})")

        # ตรวจ R:R
        if action == 'BUY':
            rr = (tp - entry) / (entry - sl) if (entry - sl) > 0 else 0
        else:
            rr = (entry - tp) / (sl - entry) if (sl - entry) > 0 else 0

        if rr < 1.0:
            errors.append(f"R:R = {rr:.2f} ต่ำกว่า 1.0")

    return {'valid': len(errors) == 0, 'errors': errors}


# ============================================================================
# MAIN CLASS
# ============================================================================

class G3ClaudeDecisionAgent:
    """
    G3a Decision Agent - ใช้ Claude API ในการตัดสินใจ

    Usage:
        agent = G3ClaudeDecisionAgent()
        result = agent.decide(world_state, balance, portfolio_state)
    """

    def __init__(self, strategy_md_path: Optional[str] = None,
                 api_key: Optional[str] = None,
                 config: Optional[Dict] = None):
        """
        Args:
            strategy_md_path: Path to Strategy MD (default: strategy/XAUUSD_AI_Trading_System_v2.1.md)
            api_key: Anthropic API key (or read from env)
            config: {'verbose': bool}
        """
        self.config = config or {}
        self.verbose = self.config.get('verbose', False)

        # API Key
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in env or config")

        # Load Strategy MD
        if strategy_md_path is None:
            strategy_md_path = 'strategy/XAUUSD_AI_Trading_System_v2.1.md'

        self.strategy_md_path = strategy_md_path

        if not os.path.exists(strategy_md_path):
            raise FileNotFoundError(f"Strategy MD not found: {strategy_md_path}")

        with open(strategy_md_path, 'r', encoding='utf-8') as f:
            self.strategy_content = f.read()

        logger.info(f"G3ClaudeDecisionAgent initialized | Strategy: {len(self.strategy_content)} chars")

    def decide(self, world_state: Dict, balance: float,
               portfolio_state: Dict) -> Dict:
        """
        ตัดสินใจ BUY/SELL/SKIP

        Args:
            world_state: output จาก G1
            balance: Account balance (USD)
            portfolio_state: Portfolio state dict

        Returns:
            {
                'decision': dict (action, entry, sl, tp, etc.),
                'llm_log': dict,
                'validation': dict,
                'success': bool
            }
        """
        # Call Claude API
        result = call_claude_decision(
            world_state, balance, portfolio_state,
            self.strategy_content, self.api_key
        )

        if not result['success']:
            logger.error("Claude API call failed")
            return result

        decision = result['decision']

        # Validate
        validation = validate_decision(decision, world_state, balance)

        if not validation['valid']:
            logger.warning(f"Decision validation failed: {validation['errors']}")
            # แปลงเป็น SKIP
            decision = {
                'action': 'SKIP',
                'skip_reason': f"Validation errors: {', '.join(validation['errors'])}"
            }

        return {
            'decision': decision,
            'llm_log': result['llm_log'],
            'validation': validation,
            'success': validation['valid']
        }
