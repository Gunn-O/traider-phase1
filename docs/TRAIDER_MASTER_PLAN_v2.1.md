# Tra(i)der — Master Plan v2.1
> **Context หลักสำหรับ Claude Code — อ่านก่อนทำงานทุกครั้ง**
> อัปเดต: Apr 2026 | Strategy: XAUUSD_AI_Trading_System v2.0 | Phase I Active

---

## การเปลี่ยนแปลงจาก v2.0 → v2.1

- เพิ่ม "1 แผน" definition และ Multi-Order per Plan logic
- เพิ่ม MTF tiebreak rules ครบ
- เพิ่ม Trailing SL tracking ใน Simulate Mode
- เพิ่ม Anti-Overtrade rules ที่ตกลงแล้ว (ไม่มี Cooldown)
- ปรับ Risk Management ตาม Part 4 ของ Strategy ใหม่
- เพิ่ม Position Monitor fix requirement
- ปรับ Lot formula ใหม่ทั้งหมด

---

## 1. นิยามสำคัญ

### "1 แผน" (1 Plan)
```
1 แผน = 1 Setup ที่วางแผนไว้ครบก่อนเปิด Order
ประกอบด้วย:
  - Chart type + Technique ที่เลือก
  - TF ที่ใช้
  - จุด Entry (อาจมีหลายจุด)
  - SL เดียว
  - TP เดียว (เลือก TP1/TP2/TP3 ที่เหมาะสม ไม่ Partial)
  - Lot ทั้งหมด + จำนวน Order ที่แบ่ง

แผน 1 แผน อาจมีได้ 1-3 Order (ทะยอยเปิดตาม Lot ที่คำนวณ)
แผนสิ้นสุดเมื่อ: ทุก Order hit SL หรือ TP หมดแล้ว
เริ่มแผนใหม่ได้: ต่อเมื่อแผนก่อนหน้าสิ้นสุดแล้วเท่านั้น
```

### Winrate Test Mode
```
ใช้ 0.01 lot ทุกไม้ โดยไม่คำนวณตาม Position Sizing
เปิดด้วย flag: --winrate-test
```

---

## 2. Risk Management (จาก Strategy Part 4)

```python
RISK_CONFIG = {
    # พอร์ต
    'min_balance': 300,          # USD ขั้นต่ำ
    'risk_per_plan_pct': 0.10,   # 10% ของพอร์ตต่อแผน

    # Loss Limits
    'max_consecutive_loss': 3,   # หยุดเมื่อแพ้ติดกัน 3 ไม้
    'max_loss_30pct': 0.30,      # หยุดเมื่อขาดทุนสะสม > 30%
    'max_loss_50pct': 0.50,      # หยุดเมื่อขาดทุนรวม > 50%

    # Trailing SL
    'trailing_sl_min_tp': 3000,  # pip — เริ่ม trailing เมื่อ TP > 3000 pip
    'trailing_sl_trigger': 2000, # pip — เลื่อน SL เมื่อราคาไป 2000 pip
    'trailing_sl_target': 500,   # pip — ตั้ง SL ที่ +500 pip
    'trailing_sl_step': 1000,    # pip — เลื่อนทุก 1000 pip

    # R:R
    'min_rr_ratio': 1.0,

    # Winrate Test
    'winrate_test_lot': 0.01
}
```

### สูตรคำนวณ Lot (ปรับใหม่)
```python
def calc_lot(balance: float, sl_pip: int, winrate_test: bool = False) -> dict:
    """
    สูตรใหม่จาก Strategy Part 4.4:
    Lot ทั้งหมด = เสียได้ (USD) / SL (pip)
    เสียได้ = balance × 10%

    ตัวอย่าง:
    balance=300, sl=900pip → lot = 30/900 = 0.033 → ปัดลง 0.03
    """
    if winrate_test:
        return {'lot_total': 0.01, 'lot_per_order': 0.01,
                'suggested_orders': 1, 'max_loss_usd': sl_pip * 0.01}

    max_loss = balance * RISK_CONFIG['risk_per_plan_pct']
    lot_total = max_loss / sl_pip
    lot_total = round(lot_total, 2)
    lot_total = max(0.01, min(lot_total, 10.0))  # min 0.01, max 10.0

    # แนะนำจำนวน order (แบ่งได้ 1-3)
    if lot_total >= 0.03:
        suggested_orders = 3
    elif lot_total >= 0.02:
        suggested_orders = 2
    else:
        suggested_orders = 1

    lot_per_order = round(lot_total / suggested_orders, 2)

    return {
        'lot_total': lot_total,
        'lot_per_order': lot_per_order,
        'suggested_orders': suggested_orders,
        'max_loss_usd': round(max_loss, 2)
    }
```

---

## 3. Timeframe Configuration (Single TF Mode)

### Current Setup
```
TIMEFRAMES = ['M5']  # Single TF only
```

### Why Single TF?
```
✅ Advantages:
- Simple & Reliable (no TF conflict)
- Fast (6x faster than MTF)
- Cost-effective (1/6 API calls)
- Clear decision logic

❌ MTF Disadvantages:
- Complex selection logic
- TF conflicts common
- Slow (scan 6 TF per cycle)
- Expensive (6x API calls)
```

### การเปลี่ยน TF
```
config.py → TIMEFRAMES = ['M5']

Options:
- ['M1'] → signal เยอะ (testing, high frequency)
- ['M5'] → balanced (recommended)
- ['M15'] → signal คุณภาพสูง (low frequency)
```

---

## 4. Anti-Overtrade Rules (ตกลงแล้ว)

```
❌ ไม่ใช้ Cooldown timer
✅ ใช้ Position-based rules เท่านั้น

Guardian Block เมื่อ:
1. มีแผนที่ยังไม่สิ้นสุด (open plan exists) → BLOCK ทันที
2. Consecutive loss ≥ 3 → BLOCK + แจ้ง LINE
3. Total loss > 30% balance → BLOCK + แจ้ง LINE
4. Total loss > 50% balance → BLOCK ถาวร + แจ้ง LINE
5. R:R < 1.0 → BLOCK
6. news_flag = true → BLOCK ±30 นาที
```

---

## 5. Agent Architecture

```
G1: Multi-TF Visual Pattern Detector
    scan H4,H1,M30,M15,M5,M1 → world_state per TF
    → select_best_setup() → best world_state
    ↓
G2: Pre-filter
    ตรวจ: open plan / loss limits / news flag
    สร้าง chart_context
    ↓ (pre_approved)
G3a: Claude API Decision (REQUIRED ทุกครั้ง)
    รับ best world_state + OHLC + Strategy content
    → decision JSON (BUY/SELL/SKIP + Entry/SL/TP/Lot)
    → LLM log (tokens, cost, latency)
    ↓
G3b: Lot Calculator (ปรับตาม Strategy Part 4.4)
    lot = max_loss_usd / sl_pip
    ↓
G3c: Guardian Risk Gate
    ตรวจ 6 เงื่อนไข Anti-Overtrade
    ↓ (approved)
G4a: LINE Notify
G4b: Sheets Log — OPEN (บันทึกแผน + ทุก Order)
G4c: Position Monitor (ทุก candle close)
     ตรวจ SL/TP hit → update Sheets → คำนวณ P&L
     ตรวจ Trailing SL ถ้า TP > 3000 pip
G4d: Human vs AI Comparison
     LINE request human opinion → record → weekly report
     ↓ (weekly)
G5: Performance Analysis (manual Phase I)
```

---

## 6. Google Sheets Schema (ปรับใหม่)

### Sheet 1: Trade Log
| Col | Field | หมายเหตุ |
|-----|-------|---------|
| A | trade_id | TRD-YYYYMMDD-NNN |
| B | plan_id | PLAN-YYYYMMDD-NNN (ทุก order ในแผนเดียวกันใช้ plan_id เดียว) |
| C | order_num | 1,2,3 (ลำดับ order ในแผน) |
| D | timestamp_open | เวลาเปิด |
| E | timeframe | H4/H1/M30/M15/M5/M1 |
| F | chart_type | uptrend/downtrend/sideway_down/sideway_up/mountain/unclear |
| G | technique | twin_candle/breakout_follow/mai_ruay/support_bounce |
| H | action | BUY/SELL |
| I | entry_price | ราคา entry |
| J | sl_price | Stop Loss |
| K | tp_price | Take Profit (เดียว) |
| L | lot_size | lot ของ order นี้ |
| M | lot_total_plan | lot ทั้งหมดของแผน |
| N | rr_ratio | R:R จริง |
| O | confidence | 0.0-1.0 |
| P | rsi_14 | metadata |
| Q | session | Asia/London/NY |
| R | ai_reason | เหตุผลจาก Claude |
| S | llm_tokens | tokens ที่ใช้ |
| T | llm_cost_usd | ต้นทุน API |
| U | result | WIN/LOSS/PENDING |
| V | pnl_usd | P&L USD |
| W | close_reason | TP_HIT/SL_HIT/MANUAL |
| X | close_price | ราคาปิด |
| Y | timestamp_close | เวลาปิด |
| Z | trailing_sl | SL ที่เลื่อนแล้ว (ถ้ามี) |
| AA | human_action | BUY/SELL/SKIP (human) |
| AB | human_agree | TRUE/FALSE |

### Sheet 2: Portfolio State (update real-time)
| Field | ความหมาย |
|-------|---------|
| active_plan_id | แผนที่กำลังเปิดอยู่ |
| open_orders_count | จำนวน order ที่เปิดอยู่ |
| total_open_lot | รวม lot ที่เปิดอยู่ |
| realized_pnl_usd | P&L ที่ปิดแล้ว (วันนี้) |
| unrealized_pnl_usd | P&L ที่ยังเปิดอยู่ (estimate) |
| consecutive_loss | SL ติดกันกี่ครั้ง |
| total_loss_pct | ขาดทุนรวม % ของ balance เริ่มต้น |
| trading_blocked | TRUE/FALSE |
| block_reason | เหตุผลที่ block |
| last_updated | เวลา update ล่าสุด |

---

## 7. Position Monitor — Fix Required (Priority #1)

### ปัญหาปัจจุบัน
```
- PENDING ไม่ถูก update เป็น WIN/LOSS
- traider.log ว่างเปล่า = loop ไม่ทำงานหรือ error เงียบ
- ราคา mock (4600+) ไม่ตรง XAUUSD จริง (~3000+)
- Trade ID duplicate
```

### Logic ที่ต้องมี
```python
def check_positions_on_candle_close(candle: dict, open_orders: list) -> list:
    """
    เรียกทุก M5/TF candle close
    ตรวจแต่ละ order ว่า hit SL หรือ TP ไหม

    กฎ: ถ้า High/Low ของแท่งครอบทั้ง SL และ TP
    → ดู Open ก่อน: ถ้า BUY และ Low ≤ SL ก่อน Open → SL hit
    → ในทางปฏิบัติ simulate: ถ้า gap ไม่ชัด → ถือว่า SL hit ก่อน (conservative)
    """
    updates = []
    for order in open_orders:
        if order['result'] != 'PENDING':
            continue

        action = order['action']
        entry = order['entry_price']
        sl = order['sl_price']
        tp = order['tp_price']

        sl_hit = (action == 'BUY' and candle['low'] <= sl) or \
                 (action == 'SELL' and candle['high'] >= sl)
        tp_hit = (action == 'BUY' and candle['high'] >= tp) or \
                 (action == 'SELL' and candle['low'] <= tp)

        if sl_hit and tp_hit:
            # ทั้งคู่ hit → conservative = SL
            result = 'LOSS'
            close_price = sl
            close_reason = 'SL_HIT'
        elif sl_hit:
            result = 'LOSS'
            close_price = sl
            close_reason = 'SL_HIT'
        elif tp_hit:
            result = 'WIN'
            close_price = tp
            close_reason = 'TP_HIT'
        else:
            # ตรวจ Trailing SL
            trailing_update = check_trailing_sl(order, candle)
            if trailing_update:
                updates.append({'trade_id': order['trade_id'],
                                'type': 'trailing_sl_update',
                                'new_sl': trailing_update})
            continue

        pnl = calc_pnl(action, entry, close_price, order['lot_size'])
        updates.append({
            'trade_id': order['trade_id'],
            'type': 'close',
            'result': result,
            'close_price': close_price,
            'close_reason': close_reason,
            'pnl_usd': pnl,
            'timestamp_close': candle['timestamp']
        })

    return updates


def check_trailing_sl(order: dict, candle: dict) -> float | None:
    """
    ตรวจและคำนวณ Trailing SL ใหม่
    เงื่อนไข: TP > 3000 pip และราคาไป > 2000 pip แล้ว
    """
    tp_pip = abs(order['tp_price'] - order['entry_price']) * 100
    if tp_pip <= 3000:
        return None

    current_profit_pip = 0
    if order['action'] == 'BUY':
        current_profit_pip = (candle['close'] - order['entry_price']) * 100
    else:
        current_profit_pip = (order['entry_price'] - candle['close']) * 100

    if current_profit_pip < 2000:
        return None

    # คำนวณ trailing SL ใหม่
    current_trailing = order.get('trailing_sl', order['sl_price'])
    steps = int((current_profit_pip - 2000) / 1000)
    new_sl_profit = 500 + (steps * 1000)  # pip จาก entry

    if order['action'] == 'BUY':
        new_sl = order['entry_price'] + (new_sl_profit / 100)
        if new_sl > current_trailing:  # เลื่อนแค่ขาขึ้นเท่านั้น
            return new_sl
    else:
        new_sl = order['entry_price'] - (new_sl_profit / 100)
        if new_sl < current_trailing:
            return new_sl

    return None


def calc_pnl(action: str, entry: float, close: float, lot: float) -> float:
    """P&L = (close - entry) × lot × 100 สำหรับ BUY"""
    if action == 'BUY':
        return round((close - entry) * lot * 100, 2)
    else:
        return round((entry - close) * lot * 100, 2)
```

---

## 8. File Structure

```
traider-phase1/
├── strategy/
│   └── XAUUSD_AI_Trading_System.md       ← v2.0 (read-only)
├── agents/
│   ├── g1_pattern_detector.py             ← ใหม่ทั้งหมด (ตาม pattern_detection_spec.md)
│   ├── g2_prefilter.py                    ← ปรับ: เช็ค open plan แทน open trades
│   ├── g3_claude_decision.py              ← ใหม่ (ตาม claude_prompt_template.md)
│   ├── g3_money_management.py             ← ปรับ: lot = max_loss / sl_pip
│   ├── g3_risk_gate.py                    ← ปรับ: 6 block conditions ใหม่
│   ├── g4_notify.py                       ← ปรับ: format ใหม่ + human request
│   ├── g4_sheets_logger.py                ← ปรับ: schema ใหม่ + plan_id
│   ├── g4_position_monitor.py             ← FIX: SL/TP hit + Trailing SL
│   └── g4_human_comparison.py             ← ใหม่
├── utils/
│   ├── data_connector.py                  ← ปรับ: MTF data fetch
│   ├── pattern_utils.py                   ← ใหม่: helper จาก pattern_detection_spec
│   ├── indicators.py                      ← คงเดิม (metadata เท่านั้น)
│   ├── position_tracker.py                ← ปรับ: plan-based tracking
│   └── constants.py                       ← ปรับ: chart types, techniques
├── docs/
│   ├── pattern_detection_spec.md          ← spec สำหรับ G1
│   └── claude_prompt_template.md          ← template สำหรับ G3a
├── backtest/
│   └── backtest_runner.py                 ← ปรับ: ใช้ Claude API จริง
├── main.py                                ← ปรับ: pipeline ใหม่
└── config.py                              ← RISK_CONFIG ทั้งหมด
```

---

## 9. กฎที่ Claude Code ต้องจำเสมอ

1. **Strategy อ่านอย่างเดียว** — `strategy/XAUUSD_AI_Trading_System.md`
2. **1 แผนต่อครั้ง** — ห้ามเปิดแผนใหม่ถ้ายังมีแผนเปิดอยู่
3. **Claude API ทุก trade** — ห้ามใช้ mock/rule-based ใน production
4. **RSI เป็น metadata** — ไม่ใช้ตัดสิน
5. **Lot = max_loss_usd / sl_pip** — ไม่ใช่ balance × 1.5%
6. **Risk 10% per plan** — ไม่ใช่ 1.5%
7. **R:R ≥ 1.0** — Guardian block ถ้าน้อยกว่า
8. **Log LLM ทุก call** — tokens, cost, latency, reason
9. **Position Monitor ต้อง update PENDING** — priority สูงสุด
10. **Winrate mode = 0.01 lot** — ใช้ flag --winrate-test

---

## 10. Phase I KPI Gate → Phase II

| KPI | เป้าหมาย |
|-----|---------|
| Win Rate | ≥ 55% |
| Position Monitor | ไม่มี PENDING ค้าง > 1 วัน |
| LLM Log | 100% trades |
| Human vs AI Agreement | วัดเป็น baseline |
| Consecutive weeks | 4 สัปดาห์ |

---

*Tra(i)der Master Plan v2.1 | Apr 2026 | Strategy v2.0 | Phase I*
