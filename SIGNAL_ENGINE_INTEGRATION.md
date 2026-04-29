# Signal Engine Integration — Complete ✅

**Date:** 2026-04-23  
**Phase:** I v2.1 Signal Engine Integration  
**Status:** Integration complete, ready for auditor review

---

## 📋 Summary

Integrated `xauusd_signal.py` as the main Signal Engine, replacing G1 pattern detection:

- **Signal Engine** (xauusd_signal.py + swing_v414.py) provides: Entry, SL, TP, Lot
- **G1 Pattern Detector** → DEPRECATED (marked for backward compatibility only)
- **Claude API role** changed: Decision maker → **Reviewer** (approve/reject signals)
- **Architecture**: Single TF (M5 only), mountain state tracking for Round 2

---

## ✅ Completed Tasks

### 1. Core Files Created/Updated

| File | Action | Purpose |
|------|--------|---------|
| `utils/xauusd_signal.py` | ✅ Created | Main signal detection engine (800+ lines, copied as-is) |
| `utils/swing_v414.py` | ✅ Created | Swing High/Low detection (176 lines, copied as-is) |
| `utils/signal_engine.py` | ✅ Created | Wrapper for integration with existing codebase |
| `main.py` | ✅ Updated | Step 2: Use `run_signal_engine()` instead of G1 |
| `agents/g2_prefilter.py` | ✅ Updated | Work with signal format, simplified setup checks |
| `agents/g3_analyst.py` | ✅ Updated | Support Reviewer mode (approve/reject signal) |
| `agents/g1_pattern_detector.py` | ✅ Deprecated | Marked as deprecated, kept for backward compat |
| `tests/test_signal_engine.py` | ✅ Created | 7 unit tests (all passing) |

### 2. Architecture Changes

**Old Pipeline (G1 Pattern Detection):**
```
G1 Pattern Detector (MTF: H4, H1, M30, M15, M5, M1)
  → Detect chart types + techniques
  → world_state (no Entry/SL/TP)
    ↓
G2 Pre-filter
  → Basic checks
    ↓
G3a Analyst (Decision Maker)
  → Calculate Entry, SL, TP
  → BUY/SELL/SKIP
```

**New Pipeline (Signal Engine):**
```
Signal Engine (Single TF: M5)
  → xauusd_signal.py + swing_v414.py
  → Signal(Entry, SL, TP, Lot, R:R) OR None
  → world_state with signal object
    ↓
G2 Pre-filter
  → Check signal validity, R:R ≥ 1.0
  → Duplicate prevention (signal.entry)
    ↓
G3a Analyst (Reviewer Mode)
  → Review signal, approve/reject
  → No calculation, only validation
```

### 3. Key Features

**Signal Engine (utils/signal_engine.py):**
- Converts candle dict → OHLC format
- Calls `find_signal(bars, portfolio, mountain_state)`
- Converts Signal → world_state dict
- Tracks mountain_state for Round 2 detection

**G2 Pre-filter (updated):**
- Validates signal exists and has Entry/SL/TP
- Checks R:R ≥ 1.0 (from signal)
- Duplicate prevention using `signal.entry`
- Removed touch validation (Signal Engine handles internally)

**G3a Analyst (Reviewer mode):**
- `reviewer_mode` flag when signal provided
- Prompt asks Claude to review signal, not create decision
- If APPROVE → use signal values as-is
- If SKIP → provide reason

**Mountain State Tracking:**
- Stored in `self.mountain_state` (main.py)
- Round 1: Creates state with peak price and entry
- Round 2: Uses state, then clears after entry

### 4. Unit Tests (7 tests, all passing)

```bash
$ python -m pytest tests/test_signal_engine.py -v
```

**Test Coverage:**
1. ✅ `test_convert_candles_to_ohlc` - Format conversion
2. ✅ `test_run_signal_engine_with_signal` - Valid signal returned
3. ✅ `test_run_signal_engine_no_signal` - No signal (unclear)
4. ✅ `test_run_signal_engine_insufficient_data` - Less than 55 candles
5. ✅ `test_mountain_state_tracking_round1` - Mountain R1 detection
6. ✅ `test_mountain_state_tracking_round2` - Mountain R2 detection
7. ✅ `test_detect_session` - Session detection from timestamp

---

## 🔍 Before Running — Auditor Checklist

Before running backtest or simulate, verify:

### Signal Engine Integration:
- [ ] `utils/xauusd_signal.py` exists (800+ lines, no modifications)
- [ ] `utils/swing_v414.py` exists (176 lines, no modifications)
- [ ] `utils/signal_engine.py` exists (wrapper, ~260 lines)

### Main Pipeline (main.py):
- [ ] Step 2 uses `run_signal_engine()` instead of `self.g1.scan_all_tf()`
- [ ] `self.mountain_state` initialized in `__init__`
- [ ] Mountain state updated from `world_state['mountain_state']`
- [ ] G1 import marked as deprecated (commented out or with DEPRECATED comment)

### G2 Pre-filter (g2_prefilter.py):
- [ ] Check 5: Validates signal exists and has Entry/SL/TP
- [ ] Check 5: Validates R:R ≥ 1.0
- [ ] Check 6: Uses `signal.entry` for duplicate prevention
- [ ] Check 7: Touch validation removed (or commented out)
- [ ] `get_reference_price()` uses `signal.entry` when available

### G3a Analyst (g3_analyst.py):
- [ ] `build_grounding()` includes `reviewer_mode` flag
- [ ] `build_grounding()` includes `signal` data when available
- [ ] `_build_user_prompt()` checks `reviewer_mode` flag
- [ ] Reviewer mode prompt asks to review signal, not create decision
- [ ] Fallback to original mode if no signal (backward compat)

### Deprecation Markers:
- [ ] `agents/g1_pattern_detector.py` has deprecation warning in docstring
- [ ] `main.py` imports G1 with "DEPRECATED" comment

### Unit Tests:
- [ ] All 7 tests in `tests/test_signal_engine.py` pass
- [ ] Run: `python -m pytest tests/test_signal_engine.py -v`

---

## 🚀 Next Steps

After auditor verification:

1. **Run unit tests**: `python -m pytest tests/test_signal_engine.py -v`
2. **Test single cycle**: `python main.py --simulate` (1 cycle, check logs)
3. **Backtest short period**: `python main.py --backtest --start 2026-04-01 --end 2026-04-07`
4. **Review audit report**: Check SKIP rate, cost per call, cache hit rate

---

## 📊 Expected Metrics

After integration, expect:

- **SKIP rate**: May increase initially (Signal Engine is stricter)
- **Cost per call**: Should remain < $0.010 (Reviewer mode uses same cache)
- **Cache hit rate**: Should be > 80% (same strategy prompt)
- **G2 block rate**: Should increase (more pre-filtering with signal validation)

---

## 🔧 Rollback Plan

If issues occur, rollback by:

1. Uncomment G1 initialization in `main.py` line ~306
2. Revert Step 2 in `run_once()` to use `self.g1.scan_all_tf()`
3. Revert `g2_prefilter.py` changes (use git to restore old version)
4. Revert `g3_analyst.py` changes (use git to restore old version)

Git reference: Compare with commit before integration

---

## 📝 Notes

- Signal Engine files (`xauusd_signal.py`, `swing_v414.py`) are **read-only** — no modifications
- G1 pattern detector kept for backward compatibility (may remove in Phase II)
- Mountain state currently tracked in-memory (main.py) — may add to Sheets later
- Reviewer mode is minimal implementation — full refactor can be done in Phase II

---

**Integration completed by:** Claude Code  
**Ready for:** @Auditor verification  
**Last updated:** 2026-04-23
