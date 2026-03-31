# XAUUSD Trading Strategy v5.0

> **Source of Truth** สำหรับ Tra(i)der Phase I
> **Timeframe Entry: M5 เท่านั้น** | Filter: H1 trend direction
> Indicators: RSI(14) + S/R Level + Candle Pattern + H1 Trend

## ขั้นตอนการวิเคราะห์ (ทำตามลำดับทุกครั้ง)

```
Step 1: ระบุ "ลักษณะกราฟ" จาก 6 แบบ (ดูจาก 80 แท่งล่าสุด)
Step 2: เลือก Technique ที่เหมาะกับ Condition นั้น
Step 3: ตรวจ 3 เงื่อนไข: S/R zone + RSI + Confirmation candle
Step 4: ถ้าครบ → คำนวณ Entry / SL / TP1–TP3
Step 5: ถ้าไม่ครบ หรือไม่แน่ใจ = SKIP เสมอ
```

## A — ลักษณะกราฟ 6 แบบ (Trading Conditions)

### A1 — เทรนขึ้น (Uptrend)
**ตรวจสอบด้วย 80 แท่ง** — ราคาขึ้นสม่ำเสมอและชัดเจนตลอด 80 แท่ง (Higher High & Higher Low)

**Action: BUY เท่านั้น**

| จุด | รายละเอียด |
|-----|-----------|
| จุดเข้า | ใกล้เคียงแท่งคู่ล่าสุดที่มีการย่อพักตัวลงมา |
| TP1 | ⅓ ของยอดก่อนหน้า (นับจากเนื้อเทียน) |
| TP2 | ½ ของยอดก่อนหน้า (นับจากเนื้อเทียน) |
| TP3 | เนื้อเทียนบนสุด หรือต่ำกว่าเล็กน้อยของยอดก่อนหน้า |
| SL | เลยปลายไส้ล่างของจุดพักตัวก่อนหน้า + buffer |

> ⚠️ ถ้าไส้ก่อนหน้ายาวมาก → พิจารณา SKIP — SL กว้างเกิน R:R ไม่คุ้ม

### A2 — เทรนลง (Downtrend)
**ตรวจสอบด้วย 80 แท่ง** — ราคาลงสม่ำเสมอและชัดเจนตลอด 80 แท่ง (Lower High & Lower Low)

**Action: SELL เท่านั้น**

| จุด | รายละเอียด |
|-----|-----------|
| จุดเข้า | ใกล้เคียงแท่งคู่ล่าสุดที่มีการสวิงกลับขึ้นไป |
| TP1 | ⅓ ของจุดต่ำสุดก่อนหน้า (นับจากเนื้อเทียน) |
| TP2 | ½ ของจุดต่ำสุดก่อนหน้า (นับจากเนื้อเทียน) |
| TP3 | เนื้อเทียนต่ำสุด หรือสูงกว่าเล็กน้อยของจุดต่ำสุดก่อนหน้า |
| SL | เลยปลายไส้บนของจุดสวิงขึ้นก่อนหน้า + buffer |

> ⚠️ ถ้าไส้สวิงขึ้นยาวมาก → พิจารณา SKIP — รอสวิงถัดไปที่ดีกว่า

### A3 — ภูเขา (Mountain)
**ตรวจสอบด้วย 50 แท่ง** — กราฟขึ้นแล้วลงกลับคล้ายภูเขา BUY ที่ฐาน (ขาขึ้นครั้งใหม่)

**ลักษณะภูเขาที่ดี:**
- ฐานแท่งคู่ด้านขวา มีความหนาแน่นพอสมควร
- มีลักษณะเป็นสามเหลี่ยมของราคาขึ้นลงชัดเจน
- ยอดของภูเขาไม่แบน
- เมื่อมองใน 50 แท่ง ฐานของภูเขาไม่ลอย

**Action: BUY ที่ฐาน**

| จุดเข้า | รายละเอียด |
|---------|-----------|
| จุดที่ 1 | เนื้อแท่งคู่ที่ฐาน หรือใกล้เคียง (ไม่เกิน 100–200 จุด) |
| จุดที่ 2 | เนื้อแท่งคู่ที่ฐาน (จุดเทคนิค) |
| จุดที่ 3 | ต่ำกว่าแท่งคู่ที่ฐาน (จุดได้เปรียบ — SL สั้น TP ไกล) |

| TP | รายละเอียด |
|----|-----------|
| TP1 | ⅓ ของภูเขา |
| TP2 | ½ ของภูเขา |
| TP3 | เกือบยอดสุดของภูเขา |
| TPอื่นๆ | สังเกตอุปสรรคที่ขวาง (กลุ่มราคา หรือแท่งคู่ขวาง) |
| SL | เลยปลายไส้ล่างของฐานซ้าย + buffer (หรือ = ระยะ TP) |

> ⚠️ ไม่ควรเข้าลอยเกิน 100–200 จุดจากฐาน เพราะ SL ไกลขึ้นและ TP เก็บได้น้อยลง

### A4 — ไซเวย์ออกข้าง ขาขึ้น (Sideways after Upleg)
ราคาขึ้นมาแรงรวดเร็วใน 1–5 แท่ง แล้วสวิงออกข้างเป็นกลุ่มชัดเจน

**Action: BUY ที่ขอบล่าง (ได้เปรียบกว่า SELL เพราะ trend ใหญ่ยังขึ้น)**

| | รายละเอียด |
|-|-----------|
| Action หลัก | BUY ที่เส้นล่างของกรอบ |
| Action รอง | SELL ที่เส้นบนของกรอบ (ระวังมากกว่า) |
| SL | ออกนอกกรอบ + buffer |
| TP | ขอบตรงข้ามของกรอบ หรือ ⅓ / ½ ของกรอบ |

> ⚠️ SKIP ถ้ากรอบแคบ < 15 pip — กำไรไม่คุ้มค่า spread

### A5 — ไซเวย์ออกข้าง ขาลง (Sideways after Downleg)
ราคาลงมาแรงรวดเร็วใน 1–5 แท่ง แล้วสวิงออกข้างเป็นกลุ่มชัดเจน

**Action: SELL ที่ขอบบน (ได้เปรียบกว่า BUY เพราะ trend ใหญ่ยังลง)**

| | รายละเอียด |
|-|-----------|
| Action หลัก | SELL ที่เส้นบนของกรอบ |
| Action รอง | BUY ที่เส้นล่างของกรอบ (ระวังมากกว่า) |
| SL | ออกนอกกรอบ + buffer |
| TP | ขอบตรงข้ามของกรอบ |

> ⚠️ SKIP ถ้ากรอบแคบ < 15 pip

### A6 — กราฟไม่ชัด (Unclear / Mixed)
ลักษณะกราฟที่ไม่อยู่ใน 5 แบบแรก

**→ ใช้เฉพาะ B1 ไม้รวย และ B3 แนวเด้ง เท่านั้น — ห้ามใช้ pattern ที่ต้องอ่าน trend**

## B — เทคนิค 3 แบบ

### B1 — ไม้รวย (Spike Reversal)
เหมาะกับ A6 และทุก Condition เมื่อเกิด spike ขนาดใหญ่

**จุดสังเกต spike:**
- การเคลื่อนไหวใหญ่มากใน 1–5 แท่ง
- สัดส่วน 60–100% ของ 50 แท่งที่ผ่านมา

| เงื่อนไข | BUY | SELL |
|---------|-----|------|
| S/R Zone | Spike ลงชน Support | Spike ขึ้นชน Resistance |
| RSI | ≤ 45 (RSI 25 ก็ BUY ได้ — อย่ากลัว extreme) | ≥ 55 (หรือ resistance แข็ง) |
| Candle | Lower wick ≥ 1.5× body size | Upper wick ≥ 1.5× body size |
| Confirm | Next candle: close > open | Next candle: close < open |
| SL | ปลาย wick + buffer | ปลาย wick + buffer |
| TP | S/R ถัดไป (R:R ≥ 1:2) | S/R ถัดไป (R:R ≥ 1:2) |

### B2 — ตามเจ้า (Smart Money Follow)
Breakout ผ่าน resistance → pullback retest → entry | เหมาะกับ A1 (BUY), A2 (SELL)

| เงื่อนไข | BUY | SELL |
|---------|-----|------|
| Setup | Strong breakout H1/M15 ผ่าน resistance | Strong breakdown H1/M15 ผ่าน support |
| Entry | Pullback retest level เดิมบน M5 + bounce | Pullback retest level เดิมบน M5 + rejection |
| RSI | 55–65 (momentum ยังมี) | 35–45 (bearish momentum) |
| SL | ใต้ retest candle low + buffer | เหนือ retest candle high + buffer |
| TP | Measured move หรือ next resistance | Measured move หรือ next support |

### B3 — แนวเด้ง (Key Level Bounce)
ราคาเด้งจาก S/R level สำคัญ — ใช้ได้ทุก Condition

| เงื่อนไข | รายละเอียด |
|---------|-----------|
| S/R Level | ราคาแตะ S/R level ที่ผ่านมาแล้วอย่างน้อย 2 ครั้ง |
| Candle | มี rejection candle ชัดเจน (wick ยาว หรือ engulfing) |
| RSI | สอดคล้องกับทิศที่จะเข้า (ไม่สวน momentum) |
| SL | เลย S/R level ออกไป + buffer |
| TP | S/R ถัดไปในทิศที่เข้า (R:R ≥ 1:2) |

## C — Condition × Technique Matrix

| Condition | Action | Technique | TP หลัก | SKIP เมื่อ |
|-----------|--------|-----------|---------|-----------|
| A1 เทรนขึ้น | BUY | ตามเจ้า, แนวเด้ง | ⅓ ½ ยอดก่อนหน้า | ไส้ยาวมาก |
| A2 เทรนลง | SELL | ตามเจ้า, แนวเด้ง | ⅓ ½ จุดต่ำสุด | ไส้ยาวมาก |
| A3 ภูเขา | BUY ฐาน | แนวเด้ง, ไม้รวย | ⅓ ½ ยอดภูเขา | ฐานลอย / เข้าลอย >200pt |
| A4 ไซเวย์ขาขึ้น | BUY ขอบล่าง | แนวเด้ง | ขอบบนกรอบ | กรอบแคบ <15 pip |
| A5 ไซเวย์ขาลง | SELL ขอบบน | แนวเด้ง | ขอบล่างกรอบ | กรอบแคบ <15 pip |
| A6 ไม่ชัด | BUY/SELL ตาม S/R | ไม้รวย, แนวเด้ง เท่านั้น | S/R ถัดไป | ไม่มี spike / ไม่มี level |

## D — RSI Rules

| RSI Zone | สถานะ | Action Rule |
|----------|-------|-------------|
| ≤ 25 | Extreme Oversold | BUY แรงมาก — ไม้รวย + support ยิ่งดี อย่ากลัว |
| 26–35 | Oversold | BUY (ไม้รวย, ภูเขา) |
| 36–44 | ใกล้ Oversold | BUY ถ้ามี pattern ชัด + confirmation candle |
| 45–54 | โซนกลาง | **SKIP** — ยกเว้น A4/A5 ไซเวย์ เท่านั้น |
| 55–65 | Momentum zone | BUY ตามเจ้า / SELL ถ้ามี pattern ที่ resistance |
| 65–70 | Strong Momentum | ตามเจ้าเฟิร์มสั้น BUY |
| > 70 | Overbought | SELL ถ้ามี pattern ที่ resistance |

> ⚠️ RSI extreme ไม่ใช่ signal stand-alone — ต้องมี pattern รองรับเสมอ ถ้าไม่มี = SKIP

## E — H1 Filter

| H1 Direction | เน้น Action | Conditions ที่ทำงาน |
|-------------|------------|-------------------|
| Uptrend (Bullish) | BUY | A1, A3 ฐาน, A4 ขอบล่าง, B2 ตามเจ้า, B3 แนวเด้ง |
| Downtrend (Bearish) | SELL | A2, A5 ขอบบน, B2 SELL, B3 แนวเด้ง SELL |
| Sideways | A4/A5 ตามกรอบ | B1 ไม้รวย / B3 แนวเด้ง ที่ extreme เท่านั้น |

> Momentum แรง ≠ มี pattern — ถ้าไม่มี pattern objective = SKIP เสมอ

## Critical Rules

1. **ถ้าไม่ครบเงื่อนไข หรือไม่แน่ใจ = SKIP เสมอ**
2. **R:R < 1:2 = SKIP** — ไม่มีข้อยกเว้น
3. **Confidence < 0.70 = SKIP** — ส่งมาจาก G2 แล้ว
4. **News flag active = SKIP** — block ±30 นาที
5. **RSI neutral (45-54) = SKIP** — ยกเว้น A4/A5 sideways
