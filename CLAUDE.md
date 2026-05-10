# CLAUDE.md — Tra(i)der Phase I v2.1 + Phase II

> **อ่านไฟล์นี้ก่อนทำงานทุกครั้ง — ห้ามข้าม**
> มี 2 Roles: Dev Agent และ Strategy Auditor
> **Phase II Focus:** Backtest, Simulation, Live Trading

---

## ⚠️ ไฟล์ที่ใช้งาน (Phase II)

### 🎯 Strategy Reference Notebooks (Source of Truth — 3 ไฟล์)

| Notebook | Strategy | Python |
|----------|----------|--------|
| `strategy/XAUUSD_Backtest_Mountain.md` | **ภูเขา** (Mountain v4.61) | `strategies/mountain.py` |
| `strategy/XAUUSD_Backtest_MaiRuay.md` | **ไม้รวย** (Father/Mother) | `strategies/mai_ruay.py` |
| `strategy/XAUUSD_Uptrend_Downtrend_Scanner_v3.4.md` | **Uptrend/Downtrend Scanner v3.4** | `strategies/uptrend_downtrend_scanner.py` (+ detectors ใน `utils/xauusd_signal.py`) |

**กฎเหล็ก:** Python ต้องตรงกับ **engine code ใน notebook** เสมอ (markdown header ใน notebook อาจล้าสมัย — engine code คือ source of truth)
**Strategies ทั้ง 3 ทำงานแยกกัน** — ไม่มีการ share state ข้าม strategy

### Supporting Files

| ไฟล์ | สถานะ |
|------|-------|
| `strategy/XAUUSD_System_Prompt_Reviewer.md` | ✅ Claude Reviewer (SIM/LIVE only) |
| `docs/TRAIDER_MASTER_PLAN_v2.1.md` | ✅ Architecture reference |
| `utils/xauusd_signal.py` | ✅ Signal helpers + Scanner v3.4 detectors |
| `utils/swing_v414.py` | ✅ Swing detection (pair_thresh = max(R55×1%, 100pip)) |
| `config/strategies.json` | ✅ Pattern toggle + per-TF allowlist (4 active patterns = 3 strategies) |

---

## ⚠️ V4.20 Architecture Change (2026-04-23, refreshed 2026-05-11)

**Signal Engine Integration:**
- **Strategy modules:** `strategies/mountain.py`, `strategies/mai_ruay.py`, `strategies/uptrend_downtrend_scanner.py`
  - คำนวณ Entry/SL/TP/Lot ทั้งหมด — ตรงกับ engine code ใน notebook 3 ไฟล์
  - แก้ได้เมื่อ notebook engine update (อย่าแก้ตามใจ — ต้อง diff กับ notebook ก่อน)
- **Signal helpers:** `utils/xauusd_signal.py` + `utils/swing_v414.py`
  - แก้ได้เฉพาะเพื่อ sync กับ notebook 3 ไฟล์ (เช่น swing_v414 pair_thresh 0.5%→1%)
  - ห้ามแก้เพื่อ "ปรับแต่งเอง" นอก spec ของ notebook
- **Single TF:** M5 (MaiRuay เปิด M1/M15/M30 ด้วย; Mountain เปิด M1+M5)
- Phase II: ใช้ใน BACKTEST, SIM, LIVE ทั้งหมด

**Claude Role (Phase II):**
- **BACKTEST mode:** ไม่ใช้ Claude เลย → AUTO_APPROVE
- **SIM/LIVE mode:** Claude = Reviewer (approve/reject signal เท่านั้น)
  - System Prompt: `strategy/XAUUSD_System_Prompt_Reviewer.md`
  - max_tokens: 300
  - เน้น cache hit rate > 80%

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

**Phase II Mode Switching:**
- **BACKTEST mode (`--backtest --no-ai`):** Signal Engine → G2 → AUTO_APPROVE → Execute → Log (ไม่เรียก Claude)
- **SIM/LIVE mode:** Signal Engine → G2 → Claude Reviewer → Execute → Log → Notify

```
Market Data (M5 Single TF, MaiRuay M1/M5/M15/M30, Mountain M1/M5)
    ↓
Signal Engine: utils/signal_engine.py — รัน 3 strategy แบบ parallel
    MOUNTAIN          → strategies/mountain.py             (ภูเขา v4.61)
    MAI_RUAY          → strategies/mai_ruay.py             (พ่อ-แม่)
    UPTREND_SCANNER   ┐
                      ├→ strategies/uptrend_downtrend_scanner.py (v3.4)
    DOWNTREND_SCANNER ┘
    เลือก best by R:R → Signal object (Entry/SL/TP/Lot คำนวณเสร็จ)
    ↓ world_state + signal
G2: Pre-filter
    ตรวจ signal validity, R:R ≥ 1.0, duplicate
    ↓ pre_approved
G3a: [BACKTEST: AUTO_APPROVE] / [SIM/LIVE: Claude Reviewer]
    BACKTEST: bypass Claude ทั้งหมด
    SIM/LIVE: system=[reviewer_prompt cached], max_tokens=300
    → APPROVE/REJECT (ไม่คำนวณ Entry/SL/TP)
    ↓ APPROVE → ใช้ค่าจาก Signal Engine
G3b: Lot adjustment (optional - ตอนนี้ใช้จาก Signal Engine)
G3c: Guardian (R:R ≥ 1.0, consecutive_loss, plan active)
    ↓
G4a: LINE Notify (SIM/LIVE only)
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

### Checklist (Phase II):

**Strategy Modules — strategies/{mountain,mai_ruay,uptrend_downtrend_scanner}.py:**
- [ ] **ตรวจ diff กับ notebook engine** ก่อนทุกครั้งที่แก้ — ถือว่า notebook = source of truth
- [ ] Mountain: pair_thresh = max(R55×1%, 100pip), buffer 5%×height, TP3=80%×height, SL=60%×height (notebook v4.61)
- [ ] MaiRuay: MAX_FATHER=8, father body 60-100%R55, mother body 4-30% ของพ่อ (engine; markdown header ของ notebook ระบุไม่ตรง — ใช้ engine)
- [ ] Scanner: C1≥60%, C2≥55% (5bars), C3≤30%, C4≥25%, C5≤30%, C6≤40% (start 5 bars)
- [ ] ทั้ง 3 strategy ทำงานแยกกัน — ไม่มี state แชร์
- [ ] Output: Signal object พร้อม entry/sl/tp/lot/rr

**Signal Helpers — utils/xauusd_signal.py + utils/swing_v414.py:**
- [ ] แก้ได้เฉพาะเพื่อ sync กับ notebook 3 ไฟล์ (เช่น swing pair_thresh)
- [ ] ห้ามแก้เพื่อ "ปรับแต่งเอง" นอก spec notebook
- [ ] Workflow: TradingView/Colab → backtest match > 90% → port to Python → run audit

**G2 Pre-filter — agents/g2_prefilter.py:**
- [ ] Block ก่อน G3: มี active_plan_id อยู่แล้ว (1 plan ต่อครั้ง)
- [ ] Block ก่อน G3: consecutive_loss ≥ 3
- [ ] Block ก่อน G3: R:R < 1.0
- [ ] **Block ก่อน G3: duplicate signal** (entry ใหม่ ± 50pip ของ active plan)
- [ ] Block rate > 70% (เพื่อลด Claude calls ใน SIM/LIVE)

**G3 Claude Reviewer — agents/g3_claude_reviewer.py (ถ้ามี):**
- [ ] **BACKTEST mode:** bypass Claude ทั้งหมด → AUTO_APPROVE
- [ ] **SIM/LIVE mode:** เรียก Claude API เป็น Reviewer
- [ ] System prompt: `XAUUSD_System_Prompt_Reviewer.md`
- [ ] system prompt ใช้ list format พร้อม cache_control
- [ ] reviewer_prompt อยู่ใน block แรก พร้อม `"cache_control": {"type": "ephemeral"}`
- [ ] max_tokens: 300 (ไม่ใช่ 2048)
- [ ] llm_log บันทึก cache_read_tokens และ cache_hit
- [ ] reason ≤ 80 ตัวอักษร
- [ ] ไม่มีการเรียก Claude เมื่อ G2 block แล้ว
- [ ] **ไม่คำนวณ Entry/SL/TP** (ใช้จาก Signal Engine)

**G3 Guardian — agents/g3_risk_gate.py:**
- [ ] R:R ≥ 1.0 (ไม่ใช่ 1.2 หรือ 1.5)
- [ ] Block ถ้า active_plan_id ไม่ว่าง (double-check หลัง G2)
- [ ] Block ถ้า consecutive_loss ≥ 3
- [ ] Block ถ้า total_loss_pct > 0.30
- [ ] Block ถ้า total_loss_pct > 0.50 (circuit breaker)
- [ ] ไม่มี confidence threshold (เลิกใช้แล้ว)
- [ ] **Lot ใช้จาก Signal Engine** ไม่ปรับแล้ว (เว้นแต่ winrate_test = 0.01)

**G4 Position Monitor — agents/g4_position_monitor.py:**
- [ ] check_and_update() ถูกเรียกทุก candle close ใน backtest/sim/live loop
- [ ] check SL/TP hit ทุก candle (ไม่ใช่ทุกวัน)
- [ ] generate_plan_id() รับ candle_time parameter
- [ ] generate_trade_id() รับ candle_time parameter
- [ ] **ไม่มี datetime.now() ใน backtest path** (ใช้ candle_time เสมอ)
- [ ] _update_portfolio_after_closes() auto-clear active_plan_id เมื่อปิดหมด
- [ ] PENDING orders ต้องมี required fields: plan_id, result, entry_price, sl_price, tp_price, lot_size

**G4 Sheets Logger — agents/g4_sheets_logger.py:**
- [ ] timestamp_open ใช้ candle_time ไม่ใช่ datetime.now()
- [ ] CSV header ตรงกับ schema ที่กำหนด
- [ ] technique/setup มาจาก signal object
- [ ] reason ไม่ถูก truncate (≤ 80 ตัวอักษร)

**G4 Notify — agents/g4_notify.py:**
- [ ] ทำงานเฉพาะ SIM/LIVE mode (ปิดใน BACKTEST)
- [ ] LINE_NOTIFY_ENABLED=false ระหว่าง backtest

**main.py — Backtest/Simulation/Live:**
- [ ] **Mode switching:**
  - BACKTEST: `--backtest --no-ai` → bypass Claude → AUTO_APPROVE
  - SIM: `--simulate` → Claude Reviewer
  - LIVE: `--live` → Claude Reviewer + confirm 2 ครั้ง
- [ ] วนลูปทุก M5 candle ไม่ใช่ทุกวัน
- [ ] ส่ง candle_time เข้า pipeline ทุก step
- [ ] monitor_positions() เรียกทุก candle (ไม่ว่าจะมี active plan หรือไม่)
- [ ] **CRITICAL:** orders ต้องมี required fields ก่อนส่ง PositionMonitor:
  ```python
  order['plan_id'] = plan_id
  order['result'] = 'PENDING'
  order['entry_price'] = order['entry']
  order['sl_price'] = order['sl']
  order['tp_price'] = order['tp']
  order['lot_size'] = order['lot']
  ```
- [ ] CSV output header ตรงกับ data schema
- [ ] host = 127.0.0.1 เสมอ (ไม่ใช่ 0.0.0.0)

### Output Format ของ Auditor:

```
## Strategy Audit Report — [วันที่] [ไฟล์ที่ตรวจ]

### ✅ PASS
- [รายการที่ผ่าน]

### ❌ FAIL — ห้าม run จนกว่าจะแก้
- [ไฟล์:บรรทัด] พบ [X] ควรเป็น [Y]
  ref: CLAUDE.md > [section]

### ⚠️ WARN — ควรแก้แต่ไม่ block
- [รายการที่น่าสงสัย]

### 💰 Cost & Performance (SIM/LIVE เท่านั้น)
- Cost/call: $X.XXX  (target < $0.010)
- Cache hit: XX%     (target > 80%)
- G2 block rate: XX% (target > 70%)
- SKIP rate: XX%     (target < 30%)

### 🚦 Verdict
[ ] RUN ได้เลย
[ ] แก้ก่อน: [รายการ FAIL]
```

---

## วิธีใช้ 2 Roles — Phase II

### Pattern บังคับ: @Dev → @Auditor เสมอ
ทุกครั้งที่ @Dev แก้โค้ดเสร็จ ต้องตาม @Auditor ทันที
ห้าม run backtest หรือ simulate ก่อน Auditor ผ่าน

### Template คำสั่งมาตรฐาน

```bash
# แก้ bug
"@Dev แก้ [ไฟล์] เพราะ [ปัญหา]
@Auditor ตรวจทันทีหลัง Dev เสร็จ ก่อน run"

# เพิ่ม feature
"@Dev implement [feature] ใน [ไฟล์] ตาม spec [section]
@Auditor ตรวจ checklist ที่เกี่ยวข้องกับ [feature] นี้"

# แก้แล้ว run backtest
"@Dev แก้ [X] แล้ว
@Auditor ตรวจก่อน run backtest --start [วัน] --end [วัน]"

# กรณีเร่งด่วน (ยังต้องมี Auditor)
"@Dev แก้ [X] ด่วน
@Auditor ตรวจเฉพาะ [ไฟล์ที่แก้] ก็พอ ไม่ต้องตรวจทั้งหมด"
```

### ตัวอย่างคำสั่ง Phase II

```bash
# Bug: Pending ไม่ถูก close
"@Dev แก้ g4_position_monitor.py ให้ check_and_update()
รันทุก candle close ทั้งใน backtest loop และ simulate loop
@Auditor ตรวจ position monitor checklist และ main.py loop order"

# Bug: Duplicate signal
"@Dev แก้ g2_prefilter.py เพิ่ม duplicate check
block ถ้า entry ใหม่อยู่ใน ±50pip ของ active plan
@Auditor ตรวจ G2 checklist ทั้งหมด"

# Bug: CSV header ไม่ตรง
"@Dev แก้ backtest output ให้ header ตรงกับ data
schema: trade_id, plan_id, timestamp, timeframe, pattern,
        setup, action, entry, sl, tp, lot, rr, confidence,
        rsi, h1_trend, session, reason, obstacles,
        api_cost, latency, result, pnl_usd, close_reason,
        close_price, close_time, open_sl
@Auditor ตรวจ Sheets Logger และ backtest output format"

# Backtest ไม่ผ่าน AI (Phase II)
"@Dev ตรวจสอบว่า backtest mode ใช้ --no-ai flag แล้ว
bypass G3 Reviewer ทั้งหมด ใช้ AUTO_APPROVE แทน
@Auditor ตรวจ main.py ว่า mode switching ถูกต้อง"

# SKIP rate ผิดปกติ
"@Auditor วิเคราะห์ผล backtest นี้:
SKIP rate = [X]% ปกติควรไม่เกิน 30%
ระบุว่า filter ไหนใน G2 เข้มเกินไป"

# Cost ผิดปกติ (SIM mode)
"@Auditor cost per call = $[X] สูงกว่า target $0.010
ตรวจ cache hit rate และ system prompt length"
```

---

## 🎯 Phase II Specifics

### AI ใช้ทำอะไรได้บ้าง

✅ **Reviewer ใน SIM/LIVE** (sanity check เท่านั้น)
✅ **Weekly Strategist:** วิเคราะห์ผล แนะนำ parameter
✅ **Monthly Evolver:** propose strategy update (human approve)
❌ **ไม่ใช้ใน Backtest loop**
❌ **ไม่คำนวณ Entry/SL/TP**

### Backtest Bug Fix Priority

1. **Header alignment** — ตรวจ CSV output ให้ตรง schema
2. **Pending resolution** — position_monitor ต้อง close ทุก candle
3. **Duplicate block** — G2 ตรวจ entry ± 50pip ไม่เปิดซ้ำ

### TradingView → Python Workflow

1. พัฒนา/ทดสอบ logic ใน Pinescript (TradingView)
2. แปลง rule เป็น Python ใน xauusd_signal.py
3. รัน backtest Python เทียบ TradingView ผล
4. ถ้า match > 90% → promote to SIM

### กฎเหล็ก Phase II

1. **3 Strategy เท่านั้น:** Mountain, MaiRuay, Uptrend/Downtrend Scanner (อิง 3 notebook ใน `strategy/`)
2. ทุก strategy ทำงานแยกกัน — ห้าม share state ข้าม strategy
3. แก้ Python strategy/helpers ได้เฉพาะเพื่อ sync กับ notebook engine code (ห้ามปรับเอง)
4. BACKTEST mode ไม่เรียก Claude API เลย
5. Claude Reviewer ใช้เฉพาะ SIM/LIVE mode
6. System Prompt = `strategy/XAUUSD_System_Prompt_Reviewer.md`
7. Timestamp = candle time เสมอ (ไม่ใช่ datetime.now())
8. G2 ต้อง block duplicate plan (same entry ± 50pip)
9. Position monitor ต้อง close position ทุก candle close
10. host = 127.0.0.1 เสมอ

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
ACCOUNT_BALANCE=500
WINRATE_TEST=true              # 0.01 lot ทุกไม้
```

**Run commands (Phase II):**
```bash
# Backtest (ไม่ใช้ AI)
python main.py --backtest --start 2026-03-01 --end 2026-03-07 --no-ai

# Winrate test (0.01 lot, ไม่ใช้ AI)
python main.py --winrate-test --no-ai

# Simulation (ใช้ Claude Reviewer)
python main.py --simulate

# Live trading (ต้อง confirm 2 ครั้ง)
python main.py --live
```

---

## สิ่งที่ห้ามทำ

**Phase I (ยังใช้):**
- ❌ อ้างอิง `XAUUSD_Strategy_v5.md` (เลิกใช้แล้ว)
- ❌ ใช้ confidence threshold ≥ 0.70 (เลิกใช้แล้ว)
- ❌ ใช้ R:R ≥ 1.2 หรือ 1.5 (ปัจจุบันใช้ 1.0)
- ❌ ใช้ lot = balance × 1.5% (ปัจจุบันใช้ 10% / sl_pip)
- ❌ เรียก Claude ทุก candle โดยไม่มี G2 block ก่อน
- ❌ ใช้ datetime.now() ใน backtest path
- ❌ ใช้ mock agent ใน production

**Phase II (ใหม่):**
- ❌ Run backtest โดยไม่ใช้ `--no-ai` flag
- ❌ แก้ Python strategy/helpers โดยไม่ตรวจ diff กับ notebook 3 ไฟล์ก่อน
- ❌ เพิ่ม strategy ใหม่นอกเหนือจาก 3 อันใน `strategy/` (Mountain / MaiRuay / Scanner)
- ❌ Activate pattern legacy (DOWNTREND, UPTREND, MOUNTAIN_R2 ฯลฯ) — ลบจาก config แล้ว
- ❌ ใช้ Claude API ใน backtest loop
- ❌ Run production ก่อน Auditor ผ่าน
- ❌ Block duplicate signal โดยไม่เช็ค entry ± 50pip
- ❌ CSV header ไม่ตรงกับ schema ที่กำหนด
