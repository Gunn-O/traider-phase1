# Changelog — Tra(i)der Phase I v2.1

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2026-04-11] — Session 4: Critical Fixes & System Validation

### 🔴 CRITICAL FIX: Position Monitor Not Closing Positions

**Issue:** Position Monitor not closing positions in backtest mode  
**Impact:** Backtest unusable — 1 plan blocks entire test, win rate unmeasurable  
**Root Cause:** Orders missing `result: 'PENDING'` field → filter returned empty list

### Changed
- **[main.py:378-385](main.py#L378-L385)**: Added required fields to orders before PositionMonitor
  - `order['plan_id']` — Required for portfolio state updates
  - `order['result'] = 'PENDING'` — **CRITICAL** for position filtering
  - `order['entry_price']`, `order['sl_price']`, `order['tp_price']`, `order['lot_size']` — Aliases for compatibility

- **[g4_position_monitor.py:286-295](agents/g4_position_monitor.py#L286-L295)**: Track closed plan IDs
  - Collect `plan_id` from closed orders
  - Call `_update_portfolio_after_closes()` when plans complete

- **[g4_position_monitor.py:357-395](agents/g4_position_monitor.py#L357-L395)**: New method `_update_portfolio_after_closes()`
  - Auto-clear `active_plan_id` when all orders in plan are closed
  - Update `consecutive_loss` counter (increment on LOSS, reset on WIN)
  - Update `realized_pnl_usd`

### Documentation
- **[AUDIT_REPORT_20260409.md](AUDIT_REPORT_20260409.md)**: Added addendum documenting bug and fix
- **[CLAUDE.md](CLAUDE.md)**: Updated Auditor checklist with required order fields

### Verification
```bash
✅ Unit test: TP hit → WIN +$30, SL hit → LOSS -$15
✅ Order fields: All required fields present
✅ Integration: Orders ready for PositionMonitor
```

### 🔧 ENHANCEMENT: Multi-Order System

**Changed:**
- **[config.py](config.py)**: `calc_lot()` returns `suggested_orders` (1-3 based on lot size)
- **[g3_money_management.py](agents/g3_money_management.py)**: `create_order_plan()` multi-order logic
  - Winrate test mode: Always 1 order with 0.01 lot
  - Simulate mode: 1-3 orders with offset pricing
  - Offset calculation: `max(range_usd * 0.05, 3.0)` USD per order
  - R:R check per entry (skip orders with R:R < 1.0)
  - Entry spread:
    - BUY: `[base+offset, base, base-offset]`
    - SELL: `[base-offset, base, base+offset]`

**Impact:**
- Better position sizing and risk distribution
- DCA-style entries for larger positions
- Maintains R:R ≥ 1.0 for each individual order

### 🧹 REMOVED: TF Whitelist Feature

**Removed:**
- `SIMULATE_TF_LIST` from [config.py](config.py)
- `BACKTEST_TF_LIST` from [config.py](config.py)

**Reason:** User requested reversal of previous TF filtering implementation  
**Impact:** System now scans all 6 timeframes regardless of mode

### 📖 DOCUMENTATION: TF Independence Principle

**Added:**
- **[strategy/XAUUSD_AI_Trading_System_v2.1.md:730](strategy/XAUUSD_AI_Trading_System_v2.1.md#L730)**: New section explaining MTF independence
  - Each TF analyzes from its own 55 candles
  - No consensus required between TFs
  - Example: H4=uptrend but M1=downtrend (quality สูงกว่า) → SELL ตาม M1

**Impact:** Clarifies that each timeframe is analyzed independently, not hierarchically

### 🐛 FIX: Mountain Instruction Complete Rewrite

**Fixed:**
- **[g3_claude_decision.py](agents/g3_claude_decision.py)**: Mountain pattern instruction completely wrong
  - ❌ Old: "Entry: SELL ใกล้ Peak ด้วย Twin Candle"
  - ✅ New: "Entry: BUY เมื่อราคาลงถึงฐานด้านขวา (≈ ฐานซ้าย)"
  - Added explicit threshold: ">50% ของ Range (เช่น 51%, 60%, 70% ผ่านทั้งหมด)"

**Impact:** Claude now correctly identifies mountain BUY setups instead of trying to SELL at peak

### 🚀 ADDED: Management Scripts

**Added:**
- **[scripts/run_simulate.sh](scripts/run_simulate.sh)**: Foreground simulator (real-time logs)
- **[scripts/run_daemon.sh](scripts/run_daemon.sh)**: Background daemon (nohup)
- **[scripts/run_winrate_test.sh](scripts/run_winrate_test.sh)**: Winrate test mode (0.01 lot)
- **[scripts/run_backtest.sh](scripts/run_backtest.sh)**: Backtest runner with date range
- **[scripts/stop_all.sh](scripts/stop_all.sh)**: Stop all running processes
- **[scripts/status.sh](scripts/status.sh)**: Check system status
- **[scripts/reset_sheets.py](scripts/reset_sheets.py)**: Reset Google Sheets
- **[scripts/README.md](scripts/README.md)**: Complete scripts documentation

**Impact:** Easy system management without remembering complex commands

### 📊 UPDATED: Cost Warning Threshold

**Changed:**
- **[main.py](main.py)**: Cost warning threshold `$0.020` → `$0.030`
- **Reason:** Normal cost with cache is ~$0.0192/call (cache_creation + cache_read)
- **Impact:** Fewer false warnings while still catching real anomalies

---

## [2026-04-09] — Session 3: System Audit & Optimization

### Added
- Comprehensive audit report: [AUDIT_REPORT_20260409.md](AUDIT_REPORT_20260409.md)
- Grade: B+ (85%)
- Identified critical issues:
  - Claude cache not functioning
  - Guardian missing confidence and R:R checks
  - TF fetching inefficiency

---

## [2026-04-09] — Session 2: G2 Setup Pre-check Implementation

### Added
- **[agents/g2_prefilter.py](agents/g2_prefilter.py)**: Check 5 — Setup Pre-check
  - Block before Claude if no valid setup detected
  - uptrend/downtrend requires twin_candle OR breakout_box
  - mountain requires `tolerance_ok = True`

### Impact
- Claude calls reduced by 100% for no-setup cases
- Cost savings: ~$16-20 per 705-candle backtest
- Before: $0.024/candle
- After: $0.00/candle

---

## [2026-04-08] — Session 1: Pattern Detection Fixes

### Fixed
- **[g3_claude_decision.py](agents/g3_claude_decision.py)**: Mountain instruction completely rewritten
  - Old (WRONG): "Entry: SELL ใกล้ Peak"
  - New (CORRECT): "Entry: BUY เมื่อราคาลงถึงฐานด้านขวา (ใกล้ Left Base)"
  - Added explicit threshold: "ความสูงภูเขา > 50% ของ Range"

### 🐛 FIX: Twin Candle Detection Thresholds

**Changed:**
- **[utils/pattern_utils.py](utils/pattern_utils.py)**: Twin candle detection constants
  - `MIN_TWIN_CANDLE_BODY`: Reduced to 0.025 (2.5% of range, ~180 pip)
  - `MAX_TWIN_CANDLE_GAP`: Reduced to 50 pip (was too strict)

**Reason:** Previous thresholds too strict, missing valid setups  
**Impact:** Better twin candle detection rate

---

## [2026-04-07] — Session 0: Backtest Forward Walk Implementation

### Added
- **[main.py](main.py)**: `_resample_m5_to_all_tf()` method
  - Resample M5 slice to all timeframes for backtest
  - Build 55-candle sliding window up to current point in time

### Changed
- **[main.py](main.py)**: `run_backtest()` forward walk
  - Loop through M5 candles: for each candle at index i, use candles[i-54:i+1]
  - No future data leakage
  - Proper historical simulation

- **[main.py](main.py)**: `run_once()` signature
  - Accept `candles_by_tf` and `current_candle` parameters
  - Allow pre-fetched data for backtest mode

- **[main.py](main.py)**: `monitor_positions()`
  - Accept `current_candle` parameter
  - Use provided candle in backtest mode

### Fixed
- Backtest was fetching "current" data every loop (price stayed same: 4749.685)
- Now walks forward through historical candles (prices change: 4765.62, 4763.84, etc.)

---

## [2026-04-02] — Thai Localization

### Changed
- **Commit:** `51bb99d`
- Thai names for conditions and patterns throughout the system

---

## [2026-04-01] — TradingView Integration & Cleanup

### Added
- **Commit:** `4434364`
- TradingView data connector integration
- Position tracker with price accuracy fix
- Duplicate trade prevention

### Removed
- **Commit:** `83de311`
- yfinance backtest code (replaced by TradingView)
- Obsolete backtest implementations

### Changed
- **Commit:** `eaaaad1`
- Strategy v5 concise version complete with all patterns

---

## [2026-03-31] — Foundation Fixes

### Fixed
- **Commit:** `fbc7bd7`
- Anti-clustering logic
- Stop Loss calculation bug
- G1 mountain detection accuracy

**Version:** v1.1

---

## [2026-03-28] — Initial Commit

### Added
- **Commit:** `5f4b779`
- Project initialization
- Basic structure and configuration

---

## Legend

- 🔴 **CRITICAL** — System-breaking bug or security issue
- 🐛 **FIX** — Bug fix
- 🔧 **ENHANCEMENT** — Feature improvement
- 🚀 **ADDED** — New feature
- 🧹 **REMOVED** — Removed feature
- 📖 **DOCUMENTATION** — Documentation update
- 📊 **CHANGED** — Modified existing functionality

---

## Format Guide

This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format:
- **Added** — New features
- **Changed** — Changes to existing functionality
- **Fixed** — Bug fixes
- **Removed** — Removed features
- **Security** — Security fixes
- **Deprecated** — Soon-to-be removed features
