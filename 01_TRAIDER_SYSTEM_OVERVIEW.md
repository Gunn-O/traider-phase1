# Tra(i)der — System Overview
> **ไฟล์นี้คือ Context หลักของ Claude Project**
> ใช้เพื่อให้ Claude เข้าใจขอบเขต สถาปัตยกรรม และกฎของระบบทั้งหมดก่อนทำงานทุกครั้ง

---

## 1. Product Vision

> *"นักเทรดที่ดีมี Strategy แต่สูญเสียเงินเพราะอารมณ์และการเฝ้าหน้าจอ"*

**Tra(i)der** แปลง Trading Strategy ที่ trader สร้างจากประสบการณ์จริง ให้กลายเป็น Structured Rule ที่ AI execute แทนได้ 24 ชั่วโมง โดย:
- ตัดปัจจัยทางจิตใจออกจากการตัดสินใจ
- เรียนรู้และปรับปรุง Strategy อย่างต่อเนื่อง
- เติบโตเป็น SaaS Platform ที่รองรับ trader ทุกคน

---

## 2. Two-Layer Architecture

ระบบแบ่งเป็น 2 ชั้นที่ต้องเข้าใจและไม่ปะปนกัน:

```
┌─────────────────────────────────────────────────────────┐
│  STRATEGY LAYER  (คงที่ — เปลี่ยนได้ผ่าน G5 เท่านั้น)   │
│                                                         │
│  XAUUSD_Strategy_v4.md                                  │
│  ├── 6 Trading Conditions (A1–A6)                       │
│  ├── 3 Techniques (B1–B3)                               │
│  ├── RSI Rules + H1 Filter                              │
│  └── TP1/2/3 + Lot Size Reference                       │
└─────────────────────────────────────────────────────────┘
           ↕ อ่านอย่างเดียว (read-only)
┌─────────────────────────────────────────────────────────┐
│  SYSTEM LAYER  (พัฒนาต่อเนื่องแต่ละ Phase)              │
│                                                         │
│  5 Agent Groups: G1 → G2 → G3 → G4 → G5               │
│  Infrastructure: MT5 → Sheets → DB → API → Dashboard   │
└─────────────────────────────────────────────────────────┘
```

**กฎสำคัญ:** Strategy Layer ห้ามแก้โดยตรง — ต้องผ่าน G5 Evaluate & Relearn flow และ User อนุมัติก่อนเท่านั้น

---

## 3. Phase Roadmap

| Phase | ชื่อ | เป้าหมายหลัก | KPI Gate |
|-------|------|-------------|----------|
| **I** | Signal + Notify + Validate | พิสูจน์ว่า AI อ่าน Strategy ถูก — Simulated Trade | Win Rate ≥ 60% × 4 สัปดาห์ |
| **II** | Connect MT5 + Real Execution + UI | Execute จริง + Dashboard + LINE Control | Real Win ≥ 55% × 8 สัปดาห์ |
| **III** | Full Platform + Self-Learning | SaaS Multi-User + AI ปรับ Strategy เอง | AI Self-improve, Users ไม่เฝ้าจอ |

**กฎของ Claude:** พัฒนาทีละ Phase ตามลำดับ อย่าข้าม Phase และอย่า implement feature ของ Phase ถัดไปก่อนผ่าน KPI

---

## 4. Agent Architecture — 5 Groups

ระบบมี 5 Agent Groups ทำงานเป็น Pipeline:

```
[Market Data]
     ↓
G1: AI Market Scanning      ← สแกน pattern ทุก M5
     ↓ (candidate ≥ 2/3 conditions)
G2: Quantitative Analysis   ← score RSI + S/R + Trend → confidence
     ↓ (confidence ≥ 0.70)
G3: Strategy MM & Position  ← Decision + Lot + SL/TP + Guardian
     ↓ (approved)
G4: Monitoring & Portfolio  ← LINE notify + Sheets log + Dashboard
     ↑↓
G5: Evaluate & Relearn      ← Weekly: analyze → propose → deploy
```

### G1 — AI Market Scanning
| Sub-Agent | หน้าที่ |
|-----------|---------|
| Market Perception | คำนวณ RSI(14), หา S/R swing, ระบุ Condition A1–A6 |
| Candle Pattern Scanner | ตรวจ wick ratio, engulfing, spike size vs 50-bar avg |
| News & Event Filter | block ±30 min รอบ NFP / FOMC / CPI |
| Session & Liquidity Scanner | ระบุ session (Asia/London/NY), ตรวจ spread spike |

**Output:** `world_state JSON` → ส่งต่อ G2

### G2 — Quantitative Analysis
| Sub-Agent | หน้าที่ |
|-----------|---------|
| RSI Zone Analyzer | ตรวจ RSI zone ตาม rules table |
| S/R Strength Scorer | นับ touches, คำนวณ zone width, fresh vs tested |
| Trend Alignment Checker | ตรวจ M5 signal สอดคล้อง H1 trend ไหม |
| Confidence Scorer | รวม score → confidence 0.0–1.0 |

**Filter:** ผ่านต่อเมื่อ confidence ≥ 0.70 เท่านั้น

### G3 — Strategy, MM & Position Planning
| Sub-Agent | หน้าที่ |
|-----------|---------|
| Decision Agent | อ่าน Strategy MD → BUY/SELL/SKIP + reason |
| Money Management Agent | คำนวณ lot size (risk 1–2% ต่อ trade) |
| Position Planner | คำนวณ SL (wick+buffer), TP1/2/3, ตรวจ R:R ≥ 1:2 |
| Guardian / Risk Gate | Max DD 5%, Daily loss 3%, Max 2 open trades |

**Output:** `{approved, lot, sl, tp1, tp2, tp3}` หรือ `{blocked, reason}`

### G4 — Monitoring & Portfolio
| Sub-Agent | หน้าที่ |
|-----------|---------|
| Trade Monitor | Loop 30 วินาที: SL/TP hit, timeout 4 ชม., trailing stop |
| Explain & Notify | แปลง JSON → LINE ภาษาไทย 4–5 บรรทัด |
| User Command Listener | รับ PAUSE/RESUME/CLOSE ALL จาก LINE |
| Portfolio Logger | Append Sheets หลังปิดไม้ทุกครั้ง |
| Dashboard Updater | Refresh charts: Win Rate, Condition, RSI heatmap |

### G5 — Evaluate & Relearn
| Sub-Agent | หน้าที่ |
|-----------|---------|
| Performance Analyzer | หา Win% per Condition, RSI zone, Session รายสัปดาห์ |
| Threshold Optimizer | เสนอปรับ RSI threshold, S/R buffer ที่ data สนับสนุน |
| Strategy Version Manager | สร้าง MD version ใหม่ + changelog |
| Deploy & Rollback Agent | Deploy หลัง approve, rollback ถ้า win rate ลด >5% |

---

## 5. Data Flow ภาพรวม

```
MT5 API (M5+H1)
    │
    ▼
G1: scan() → world_state
    │ [pattern candidate]
    ▼
G2: analyze() → confidence
    │ [≥ 0.70]
    ▼
G3: decide() + plan() + guard()
    │ [approved]
    ├──► G4: notify LINE
    ├──► G4: log → Google Sheets
    └──► [Phase II] MT5 execute order
              │
              ▼
         G4: monitor() loop 30s
              │
              ▼
         G4: log close → Sheets
              │
    [weekly]  ▼
         G5: analyze → propose → LINE → user approve → deploy
```

---

## 6. Google Sheets Schema (Phase I & II)

### Sheet 1: Trade Log (Bot append อัตโนมัติ — ห้ามแก้มือ)

| Col | Field | Type | หมายเหตุ |
|-----|-------|------|---------|
| A | trade_id | String | TRD-YYYYMMDD-NNN |
| B | open_time | DateTime | เวลา signal |
| C | chart_condition | String | A1–A6 |
| D | pattern | String | B1/B2/B3 |
| E | action | String | BUY/SELL/SKIP |
| F | entry_price | Number | ราคา entry |
| G | sl_price | Number | Stop Loss |
| H | tp1_price | Number | TP1 |
| I | tp2_price | Number | TP2 |
| J | tp3_price | Number | TP3 |
| K | lot_size | Number | ขนาด lot |
| L | confidence | Float | 0.0–1.0 |
| M | rsi_at_entry | Number | RSI(14) |
| N | h1_trend | String | bullish/bearish/sideways |
| O | session | String | Asia/London/NY |
| P | simulated_result | String | WIN/LOSS/BE **(Phase I key)** |
| Q | pnl_if_executed | Number | กำไร/ขาดทุน USD สมมติ |
| R | line_sent | Boolean | ส่ง LINE สำเร็จ |
| S | close_reason | String | TP1/2/3_HIT, SL_HIT, TIMEOUT |
| T | duration_min | Number | ระยะเวลาถือ (นาที) |

### Sheet 2: Daily Summary (Formula auto-generated)
- Win Rate % = WIN / Total
- Best Condition = ที่ win rate สูงสุด
- Total PnL USD = SUMIF
- Avg Confidence ของ WIN trades

---

## 7. Tech Stack

| Layer | Technology | Phase | หมายเหตุ |
|-------|-----------|-------|---------|
| AI / LLM | Claude Sonnet (claude-sonnet-4-5) | I, II, III | G1–G5 agents |
| Market Data | MetaTrader5 Python API | I, II, III | M5+H1 OHLCV |
| Notification | LINE Notify API | I, II, III | Signal + weekly |
| Data Store | Google Sheets + gspread | I, II | Trade log |
| Data Store | PostgreSQL + Supabase | III | Multi-user |
| Backend | Python 3.11 + FastAPI | I→III | Scripts → API |
| Frontend | Next.js + React + Tailwind | II, III | Dashboard |
| Auth | Supabase Auth + JWT | III | Multi-user |
| Dev Tools | Claude Code + Claude Cowork | I, II, III | Primary tools |

**Token cost estimate:** ~8,000–10,000 tokens/วัน ≈ **$0.02–0.06/วัน** (Sonnet)

---

## 8. Risk Profile (Default)

```json
{
  "max_dd_pct": 5.0,
  "max_daily_loss_pct": 3.0,
  "max_open_trades": 2,
  "risk_per_trade_pct": 1.5,
  "min_confidence": 0.70,
  "min_rr_ratio": 2.0,
  "blocked_news_minutes": 30,
  "trading_hours": "00:00-23:59 UTC",
  "blocked_conditions": []
}
```

---

## 9. Claude Output JSON Format (Decision Agent)

```json
{
  "chart_condition": "A1_uptrend | A2_downtrend | A3_mountain | A4_sideways_up | A5_sideways_down | A6_unclear",
  "pattern":         "ไม้รวย | ตามเจ้า | แนวเด้ง | ทะลุTP | SKIP",
  "action":          "BUY | SELL | SKIP",
  "confidence":      0.87,
  "entry":           3050.48,
  "sl":              3044.00,
  "tp1":             3062.00,
  "tp2":             3068.00,
  "tp3":             3075.00,
  "lot":             0.58,
  "rsi_now":         36.20,
  "h1_trend":        "bullish | bearish | sideways",
  "session":         "London | Asia | NY",
  "candles_checked": 80,
  "skip_reason":     "ระบุเหตุผลถ้า SKIP — ว่างถ้าไม่ SKIP",
  "reason":          "อธิบายสั้นๆ เงื่อนไขที่ครบ"
}
```

---

## 10. LINE Message Format

```
📊 Tra(i)der Signal
──────────────────────────
🟢 BUY  |  A3 ภูเขา + B3 แนวเด้ง
Entry: 3,050.48  |  Confidence: 87%
TP1: 3,062  TP2: 3,068  TP3: 3,075
SL: 3,044  |  Lot: 0.58
──────────────────────────
เหตุผล: ฐานภูเขาชัด RSI 36 curve ขึ้น แนวรับ 3050 แตะแล้ว 3 ครั้ง
H1: Bullish  |  Session: London
```

---

## 11. กฎที่ Claude ต้องจำเสมอ

1. **อย่า implement feature Phase II/III ในขณะที่กำลังทำ Phase I** — ทำตามลำดับ
2. **Strategy MD อ่านอย่างเดียว** — ห้าม hardcode rule ใน Python แทน MD
3. **ทุก trade decision ต้องผ่าน Guardian** ก่อนส่ง LINE เสมอ
4. **Simulated mode Phase I** — ไม่มี MT5 order execution จริง ใช้ราคาปิดจาก feed ตรวจสอบ
5. **SKIP เสมอถ้าไม่มั่นใจ** — ระบบที่ดีคือระบบที่รู้จัก SKIP มากกว่าเทรดผิด
6. **confidence < 0.70 = SKIP** — ไม่มีข้อยกเว้น
7. **R:R < 1:2 = SKIP** — ไม่มีข้อยกเว้น
8. **NEWS flag active = SKIP** — block ±30 นาทีรอบ high-impact event เสมอ

---

*Tra(i)der System Overview v2.0 | อ้างอิง: XAUUSD_Strategy_v4.md + Tra(i)der_Roadmap_v1 | Mar 2025*
