# CLAUDE.md — Tra(i)der Phase I v2.1

> **อ่านไฟล์นี้ก่อนทำงานทุกครั้ง — ห้ามข้าม**
> มี 2 Roles: Dev Agent และ Strategy Auditor

---

## ⚠️ Strategy ที่ใช้จริง

| ไฟล์ | สถานะ |
|------|-------|
| `strategy/XAUUSD_AI_Trading_System_v2.1.md` | ✅ **ใช้จริง** — read-only |
| `strategy/XAUUSD_Strategy_v5.md` | ❌ **เลิกใช้แล้ว** — ห้ามอ้างอิง |
| `docs/TRAIDER_MASTER_PLAN_v2.1.md` | ✅ Architecture reference |
| `docs/pattern_detection_spec.md` | ❌ **เลิกใช้แล้ว** — ใช้ Signal Engine แทน |
| `docs/claude_prompt_template.md` | ❌ **เลิกใช้แล้ว** — ใช้ Reviewer Prompt แทน |

---

## ⚠️ V4.20 Architecture Change (2026-04-23)

**Signal Engine Integration:**
- **Signal Engine:** `utils/xauusd_signal.py` + `utils/swing_v414.py`
  - คำนวณ Entry/SL/TP/Lot ทั้งหมด
  - **ห้ามแก้ไข** xauusd_signal.py และ swing_v414.py
  - Single TF: M5 only
  
- **G1 Pattern Detector:** `agents/g1_pattern_detector.py`
  - ❌ **DEPRECATED** — เก็บไว้เพื่อ backward compatibility
  - ใช้ Signal Engine แทน

**Claude Role Change:**
- **Before:** Decision Maker (คำนวณ Entry/SL/TP)
- **After:** Reviewer (approve/reject signal เท่านั้น)

- **System Prompt:** `strategy/XAUUSD_System_Prompt_Reviewer.md`
  - ✅ **ใช้ตอนนี้** — สั้นกว่า V43 มาก (cache ดีกว่า)
  - ❌ ไม่ใช้ `XAUUSD_System_PromptV43.md` อีกต่อไป
  - max_tokens: 300 (ลดจาก 2048)

- **Reference Docs (อ่านอย่างเดียว):**
  - `strategy/XAUUSD_AI_Trading_SystemV43.md` — เก็บเป็น reference
  - `strategy/XAUUSD_System_PromptV43.md` — เก็บเป็น reference
  - **ไม่ส่งให้ Claude อีกต่อไป**

---

## 🔧 Role 1: Dev Agent

รับผิดชอบ: เขียนโค้ด, แก้ bug, implement feature ตาม Master Plan v2.1

### กฎ Dev:
1. **Strategy MD อ่านอย่างเดียว** — ห้าม hardcode rule ใน Python แทน MD
2. **Claude API ทุก trade** — ห้ามใช้ mock/rule-based ใน production pipeline
3. **RSI เป็น metadata เท่านั้น** — ไม่ใช้ตัดสิน BUY/SELL
4. **Lot = max_loss_usd / sl_pip** — ไม่ใช่ balance × 1.5%
5. **Risk 10% per plan** — ไม่ใช่ 1.5%
6. **1 แผนต่อครั้ง** — ห้ามเปิดแผนใหม่ถ้ายังมีแผนเปิดอยู่
7. **Timestamp = candle time** — ห้ามใช้ datetime.now() ใน backtest
8. **Technique log** มาจาก decision['technique'] ไม่ใช่ world_state

### Architecture Pipeline (V4.20):
```
Market Data (M5 Single TF)
    ↓
Signal Engine: xauusd_signal.py
    Entry/SL/TP/Lot คำนวณเสร็จ → Signal object
    ↓ world_state + signal
G2: Pre-filter
    ตรวจ signal validity, R:R ≥ 1.0, duplicate
    ↓ pre_approved
G3a: Claude API Reviewer (max_tokens=300)
    system=[reviewer_prompt cached]
    → APPROVE/REJECT (ไม่คำนวณ Entry/SL/TP)
    ↓ APPROVE → ใช้ค่าจาก Signal Engine
G3b: Lot adjustment (optional - ตอนนี้ใช้จาก Signal Engine)
G3c: Guardian (R:R ≥ 1.0, consecutive_loss, plan active)
    ↓
G4a: LINE Notify
G4b: Sheets Log (candle timestamp ไม่ใช่ datetime.now())
G4c: Position Monitor (ตรวจทุก candle close)
```

**OLD Pipeline (DEPRECATED):**
```
G1 Pattern Detector → G2 → G3a Decision Maker → G3b Lot → G3c Guardian → G4
```

### Risk Config (v2.1):
```python
risk_per_plan_pct = 0.10       # 10% ไม่ใช่ 1.5%
min_rr_ratio = 1.0             # ไม่ใช่ 1.2 หรือ 1.5
max_consecutive_loss = 3
max_loss_30pct = 0.30
max_loss_50pct = 0.50
min_chart_quality = 0.50
trailing_sl_min_tp = 3000      # pip
winrate_test_lot = 0.01
```

---

## 📊 Role 2: Strategy Auditor

รับผิดชอบ: ตรวจโค้ดว่าสอดคล้องกับ Strategy MD ก่อน run ทุกครั้ง

### เรียกใช้เมื่อ:
- Dev เขียน/แก้โค้ดเสร็จ
- ก่อน run backtest หรือ simulate
- เมื่อ SKIP rate สูงผิดปกติ (> 90%)
- เมื่อ cost per call สูงผิดปกติ (> $0.025)

### Checklist:

**G1 Pattern Detector — agents/g1_pattern_detector.py:**
- [ ] Slope วัดจาก first_swing_low → last_swing_high (ไม่ใช่ระหว่าง 2 แท่ง)
- [ ] Slope threshold: 43-52° (±3° tolerance)
- [ ] แท่งคู่: body ≥ 5% Range AND gap ≤ 10 pip (0.10 USD)
- [ ] แท่งพ่อ: เคลื่อน 60-100% Range ใน 1-5 แท่ง (เนื้อเทียนเท่านั้น ไม่รวมไส้)
- [ ] Sideway: กรอบ ≤ 50% Range ถึงจะเป็น sideway
- [ ] Mountain: tolerance ฐาน ≤ 5% Range หรือ 300 pip
- [ ] Breakout box (ตามเจ้า): ≤ 35% Range
- [ ] Single TF: ใช้ M5 เท่านั้น (config: TIMEFRAMES = ['M5'])
- [ ] SKIP เมื่อ M5 chart = unclear หรือ quality < 0.5

**G2 Pre-filter — agents/g2_prefilter.py:**
- [ ] Block ก่อน Claude: uptrend/downtrend แต่ไม่มี twin_candle AND ไม่มี breakout_box
- [ ] Block ก่อน Claude: mountain แต่ tolerance_ok = False
- [ ] Block ก่อน Claude: มี active_plan_id อยู่แล้ว
- [ ] Block ก่อน Claude: consecutive_loss ≥ 3
- [ ] ไม่ block เพราะ RSI zone (RSI เป็นแค่ metadata)

**G3a Claude Decision — agents/g3_claude_decision.py:**
- [ ] system prompt ใช้ list format พร้อม cache_control (ไม่ใช่ string)
- [ ] strategy_content อยู่ใน block แรก พร้อม `"cache_control": {"type": "ephemeral"}`
- [ ] llm_log บันทึก cache_read_tokens และ cache_hit
- [ ] reason ใน output format ≤ 80 ตัวอักษร
- [ ] ไม่มีการเรียก Claude เมื่อ G2 block แล้ว

**G3b Money Management — agents/g3_money_management.py:**
- [ ] `lot = (balance × 0.10) / sl_pip` — ไม่ใช่ balance × 0.015
- [ ] winrate_test mode: lot = 0.01 เสมอ

**G3c Guardian — agents/g3_risk_gate.py:**
- [ ] R:R ≥ 1.0 (ไม่ใช่ 1.2 หรือ 1.5)
- [ ] Block ถ้า active_plan_id ไม่ว่าง
- [ ] Block ถ้า consecutive_loss ≥ 3
- [ ] Block ถ้า total_loss_pct > 0.30
- [ ] ไม่มี confidence threshold (เลิกใช้แล้ว)

**G4 Position Monitor — agents/g4_position_monitor.py:**
- [ ] check_and_update() ถูกเรียกใน run_once() เป็น Step 0
- [ ] check_and_update() ถูกเรียกทุก candle ใน backtest loop
- [ ] generate_plan_id() รับ candle_time parameter
- [ ] generate_trade_id() รับ candle_time parameter
- [ ] ไม่มี datetime.now() ใน backtest path
- [ ] _update_portfolio_after_closes() auto-clear active_plan_id เมื่อปิดหมด

**G4 Sheets Logger — agents/g4_sheets_logger.py:**
- [ ] timestamp_open ใช้ candle_time ไม่ใช่ datetime.now()
- [ ] technique มาจาก decision['technique'] ไม่ใช่ world_state['technique_candidate']
- [ ] reason ไม่ถูก truncate (prompt บังคับ ≤ 80 ตัวแล้ว)

**Backtest — main.py:**
- [ ] วนลูปทุก M5 candle ไม่ใช่ทุกวัน
- [ ] ส่ง candle_time เข้า pipeline ทุก step
- [ ] monitor_positions() เรียกทุก candle (ไม่ว่าจะมี active plan หรือไม่)
- [ ] **CRITICAL:** orders ต้องมี required fields ก่อนส่ง PositionMonitor:
  ```python
  order['plan_id'] = plan_id
  order['result'] = 'PENDING'
  order['entry_price'] = order['entry']  # alias
  order['sl_price'] = order['sl']
  order['tp_price'] = order['tp']
  order['lot_size'] = order['lot']
  ```

### Output Format ของ Auditor:

```
## Strategy Audit Report — [วันที่]

### ✅ PASS
- [รายการที่ผ่าน]

### ❌ FAIL
- [ไฟล์:บรรทัด] — [สิ่งที่พบ] ≠ [สิ่งที่ควรเป็น] (Strategy ref: section X.X)

### ⚠️ WARN
- [รายการที่น่าสงสัย]

### 💰 Cost Check
- Cost per call: $X.XXX (target: < $0.010 หลัง cache)
- Cache hit rate: XX% (target: > 80%)
- G2 block rate: XX% (target: > 70% เพื่อลด Claude calls)

### Recommendation
[ ] Run ได้เลย
[ ] แก้ก่อน: [รายการ]
```

---

## วิธีใช้ 2 Roles

```bash
# ต้องการแก้โค้ด
"@Dev แก้ g2_prefilter.py เพิ่ม Setup Pre-check..."

# ต้องการตรวจก่อน run
"@Auditor ตรวจโค้ดที่แก้ล่าสุดก่อน run backtest"

# ต้องการทั้งคู่ (แก้แล้วตรวจทันที)
"@Dev แก้ X แล้ว @Auditor ตรวจก่อน run"

# SKIP rate สูงผิดปกติ
"@Auditor SKIP 95% ใน backtest วิเคราะห์ว่า filter ไหนเข้มเกินไป"

# Cost สูงผิดปกติ
"@Auditor cost $0.018/call แสดงว่า cache ไม่ทำงาน หาสาเหตุ"
```

---

## Environment Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**.env สำคัญ:**
```
ANTHROPIC_API_KEY=sk-ant-...
LINE_NOTIFY_ENABLED=false      # ปิดระหว่าง backtest
SHEETS_ENABLED=false           # ปิดระหว่าง backtest
DATA_MODE=backtest
ACCOUNT_BALANCE=500
WINRATE_TEST=true              # 0.01 lot ทุกไม้
```

**Run commands:**
```bash
python main.py --winrate-test              # Winrate test (0.01 lot)
python main.py --simulate                  # Paper trading
python main.py --backtest --start 2026-03-01 --end 2026-03-07
```

---

## สิ่งที่ห้ามทำ

- ❌ อ้างอิง `XAUUSD_Strategy_v5.md` (เลิกใช้แล้ว)
- ❌ ใช้ confidence threshold ≥ 0.70 (เลิกใช้แล้ว)
- ❌ ใช้ R:R ≥ 1.2 หรือ 1.5 (ปัจจุบันใช้ 1.0)
- ❌ ใช้ lot = balance × 1.5% (ปัจจุบันใช้ 10% / sl_pip)
- ❌ เรียก Claude ทุก candle โดยไม่มี G2 block ก่อน
- ❌ ใช้ datetime.now() ใน backtest path
- ❌ ใช้ mock agent ใน production
- ❌ Implement Phase II feature ระหว่าง Phase I
