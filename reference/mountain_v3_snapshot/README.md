# Mountain v3 — Backtest (standalone snapshot)

snapshot สำหรับรัน strategy `mountain_v3` (ภูเขา) แบบแยกเดี่ยว (ไม่พึ่ง repo หลัก · ไม่มี v1/v2/numpy)

## ติดตั้ง

```
pip install -r requirements.txt
```

(ต้องการแค่ `pandas` + `pyyaml`)

## รัน (2 config)

**tpsl — R:R 1.0** (`tp_adj: 5` ดัน TP ให้ระยะ = SL)
```
python -m bt run --strategy mountain_v3 \
  --config configs/mountain_v3_tpsl.yaml \
  --global configs/global.yaml \
  --data data/XAUUSD_M1_2026-06-09.csv \
  --out runs/check_tpsl/
```

**rr85 — R:R ~0.85** (`adj_on: false` ใช้ base 40/35 ตรงๆ)
```
python -m bt run --strategy mountain_v3 \
  --config configs/mountain_v3_tpsl_rr85.yaml \
  --global configs/global.yaml \
  --data data/XAUUSD_M1_2026-06-09.csv \
  --out runs/check_rr85/
```

ผลลัพธ์แต่ละรอบอยู่ใน `runs/check_*/` (5 ไฟล์: `summary.json` · `trades.csv` · `plans.csv` · `unfilled.csv` · `plan_meta.csv`)

## เทียบกับผลอ้างอิง

```
diff runs/check_tpsl/trades.csv  expected_results/mountain_v3_tpsl/trades.csv
diff runs/check_rr85/trades.csv  expected_results/mountain_v3_tpsl_rr85/trades.csv
```
(เทียบครบ 5 ไฟล์ต่อ config — ทั้งหมดต้อง **identical**)

**ผลที่คาดไว้ (M1 · 150,063 แท่ง):**

| config | R:R | ไม้ | win rate | net pip | portfolio |
|---|---|---|---|---|---|
| `mountain_v3_tpsl`      | 1.00 | 194 | 62.37% | +21,746 | 1000 → 5,675.77 |
| `mountain_v3_tpsl_rr85` | 0.85 | 181 | 66.30% | +19,954 | 1000 → 5,280.46 |

## 2 config ต่างกันตรงไหน

โครงเหมือนกันเป๊ะ (1 tier `when height ≥ 50%R55` · 1 ไม้ `offset_pct_height: 5` · base `tp 40 / sl 35 %ความสูง`) — ต่างที่ leg adjust บรรทัดเดียว:

- **tpsl:** `tp_adj: 5` → TP = 40+5 = 45%ความสูง → จาก entry (base_lo+5%) ระยะ TP = SL = 40%ความสูง → **R:R 1.0**
- **rr85:** `adj_on: false` → ปิด adjust ใช้ base 40% → จาก entry ระยะ TP 35% / SL 40% → **R:R 0.875 (~0.85)**

## หมายเหตุ

- snapshot นี้มีเฉพาะ `mountain_v3` (registry ตัด strategy อื่นออก) · ใช้ engine/contract/report เดียวกับ repo หลัก
- `_util.py` (swing/lot/r55 helper) bundle มาในก้อน → strategy รันได้เองไม่ต้องมี repo หลัก
- CLI-only (ไม่รวม console/server) · offline 100%
