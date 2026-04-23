# Claude Reviewer Mode — Implementation Complete ✅

**Date:** 2026-04-23  
**Version:** V4.20  
**Status:** Ready for testing

---

## 📋 Summary

เปลี่ยน Claude จาก **Decision Maker** → **Reviewer**  
Signal Engine คำนวณ Entry/SL/TP/Lot → Claude แค่ approve/reject

---

## ✅ Completed Tasks

### STEP 1: Reviewer System Prompt ✅

Created: [`strategy/XAUUSD_System_Prompt_Reviewer.md`](strategy/XAUUSD_System_Prompt_Reviewer.md)

- **Content:** 49 lines (สั้นกว่า V43 มาก → cache ดีกว่า)
- **Role:** Reviewer only (ไม่คำนวณ Entry/SL/TP)
- **Output:** JSON format (decision, confidence, reason, obstacles)
- **Rules:** 
  - APPROVE ถ้าไม่แน่ใจ
  - REJECT เฉพาะถ้าเห็นปัญหาชัดเจนมาก
  - ตรวจแค่ 3 ข้อ: Pattern ตรง OHLC, Entry สมเหตุสมผล, อุปสรรค TP

### STEP 2: Modified agents/g3_analyst.py ✅

**2a. Changed __init__():**
- ✅ โหลด `XAUUSD_System_Prompt_Reviewer.md` แทน V43
- ✅ เก็บใน `self.reviewer_content`
- ✅ Log: "Reviewer Prompt loaded (X chars)"

**2b. Added review() method:**
- ✅ รับ world_state, balance, portfolio_state, reflection_summary
- ✅ Build signal format text + OHLC last 5 bars
- ✅ เรียก _call_claude_review()
- ✅ Validate output (decision, confidence, reason, obstacles)
- ✅ API fail → APPROVE อัตโนมัติ
- ✅ คืน: {"review": {...}, "llm_log": {...}}

**2c. Added _call_claude_review() method:**
- ✅ ใช้ reviewer_content ใน system_blocks (cached)
- ✅ max_tokens=300 (ลดจาก 2048)
- ✅ Retry logic (3 attempts, wait 60s on rate limit)
- ✅ Cost calculation (Sonnet 4 pricing)
- ✅ Cache hit detection
- ✅ Push to dashboard (add_agent_log)
- ✅ JSON parse with markdown removal

**2d. Modified decide() method:**
- ✅ Backward compatible wrapper
- ✅ ถ้า world_state มี signal → เรียก review()
- ✅ แปลง review → decision format (ใช้ค่าจาก signal engine)
- ✅ APPROVE → ใช้ sig.entry, sig.sl, sig.tp_order เป๊ะ
- ✅ REJECT → SKIP พร้อม reason
- ✅ ถ้าไม่มี signal → SKIP

### STEP 3: Updated CLAUDE.md ✅

Added section: **⚠️ V4.20 Architecture Change**

- ✅ Signal Engine integration notes
- ✅ Claude role change (Decision Maker → Reviewer)
- ✅ New system prompt path
- ✅ Deprecated files (G1, V43 prompt)
- ✅ Updated architecture pipeline diagram
- ✅ max_tokens: 300 note

### STEP 4: Deprecation Markers ✅

- ✅ `agents/g1_pattern_detector.py` — marked DEPRECATED
- ✅ `strategy/XAUUSD_System_PromptV43.md` — reference only
- ✅ `docs/pattern_detection_spec.md` — reference only

---

## 🔧 Technical Details

**Old Flow (DEPRECATED):**
```
G1 → detect pattern
  ↓
G2 → pre-filter
  ↓
G3a → Claude calculates Entry/SL/TP (max_tokens=2048)
  ↓
G3b → adjust lot
  ↓
G4 → execute
```

**New Flow (V4.20):**
```
Signal Engine → Entry/SL/TP/Lot calculated
  ↓
G2 → validate signal, R:R ≥ 1.0
  ↓
G3a → Claude reviews signal (max_tokens=300)
      APPROVE → use signal values as-is
      REJECT  → SKIP
  ↓
G4 → execute
```

**Key Differences:**
- **Before:** Claude calculates → 2048 tokens, expensive
- **After:** Claude reviews → 300 tokens, cheap
- **Cost:** Expected ~70% reduction (2048 → 300 tokens)
- **Cache:** Better (shorter prompt = faster cache)

---

## 📊 Expected Metrics (After Implementation)

| Metric | Target | Notes |
|--------|--------|-------|
| max_tokens | 300 | ลดจาก 2048 (85% reduction) |
| Cost per call | < $0.005 | ลดจาก ~$0.0125 (60% reduction) |
| Cache hit rate | > 90% | Shorter prompt = better cache |
| Response time | < 1s | Faster due to shorter output |

---

## 🧪 Next: Testing Required

### Test 1: Unit Tests (TODO)

Create `tests/test_reviewer.py`:
```python
def test_review_approve_uptrend():
    # Signal Engine ให้ UPTREND BUY signal
    # Reviewer ควร APPROVE

def test_review_reject_bad_entry():
    # Signal Engine ให้ entry ห่างจากราคาปัจจุบันมาก
    # Reviewer ควร REJECT

def test_review_api_fail_auto_approve():
    # Mock API fail
    # Reviewer ควร auto APPROVE (ไม่บล็อกระบบ)
```

### Test 2: Integration Test

Run backtest with Reviewer mode:
```bash
python main.py --backtest --start 2026-04-01 --end 2026-04-07
```

**Expected Results:**
- ✅ Signal Engine generates signals
- ✅ G2 pre-filter validates
- ✅ Claude Reviewer approves/rejects
- ✅ Cost per call < $0.005
- ✅ Some signals APPROVED → plans opened

### Test 3: Compare Results

| Metric | Decision Maker (Old) | Reviewer (New) | Improvement |
|--------|---------------------|----------------|-------------|
| Cost/call | $0.0125 | < $0.005 | ~60% ↓ |
| max_tokens | 2048 | 300 | 85% ↓ |
| Response time | ~2s | < 1s | 50% ↓ |
| Cache hit | 98% | > 95% | Similar |

---

## ⚠️ Important Notes

1. **API Fail Handling:**
   - Old: SKIP (block trading)
   - New: APPROVE (trust Signal Engine)

2. **Backward Compatibility:**
   - `decide()` method still works
   - Returns same format as before
   - No changes needed in main.py

3. **Signal Engine Trust:**
   - Signal Engine คำนวณถูกต้องแล้ว
   - Claude เป็นแค่ safety check
   - Default behavior: APPROVE

4. **Prompt Caching:**
   - Reviewer prompt สั้นกว่า V43 มาก
   - Cache hit ควรดีกว่าเดิม
   - Cost ต่ำกว่าแม้ cache miss

---

## 🔍 @Auditor Checklist

Before running backtest, verify:

### Files Created:
- [ ] `strategy/XAUUSD_System_Prompt_Reviewer.md` exists
- [ ] Content มี pattern descriptions, rules, output format

### agents/g3_analyst.py Modified:
- [ ] `__init__()` โหลด reviewer_content ไม่ใช่ system_prompt_content
- [ ] `review()` method มีอยู่
- [ ] `_call_claude_review()` method มีอยู่
- [ ] `_call_claude_review()` ใช้ max_tokens=300
- [ ] `decide()` backward compatible (เรียก review() ถ้ามี signal)
- [ ] API fail → APPROVE อัตโนมัติ

### CLAUDE.md Updated:
- [ ] มี section "V4.20 Architecture Change"
- [ ] อธิบาย Signal Engine integration
- [ ] อธิบาย Claude role change
- [ ] ระบุ deprecated files
- [ ] Updated architecture diagram

### Deprecation:
- [ ] `agents/g1_pattern_detector.py` มี DEPRECATED warning
- [ ] CLAUDE.md ระบุว่า V43 prompt เป็น reference only

---

**Implementation:** @Dev  
**Ready for:** @Auditor verification + Testing  
**Last updated:** 2026-04-23  
**Version:** V4.20
