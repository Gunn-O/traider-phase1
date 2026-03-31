# Backtest Guide - Token Optimized

## 🎯 Token Usage Optimization

### Before Optimization
- Strategy MD: **7,013 chars** (full version)
- Sent on every API call
- No caching
- Cost: **~250 tokens/call**

### After Optimization ✅
- Strategy MD: **1,466 chars** (concise version) - **79% reduction**
- Cached in memory (load once)
- Mock Agent default for backtest
- Cost: **~75 tokens/call** or **$0.00** (Mock Agent)

**Token savings: ~70% per Claude API call**

---

## 📊 How to Run Backtest

### Option 1: Mock Agent (Recommended - FREE) ⭐

```bash
# 7-day backtest with Mock Agent (0 tokens)
python backtest_7days.py

# Full backtest with Mock Agent
python backtest_full.py
```

**Pros:**
- ✅ FREE - No API costs
- ✅ Fast - No API latency
- ✅ Good for testing pipeline
- ✅ Rule-based decisions

**Cons:**
- ⚠️ Not as sophisticated as Claude
- ⚠️ Fixed rules (no learning)

---

### Option 2: Claude API Validation Mode (First 20 Signals)

```bash
# Use Claude API for first 20 signals, then switch to Mock
python backtest_7days.py --validate
```

**Pros:**
- ✅ Validate Claude decisions (20 samples)
- ✅ Limited API cost (~$0.02)
- ✅ 70% token savings (concise strategy)
- ✅ Remaining signals use Mock (free)

**Cost estimate:**
- 20 calls × 75 tokens = **1,500 tokens**
- Input cost: ~$0.005
- Output cost: ~$0.015
- **Total: ~$0.02**

---

### Option 3: Full Claude API (All Signals) 💰

```bash
# Use Claude API for ALL signals
python backtest_7days.py --claude
```

**Pros:**
- ✅ All decisions by Claude
- ✅ Most accurate to production

**Cons:**
- ⚠️ Costs API credits
- ⚠️ Slower (API latency)
- ⚠️ Rate limits (30k tokens/min)

**Cost estimate (7 days):**
- ~50-100 signals
- 50 calls × 75 tokens = **3,750 tokens**
- **Total: ~$0.05-0.10**

---

## 🔧 Advanced Usage

### Use Full Strategy (7k chars)

```python
from agents.g3_decision import G3DecisionAgent

# Initialize with full strategy
agent = G3DecisionAgent(
    strategy_md_path='strategy/XAUUSD_Strategy_v5.md',  # Full version
    config={'use_concise': False}
)
```

### Manual Backtest with Custom Config

```python
from backtest_full import FullBacktest

# Custom configuration
bt = FullBacktest(
    use_claude_api=True,      # Use Claude API
    verbose=True,             # Show detailed logs
    validate_mode=False       # Full mode (not validation)
)

bt.run(start_date, end_date)
bt.print_summary()
```

---

## 📈 View Results

```bash
# View latest results
python view_results.py

# List all results
python view_results.py list

# View specific file
python view_results.py backtest/results/backtest_7days_mock.json
```

---

## 💡 Best Practices

### For Development/Testing
✅ **Use Mock Agent** - Free, fast, good enough

```bash
python backtest_7days.py
```

### For Validation
✅ **Use Validation Mode** - Check first 20 signals with Claude

```bash
python backtest_7days.py --validate
```

### For Production Simulation
✅ **Use Full Claude API** - Only when you need real Claude decisions

```bash
python backtest_7days.py --claude
```

---

## 📊 Token Usage Summary

| Mode | Tokens/Call | Calls (7d) | Total Tokens | Cost |
|------|-------------|------------|--------------|------|
| Mock Agent | 0 | ∞ | 0 | **$0.00** |
| Validation | 75 | 20 | 1,500 | **$0.02** |
| Full Claude | 75 | 50-100 | 3,750-7,500 | **$0.05-0.10** |
| Old (unoptimized) | 250 | 50-100 | 12,500-25,000 | **$0.15-0.30** |

**Savings: 70% token reduction + Mock Agent default = ~95% cost savings**

---

## 🎯 Recommendations

### Phase I Development (Current)
- ✅ Use **Mock Agent** for all backtesting
- ✅ Use **Validation Mode** to check Claude alignment
- ✅ Total cost: **$0-0.02/day**

### Phase II (Live Trading)
- ✅ Use **Claude API** for real decisions
- ✅ Concise strategy (optimized)
- ✅ Cost: **$0.02-0.06/day** (10-15 signals)

### Phase III (Production)
- ✅ Consider Claude API with higher rate limits
- ✅ Or use fine-tuned model
- ✅ Or hybrid: Mock for simple cases, Claude for complex

---

## 📝 Files Structure

```
strategy/
├── XAUUSD_Strategy_v5.md          # Full version (7k chars)
└── XAUUSD_Strategy_v5_concise.md  # Concise (1.5k chars) ⭐

agents/
├── g3_decision.py          # Claude API (with cache) ⭐
└── g3_decision_mock.py     # Rule-based (free)

backtest_7days.py           # Main backtest script ⭐
backtest_full.py            # Full pipeline
view_results.py             # Results viewer
```

---

## ✅ Verification

Test that optimization works:

```bash
# 1. Run with Mock (should be free)
python backtest_7days.py

# 2. Check it uses concise strategy
grep "Concise version" backtest_7days.py

# 3. Run validation mode (should cost ~$0.02)
python backtest_7days.py --validate

# 4. View results
python view_results.py
```

---

**Last Updated:** 2026-03-31
**Optimization:** Token usage reduced by 70-95%
