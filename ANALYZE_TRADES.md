# 🔍 วิธีวิเคราะห์ Trades แบบแม่นยำ

## ข้อมูลที่ต้องมี:

จาก **Google Sheets** (Trade Log tab):
```
Plan ID | Timestamp | TF | Chart Type | Technique | Entry | SL | TP | R:R | Result
```

จาก **LINE Notify** (screenshot):
```
[เวลา] TF | Chart | Technique
Entry: X.XX | SL: X.XX | TP: X.XX
```

---

## วิเคราะห์ Trade:

### Trade 1: H1 Mountain @ 17:54
```bash
python analyze_trade.py \
  --time "2026-04-17 17:54" \
  --tf H1 \
  --technique mountain
```

**จะแสดง:**
- Peak อยู่ที่แท่งไหน (index + เวลา)
- Left Base อยู่ที่แท่งไหน (ฐานซ้าย)
- Twin Candle ใกล้ base (ถ้ามี)
- Tech Price = เท่าไร

---

### Trade 2: M1 Uptrend @ 20:01
```bash
python analyze_trade.py \
  --time "2026-04-17 20:01" \
  --tf M1 \
  --technique twin_candle \
  --entry 4839.99
```

**จะแสดง:**
- แท่งคู่อยู่ที่ index ไหน
- เวลาของแท่งทั้ง 2
- Tech Price vs Entry Price (ตรงกันไหม)
- Body % ของแท่งคู่

---

## ตรวจสอบ TF:

### ถ้า TF = H1/M1 แต่รันหลัง 17:15:

**เป็นไปได้:**
1. ❌ Config ยังไม่ถูกใช้ (check TIMEFRAMES in config.py)
2. ❌ มี Traider instance อื่นรันอยู่ (check ps aux)
3. ❌ Sheets มี cache หรือ manual entry

**วิธีเช็ค:**
```bash
# 1. Config จริง
grep "TIMEFRAMES" config.py

# 2. Git log (ดูว่าแก้เมื่อไร)
git log --oneline --since="2026-04-17" config.py

# 3. Log file (ดูว่า Selected TF อะไร)
grep "Selected" /tmp/traider_m5_live.log
```

---

## วิธีเช็ค Google Sheets:

1. เปิด: https://docs.google.com/spreadsheets/d/[YOUR_ID]/edit
2. ไปที่ **Trade Log** tab
3. ดู column E: **timeframe**
4. Filter trades วันนี้ (2026-04-17)
5. ดูว่ามี TF อะไรบ้าง:
   - ✅ M5 → ถูกต้อง (config ใหม่)
   - ❌ H1/M1 → ข้อมูลเก่า หรือ bug

---

## สรุป:

**ถ้า H1/M1 = ข้อมูลเก่า:**
- ลบออกหรือ filter เฉพาะ M5
- วิเคราะห์เฉพาะ trades ใหม่ (หลัง 17:15)

**ถ้า H1/M1 = มาจากการรันจริง:**
- Bug! ต้องหาว่า selected_tf มาจากไหน
- Check main.py → G1 → world_state['selected_tf']

