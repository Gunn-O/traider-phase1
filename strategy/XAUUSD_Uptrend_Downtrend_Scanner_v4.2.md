{
 "nbformat": 4,
 "nbformat_minor": 5,
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "name": "python",
   "version": "3.10.0"
  },
  "colab": {
   "provenance": [],
   "name": "XAUUSD_Uptrend_Scanner.ipynb"
  },
  "title": "XAUUSD Uptrend+Downtrend Scanner v4.2"
 },
 "cells": [
  {
   "cell_type": "markdown",
   "id": "cell_md_header",
   "metadata": {},
   "source": [
    "# XAUUSD Uptrend + Downtrend Scanner — v4.2\nสแกนหาช่วงเวลาที่ 55-bar window เข้าเทรนด์ขึ้น/ลง ตามเงื่อนไข C1–C6\n\n---\n\n**Criteria Uptrend (C1–C6):**\n\n| # | ชื่อ | วัดอย่างไร | เกณฑ์ |\n|---|------|-----------|-------|\n| C1 | Close position | ปิดล่าสุดเป็นเปอร์เซ็นต์ของระยะ | Close ≥ 60% ของ R55 |\n| C2 | Recent low | Low ต่ำสุดใน **5** แท่งล่าสุด | ≥ 55% ของ R55 |\n| C3 | Drop from HH | HH ทั้ง window → Close ล่าสุด | Drop ≤ 30% ของ R55 |\n| C4 | Launch impulse | สูงสุด 55 แท่ง | Consecutive bullish body ≥ 25% R55 ใน 2–8 แท่ง |\n| C5 | 25-bar lookback | 25 แท่งก่อน window | ไม่มี bearish bar body > **30%** ของ R55 |\n| C6 | ราคาต้น window | C6_START_BARS (5) แรกของเรา + lookback | **max** close ≤ **40%** R55 จากล่าง (ทุก close ต่ำ) |\n\n**Criteria Downtrend (C1D–C6D) — TRUE Mirror ของ Uptrend:**\n\n| # | ชื่อ | วัดอย่างไร | เกณฑ์ |\n|---|------|-----------|-------|\n| C1D | Close position | ปิดล่าสุดเป็นเปอร์เซ็นต์ของระยะ | Close ≤ 40% ของ R55 (จากบน) |\n| C2D | Recent high | High สูงสุดใน **5** แท่งล่าสุด | ≤ 45% ของ R55 (จากบน) |\n| C3D | Rise from LL | LL ทั้ง window → Close ล่าสุด | Rise ≤ 30% ของ R55 |\n| C4D | Launch impulse | สูงสุด 55 แท่ง | Consecutive bearish body ≥ 25% R55 ใน 2–8 แท่ง |\n| C5D | 25-bar lookback | 25 แท่งก่อน window | ไม่มี bullish bar body > **30%** ของ R55 |\n| C6D | ราคาต้น window | C6_START_BARS (5) แรกของเรา + lookback | **min** close ≥ **60%** R55 จากล่าง (ทุก close สูง) |\n\n---\n\n**Changelog v3.8 → v4.2:**\n- **C6D mirror fix**: `max(closes) >= level` (v3.8) → `min(closes) >= level` (v4.2) — TRUE mirror ของ C6 UP. ทุก close ต้นต้องอยู่ใน top 40% ไม่ใช่แค่ 1 close\n- **MIN_TP_PIP = 200** ใน simulate_trades — skip signal ที่ TP distance < 200 pip (จะตั้ง SL/TP สั้นแปลกๆ ตอน setup volatility ต่ำ)\n- **Entry-bar fill check** ใน simulate — bar ที่สัญญาณยิงต้องแตะ entry จริง (high >= entry AND low <= entry สำหรับ BUY; mirror สำหรับ SELL)\n- UP path: ไม่มีการเปลี่ยนแปลง criteria\n- SELL body filter (`*100` quirk): คงไว้เหมือนเดิม\n\n---\n\n**Entry Uptrend (BUY):** Swing Low ใน zone 65–85% R55 → price แตะ level → BUY  \n**Entry Downtrend (SELL):** Swing High ใน zone 15–35% R55 → price แตะ level → SELL  \n**TP/SL:** Symmetric 50% × (Swing High − Entry) | R:R = 1.0 | Lot = Portfolio×10% ÷ SL(pip)  \n**Min trade size:** TP distance ≥ 200 pip (else skip)\n\n---\n\n**หมายเหตุ:**  \n- `C4_MIN = 0.25` (ค่าเริ่มต้น) รองรับ continuation phase ที่ R55 เล็กลง  \n- `C5_MAX = 0.30` (30% R55) ไม่ใช้ 35%  \n- `C2` วัด **5 แท่ง** ล่าสุด ไม่ใช้ 10 แท่ง  \n- Anti-trend filter: detect_down/up_father (40–100% R55 ใน 1–8 แท่ง)\n"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "cell_md_v42_engine",
   "metadata": {},
   "source": [
    "## v4.2 Engine code (source of truth)\n\nNotebook reference — Python engine จริงอยู่ที่ `utils/xauusd_signal.py` (`_detect_uptrend_scanner` / `_detect_downtrend_scanner`) ตรงกับ Cell 3 ของ notebook นี้\n\n### Uptrend criteria (ไม่เปลี่ยนจาก v3.8)\n```python\ndef check_c1(w, L55, R55):\n    val = (w['close'].iloc[-1] - L55) / R55\n    return val, val >= C1_MIN   # 0.60\n\ndef check_c2(w, L55, R55, n_bars=5):\n    val = (w['low'].iloc[-n_bars:].min() - L55) / R55\n    return val, val >= C2_MIN   # 0.55\n\ndef check_c3(w, R55):\n    val = (w['high'].max() - w['close'].iloc[-1]) / R55\n    return val, val <= C3_MAX   # 0.30\n\ndef check_c4(w, R55):\n    # consecutive bullish bars, body sum >= C4_MIN * R55 within 2-8 bars\n    ...\n\ndef check_c5(lb, R55):\n    if lb is None or len(lb) < 5: return 0.0, True, 'n/a'\n    # worst bearish body > C5_MAX * R55 → fail\n    ...\n\ndef check_c6(w, lb, L55, R55):\n    level = L55 + C6_MAX_START * R55     # 0.40 from below\n    # max(lookback + first 5 closes) <= level → pass (ทุก close ต่ำ)\n    return ..., max_close <= level\n```\n\n### Downtrend criteria (v4.2 TRUE mirror)\n```python\ndef check_c1d(w, H55, R55):\n    val = (H55 - w['close'].iloc[-1]) / R55\n    return val, val >= C1_MIN   # 0.60 (same threshold, mirrored value)\n\ndef check_c2d(w, H55, R55, n_bars=5):\n    val = (H55 - w['high'].iloc[-n_bars:].max()) / R55\n    return val, val >= C2_MIN   # 0.55\n\ndef check_c3d(w, R55):\n    val = (w['close'].iloc[-1] - w['low'].min()) / R55\n    return val, val <= C3_MAX   # 0.30\n\ndef check_c4d(w, R55):\n    # consecutive bearish bars, body sum (pip) / (R55 pip) >= C4_MIN\n    # body = (open - close) * 100, R55 in USD so denominator = R55 * 100\n    ...\n\ndef check_c5d(lb, R55):\n    if lb is None or len(lb) < 5 or R55 < 1e-6:\n        return 0.0, True, 'n/a'\n    # worst bullish body > C5_MAX * R55 → fail\n    ...\n\ndef check_c6d(w, lb, H55, R55):\n    level = H55 - C6_MAX_START * R55     # 0.40 from top\n    start_closes = w['close'].iloc[:C6_START_BARS]\n    if lb is not None and len(lb) > 0:\n        all_closes = pd.concat([lb['close'], start_closes])\n    else:\n        all_closes = start_closes\n    # v4.2 TRUE MIRROR: min(closes) >= level (ทุก close สูง)\n    # v3.8 used max(closes) >= level (อย่างน้อย 1 close) — too permissive\n    return ..., all_closes.min() >= level\n```\n\n### Simulate trades — MIN_TP_PIP filter + entry-bar fill check (v4.2)\n```python\nfor bi in range(n):\n    # ... entry checks: must reach entry level on this bar\n    if cur[3] < e['entry_price']:    # BUY: high < entry → ไม่ถึง\n        continue\n    if cur[4] > e['entry_price']:    # BUY: low > entry → ไม่แตะ\n        continue\n    # SELL mirror: low > entry OR high < entry → skip\n    ...\n    reward = sh_hi - e['entry_price']\n    tp_dist = 0.50 * reward\n    if tp_dist * 100 < 200:           # v4.2: MIN_TP_PIP = 200\n        continue\n    # ... open the trade\n```\n\n### Stateful segment tracking (v3.7+, merged-trend)\n```python\n# Segment is the union of overlapping passing windows.\n# Segment_id only changes when next PASS has cur_ws >= last_confirmed_we (no overlap).\n# On FAIL: segment_id is left alone (sticks).\n# On LOSS: add segment_id to stopped_*_segments → block re-entry until new segment.\n```\n\n### Anti-trend filter\n```python\ndef detect_up_father(bars, i, R55, max_bars=8, min_pct=40.0, max_pct=100.0):\n    # For SELL: refuse setup if there's a bullish father bar (close > open by\n    # 40-100% of R55 across 1-8 consecutive bars)\n    ...\n\ndef detect_down_father(bars, i, R55, max_bars=8, min_pct=40.0, max_pct=100.0):\n    # For BUY: refuse setup if there's a bearish father bar (40-100% R55)\n    ...\n```\n"
   ]
  }
 ]
}
