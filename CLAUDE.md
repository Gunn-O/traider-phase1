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
| `strategy/XAUUSD_Uptrend_Downtrend_Scanner_v3.8.md` | **Uptrend/Downtrend Scanner v3.8** | `strategies/uptrend_downtrend_scanner.py` (+ detectors ใน `utils/xauusd_signal.py`) |

**กฎเหล็ก:** Python ต้องตรงกับ **engine code ใน notebook** เสมอ (markdown header ใน notebook อาจล้าสมัย — engine code คือ source of truth)
**Strategies ทั้ง 3 ทำงานแยกกัน** — ไม่มีการ share state ข้าม strategy

### Supporting Files

| ไฟล์ | สถานะ |
|------|-------|
| `strategy/XAUUSD_System_Prompt_Reviewer.md` | ⚠️ Legacy — Reviewer per-trade is **disabled** (see Architecture below) |
| `docs/TRAIDER_MASTER_PLAN_v2.1.md` | ✅ Architecture reference |
| `utils/xauusd_signal.py` | ✅ Signal helpers + Scanner v3.8 detectors |
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

**Claude Role (Phase II — refreshed 2026-05-11):**
- **Per-trade pipeline = Python only (no AI in any mode)**
  - BACKTEST / SIM / LIVE — ทั้งหมด AUTO_APPROVE จาก Signal Engine
  - Guardian (G3c) เป็น Python rules ล้วน
  - เหตุผล: criteria ทั้งหมดอยู่ใน Python strategies แล้ว, Reviewer ซ้ำซ้อน
- **AI ใช้เฉพาะ off-cycle agents (ไม่ใช่ทุก trade):**
  - **Weekly Strategist** — สัปดาห์ละครั้ง: วิเคราะห์ผล → แนะนำ parameter
  - **Monthly Evolver** — เดือนละครั้ง: propose strategy update (human approve)
- Reviewer per-trade prompt (`XAUUSD_System_Prompt_Reviewer.md`) เก็บไว้เป็น legacy — ไม่โหลดในรันปัจจุบัน

---

## 🔧 Role 1: Dev Agent

รับผิดชอบ: เขียนโค้ด, แก้ bug, implement feature ตาม Master Plan v2.1

### กฎ Dev:
1. **Strategy notebook = source of truth** — Python ต้องตรงกับ engine code ใน 3 notebooks
2. **Per-trade pipeline = Python only** — ห้ามเรียก Claude ตอน decide/lot/guardian (เลิกใช้แล้ว)
3. **Lot = portfolio × 10% / sl_pip** — Signal Engine คำนวณให้, อย่า override
4. **1 plan ต่อ pattern** — Mountain + MaiRuay เปิดขนานกันได้ (ตาม Guardian Rule 1)
5. **Timestamp = candle time** — ห้ามใช้ datetime.now() ใน backtest
6. **Technique log** มาจาก signal.pattern (โดย decision['setup'])

### Architecture Pipeline (Phase II — Python-only per trade)

ทุก mode (BACKTEST / SIM / LIVE) ใช้ **pipeline เดียวกัน** — ต่างกันแค่ที่ Execute step (broker target):

```
Market Data
    ↓
Signal Engine: utils/signal_engine.py — รัน 3 strategy แบบ parallel
    MOUNTAIN          → strategies/mountain.py              (ภูเขา v4.61, M1/M5)
    MAI_RUAY          → strategies/mai_ruay.py              (พ่อ-แม่, M1/M5/M15/M30)
    UPTREND_SCANNER   ┐
                      ├→ strategies/uptrend_downtrend_scanner.py (v3.8, M5 only)
    DOWNTREND_SCANNER ┘
    เลือก best by R:R → Signal object (Entry/SL/TP/Lot คำนวณเสร็จ)
    ↓ world_state + signal
G2 Pre-filter (Python)
    block ก่อนถึง execute: active_plan, consecutive_loss≥3, R:R<1.0,
    duplicate signal ±50pip
    ↓ pre_approved
Step 3a Decision (AUTO_APPROVE)
    ใช้ signal จาก Signal Engine ตรงๆ — ไม่เรียก Claude (deprecated)
Step 3b Lot
    ใช้ signal.lot ตรงๆ (WINRATE_TEST=true → 0.01 override)
Step 3c Guardian (Python rules)
    Rule 1: active plan ของ pattern เดียวกัน → block
    Rule 2: consecutive_loss ≥ 3 → block
    Rule 3: total_loss > 30% → block
    Rule 4: total_loss > 50% → block ถาวร
    Rule 5: R:R < min_rr_ratio (config 0.0 = ปิด)
    ↓ approved
Step 4 Execute → Broker
    BACKTEST  → PaperBroker (in-memory simulation)
    SIM/paper → PaperBroker (real-time data, fake orders)
    micro     → MT5LiveBroker (real Cent account orders)
    live      → MT5LiveBroker (real money orders)
    ↓
G4b Sheets Log (candle timestamp)
G4c Position Monitor (ทุก candle close — check SL/TP hit)
```

**สิ่งที่ "เลิกใช้" จาก architecture เดิม:**
- ❌ G3a Claude Reviewer per-trade (ไม่ wired แล้ว)
- ❌ G3b Risk Manager (Haiku) (ไม่ wired แล้ว — `self.risk_manager = None` ลบทิ้ง)
- ❌ Confidence threshold (Signal Engine confidence=1.0 เสมอ)
- ❌ G1 Pattern Detector (แทนด้วย Signal Engine)

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
- [ ] Block ก่อน execute: มี active_plan_id อยู่แล้ว (1 plan ต่อครั้ง)
- [ ] Block ก่อน execute: consecutive_loss ≥ 3
- [ ] Block ก่อน execute: R:R < 1.0
- [ ] **Block ก่อน execute: duplicate signal** (entry ใหม่ ± 50pip ของ active plan)

**Step 3a/3b — main.py (no AI):**
- [ ] Step 3a: AUTO_APPROVE — ห้ามเพิ่ม Claude call กลับมา
- [ ] Step 3b: ใช้ `signal.lot` ตรงๆ (override เป็น 0.01 เฉพาะ WINRATE_TEST=true)
- [ ] llm_log = `{action: 'AUTO_APPROVE', cost_usd: 0.0}` (สำหรับ Sheets/LocalDB schema)
- [ ] **ไม่มี `self.risk_manager`, `self.analyst`** ใน TraiderMainLoop

**Step 3c Guardian — agents/g3_risk_gate.py:**
- [ ] Block ถ้ามี active plan ของ pattern เดียวกัน (per-pattern slot)
- [ ] Block ถ้า consecutive_loss ≥ 3
- [ ] Block ถ้า total_loss_pct > 0.30
- [ ] Block ถ้า total_loss_pct > 0.50 (circuit breaker, ถาวร)
- [ ] R:R block: ใช้ `RISK_CONFIG['min_rr_ratio']` (default 0.0 = ปิด)
- [ ] ไม่มี confidence threshold (Signal Engine = 1.0 เสมอ)
- [ ] ไม่มี Claude/AI call ใน Guardian — Python rules ล้วน

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

# SKIP rate ผิดปกติ
"@Auditor วิเคราะห์ผล run นี้:
SKIP rate = [X]% ปกติควรไม่เกิน 30%
ระบุว่า filter ไหนใน Signal Engine / G2 เข้มเกินไป"

# Per-strategy SKIP reason (Tier 2 heartbeat)
"@Auditor ดู skip_reasons ใน /api/bots heartbeat:
ส่วนใหญ่ block ที่ criterion ไหนใน Mountain/MaiRuay/Scanner?"
```

---

## 🎯 Phase II Specifics

### AI ใช้ทำอะไรได้บ้าง (refreshed 2026-05-11)

✅ **Weekly Strategist:** วิเคราะห์ผลรายสัปดาห์ → แนะนำ parameter (ไม่บังคับใช้)
✅ **Monthly Evolver:** propose strategy update รายเดือน (human approve เสมอ)
❌ **ไม่ใช้ใน per-trade pipeline เลย** (BACKTEST, SIM, LIVE = AUTO_APPROVE ทั้งหมด)
❌ **ไม่ใช้เป็น Reviewer per signal** (ลบ wiring แล้ว)
❌ **ไม่ใช้เป็น Risk Manager (Haiku)** (ลบ wiring แล้ว)
❌ **ไม่คำนวณ Entry/SL/TP/Lot** (Signal Engine คำนวณทั้งหมด)
❌ **ไม่ใช้ใน Guardian** (Python rules ล้วน)

### Backtest Bug Fix Priority

1. **Header alignment** — ตรวจ CSV output ให้ตรง schema
2. **Pending resolution** — position_monitor ต้อง close ทุก candle
3. **Duplicate block** — G2 ตรวจ entry ± 50pip ไม่เปิดซ้ำ

### TradingView → Python Workflow

1. พัฒนา/ทดสอบ logic ใน Pinescript (TradingView)
2. แปลง rule เป็น Python ใน xauusd_signal.py
3. รัน backtest Python เทียบ TradingView ผล
4. ถ้า match > 90% → promote to SIM

### กฎเหล็ก Phase II (refreshed 2026-05-11)

1. **3 Strategy เท่านั้น:** Mountain, MaiRuay, Uptrend/Downtrend Scanner (อิง 3 notebook ใน `strategy/`)
2. ทุก strategy ทำงานแยกกัน — ห้าม share state ข้าม strategy
3. แก้ Python strategy/helpers ได้เฉพาะเพื่อ sync กับ notebook engine code (ห้ามปรับเอง)
4. **Per-trade pipeline = Python only** — ห้ามใส่ Claude/Haiku/AI กลับเข้า G3a/G3b/Guardian
5. **AI ใช้ได้เฉพาะ Weekly Strategist + Monthly Evolver** (off-cycle, ไม่ใช่ทุก trade)
6. Timestamp = candle time เสมอ (ไม่ใช่ datetime.now())
7. G2 ต้อง block duplicate plan (same entry ± 50pip)
8. Position monitor ต้อง close position ทุก candle close
9. host = 127.0.0.1 เสมอ

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
ANTHROPIC_API_KEY=sk-ant-...   # ใช้เฉพาะ Weekly/Monthly agents
LINE_NOTIFY_ENABLED=false      # ปิดระหว่าง backtest
SHEETS_ENABLED=true            # เปิดสำหรับ live tracking (ต้องมี credentials.json)
GOOGLE_SHEETS_ID=...           # Google Sheet ID ที่ share กับ service account
GOOGLE_CREDENTIALS_JSON=./credentials.json  # service account key (gitignored)
ACCOUNT_BALANCE=1000
WINRATE_TEST=false             # true = lock ทุกไม้ที่ 0.01 lot
```

**Run commands (Phase II):**
```bash
# Backtest (Python only — no AI per trade)
python main.py --backtest --start 2026-03-01 --end 2026-03-07

# Winrate test (0.01 lot ทุกไม้)
python main.py --winrate-test

# Simulation (Python only — paper broker, no AI per trade)
python main.py --simulate

# Live trading (ต้อง confirm 2 ครั้ง — ส่ง order จริงเข้า MT5)
python main.py --live
```

หมายเหตุ: `--no-ai` flag ไม่จำเป็นแล้ว — per-trade pipeline ไม่เรียก AI ทุก mode

---

## สิ่งที่ห้ามทำ

**Per-trade pipeline (เด็ดขาด):**
- ❌ ใส่ Claude/Haiku/AI กลับเข้าไปใน Step 3a (Decision), Step 3b (Lot), Step 3c (Guardian)
- ❌ ตั้ง `self.analyst` หรือ `self.risk_manager` กลับใน TraiderMainLoop
- ❌ ใช้ confidence threshold (Signal Engine = 1.0 เสมอ)
- ❌ ปรับ lot นอก Signal Engine (เว้นแต่ WINRATE_TEST=true)
- ❌ Override Entry/SL/TP จาก Signal Engine

**Strategy:**
- ❌ เพิ่ม strategy ใหม่นอกเหนือ 3 อันใน `strategy/` (Mountain / MaiRuay / Scanner)
- ❌ Activate pattern legacy (DOWNTREND, UPTREND, MOUNTAIN_R2 ฯลฯ) — ลบจาก config แล้ว
- ❌ แก้ Python strategy/helpers โดยไม่ตรวจ diff กับ notebook 3 ไฟล์ก่อน

**Misc:**
- ❌ ใช้ datetime.now() ใน backtest path (ใช้ candle_time)
- ❌ Block duplicate signal โดยไม่เช็ค entry ± 50pip
- ❌ Run production ก่อน Auditor ผ่าน
- ❌ Commit `credentials.json` (gitignored, มี private key)
