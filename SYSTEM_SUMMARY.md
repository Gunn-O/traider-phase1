# Tra(i)der Phase I v2.1 — System Summary

**Last Updated:** 2026-04-14  
**Status:** ✅ Ready for Simulate Mode

---

## 🎯 **What is Tra(i)der?**

AI-powered XAUUSD (Gold) trading system using **Claude 4.6 Sonnet** for decision-making.

**Key Features:**
- **Hybrid Architecture:** Python pattern detection (G1) + Claude AI decisions (G3)
- **Risk Management:** 10% risk per plan, R:R ≥ 1.0, max 3 consecutive losses
- **Prompt Caching:** 98-100% cache hit rate → ~$0.02/decision
- **Duplicate Prevention:** Blocks identical setups within 30 pip
- **Google Sheets Logging:** Real-time trade tracking

---

## 📐 **Architecture (6-Agent Pipeline)**

```
Market Data (H4/H1/M30/M15/M5/M1)
    ↓
G1: Pattern Detector (Python)
    - Detects: uptrend/downtrend/mountain/sideway
    - Finds: twin_candle, father_candle (breakout_follow), mai_ruay
    - Multi-timeframe: Selects best quality setup
    ↓
G2: Pre-filter (Python)
    - Blocks: unclear charts, quality < 0.65, duplicate setups
    - Checks: active_plan_id, consecutive_loss, news_flag
    ↓
G3a: Claude Decision (Claude 4.6 Sonnet)
    - Reads: 29,483-char strategy (cached)
    - Outputs: BUY/SELL/SKIP + entry/SL/TP + reason
    ↓
G3b: Money Management (Python)
    - Lot = (balance × 10%) / sl_pip
    ↓
G3c: Guardian (Python)
    - Blocks: R:R < 1.0, active plan exists, consecutive_loss ≥ 3
    ↓
G4a: LINE Notify
G4b: Google Sheets Logger
G4c: Position Monitor (SL/TP check every M5 candle)
```

---

## 📊 **Strategy Overview**

**Source:** `strategy/XAUUSD_AI_Trading_System_v2.1.md` (29,483 chars)

### **Chart Types:**
1. **Uptrend:** 43-52° slope, swing points ascending
2. **Downtrend:** 43-52° slope, swing points descending
3. **Mountain:** Dome shape with symmetric bases
4. **Sideway:** Price range ≤ 50% of trend range

### **Techniques:**
1. **Twin Candle (แท่งคู่):** 2 parallel candles, body ≥ 5% range
2. **Breakout Follow (กรอบตามเจ้า):** Father candle + mother breakout
3. **Mai Ruay (ไม้เรว):** Mountain + reversal at base

### **Risk Rules:**
- Risk: 10% per plan (not 1.5%)
- R:R: ≥ 1.0 (not 1.2 or 1.5)
- Max consecutive loss: 3
- Loss limits: 30% pause, 50% permanent block

---

## 🔧 **Recent Fixes (2026-04-09 to 2026-04-14)**

### **Fix 1: Duplicate Prevention (All Techniques)**
**Problem:** Breakout_follow duplicates bypassed twin_candle-only check

**Solution:**
- Added `get_reference_price()` for all techniques
- Extended duplicate check to all techniques (not just twin_candle)
- Threshold: 30 pip + same chart_type

**Result:** ✅ 0 duplicates in 4-day backtest (blocked 38 attempts)

### **Fix 2: Race Condition (active_plan_id)**
**Problem:** Sheets sync delay → duplicate plans opened

**Solution:**
- In-memory cache for `active_plan_id`, `last_technical_price`, `last_plan_chart_type`
- Cache updated immediately when plan opens/closes
- Hybrid approach: reload from Sheets but preserve cache

**Result:** ✅ No race conditions, Guardian blocks work correctly

---

## 📈 **Backtest Results (2026-04-07 to 2026-04-10)**

```
Total Plans:      18
Win Rate:         92.3% (12W / 1L / 5P)
Total P&L:        $2,002.37
Cache Hit:        100%
Cost per Call:    $0.0197
Duplicates:       0
G2 Blocks:        74 (saved Claude calls)
```

**PENDING Orders:** 5 (27.8%) — normal for backtest limitation (date range ends)

---

## 🚀 **How to Use**

### **Setup:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY, SHEETS credentials
```

### **Run Modes:**
```bash
# Backtest (historical data)
python main.py --backtest --start 2026-04-07 --end 2026-04-10 --log-sheets

# Simulate (paper trading, real-time)
python main.py --simulate

# Live (real money - not implemented yet)
python main.py --live
```

### **Reset Sheets:**
```bash
python scripts/reset_sheets.py              # Reset all
python scripts/reset_sheets.py --keep-data  # Reset Portfolio State only
```

---

## 📁 **Key Files**

### **Must Read (Tier 1):**
1. `CLAUDE.md` — Rules, roles (Dev/Auditor), checklist
2. `strategy/XAUUSD_AI_Trading_System_v2.1.md` — Trading strategy (29KB)
3. `docs/TRAIDER_MASTER_PLAN_v2.1.md` — Architecture

### **Core Code (Tier 2):**
4. `config.py` — Risk config, constants, schema
5. `main.py` — Pipeline, backtest/simulate loop
6. `agents/g1_pattern_detector.py` — Pattern detection
7. `agents/g2_prefilter.py` — Duplicate prevention (**recent fix**)
8. `agents/g3_claude_decision.py` — Claude API integration
9. `agents/g4_position_monitor.py` — SL/TP monitoring
10. `agents/g4_sheets_logger.py` — Google Sheets logging

### **Deprecated (DO NOT USE):**
- ❌ `XAUUSD_Strategy_v5.md` — **Deleted** (obsolete)
- ❌ `agents/g3_decision.py` — Old G3 (replaced by g3_claude_decision.py)

---

## ⚠️ **Important Notes**

### **DO:**
- ✅ Use Claude API for ALL decisions (no mock/rule-based)
- ✅ Use 10% risk per plan (not 1.5%)
- ✅ Use R:R ≥ 1.0 (not 1.2 or 1.5)
- ✅ Read `XAUUSD_AI_Trading_System_v2.1.md` (not v5)
- ✅ Update cache when plan opens/closes
- ✅ Check CLAUDE.md before making changes

### **DON'T:**
- ❌ Reference `XAUUSD_Strategy_v5.md` (deleted)
- ❌ Use confidence threshold ≥ 0.70 (removed in v2.1)
- ❌ Clear `last_technical_price` when plan closes
- ❌ Skip Claude API calls (use real decisions always)
- ❌ Modify strategy rules in Python (keep in MD)

---

## 🎓 **For New Claude Chat Sessions**

**Quick Start Prompt:**
```
Read these 3 files first:
1. CLAUDE.md
2. strategy/XAUUSD_AI_Trading_System_v2.1.md
3. docs/TRAIDER_MASTER_PLAN_v2.1.md

Then summarize:
- What does this system do?
- What are the 6 agents and their roles?
- What is the risk management strategy?
- What techniques does G1 detect?
```

**For Code Work:**
```
Also read:
- config.py
- main.py
- agents/g2_prefilter.py (recent duplicate prevention fix)
- agents/g3_claude_decision.py (Claude integration)
```

---

## 📞 **Support**

- **Project Root:** `/Users/gunno/Desktop/projects/traider-phase1`
- **Google Sheets:** Trade Log + Portfolio State (see `.env`)
- **CLAUDE.md:** Full rules and checklist
- **Issues:** Check `G2_BLOCK_DIAGNOSIS.md`, `AUDIT_REPORT_*.md`

---

**Status:** ✅ Duplicate prevention fixed, ready for simulate mode
**Next Step:** Run `python main.py --simulate` for real-time testing
