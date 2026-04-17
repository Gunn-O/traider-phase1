# Claude Code Instructions v2.1
> คัดลอก Prompt ด้านล่างไปใส่ใน Claude Code เพื่อเริ่ม V2

---

## ไฟล์ที่ต้อง Upload ใน Claude Project

| ไฟล์ | บทบาท |
|------|-------|
| `XAUUSD_AI_Trading_System.md` | Strategy (read-only) |
| `TRAIDER_MASTER_PLAN_v2.1.md` | แผนระบบ — อ่านทุกครั้ง |
| `pattern_detection_spec.md` | Spec G1 — อ่านก่อนเขียน G1 |
| `claude_prompt_template.md` | Template G3a — อ่านก่อนเขียน G3a |
| `CLAUDE_CODE_INSTRUCTIONS_v2.1.md` | ไฟล์นี้ |

---

## Prompt สำหรับ Claude Code

```
อ่าน TRAIDER_MASTER_PLAN_v2.1.md, pattern_detection_spec.md และ claude_prompt_template.md ใน Project ก่อน จากนั้น scan โครงสร้างโปรเจ็คปัจจุบัน

ทำตาม 10 Steps นี้เรียงตามลำดับ:

---

## STEP 1 — FIX g4_position_monitor.py (ด่วนที่สุด)

แก้ไขให้:
- ตรวจ SL/TP hit ทุก candle close (M5 หรือ TF ที่ใช้)
- Logic: ถ้า candle.low ≤ SL (BUY) → LOSS | ถ้า candle.high ≥ TP (BUY) → WIN
- ถ้า hit ทั้ง SL และ TP ในแท่งเดียว → SL hit ก่อน (conservative)
- อัปเดต Sheets ทันทีเมื่อ hit: result, close_price, close_reason, pnl_usd, timestamp_close
- เพิ่ม Trailing SL logic: TP > 3000 pip → เลื่อน SL เมื่อราคาไป > 2000 pip
- Fix Trade ID ให้ไม่ duplicate (ใช้ timestamp microsecond หรือ UUID)
- เพิ่ม logging ทุก action ใน traider.log

ดูโค้ด reference ใน TRAIDER_MASTER_PLAN_v2.1.md Section 7

---

## STEP 2 — ปรับ utils/constants.py

เพิ่ม/แก้:
- CHART_TYPES: uptrend, downtrend, sideway_down, sideway_up, mountain, unclear
- TECHNIQUES: twin_candle, breakout_follow, mai_ruay, support_bounce
- TIMEFRAMES: ['H4', 'H1', 'M30', 'M15', 'M5', 'M1']
- TF_SIZE: {'H4': 6, 'H1': 5, 'M30': 4, 'M15': 3, 'M5': 2, 'M1': 1}
- RISK_CONFIG: ตาม Master Plan Section 2
- ลบ/comment A1-A6 condition names เก่า

---

## STEP 3 — สร้าง agents/g1_pattern_detector.py ใหม่

ใช้ pattern_detection_spec.md เป็น blueprint ทั้งหมด

Functions ที่ต้องมี:
- calc_range(candles) → range dict
- calc_slope_angle(price_start, price_end, candle_start, candle_end, range_usd) → float
- find_swing_points(candles, window=3) → dict
- detect_uptrend(candles, range_data) → dict
- detect_downtrend(candles, range_data) → dict
- detect_sideway(candles, range_data) → dict
- detect_mountain(candles, range_data) → dict
- detect_father_candle(candles, range_data) → dict
- find_twin_candle(candles, search_start, near_price, range_usd) → dict
- detect_breakout_box(candles, range_data, chart_type) → dict
- check_sideway_still_valid(candles, sideway_state, range_data) → dict
- select_best_setup(tf_results) → dict (MTF tiebreak)
- build_world_state(candles_by_tf, selected_tf) → dict

ต้อง scan ทุก TF แล้วเรียก select_best_setup()

---

## STEP 4 — สร้าง agents/g3_claude_decision.py ใหม่

ใช้ claude_prompt_template.md เป็น blueprint

Functions:
- build_system_prompt(strategy_content) → str
- build_user_prompt(world_state, balance, portfolio_state) → str
- format_ohlc_table(candles, tf) → str
- format_twin_candle(twin) → str
- format_father_candle(father) → str
- format_tf_selection_reason(tf_results, selected_tf) → str
- call_claude_decision(world_state, balance, portfolio_state) → dict
- validate_decision(decision, world_state, balance) → dict
- calc_cost(usage) → float

สำคัญ:
- โหลด strategy/XAUUSD_AI_Trading_System.md ทุกครั้ง (ไม่ cache)
- บันทึก LLM log ครบทุก field
- ถ้า JSON parse fail → return SKIP

---

## STEP 5 — ปรับ agents/g3_money_management.py

เปลี่ยนสูตรจาก:
  lot = (balance × 0.015) / (sl_distance × 0.1)

เป็น:
  max_loss = balance × 0.10
  lot_total = max_loss / sl_pip
  lot_per_order = lot_total / suggested_orders

เพิ่ม winrate_test mode: ถ้า flag ใช้ 0.01 lot เสมอ

---

## STEP 6 — ปรับ agents/g3_risk_gate.py

Block conditions (แทนของเดิมทั้งหมด):
1. มี active plan อยู่ (active_plan_id ใน Portfolio State ไม่ว่าง)
2. consecutive_loss >= 3
3. total_loss_pct > 0.30
4. total_loss_pct > 0.50 (block ถาวร ต้อง manual reset)
5. rr_ratio < 1.0
6. news_flag = true
7. r:r ที่ Claude คำนวณมา < 1.0

ลบ: confidence threshold, same-condition check แบบเดิม

---

## STEP 7 — ปรับ agents/g4_sheets_logger.py

Schema ใหม่ตาม Master Plan Section 6:
- เพิ่ม columns: plan_id, order_num, timeframe, lot_total_plan,
  rr_ratio, tp_price, close_price, timestamp_close, trailing_sl,
  human_action, human_agree
- เพิ่ม method: log_plan_open(plan_id, order_num, ...)
- เพิ่ม method: update_order_close(trade_id, result, close_price, ...)
- เพิ่ม method: update_trailing_sl(trade_id, new_sl)
- เพิ่ม method: update_human_action(trade_id, human_action)
- เพิ่ม Sheet "Portfolio State" update real-time

---

## STEP 8 — ปรับ agents/g2_prefilter.py

เปลี่ยน logic จาก "check open trades" เป็น "check active plan":
- ดึง active_plan_id จาก Portfolio State sheet
- ถ้ามี active plan → pre_approved = False, reason = "plan_in_progress"
- ตรวจ loss limits จาก Portfolio State
- ตรวจ news flag
- สร้าง chart_context จาก world_state

---

## STEP 9 — ปรับ main.py

Pipeline ใหม่:
1. Fetch data ทุก 6 TF (H4, H1, M30, M15, M5, M1)
2. G1: detect pattern ทุก TF → select_best_setup()
3. G2: pre-filter + context builder
4. ถ้าไม่ผ่าน → log SKIP reason → จบรอบ
5. G3a: Claude API decision
6. Validate decision
7. G3b: calc lot
8. G3c: Guardian check
9. ถ้าไม่ผ่าน → log block reason → จบรอบ
10. G4a: LINE notify
11. G4b: log plan open (ทุก suggested_orders)
12. G4c: position monitor check existing
13. Update Portfolio State

เพิ่ม flags:
- --simulate (default): paper trading
- --winrate-test: 0.01 lot, no LINE
- --backtest --start YYYY-MM-DD --end YYYY-MM-DD
- --live (Phase II only, raise NotImplementedError)

---

## STEP 10 — สร้าง tests/

สร้างไฟล์ test:

tests/test_pattern_detection.py:
- ทดสอบ detect_uptrend() ด้วย sample OHLC ที่รู้คำตอบ
- ทดสอบ detect_sideway() — กรอบใหญ่เกิน 50% ต้อง return False
- ทดสอบ find_twin_candle() — เงื่อนไข 5% body, 10 pip gap
- ทดสอบ select_best_setup() — MTF tiebreak rules

tests/test_risk_gate.py:
- ทดสอบ block เมื่อมี active plan
- ทดสอบ block เมื่อ consecutive_loss >= 3
- ทดสอบ block เมื่อ R:R < 1.0

tests/test_position_monitor.py:
- ทดสอบ SL hit detection
- ทดสอบ TP hit detection
- ทดสอบ trailing SL calculation

---

## ข้อกำหนดสำคัญ

- อ่าน pattern_detection_spec.md ก่อนเขียน G1 ทุกครั้ง
- อ่าน claude_prompt_template.md ก่อนเขียน G3a ทุกครั้ง
- Strategy MD ใน strategy/ = read-only เสมอ
- ถ้าไม่แน่ใจ path หรือ logic → ถามก่อนเสมอ
- เริ่ม STEP 1 ก่อนเสมอ เพราะ Position Monitor คือ bug ที่ทำให้ data ไม่มีความหมาย
```

---

## ข้อมูลที่ต้องตั้งค่าก่อน Run

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
LINE_CHANNEL_ACCESS_TOKEN=...
SPREADSHEET_ID=...
GOOGLE_CREDENTIALS_PATH=credentials.json
BALANCE=500        # USD
WINRATE_TEST=true  # true ระหว่างทดสอบ
```

## Run Commands

```bash
# Winrate test (แนะนำให้ใช้ก่อน)
python main.py --winrate-test

# Simulate (paper trading)
python main.py --simulate

# Backtest
python main.py --backtest --start 2025-01-01 --end 2025-03-31
```
