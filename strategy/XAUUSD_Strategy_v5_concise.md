# XAUUSD Strategy v5.0 - Concise (for Claude API)

## Conditions (A1-A6)
- **A1 Uptrend**: BUY only | 80 candles | Higher High & Higher Low
- **A2 Downtrend**: SELL only | 80 candles | Lower High & Lower Low
- **A3 Mountain (ภูเขา)**: BUY at base only | 50 candles
  - ฐานต้องไม่ลอย, ยอดไม่แบน, H1 ต้องไม่ bearish
  - ห้ามเข้าลอยเกิน 200 points จากฐาน
- **A4 ในกรอบ ขาขึ้น**: BUY ขอบล่าง (หลัก), SELL ขอบบน (รอง)
- **A5 ในกรอบ ขาลง**: SELL ขอบบน (หลัก), BUY ขอบล่าง (รอง)
  - SKIP ถ้ากรอบแคบ < 15 pip
- **A6 Unclear**: B1 ไม้รวย หรือ B3 แนวเด้ง เท่านั้น

## Patterns (B1-B3)
- **B1 ไม้รวย (Spike Reversal)**:
  - Spike 60-100% ของ 50 แท่งก่อนหน้า
  - Lower/Upper wick ≥ 1.5x body
  - BUY: RSI ≤45 | SELL: RSI ≥55
  - ต้องมี confirmation candle ถัดไป
- **B2 ตามเจ้า (Smart Money)**: Breakout → pullback → retest
  - BUY: RSI 55-65 | SELL: RSI 35-45
- **B2s ตามเจ้าเฟิร์มสั้น**: Trend ชัดมาก เข้าทันที lot 0.06-0.28
- **B3 แนวเด้ง (Key Level)**: S/R แตะ ≥2 ครั้ง + rejection candle

## Open Position Rules
- Max 1 trade per condition
- Max 2 trades total (ต้อง condition ต่างกัน)
- Same condition มี trade เปิดอยู่ = SKIP

## RSI Rules
- ≤25: BUY strong (อย่ากลัว extreme)
- 26-35: BUY | 36-44: BUY ถ้ามี pattern ชัด
- 45-54: SKIP ยกเว้น A4/A5 เท่านั้น
- 55-65: BUY ตามเจ้า / SELL ที่ resistance
- 65-70: B2s ตามเจ้าเฟิร์มสั้น
- >70: SELL ถ้ามี pattern

## Matrix (Condition → Technique)
| Condition | Patterns Allowed |
|-----------|-----------------|
| A1 | B2 ตามเจ้า, B3 แนวเด้ง |
| A2 | B2 ตามเจ้า, B3 แนวเด้ง |
| A3 | B3 แนวเด้ง, B1 ไม้รวย (BUY only) |
| A4 | B3 แนวเด้ง (BUY ขอบล่าง) |
| A5 | B3 แนวเด้ง (SELL ขอบบน) |
| A6 | B1 ไม้รวย, B3 แนวเด้ง เท่านั้น |

## Critical Rules
1. Confidence < 0.70 = SKIP
2. R:R < 1:2 = SKIP
3. News flag = SKIP
4. Same condition มี position = SKIP
5. No clear pattern = SKIP

## Output Format
```json
{
  "action": "BUY|SELL|SKIP",
  "entry": 0.0, "sl": 0.0,
  "tp1": 0.0, "tp2": 0.0, "tp3": 0.0,
  "condition": "A1-A6",
  "pattern": "B1-B3|SKIP",
  "confidence": 0.0,
  "reason": "brief"
}
```
