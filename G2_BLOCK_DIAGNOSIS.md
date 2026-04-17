# G2 Block 100% - Diagnosis Report

**Date:** 2026-04-09  
**Auditor:** Claude Code (@Auditor Mode)  
**Status:** ⚠️ NOT READY for production

---

## Executive Summary

G2 is blocking 100% of signals **by design** - it's working correctly, but G1 has a fundamental flaw that prevents setup detection.

**Root Cause:** G1 selects timeframe based on chart quality (H4 = best uptrend), but only scans for entry setups (twin candles) in that selected timeframe. Twin candles exist in M5, not H4, resulting in zero setups found.

---

## Detailed Findings

### 1. Twin Candle Detection - Working ✅

**Manual Test Results:**
```
Range: 27.65 USD = 2,765 pip
5% threshold: 0.69 USD (69 pip)
Twin candles found: 33 pairs in 55 M5 bars

Examples:
  idx=1: body1=1.16 USD, body2=3.89 USD, gap=2.0 pip
  idx=2: body1=3.89 USD, body2=1.63 USD, gap=3.0 pip
  idx=3: body1=1.63 USD, body2=3.68 USD, gap=11.5 pip
```

**Conclusion:** Threshold (2.5%) is correct. Detection logic works.

### 2. Price Verification - Correct ✅

```
XAUUSD/OANDA: $4,721-4,723
3-day range: $250.59 USD
```

Matches real XAUUSD spot prices. Data is accurate.

### 3. G1 Output - Found the Bug ❌

**G1 World State:**
```python
{
  'selected_tf': 'H4',           # Selected H4 (best chart quality)
  'chart_type': 'uptrend',       # ✓ Detected correctly
  'quality': 0.85,               # ✓ High quality
  'technique_candidate': 'twin_candle',  # ✓ Knows what to look for
  'twin_candle': {
    'found': False               # ✗ Didn't find it in H4!
  },
  'father_candle': {
    'found': False               # ✗ No father candle either
  }
}
```

**The Problem:**
1. G1 scans all 6 timeframes for chart patterns (uptrend, downtrend, etc.)
2. G1 picks H4 as "best" because it has highest quality uptrend (0.85)
3. BUT G1 only looks for twin candles in H4 data
4. Twin candles exist in M5 (33 pairs!), not in H4
5. Result: `technique_candidate = "twin_candle"` but `found = False`

**G2's Response:**
```python
# G2 Setup Pre-check (agents/g2_prefilter.py line 92-106)
if chart_type in ['uptrend', 'downtrend']:
    has_twin = twin_candle.get('found', False)
    has_father = father_candle.get('found', False)
    
    if not has_twin and not has_father:
        SKIP: "uptrend แต่ไม่มีแท่งคู่และไม่มีกรอบตามเจ้า"
```

G2 is **working correctly** - there's no setup in the selected timeframe!

---

## Root Cause Analysis

### The Architectural Flaw

**Current G1 Logic:**
```
1. Scan ALL timeframes for chart patterns
2. Select best timeframe by quality score
3. Look for setups ONLY in selected timeframe
4. If no setup found → technique_candidate="skip" (or found=False)
```

**Problem:**
- Best chart pattern (H4 uptrend, 0.85) != Best entry point (M5 twin candles)
- G1 prioritizes chart quality over setup availability
- Misses actionable setups in lower timeframes

**Example from Current Data:**
```
H4: uptrend quality=0.85, twin_candle=No  → Selected but unusable
M5: uptrend quality=0.66, twin_candle=Yes → Ignored despite having entry!
```

---

## Solutions

### Option 1: Fix G1 Scoring (Best Long-term) 🎯

**Change:** Include setup availability in timeframe selection

```python
def select_best_setup(tf_results):
    scores = {}
    for tf, result in tf_results.items():
        quality = result['quality']
        has_setup = result['twin_candle']['found'] or result['father_candle']['found']
        
        # Boost score if setup found
        setup_multiplier = 2.0 if has_setup else 0.5
        scores[tf] = quality * setup_multiplier
    
    return max(scores, key=scores.get)
```

**Impact:**
- H4: 0.85 × 0.5 = 0.425
- M5: 0.66 × 2.0 = 1.320 → **M5 selected** ✓

**Pros:**
- Solves root cause
- Logical: prioritize actionable setups

**Cons:**
- Requires G1 refactor
- Need to scan setups across ALL TFs (currently only scans selected TF)

**Effort:** 1-2 hours

---

### Option 2: G2 Cross-TF Setup Check (Quick Fix) ⚡

**Change:** G2 checks for setups across ALL timeframes, not just selected one

```python
# In g2_prefilter.py, replace lines 92-106:
if chart_type in ['uptrend', 'downtrend']:
    # Check ALL timeframes for setups
    tf_results = world_state.get('tf_results', {})
    
    any_twin = any(
        result.get('twin_candle', {}).get('found', False)
        for result in tf_results.values()
    )
    any_father = any(
        result.get('father_candle', {}).get('found', False)
        for result in tf_results.values()
    )
    
    if not any_twin and not any_father:
        SKIP: "ไม่มี setup ในทุก TF"
```

**Pros:**
- Fast to implement (5 minutes)
- Works around G1 limitation
- Unblocks deployment

**Cons:**
- Doesn't fix root cause
- May select suboptimal TF for entry

**Effort:** 5 minutes

---

### Option 3: Lower Quality Threshold (Workaround) 🔧

**Change:** Allow lower quality TFs to compete

```python
# In g1_pattern_detector.py
MIN_QUALITY = 0.50  # from 0.70
```

**Why this won't work:**
- M5 quality (0.66) > H4 quality (0.85) → H4 still wins
- Doesn't solve the fundamental issue
- Just allows more bad charts through

**Not recommended.**

---

## Recommendation

**Deploy with Option 2** (G2 Cross-TF Setup Check)

**Rationale:**
1. **Fast:** 5 minutes to implement
2. **Effective:** Unblocks 100% → 10-30% pass rate
3. **Safe:** Doesn't change G1 logic (less risk)
4. **Reversible:** Can replace with Option 1 in v2.2

**Implementation Plan:**
```
1. Edit agents/g2_prefilter.py (5 min)
2. Run same backtest (7 min)
3. Verify G2 pass rate > 0% (1 min)
4. Deploy (if > 0%)

Total: 15 minutes
```

**Expected Results After Fix:**
- G2 pass rate: **10-30%** (from 0%)
- Claude calls: **12-36** per 120 candles (from 0)
- Actual trades: **1-5** (after Claude + Guardian filters)
- Cost: **$0.20-0.60** per 120 candles (acceptable)

---

## Deploy Decision

**Current Status:** ⚠️ **NOT READY**

**Blocking Issues:**
- ❌ G2 blocks 100% (by design, but useless)
- ❌ Cannot generate any trades
- ❌ Cannot test Claude cache (no calls)
- ❌ Cannot test Guardian checks (no calls)

**Action Required:**
1. ✅ Implement Option 2 (G2 cross-TF check)
2. ✅ Backtest with same data
3. ✅ Verify G2 pass rate > 0%
4. ✅ See at least 1 Claude call
5. ✅ Then DEPLOY

**After Fix:**
- Ready for Phase I simulated trading
- Can finally test cache and guardian
- Can collect real signal data

---

**Report Generated:** 2026-04-09 13:05:00  
**Next Action:** Implement Option 2 → Retest → Deploy
