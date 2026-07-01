# ไม้รวย v2 — Backtest (standalone snapshot)

snapshot สำหรับรัน strategy `mai_ruay_v2` แบบแยกเดี่ยว (ไม่พึ่ง repo หลัก · ไม่มี v1/numpy)

## ติดตั้ง

```
pip install -r requirements.txt
```

(ต้องการแค่ `pandas` + `pyyaml`)

## รัน

```
python -m bt run --strategy mai_ruay_v2 \
  --config configs/mairuay_v2_1entry_con360-510.yaml \
  --global configs/global.yaml \
  --data data/XAUUSD_M1_2026-06-09.csv \
  --out runs/check/
```

ผลลัพธ์จะอยู่ใน `runs/check/` (5 ไฟล์: `summary.json` · `trades.csv` · `plans.csv` · `unfilled.csv` · `plan_meta.csv`)

## เทียบกับผลอ้างอิง

```
diff runs/check/summary.json   expected_results/con360-510_m1/summary.json
diff runs/check/trades.csv     expected_results/con360-510_m1/trades.csv
diff runs/check/plans.csv      expected_results/con360-510_m1/plans.csv
diff runs/check/unfilled.csv   expected_results/con360-510_m1/unfilled.csv
diff runs/check/plan_meta.csv  expected_results/con360-510_m1/plan_meta.csv
```

ทั้ง 5 ไฟล์ต้อง **identical** · ผลที่คาดไว้: 177 ไม้ · win rate 44.07% · net +24490.8 pip · portfolio 1000 → 8373.94

## หมายเหตุ

- ผลอ้างอิงใน `expected_results/` รันบนโค้ดล่าสุด (v2 decouple จาก v1 + cleanup Signal เหลือ 9 field — pure refactor ผลไม่เปลี่ยน)
- snapshot นี้มีเฉพาะ `mai_ruay_v2` (registry ตัด v1 ออกแล้ว) · ใช้ engine/contract/report เดียวกับ repo หลัก
