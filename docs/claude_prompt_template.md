# Claude Prompt Template v1.0
> สำหรับ G3a Claude Decision Agent
> Model: claude-sonnet-4-20250514
> อ้างอิง: XAUUSD_AI_Trading_System.md v2.0

---

## System Prompt

```
คุณคือ XAUUSD Trading Analyst ที่มีประสบการณ์สูง

หน้าที่ของคุณ:
1. อ่าน Strategy Document ด้านล่างให้เข้าใจ
2. วิเคราะห์ข้อมูลกราฟที่ได้รับ
3. ตัดสินใจ BUY / SELL / SKIP พร้อมระบุ Entry, SL, TP และเหตุผล

=== STRATEGY DOCUMENT ===
{STRATEGY_CONTENT}
=== END STRATEGY ===

กฎที่ต้องปฏิบัติเสมอ:
- ตัดสินใจตาม Strategy ข้างต้นเท่านั้น ห้ามใช้ทฤษฎีอื่น
- RSI และ indicators เป็นข้อมูลประกอบเท่านั้น ไม่ใช้ตัดสิน BUY/SELL
- R:R ต้องได้ ≥ 1.0 เสมอ ถ้าไม่ได้ → SKIP
- ถ้าไม่แน่ใจ → SKIP ดีกว่าเข้าผิด
- ตอบเป็น JSON เท่านั้น ห้ามมีข้อความนอก JSON
```

---

## User Prompt Template

```
วิเคราะห์กราฟ XAUUSD และตัดสินใจเทรด

=== ข้อมูลกราฟ ===
Timeframe ที่เลือก: {SELECTED_TF}
เหตุผลที่เลือก TF นี้: {TF_SELECTION_REASON}

Chart Type ที่ตรวจพบ: {CHART_TYPE}
Chart Quality Score: {CHART_QUALITY}/1.0
Technique Candidate: {TECHNIQUE_CANDIDATE}

Range 55 แท่ง:
- High: {RANGE_HIGH}
- Low: {RANGE_LOW}
- Range: {RANGE_USD} USD ({RANGE_PIP} pip)

ราคาปัจจุบัน: {CURRENT_PRICE}
Session: {SESSION}

=== รายละเอียด Chart Pattern ===
{CHART_DETAIL_TEXT}

=== แท่งคู่ (จุดเทคนิค) ===
{TWIN_CANDLE_TEXT}

=== แท่งพ่อ (ถ้ามี) ===
{FATHER_CANDLE_TEXT}

=== OHLC ล่าสุด 10 แท่ง ({SELECTED_TF}) ===
{OHLC_TABLE}

=== ข้อมูล Metadata (อ้างอิงเท่านั้น) ===
RSI(14): {RSI_VALUE}

=== สถานะพอร์ต ===
Balance: {BALANCE} USD
Open Trades: {OPEN_TRADES}
Current Plan: {CURRENT_PLAN}
Consecutive Loss: {CONSECUTIVE_LOSS}

=== คำถาม ===
จากข้อมูลทั้งหมดข้างต้น:
1. Chart type นี้ตรงกับ Strategy ข้อไหน?
2. มี Setup ที่เข้าได้ไหม? ถ้ามีคือ Technique อะไร?
3. ถ้าเข้า — Entry, SL, TP อยู่ที่เท่าไหร่? R:R ได้เท่าไหร่?
4. ถ้า SKIP — เหตุผลคืออะไร?

ตอบในรูปแบบ JSON ตามนี้เท่านั้น:
{OUTPUT_FORMAT}
```

---

## Output Format (JSON Schema)

```json
{
  "chart_type": "uptrend|downtrend|sideway_down|sideway_up|mountain|unclear",
  "technique": "twin_candle|breakout_follow|mai_ruay|support_bounce|none",
  "action": "BUY|SELL|SKIP",
  "confidence": 0.85,
  "entry": 3245.50,
  "sl": 3230.00,
  "tp": 3261.00,
  "rr_ratio": 1.03,
  "lot_total": 0.03,
  "lot_per_order": 0.01,
  "suggested_orders": 3,
  "sl_pip": 1550,
  "tp_pip": 1550,
  "skip_reason": "",
  "reason": "อธิบาย visual pattern ที่เห็น และเหตุผลการตัดสินใจ 2-3 ประโยค",
  "pattern_quality": "excellent|good|fair|poor",
  "tf_used": "M5",
  "session": "London"
}
```

**กฎ JSON:**
- ถ้า SKIP → entry/sl/tp/rr_ratio = 0, skip_reason ต้องมีข้อความ
- ถ้า BUY/SELL → skip_reason = ""
- confidence: ความมั่นใจในการตัดสินใจ (0.0-1.0)
- lot_total: คำนวณจาก balance × 10% / sl_pip
- suggested_orders: แนะนำกี่ order (1-3) โดย lot_per_order = lot_total / suggested_orders
- ห้ามมีข้อความนอก JSON เด็ดขาด

---

## Chart Detail Text Templates

### Uptrend
```
Uptrend ที่ตรวจพบ:
- ความชัน: {slope_angle}° (อ้างอิง: 45-50°)
- Higher High พบ: {hh_count} ครั้ง
- Higher Low พบ: {hl_count} ครั้ง
- ต่อเนื่องไม่มีสวนทิศ: {consecutive}
- ช่วงพักตัวล่าสุด: ย่อมาจาก {last_high} ปัจจุบัน {current_price}
```

### Downtrend
```
Downtrend ที่ตรวจพบ:
- ความชัน: {slope_angle}° (อ้างอิง: 45-50°)
- Lower High พบ: {lh_count} ครั้ง
- Lower Low พบ: {ll_count} ครั้ง
- ต่อเนื่องไม่มีสวนทิศ: {consecutive}
- ช่วงดีดขึ้นล่าสุด: ดีดจาก {last_low} ปัจจุบัน {current_price}
```

### Sideway Press Down
```
Sideway Press Down ที่ตรวจพบ:
- ขาลงแรง: {impulse_candles} แท่ง = {impulse_pct_str}% ของ Range
- กรอบ Sideway: {box_low} - {box_high} ({box_pct_str}% ของ Range)
- ตำแหน่งราคาปัจจุบัน: {current_position}
  (near_top = ใกล้กรอบบน → SELL, near_bottom = ใกล้กรอบล่าง → BUY)
```

### Sideway Press Up
```
Sideway Press Up ที่ตรวจพบ:
- ขาขึ้นแรง: {impulse_candles} แท่ง = {impulse_pct_str}% ของ Range
- กรอบ Sideway: {box_low} - {box_high} ({box_pct_str}% ของ Range)
- ตำแหน่งราคาปัจจุบัน: {current_position}
```

### Mountain
```
ภูเขาที่ตรวจพบ:
- ยอดภูเขา: {peak_price} (แท่งที่ {peak_idx} จากปัจจุบัน)
- ฐานซ้าย: {left_base_price}
- ความสูง: {height_usd} USD = {height_pct_str}% ของ Range
- แท่งที่วกกลับฐาน: {return_candles} แท่ง (ดี ≤ 40)
- ราคาปัจจุบัน {current_price} ห่างจากฐาน {base_diff_pip} pip
  (Tolerance: ±{tolerance_pip} pip)
```

### Unclear + Father Candle
```
กราฟไม่ชัด — ตรวจพบแท่งพ่อ (ไม้รวย):
- ทิศทางแท่งพ่อ: {father_direction} ({pct_range_str}% ของ Range, {candle_count} แท่ง)
- แท่งแม่: {mother_beauty} (ขนาด {body_ratio_str}% ของพ่อ)
- จุดเทคนิค: {technical_price}
- ทิศทางเล่น: {"BUY" if father_direction == "down" else "SELL"}
```

---

## OHLC Table Format

```python
def format_ohlc_table(candles: list, tf: str) -> str:
    """สร้างตาราง OHLC ล่าสุด 10 แท่ง"""
    header = f"{'แท่ง':>4} | {'Open':>8} | {'High':>8} | {'Low':>8} | {'Close':>8} | {'Dir':>5}"
    lines = [header, "-" * 55]
    recent = candles[-10:]
    for i, c in enumerate(recent):
        n = i - len(recent) + 1  # -9 ถึง 0
        direction = "▲" if c['close'] >= c['open'] else "▼"
        lines.append(
            f"{n:>4} | {c['open']:>8.2f} | {c['high']:>8.2f} | "
            f"{c['low']:>8.2f} | {c['close']:>8.2f} | {direction:>5}"
        )
    return "\n".join(lines)
```

---

## Twin Candle Text Format

```python
def format_twin_candle(twin: dict) -> str:
    if not twin.get('found'):
        return "ไม่พบแท่งคู่ในบริเวณที่ค้นหา"
    return (
        f"พบแท่งคู่:\n"
        f"- จุดเทคนิค (Technical Price): {twin['technical_price']:.2f}\n"
        f"- ขนาดเนื้อเทียน: {twin['body_pct']*100:.1f}% ของ Range\n"
        f"- ตำแหน่ง: แท่งที่ {twin['candle1_idx']} และ {twin['candle2_idx']}"
    )
```

---

## Father Candle Text Format

```python
def format_father_candle(father: dict) -> str:
    if not father.get('found'):
        return "ไม่พบแท่งพ่อ"

    mother = father.get('mother_candle', {})
    dir_th = "ลง" if father['direction'] == 'down' else "ขึ้น"
    play_th = "BUY" if father['direction'] == 'down' else "SELL"

    result = (
        f"พบแท่งพ่อ:\n"
        f"- ทิศทาง: พุ่ง{dir_th} → เตรียมเล่น {play_th}\n"
        f"- ขนาด: {father['pct_range']*100:.0f}% ของ Range "
        f"({father['candle_count']} แท่ง)\n"
        f"- Quality: {father['quality']:.2f}\n"
    )

    if mother.get('found'):
        result += (
            f"แท่งแม่:\n"
            f"- ขนาดเนื้อเทียน: {mother['body_ratio']*100:.1f}% ของพ่อ "
            f"({mother['beauty']})\n"
            f"- ปิดสวนทิศ: {'✅' if mother['reversed_close'] else '❌'}\n"
            f"- จุดเทคนิค: {mother['technical_price']:.2f}\n"
            f"- ใช้ได้: {'✅' if mother['valid'] else '❌'}"
        )
    else:
        result += "แท่งแม่: ยังไม่เกิด (รอแท่งถัดไป)"

    return result
```

---

## TF Selection Reason Text

```python
def format_tf_selection_reason(tf_results: dict, selected_tf: str) -> str:
    """อธิบายเหตุผลที่เลือก TF นี้"""
    selected = tf_results[selected_tf]
    others = {tf: r for tf, r in tf_results.items() if tf != selected_tf}

    reason = (
        f"เลือก {selected_tf} เพราะ Chart Type '{selected['chart_type']}' "
        f"มี Quality {selected['quality']:.2f}"
    )

    # TF อื่นที่มีข้อมูล
    active_others = {tf: r for tf, r in others.items()
                     if r.get('chart_type') != 'unclear'}
    if active_others:
        other_summary = ", ".join(
            f"{tf}={r['chart_type']}({r['quality']:.2f})"
            for tf, r in active_others.items()
        )
        reason += f"\nTF อื่นที่พบ: {other_summary}"

    return reason
```

---

## ตัวอย่าง Prompt ที่ Build แล้ว (Sample)

```
วิเคราะห์กราฟ XAUUSD และตัดสินใจเทรด

=== ข้อมูลกราฟ ===
Timeframe ที่เลือก: H1
เหตุผลที่เลือก TF นี้: เลือก H1 เพราะ Chart Type 'uptrend' มี Quality 0.82
TF อื่นที่พบ: M5=uptrend(0.71), H4=unclear(0.00)

Chart Type ที่ตรวจพบ: uptrend
Chart Quality Score: 0.82/1.0
Technique Candidate: twin_candle

Range 55 แท่ง:
- High: 3280.50
- Low: 3215.00
- Range: 65.50 USD (6550 pip)

ราคาปัจจุบัน: 3241.20
Session: London

=== รายละเอียด Chart Pattern ===
Uptrend ที่ตรวจพบ:
- ความชัน: 47.3° (อ้างอิง: 45-50°)
- Higher High พบ: 4 ครั้ง
- Higher Low พบ: 4 ครั้ง
- ต่อเนื่องไม่มีสวนทิศ: True
- ช่วงพักตัวล่าสุด: ย่อมาจาก 3265.00 ปัจจุบัน 3241.20

=== แท่งคู่ (จุดเทคนิค) ===
พบแท่งคู่:
- จุดเทคนิค (Technical Price): 3238.50
- ขนาดเนื้อเทียน: 6.2% ของ Range
- ตำแหน่ง: แท่งที่ 48 และ 49

=== แท่งพ่อ (ถ้ามี) ===
ไม่พบแท่งพ่อ

=== OHLC ล่าสุด 10 แท่ง (H1) ===
แท่ง |     Open |     High |      Low |    Close |   Dir
-------------------------------------------------------
  -9 |  3262.10 |  3265.00 |  3258.30 |  3260.50 |     ▼
  -8 |  3260.50 |  3263.20 |  3255.40 |  3258.80 |     ▼
  -7 |  3258.80 |  3261.00 |  3250.20 |  3251.30 |     ▼
  -6 |  3251.30 |  3253.50 |  3244.60 |  3245.80 |     ▼
  -5 |  3245.80 |  3248.20 |  3239.10 |  3241.50 |     ▼
  -4 |  3241.50 |  3244.30 |  3237.80 |  3243.20 |     ▲
  -3 |  3243.20 |  3245.00 |  3238.00 |  3239.40 |     ▼
  -2 |  3239.40 |  3242.10 |  3237.20 |  3240.80 |     ▲
  -1 |  3240.80 |  3243.50 |  3238.60 |  3241.20 |     ▲
   0 |  3241.20 |  (live)  |  (live)  |  (live)  |

=== ข้อมูล Metadata (อ้างอิงเท่านั้น) ===
RSI(14): 48.3

=== สถานะพอร์ต ===
Balance: 500 USD
Open Trades: 0
Current Plan: ไม่มีแผนที่เปิดอยู่
Consecutive Loss: 0
```

---

## การ Call API

```python
import anthropic
import json
import time
from pathlib import Path

def call_claude_decision(world_state: dict, balance: float,
                          portfolio_state: dict) -> dict:
    """
    G3a: เรียก Claude API เพื่อตัดสินใจ
    return: decision dict + log dict
    """
    client = anthropic.Anthropic()

    # โหลด Strategy
    strategy_path = Path("strategy/XAUUSD_AI_Trading_System.md")
    strategy_content = strategy_path.read_text(encoding='utf-8')

    # Build prompt
    system_prompt = build_system_prompt(strategy_content)
    user_prompt = build_user_prompt(world_state, balance, portfolio_state)

    start_time = time.time()
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt
        )
        latency = round(time.time() - start_time, 2)

        # Parse JSON
        raw_text = response.content[0].text.strip()
        # ลบ markdown code block ถ้ามี
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        decision = json.loads(raw_text)

        # LLM Log
        llm_log = {
            'timestamp': time.strftime('%Y-%m-%d %Human:%M:%S'),
            'model': 'claude-sonnet-4-20250514',
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.input_tokens + response.usage.output_tokens,
            'cost_usd': calc_cost(response.usage),
            'latency_sec': latency,
            'action': decision.get('action'),
            'confidence': decision.get('confidence'),
            'reason': decision.get('reason', '')[:200]  # ตัดถ้ายาวเกิน
        }

        return {'decision': decision, 'llm_log': llm_log, 'success': True}

    except json.JSONDecodeError as e:
        return {
            'decision': {'action': 'SKIP', 'skip_reason': f'JSON parse error: {e}'},
            'llm_log': {'action': 'ERROR', 'latency_sec': latency},
            'success': False
        }
    except Exception as e:
        return {
            'decision': {'action': 'SKIP', 'skip_reason': f'API error: {e}'},
            'llm_log': {'action': 'ERROR'},
            'success': False
        }


def calc_cost(usage) -> float:
    """
    claude-sonnet-4-20250514 pricing:
    Input: $3/MTok | Output: $15/MTok
    """
    input_cost = (usage.input_tokens / 1_000_000) * 3.0
    output_cost = (usage.output_tokens / 1_000_000) * 15.0
    return round(input_cost + output_cost, 6)
```

---

## Validation — ตรวจ Output ก่อนส่ง G3b

```python
def validate_decision(decision: dict, world_state: dict,
                       balance: float) -> dict:
    """
    ตรวจ output จาก Claude ก่อนส่งต่อ
    return: {valid: bool, errors: list}
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
    required = ['entry', 'sl', 'tp', 'rr_ratio', 'lot_total']
    for field in required:
        if not decision.get(field):
            errors.append(f"ขาด field: {field}")

    entry = decision.get('entry', 0)
    sl = decision.get('sl', 0)
    tp = decision.get('tp', 0)

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
```
