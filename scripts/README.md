# 🚀 Tra(i)der Scripts

Quick commands สำหรับรัน Tra(i)der ในโหมดต่างๆ

---

## 📋 Scripts ที่มี

### 1️⃣ **run_simulate.sh** — Simulator (แนะนำ)
รัน simulate mode แบบปกติ ทุก 5 นาที จนถึงพรุ่งนี้ตี 3

```bash
bash scripts/run_simulate.sh
```

**คุณสมบัติ:**
- ✅ แสดงผลแบบ real-time
- ✅ เห็น log ทุก cycle
- ✅ รันต่อได้แม้ปิด VSCode (ถ้าเปิด Terminal ทิ้งไว้)
- ✅ Log: `logs/simulate_YYYYMMDD_HHMMSS.log`
- ⏹️ หยุด: กด `Ctrl+C` หรือ `bash scripts/stop_all.sh`

---

### 2️⃣ **run_daemon.sh** — Background Daemon
รันในพื้นหลัง แม้ปิด Terminal หรือปิดหน้าจอก็ยังรันต่อ

```bash
bash scripts/run_daemon.sh
```

**คุณสมบัติ:**
- ✅ รันต่อแม้ปิด Terminal
- ✅ รันต่อแม้ปิดหน้าจอ/Sleep
- ❌ หยุดถ้า Shutdown เครื่อง
- 📝 Log: `logs/simulate_daemon_YYYYMMDD_HHMMSS.log`
- 👀 ดู log: `tail -f logs/simulate_daemon_*.log`
- ⏹️ หยุด: `bash scripts/stop_all.sh`

---

### 3️⃣ **run_winrate_test.sh** — Winrate Test
รัน winrate test (lot 0.01 ทุกไม้)

```bash
bash scripts/run_winrate_test.sh
```

**คุณสมบัติ:**
- 🧪 Lot: 0.01 ทุก trade
- ✅ แสดงผลแบบ real-time
- 📝 Log: `logs/winrate_test_YYYYMMDD_HHMMSS.log`

---

### 4️⃣ **run_backtest.sh** — Backtest
รัน backtest ย้อนหลัง

```bash
# 7 วันย้อนหลัง (default)
bash scripts/run_backtest.sh

# กำหนดช่วงเอง
bash scripts/run_backtest.sh 2026-04-01 2026-04-07
```

**คุณสมบัติ:**
- 📊 รัน M5 candle ทุกแท่ง
- ✅ Session summary (cost, win rate)
- 📝 Log: `logs/backtest_START_to_END_HHMMSS.log`

---

### 5️⃣ **status.sh** — ดูสถานะ
เช็คว่ามี simulator/daemon รันอยู่ไหม

```bash
bash scripts/status.sh
```

**แสดง:**
- 🟢 Process ที่กำลังรัน
- 📊 จำนวน cycles
- 📝 SKIP reason ล่าสุด
- 📊 Google Sheets status

---

### 6️⃣ **stop_all.sh** — หยุดทุก process
หยุดทุก simulator/daemon ที่รันอยู่

```bash
bash scripts/stop_all.sh
```

---

## 🎯 Workflow แนะนำ

### สำหรับ Testing (เห็นผลเร็ว)
```bash
# 1. รัน backtest 7 วัน
bash scripts/run_backtest.sh

# 2. ดู session summary (cost, win rate)
```

### สำหรับ Live Simulation (เปิดคอมทิ้งไว้)
```bash
# 1. รัน simulator
bash scripts/run_simulate.sh

# 2. ดูสถานะ (terminal อื่น)
bash scripts/status.sh

# 3. หยุดเมื่อเสร็จ
Ctrl+C
```

### สำหรับ Background (ปิดหน้าจอได้)
```bash
# 1. รัน daemon
bash scripts/run_daemon.sh

# 2. ดู log
tail -f logs/simulate_daemon_*.log

# 3. ปิดหน้าจอได้เลย

# 4. กลับมาเช็คสถานะ
bash scripts/status.sh

# 5. หยุด daemon
bash scripts/stop_all.sh
```

---

## 📁 Logs Location

ทุก log อยู่ที่ `logs/`:
- `simulate_*.log` — Simulator logs
- `simulate_daemon_*.log` — Daemon logs
- `winrate_test_*.log` — Winrate test logs
- `backtest_*.log` — Backtest logs
- `archive/` — Logs เก่าที่ถูกย้าย

---

## ⚙️ Configuration

แก้ `.env` สำหรับ:
- `ACCOUNT_BALANCE` — เงินเริ่มต้น
- `WINRATE_TEST` — true/false
- `LINE_NOTIFY_ENABLED` — แจ้งเตือน LINE
- `SHEETS_ENABLED` — บันทึก Google Sheets

---

## 🐛 Troubleshooting

**Simulator ไม่เปิด plan:**
- ✅ ปกติ — Claude รอ setup ที่เหมาะสมตาม strategy
- 🔍 ดู SKIP reason: `grep "SKIP:" logs/simulate_*.log | tail -5`

**Process ค้าง:**
```bash
bash scripts/stop_all.sh
```

**ต้องการเคลียร์ Sheets:**
```bash
python scripts/reset_sheets.py
```

---

## 📞 Contact

เจอปัญหา: ดู `CLAUDE.md` หรือ check GitHub issues
