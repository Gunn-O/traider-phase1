# XAUUSD Strategy v4.0 + Phase I Agent AI
> **ไฟล์นี้ใช้สำหรับ Phase I Development**
> รวม Strategy Document (Source of Truth) + Agent Specification + Implementation Guide ครบในไฟล์เดียว

---

## ส่วนที่ 1 — XAUUSD Trading Strategy v4.0 (Source of Truth)

> อัปเดตจาก Trading Condition Document + 49 Case Studies (Jan–Mar 2025)
> **Timeframe Entry: M5 เท่านั้น** | Filter: H1 trend direction
> Indicators: RSI(14) + S/R Level + Candle Pattern + H1 Trend

### ขั้นตอนการวิเคราะห์ (ทำตามลำดับทุกครั้ง)

```
Step 1: ระบุ "ลักษณะกราฟ" จาก 6 แบบ (ดูจาก 80 แท่งล่าสุด)
Step 2: เลือก Technique ที่เหมาะกับ Condition นั้น
Step 3: ตรวจ 3 เงื่อนไข: S/R zone + RSI + Confirmation candle
Step 4: ถ้าครบ → คำนวณ Entry / SL / TP1–TP3
Step 5: ถ้าไม่ครบ หรือไม่แน่ใจ = SKIP เสมอ
```

---

### A — ลักษณะกราฟ 6 แบบ (Trading Conditions)

#### A1 — เทรนขึ้น (Uptrend)
**ตรวจสอบด้วย 80 แท่ง** — ราคาขึ้นสม่ำเสมอและชัดเจนตลอด 80 แท่ง (Higher High & Higher Low)

**Action: BUY เท่านั้น**

| จุด | รายละเอียด |
|-----|-----------|
| จุดเข้า | ใกล้เคียงแท่งคู่ล่าสุดที่มีการย่อพักตัวลงมา |
| TP1 | ⅓ ของยอดก่อนหน้า (นับจากเนื้อเทียน) |
| TP2 | ½ ของยอดก่อนหน้า (นับจากเนื้อเทียน) |
| TP3 | เนื้อเทียนบนสุด หรือต่ำกว่าเล็กน้อยของยอดก่อนหน้า |
| SL | เลยปลายไส้ล่างของจุดพักตัวก่อนหน้า + buffer |

> ⚠️ ถ้าไส้ก่อนหน้ายาวมาก → พิจารณา SKIP — SL กว้างเกิน R:R ไม่คุ้ม

---

#### A2 — เทรนลง (Downtrend)
**ตรวจสอบด้วย 80 แท่ง** — ราคาลงสม่ำเสมอและชัดเจนตลอด 80 แท่ง (Lower High & Lower Low)

**Action: SELL เท่านั้น**

| จุด | รายละเอียด |
|-----|-----------|
| จุดเข้า | ใกล้เคียงแท่งคู่ล่าสุดที่มีการสวิงกลับขึ้นไป |
| TP1 | ⅓ ของจุดต่ำสุดก่อนหน้า (นับจากเนื้อเทียน) |
| TP2 | ½ ของจุดต่ำสุดก่อนหน้า (นับจากเนื้อเทียน) |
| TP3 | เนื้อเทียนต่ำสุด หรือสูงกว่าเล็กน้อยของจุดต่ำสุดก่อนหน้า |
| SL | เลยปลายไส้บนของจุดสวิงขึ้นก่อนหน้า + buffer |

> ⚠️ ถ้าไส้สวิงขึ้นยาวมาก → พิจารณา SKIP — รอสวิงถัดไปที่ดีกว่า

---

#### A3 — ภูเขา (Mountain)
**ตรวจสอบด้วย 50 แท่ง** — กราฟขึ้นแล้วลงกลับคล้ายภูเขา BUY ที่ฐาน (ขาขึ้นครั้งใหม่)

**ลักษณะภูเขาที่ดี:**
- ฐานแท่งคู่ด้านขวา มีความหนาแน่นพอสมควร
- มีลักษณะเป็นสามเหลี่ยมของราคาขึ้นลงชัดเจน
- ยอดของภูเขาไม่แบน
- เมื่อมองใน 50 แท่ง ฐานของภูเขาไม่ลอย

**Action: BUY ที่ฐาน**

| จุดเข้า | รายละเอียด |
|---------|-----------|
| จุดที่ 1 | เนื้อแท่งคู่ที่ฐาน หรือใกล้เคียง (ไม่เกิน 100–200 จุด) |
| จุดที่ 2 | เนื้อแท่งคู่ที่ฐาน (จุดเทคนิค) |
| จุดที่ 3 | ต่ำกว่าแท่งคู่ที่ฐาน (จุดได้เปรียบ — SL สั้น TP ไกล) |

| TP | รายละเอียด |
|----|-----------|
| TP1 | ⅓ ของภูเขา |
| TP2 | ½ ของภูเขา |
| TP3 | เกือบยอดสุดของภูเขา |
| TPอื่นๆ | สังเกตอุปสรรคที่ขวาง (กลุ่มราคา หรือแท่งคู่ขวาง) |
| SL | เลยปลายไส้ล่างของฐานซ้าย + buffer (หรือ = ระยะ TP) |

> ⚠️ ไม่ควรเข้าลอยเกิน 100–200 จุดจากฐาน เพราะ SL ไกลขึ้นและ TP เก็บได้น้อยลง

---

#### A4 — ไซเวย์ออกข้าง ขาขึ้น (Sideways after Upleg)
ราคาขึ้นมาแรงรวดเร็วใน 1–5 แท่ง แล้วสวิงออกข้างเป็นกลุ่มชัดเจน

**Action: BUY ที่ขอบล่าง (ได้เปรียบกว่า SELL เพราะ trend ใหญ่ยังขึ้น)**

| | รายละเอียด |
|-|-----------|
| Action หลัก | BUY ที่เส้นล่างของกรอบ |
| Action รอง | SELL ที่เส้นบนของกรอบ (ระวังมากกว่า) |
| SL | ออกนอกกรอบ + buffer |
| TP | ขอบตรงข้ามของกรอบ หรือ ⅓ / ½ ของกรอบ |

> ⚠️ SKIP ถ้ากรอบแคบ < 15 pip — กำไรไม่คุ้มค่า spread

---

#### A5 — ไซเวย์ออกข้าง ขาลง (Sideways after Downleg)
ราคาลงมาแรงรวดเร็วใน 1–5 แท่ง แล้วสวิงออกข้างเป็นกลุ่มชัดเจน

**Action: SELL ที่ขอบบน (ได้เปรียบกว่า BUY เพราะ trend ใหญ่ยังลง)**

| | รายละเอียด |
|-|-----------|
| Action หลัก | SELL ที่เส้นบนของกรอบ |
| Action รอง | BUY ที่เส้นล่างของกรอบ (ระวังมากกว่า) |
| SL | ออกนอกกรอบ + buffer |
| TP | ขอบตรงข้ามของกรอบ |

> ⚠️ SKIP ถ้ากรอบแคบ < 15 pip

---

#### A6 — กราฟไม่ชัด (Unclear / Mixed)
ลักษณะกราฟที่ไม่อยู่ใน 5 แบบแรก

**→ ใช้เฉพาะ B1 ไม้รวย และ B3 แนวเด้ง เท่านั้น — ห้ามใช้ pattern ที่ต้องอ่าน trend**

---

### B — เทคนิค 3 แบบ

#### B1 — ไม้รวย (Spike Reversal)
เหมาะกับ A6 และทุก Condition เมื่อเกิด spike ขนาดใหญ่

**จุดสังเกต spike:**
- การเคลื่อนไหวใหญ่มากใน 1–5 แท่ง
- สัดส่วน 60–100% ของ 50 แท่งที่ผ่านมา

| เงื่อนไข | BUY | SELL |
|---------|-----|------|
| S/R Zone | Spike ลงชน Support | Spike ขึ้นชน Resistance |
| RSI | ≤ 45 (RSI 25 ก็ BUY ได้ — อย่ากลัว extreme) | ≥ 55 (หรือ resistance แข็ง) |
| Candle | Lower wick ≥ 1.5× body size | Upper wick ≥ 1.5× body size |
| Confirm | Next candle: close > open | Next candle: close < open |
| SL | ปลาย wick + buffer | ปลาย wick + buffer |
| TP | S/R ถัดไป (R:R ≥ 1:2) | S/R ถัดไป (R:R ≥ 1:2) |

---

#### B2 — ตามเจ้า (Smart Money Follow)
Breakout ผ่าน resistance → pullback retest → entry | เหมาะกับ A1 (BUY), A2 (SELL)

| เงื่อนไข | BUY | SELL |
|---------|-----|------|
| Setup | Strong breakout H1/M15 ผ่าน resistance | Strong breakdown H1/M15 ผ่าน support |
| Entry | Pullback retest level เดิมบน M5 + bounce | Pullback retest level เดิมบน M5 + rejection |
| RSI | 55–65 (momentum ยังมี) | 35–45 (bearish momentum) |
| SL | ใต้ retest candle low + buffer | เหนือ retest candle high + buffer |
| TP | Measured move หรือ next resistance | Measured move หรือ next support |

---

#### B3 — แนวเด้ง (Key Level Bounce)
ราคาเด้งจาก S/R level สำคัญ — ใช้ได้ทุก Condition

| เงื่อนไข | รายละเอียด |
|---------|-----------|
| S/R Level | ราคาแตะ S/R level ที่ผ่านมาแล้วอย่างน้อย 2 ครั้ง |
| Candle | มี rejection candle ชัดเจน (wick ยาว หรือ engulfing) |
| RSI | สอดคล้องกับทิศที่จะเข้า (ไม่สวน momentum) |
| SL | เลย S/R level ออกไป + buffer |
| TP | S/R ถัดไปในทิศที่เข้า (R:R ≥ 1:2) |

---

### C — Condition × Technique Matrix (Quick Reference)

| Condition | Action | Technique | TP หลัก | SKIP เมื่อ |
|-----------|--------|-----------|---------|-----------|
| A1 เทรนขึ้น | BUY | ตามเจ้า, แนวเด้ง | ⅓ ½ ยอดก่อนหน้า | ไส้ยาวมาก |
| A2 เทรนลง | SELL | ตามเจ้า, แนวเด้ง | ⅓ ½ จุดต่ำสุด | ไส้ยาวมาก |
| A3 ภูเขา | BUY ฐาน | แนวเด้ง, ไม้รวย | ⅓ ½ ยอดภูเขา | ฐานลอย / เข้าลอย >200pt |
| A4 ไซเวย์ขาขึ้น | BUY ขอบล่าง | แนวเด้ง | ขอบบนกรอบ | กรอบแคบ <15 pip |
| A5 ไซเวย์ขาลง | SELL ขอบบน | แนวเด้ง | ขอบล่างกรอบ | กรอบแคบ <15 pip |
| A6 ไม่ชัด | BUY/SELL ตาม S/R | ไม้รวย, แนวเด้ง เท่านั้น | S/R ถัดไป | ไม่มี spike / ไม่มี level |

---

### D — RSI Rules

| RSI Zone | สถานะ | Action Rule |
|----------|-------|-------------|
| ≤ 25 | Extreme Oversold | BUY แรงมาก — ไม้รวย + support ยิ่งดี อย่ากลัว |
| 26–35 | Oversold | BUY (ไม้รวย, ภูเขา) |
| 36–44 | ใกล้ Oversold | BUY ถ้ามี pattern ชัด + confirmation candle |
| 45–54 | โซนกลาง | **SKIP** — ยกเว้น A4/A5 ไซเวย์ เท่านั้น |
| 55–65 | Momentum zone | BUY ตามเจ้า / SELL ถ้ามี pattern ที่ resistance |
| 65–70 | Strong Momentum | ตามเจ้าเฟิร์มสั้น BUY |
| > 70 | Overbought | SELL ถ้ามี pattern ที่ resistance |

> ⚠️ RSI extreme ไม่ใช่ signal stand-alone — ต้องมี pattern รองรับเสมอ ถ้าไม่มี = SKIP

---

### E — H1 Filter

| H1 Direction | เน้น Action | Conditions ที่ทำงาน |
|-------------|------------|-------------------|
| Uptrend (Bullish) | BUY | A1, A3 ฐาน, A4 ขอบล่าง, B2 ตามเจ้า, B3 แนวเด้ง |
| Downtrend (Bearish) | SELL | A2, A5 ขอบบน, B2 SELL, B3 แนวเด้ง SELL |
| Sideways | A4/A5 ตามกรอบ | B1 ไม้รวย / B3 แนวเด้ง ที่ extreme เท่านั้น |

> Momentum แรง ≠ มี pattern — ถ้าไม่มี pattern objective = SKIP เสมอ

---

### F — Lot Size Reference

| Condition | Pattern | Confidence | Lot Size |
|-----------|---------|-----------|----------|
| A1/A2 Trend | ตามเจ้า / แนวเด้ง | ปานกลาง | 0.38–0.58 |
| A3 ภูเขา จุด 1 | แนวเด้ง ที่ฐาน | ปานกลาง | 0.28–0.58 |
| A3 ภูเขา จุด 3 | แนวเด้ง จุดได้เปรียบ | สูง | 0.48–0.88 |
| A4/A5 ไซเวย์ | แนวเด้ง ขอบกรอบ | ปานกลาง | 0.48–0.88 |
| A6 ไม้รวย RSI > 35 | Spike Reversal | ปานกลาง | 0.18–0.38 |
| A6 ไม้รวย RSI < 30 | Spike Reversal extreme | สูง | 0.48–0.68 |
| TP Continuation | ทะลุ TP แล้วยัง run | ปานกลาง | 0.28–0.48 |

> สูตร: `lot = (account_balance × risk_pct) / (sl_distance_points × point_value)`
> Default risk_pct = 1.5%, จำกัด max lot ตาม risk_profile เสมอ

---

## ส่วนที่ 2 — Phase I Agent AI Specification

### Phase I เป้าหมาย

พิสูจน์ว่า AI อ่าน Strategy ได้ถูกต้อง โดยรัน **Simulated Trade** — ไม่มี MT5 execution จริง ทุก decision จะถูก log และตรวจสอบย้อนหลังกับราคาจริง

**KPI ที่ต้องผ่านก่อน Phase II:**
- Simulated Win Rate ≥ 60% ติดต่อกัน 4 สัปดาห์
- Signal Accuracy (TP reached) ≥ 70%
- Guardian Block Rate < 20%
- LINE Delivery Rate = 100%

---

### Pipeline Phase I

```
[MT5 API] M5 close ทุก 5 นาที
    ↓
[G1] signal_logic.py
     - คำนวณ RSI(14)
     - หา S/R swing levels
     - ระบุ Condition A1–A6
     - ตรวจ news flag
     - ผ่านถ้า pattern ครบ 2/3 เงื่อนไข
    ↓ world_state JSON
[G2] quant_analysis.py
     - RSI Zone score
     - S/R Strength score
     - Trend Alignment score
     - รวม → confidence 0.0–1.0
    ↓ confidence ≥ 0.70
[G3] claude_decision.py  ← ส่ง world_state + Strategy MD เป็น system prompt
     - Decision Agent (Claude API)
     - Money Management
     - Position Planner
     - Guardian (rule-based)
    ↓ {approved: true, action, entry, sl, tp1-3, lot}
[G4a] notify.py
      - Format LINE message ภาษาไทย
      - ส่ง LINE Notify API
[G4b] sheets_logger.py
      - Append 1 row → Google Sheets
      - บันทึก simulated_result (คำนวณจากราคาจริงหลังสุด)
    ↓ [รายสัปดาห์]
[G5] weekly_report.py
     - อ่าน Sheets 7 วันล่าสุด
     - หา win% per condition/RSI zone/session
     - เสนอปรับ threshold
     - ส่งรายงาน LINE
```

---

### Agent Prompts & Specs

#### G1 — Perception Agent
**ไฟล์:** `signal_logic.py`
**เรียกบ่อย:** ทุก M5 candle (Python logic หลัก — เรียก Claude เฉพาะ edge case)

**Input ที่ต้องการ:**
```python
{
    "m5_ohlcv": [...],    # 80 แท่งล่าสุด
    "h1_candles": [...],  # 20 แท่งล่าสุด
    "rsi_14": float,      # RSI(14) ปัจจุบัน
    "current_price": float,
    "timestamp": str
}
```

**Logic หลัก (Python — ไม่ต้องเรียก Claude):**
```python
def scan_conditions(data) -> dict:
    conditions_met = 0
    
    # เงื่อนไข 1: RSI zone ไม่ใช่โซนกลาง (45–54) เว้นแต่ sideways
    if not (45 <= data["rsi_14"] <= 54):
        conditions_met += 1
    
    # เงื่อนไข 2: ราคาใกล้ S/R level (within buffer)
    sr_distance = min(abs(data["current_price"] - sr) for sr in data["sr_levels"])
    if sr_distance <= SR_BUFFER_POINTS:
        conditions_met += 1
    
    # เงื่อนไข 3: มี pattern candidate (wick ratio หรือ spike)
    if detect_pattern_candidate(data["m5_ohlcv"]):
        conditions_met += 1
    
    # ส่งต่อ G2 เฉพาะเมื่อ ≥ 2/3 เงื่อนไขครบ
    if conditions_met >= 2:
        return build_world_state(data)
    return None
```

**Output (`world_state` JSON):**
```json
{
    "price": 3050.48,
    "rsi": 36.20,
    "h1_trend": "bullish",
    "condition_candidate": "A3_mountain",
    "nearest_sr": 3050.00,
    "sr_distance": 0.48,
    "sr_touches": 3,
    "pattern_candidate": "แนวเด้ง",
    "spike_detected": false,
    "spike_ratio": 0.0,
    "news_flag": false,
    "news_event": "",
    "session": "London",
    "spread_ok": true,
    "candles_checked": 80,
    "timestamp": "2025-03-12T14:05:00Z"
}
```

---

#### G2 — Quantitative Analysis Agent
**ไฟล์:** `quant_analysis.py`
**เรียกบ่อย:** เมื่อ G1 ส่ง candidate มา (~20 ครั้ง/วัน)

**Scoring Logic:**
```python
def calculate_confidence(world_state) -> float:
    score = 0.0
    weights = {"rsi": 0.30, "sr": 0.40, "trend": 0.30}
    
    # RSI Zone Score (0.0–1.0)
    rsi = world_state["rsi"]
    if rsi <= 25 or rsi >= 75:
        rsi_score = 1.0   # extreme — strongest signal
    elif rsi <= 35 or rsi >= 65:
        rsi_score = 0.85
    elif rsi <= 44 or rsi >= 56:
        rsi_score = 0.70
    elif 45 <= rsi <= 54:
        rsi_score = 0.30  # โซนกลาง — ต่ำมาก
    else:
        rsi_score = 0.50
    
    # S/R Strength Score (0.0–1.0)
    touches = world_state["sr_touches"]
    distance = world_state["sr_distance"]
    sr_score = min(touches / 4, 1.0) * (1 - min(distance / 50, 1.0))
    
    # Trend Alignment Score (0.0–1.0)
    h1 = world_state["h1_trend"]
    cond = world_state["condition_candidate"]
    is_aligned = (
        (h1 == "bullish" and "BUY" in get_action(cond)) or
        (h1 == "bearish" and "SELL" in get_action(cond)) or
        h1 == "sideways"
    )
    trend_score = 1.0 if is_aligned else 0.30
    
    # Weighted score
    score = (rsi_score * weights["rsi"] +
             sr_score   * weights["sr"] +
             trend_score * weights["trend"])
    
    return round(score, 3)

# ผ่านต่อ G3 เฉพาะเมื่อ confidence >= 0.70
```

**Output:**
```json
{
    "confidence": 0.87,
    "filter_pass": true,
    "rsi_score": 0.85,
    "sr_score": 0.92,
    "trend_score": 1.00,
    "breakdown": "RSI 36 (oversold zone), S/R 3 touches at 3050, H1 bullish aligned"
}
```

---

#### G3a — Decision Agent (Claude API)
**ไฟล์:** `claude_decision.py`
**เรียกบ่อย:** ~10–15 ครั้ง/วัน | ~250 tokens/ครั้ง

**System Prompt ที่ส่งให้ Claude:**
```
คุณคือ XAUUSD Trading Analyst ผู้เชี่ยวชาญ

อ่าน Strategy Document ด้านล่างแล้วตัดสินใจ BUY / SELL / SKIP
ตอบเป็น JSON เท่านั้น ห้าม markdown ห้าม explanation นอก JSON

[แทรก XAUUSD_Strategy_v4.md ทั้งหมดที่นี่]

กฎเพิ่มเติม:
- confidence < 0.70 = SKIP เสมอ
- R:R < 1:2 = SKIP เสมอ
- news_flag = true = SKIP เสมอ
- ตอบ JSON format ที่กำหนดเท่านั้น
```

**User Message ที่ส่ง:**
```python
user_msg = f"""
วิเคราะห์ market state นี้และตัดสินใจ:

{json.dumps(world_state, ensure_ascii=False, indent=2)}
Confidence จาก G2: {confidence_data['confidence']}
Breakdown: {confidence_data['breakdown']}

ตอบเป็น JSON ตาม format นี้เท่านั้น:
{{
  "chart_condition": "...",
  "pattern": "...",
  "action": "BUY | SELL | SKIP",
  "confidence": 0.0,
  "entry": 0.0,
  "sl": 0.0,
  "tp1": 0.0,
  "tp2": 0.0,
  "tp3": 0.0,
  "lot": 0.0,
  "rsi_now": 0.0,
  "h1_trend": "...",
  "session": "...",
  "candles_checked": 80,
  "skip_reason": "ถ้า SKIP",
  "reason": "อธิบายสั้นๆ"
}}
"""
```

**API Call:**
```python
import anthropic

client = anthropic.Anthropic()

def get_decision(world_state: dict, confidence_data: dict, strategy_md: str) -> dict:
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=build_system_prompt(strategy_md),
        messages=[{"role": "user", "content": build_user_msg(world_state, confidence_data)}]
    )
    
    raw = response.content[0].text.strip()
    # Strip markdown if present
    raw = re.sub(r"```json\n?|\n?```", "", raw).strip()
    
    decision = json.loads(raw)
    
    # Validate required fields
    assert decision["action"] in ["BUY", "SELL", "SKIP"]
    assert 0.0 <= decision["confidence"] <= 1.0
    
    return decision
```

---

#### G3b — Money Management Agent
**ไฟล์:** `money_management.py` (pure Python — ไม่ต้องเรียก Claude)

```python
def calculate_lot(
    action: str,
    entry: float,
    sl: float,
    account_balance: float,
    risk_profile: dict
) -> float:
    """คำนวณ lot size จาก risk per trade"""
    
    risk_pct = risk_profile["risk_per_trade_pct"] / 100  # 0.015
    risk_amount = account_balance * risk_pct              # USD
    
    sl_distance = abs(entry - sl)                         # points
    point_value = 0.1                                     # USD per 0.01 lot per point (XAUUSD)
    
    # lot = risk_amount / (sl_distance × pip_value_per_lot)
    pip_value_per_lot = sl_distance * 100 * point_value   # USD per lot
    raw_lot = risk_amount / pip_value_per_lot
    
    # Round to 2 decimal places
    lot = round(raw_lot, 2)
    
    # Apply min/max limits
    lot = max(0.01, min(lot, risk_profile.get("max_lot", 1.00)))
    
    return lot
```

---

#### G3c — Guardian Agent
**ไฟล์:** `risk_gate.py` (rule-based — ไม่ต้องเรียก Claude)

```python
def guardian_check(
    decision: dict,
    lot: float,
    account_state: dict,
    risk_profile: dict
) -> dict:
    """ตรวจ risk profile ก่อน approve signal"""
    
    reasons = []
    
    # 1. Max Daily Drawdown
    if account_state["daily_pnl_pct"] <= -risk_profile["max_daily_loss_pct"]:
        reasons.append(f"Daily loss limit reached: {account_state['daily_pnl_pct']:.1f}%")
    
    # 2. Max Total Drawdown
    if account_state["total_dd_pct"] >= risk_profile["max_dd_pct"]:
        reasons.append(f"Max DD reached: {account_state['total_dd_pct']:.1f}%")
    
    # 3. Max Open Trades
    if account_state["open_trades"] >= risk_profile["max_open_trades"]:
        reasons.append(f"Max open trades: {account_state['open_trades']}")
    
    # 4. Confidence threshold
    if decision["confidence"] < risk_profile["min_confidence"]:
        reasons.append(f"Confidence too low: {decision['confidence']}")
    
    # 5. R:R ratio
    if decision["action"] != "SKIP":
        entry = decision["entry"]
        sl = decision["sl"]
        tp1 = decision["tp1"]
        rr = abs(tp1 - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
        if rr < risk_profile["min_rr_ratio"]:
            reasons.append(f"R:R too low: {rr:.2f} (min {risk_profile['min_rr_ratio']})")
    
    # 6. News flag
    if decision.get("news_flag") or account_state.get("news_active"):
        reasons.append("High-impact news event active")
    
    # 7. Blocked conditions
    if decision["chart_condition"] in risk_profile.get("blocked_conditions", []):
        reasons.append(f"Condition blocked by user: {decision['chart_condition']}")
    
    approved = len(reasons) == 0
    
    return {
        "approved": approved,
        "reason": " | ".join(reasons) if reasons else "All checks passed",
        "adjusted_lot": lot if approved else 0.0,
        "blocked_condition": decision["chart_condition"] if not approved else ""
    }
```

---

#### G4a — Explain & Notify Agent
**ไฟล์:** `notify.py`
**เรียกบ่อย:** ~10–15 ครั้ง/วัน | ~120 tokens/ครั้ง

**Prompt:**
```
แปลง trade signal JSON เป็นข้อความ LINE ภาษาไทยกระชับ 4–5 บรรทัด
ระบุ: Condition, Pattern, ทิศทาง, ราคา Entry/SL/TP, เหตุผลสั้นๆ
ไม่ต้องอธิบายยาว — trader อ่านแล้วตัดสินใจได้ทันที
ใช้ emoji เหมาะสม: 🟢 BUY 🔴 SELL ⏭ SKIP
```

**Output Format:**
```
📊 Tra(i)der Signal
──────────────────────────
🟢 BUY  |  {condition} + {pattern}
Entry: {entry}  |  Confidence: {confidence*100:.0f}%
TP1: {tp1}  TP2: {tp2}  TP3: {tp3}
SL: {sl}  |  Lot: {lot}
──────────────────────────
เหตุผล: {reason_thai}
H1: {h1_trend}  |  Session: {session}
```

**LINE API call:**
```python
import requests

def send_line_notify(message: str, token: str) -> bool:
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"message": f"\n{message}"}
    
    resp = requests.post(url, headers=headers, data=payload)
    return resp.status_code == 200
```

---

#### G4b — Sheets Logger
**ไฟล์:** `sheets_logger.py`

```python
import gspread
from google.oauth2.service_account import Credentials

def log_trade(decision: dict, guardian: dict, world_state: dict,
              simulated_result: str = "PENDING", pnl_if_executed: float = 0.0):
    """Append 1 row ไปยัง Google Sheets"""
    
    gc = gspread.authorize(get_credentials())
    sh = gc.open(SHEET_NAME)
    ws = sh.worksheet("Trade Log")
    
    trade_id = generate_trade_id()
    
    row = [
        trade_id,                           # A: trade_id
        world_state["timestamp"],           # B: open_time
        decision["chart_condition"],        # C: chart_condition
        decision["pattern"],                # D: pattern
        decision["action"],                 # E: action
        decision.get("entry", 0),           # F: entry_price
        decision.get("sl", 0),              # G: sl_price
        decision.get("tp1", 0),             # H: tp1_price
        decision.get("tp2", 0),             # I: tp2_price
        decision.get("tp3", 0),             # J: tp3_price
        guardian.get("adjusted_lot", 0),    # K: lot_size
        decision["confidence"],             # L: confidence
        world_state["rsi"],                 # M: rsi_at_entry
        world_state["h1_trend"],            # N: h1_trend
        world_state["session"],             # O: session
        simulated_result,                   # P: simulated_result ← KEY
        pnl_if_executed,                    # Q: pnl_if_executed
        True,                               # R: line_sent
        "",                                 # S: close_reason (update later)
        0,                                  # T: duration_min (update later)
    ]
    
    ws.append_row(row)
    return trade_id
```

---

#### G5 — Learning Agent (Weekly)
**ไฟล์:** `weekly_report.py`
**เรียกบ่อย:** 1 ครั้ง/สัปดาห์ | ~2,000 tokens

**Prompt:**
```
คุณคือ Trading Performance Analyst

วิเคราะห์ trade log 7 วันที่ผ่านมาและสรุปผล:

1. Win rate รวม และ แยกตาม Condition (A1–A6)
2. RSI zone ไหนให้ผลดีที่สุด/แย่ที่สุด
3. Session ไหน (Asia/London/NY) win rate สูงสุด
4. Pattern ไหน (B1/B2/B3) ควร pause ชั่วคราว (win rate < 50%)
5. ข้อเสนอปรับ threshold (RSI, S/R buffer, wick ratio) พร้อมเหตุผลจากข้อมูล

ตอบเป็นภาษาไทย กระชับ อ่านเข้าใจง่าย
```

---

### File Structure Phase I

```
traider-phase1/
├── main.py                     # Entry point — main loop ทุก M5
├── config.py                   # API keys, risk profile, paths
├── strategy/
│   └── XAUUSD_Strategy_v4.md  # Source of Truth (read-only)
├── agents/
│   ├── g1_signal_logic.py      # G1: Market Scanning
│   ├── g2_quant_analysis.py    # G2: Quantitative Analysis
│   ├── g3_claude_decision.py   # G3a: Decision (Claude API)
│   ├── g3_money_management.py  # G3b: Lot calculation
│   ├── g3_risk_gate.py         # G3c: Guardian
│   ├── g4_notify.py            # G4a: LINE notification
│   ├── g4_sheets_logger.py     # G4b: Google Sheets
│   └── g5_weekly_report.py     # G5: Learning agent
├── utils/
│   ├── mt5_connector.py        # MT5 data feed
│   ├── sr_detector.py          # S/R swing level detection
│   └── simulated_result.py     # คำนวณ simulated WIN/LOSS
└── requirements.txt
```

---

### Main Loop

```python
# main.py
import time
import schedule
from agents import g1, g2, g3, g4, g5
from utils.mt5_connector import get_latest_candles
from config import RISK_PROFILE, ACCOUNT_STATE

def on_m5_close():
    """รันทุก M5 candle close"""
    
    # ดึงข้อมูลจาก MT5
    data = get_latest_candles(m5_count=80, h1_count=20)
    
    # G1: Scan
    world_state = g1.scan_conditions(data)
    if world_state is None:
        return  # ไม่มี candidate — รอ candle ถัดไป
    
    # G2: Analyze
    confidence_data = g2.calculate_confidence(world_state)
    if not confidence_data["filter_pass"]:
        return  # confidence ต่ำกว่า 0.70
    
    # G3a: Decision (Claude)
    strategy_md = open("strategy/XAUUSD_Strategy_v4.md").read()
    decision = g3.get_decision(world_state, confidence_data, strategy_md)
    
    if decision["action"] == "SKIP":
        return  # Claude ตัดสินใจ SKIP
    
    # G3b: Money Management
    lot = g3.calculate_lot(decision, ACCOUNT_STATE, RISK_PROFILE)
    
    # G3c: Guardian
    guardian = g3.guardian_check(decision, lot, ACCOUNT_STATE, RISK_PROFILE)
    
    if not guardian["approved"]:
        print(f"Guardian blocked: {guardian['reason']}")
        return
    
    # G4a: Notify
    line_token = config.LINE_TOKEN
    message = g4.format_line_message(decision, guardian, world_state)
    sent = g4.send_line_notify(message, line_token)
    
    # G4b: Log (Simulated)
    trade_id = g4.log_trade(decision, guardian, world_state, line_sent=sent)
    
    print(f"Signal logged: {trade_id} | {decision['action']} @ {decision['entry']}")

def on_weekly():
    """รันทุกวันอาทิตย์ 08:00 UTC"""
    report = g5.generate_weekly_report()
    g4.send_line_notify(report, config.LINE_TOKEN)

# Schedule
schedule.every(5).minutes.do(on_m5_close)
schedule.every().sunday.at("08:00").do(on_weekly)

if __name__ == "__main__":
    print("Tra(i)der Phase I — Started")
    while True:
        schedule.run_pending()
        time.sleep(1)
```

---

### Simulated Result Calculation

```python
# utils/simulated_result.py

def calculate_simulated_result(
    action: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    lot: float,
    subsequent_candles: list  # candles หลัง signal
) -> tuple[str, float]:
    """
    คำนวณ WIN/LOSS/BE โดยไม่ execute จริง
    Returns: (result, pnl_usd)
    """
    
    for candle in subsequent_candles:
        high = candle["high"]
        low  = candle["low"]
        
        if action == "BUY":
            if low <= sl:
                pnl = (sl - entry) * lot * 100  # negative
                return "LOSS", round(pnl, 2)
            if high >= tp3:
                pnl = (tp3 - entry) * lot * 100
                return "WIN", round(pnl, 2)
            if high >= tp2:
                pnl = (tp2 - entry) * lot * 100
                return "WIN", round(pnl, 2)
            if high >= tp1:
                pnl = (tp1 - entry) * lot * 100
                return "WIN", round(pnl, 2)
        
        elif action == "SELL":
            if high >= sl:
                pnl = (entry - sl) * lot * 100
                return "LOSS", round(pnl, 2)
            if low <= tp3:
                pnl = (entry - tp3) * lot * 100
                return "WIN", round(pnl, 2)
            if low <= tp2:
                pnl = (entry - tp2) * lot * 100
                return "WIN", round(pnl, 2)
            if low <= tp1:
                pnl = (entry - tp1) * lot * 100
                return "WIN", round(pnl, 2)
    
    return "PENDING", 0.0  # ยังไม่ hit TP หรือ SL
```

---

### Development Checklist Phase I

```
[ ] 1. Setup Python env + install dependencies
      pip install MetaTrader5 anthropic gspread schedule requests

[ ] 2. MT5 Connection
      - Test get_latest_candles() returns M5 + H1 data
      - Verify OHLCV format matches expected structure

[ ] 3. G1 Signal Logic
      - Implement RSI calculation (ta-lib หรือ manual)
      - Implement S/R swing detection (last N highs/lows)
      - Test condition A1–A6 detection ด้วย historical data

[ ] 4. G2 Quant Analysis
      - Implement scoring functions
      - Unit test: confidence ≥ 0.70 ที่ known good setups

[ ] 5. G3 Claude Decision
      - Test Claude API connection
      - Verify JSON output parses correctly
      - Test SKIP cases (RSI neutral, no pattern)

[ ] 6. G3 MM + Guardian
      - Unit test lot calculation formula
      - Unit test guardian blocks correctly

[ ] 7. G4 LINE + Sheets
      - Test LINE Notify token
      - Test Google Sheets append
      - Verify all 20 columns log correctly

[ ] 8. G5 Weekly Report
      - Test อ่าน Sheets 7 วัน
      - Test Claude analyze + format report

[ ] 9. Integration Test
      - Run ด้วย historical data 1 สัปดาห์
      - ตรวจ simulated_result calculation

[ ] 10. Go Live (Simulated Mode)
       - รันจริงแต่ไม่ execute order
       - Monitor 4 สัปดาห์
       - ถ้า Win Rate ≥ 60% → เตรียม Phase II
```

---

### Requirements

```txt
# requirements.txt
MetaTrader5>=5.0.45
anthropic>=0.39.0
gspread>=6.0.0
google-auth>=2.0.0
schedule>=1.2.0
requests>=2.31.0
pandas>=2.0.0
numpy>=1.24.0
python-dotenv>=1.0.0
```

---

### Environment Variables

```env
# .env
ANTHROPIC_API_KEY=sk-ant-...
LINE_NOTIFY_TOKEN=...
GOOGLE_SHEETS_ID=...
GOOGLE_CREDENTIALS_JSON=./credentials.json
MT5_LOGIN=...
MT5_PASSWORD=...
MT5_SERVER=...
ACCOUNT_BALANCE=10000
```

---

*XAUUSD Strategy v4.0 + Phase I Agent Spec | Tra(i)der | Mar 2025*
