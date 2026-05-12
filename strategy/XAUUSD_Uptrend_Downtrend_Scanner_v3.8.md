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
  "title": "XAUUSD Uptrend+Downtrend Scanner v3.8"
 },
 "cells": [
  {
   "cell_type": "markdown",
   "id": "cell_md_header",
   "metadata": {},
   "source": [
    "# XAUUSD Uptrend + Downtrend Scanner — v3.8\nสแกนหาช่วงเวลาที่ 55-bar window เข้าเทรนด์ขึ้น/ลง ตามเงื่อนไข C1–C6\n\n---\n\n**Criteria Uptrend (C1–C6):**\n\n| # | ชื่อ | วัดอย่างไร | เกณฑ์ |\n|---|------|-----------|-------|\n| C1 | Close position | ปิดล่าสุดเป็นเปอร์เซ็นต์ของระยะ | Close ≥ 60% ของ R55 |\n| C2 | Recent low | Low ต่ำสุดใน **5** แท่งล่าสุด | ≥ 55% ของ R55 |\n| C3 | Drop from HH | HH ทั้ง window → Close ล่าสุด | Drop ≤ 30% ของ R55 |\n| C4 | Launch impulse | สูงสุด 55 แท่ง | Consecutive bullish body ≥ 25% R55 ใน 2–8 แท่ง |\n| C5 | 25-bar lookback | 25 แท่งก่อน window | ไม่มี bearish bar body > **30%** ของ R55 |\n| C6 | ราคาต้น window | C6_START_BARS (5) แรกของเรา + lookback | Close ≤ **40%** ของ R55 จากล่าง |\n\n**Criteria Downtrend (C1D–C6D) — Mirror ของ Uptrend:**\n\n| # | ชื่อ | วัดอย่างไร | เกณฑ์ |\n|---|------|-----------|-------|\n| C1D | Close position | ปิดล่าสุดเป็นเปอร์เซ็นต์ของระยะ | Close ≤ 40% ของ R55 (จากบน) |\n| C2D | Recent high | High สูงสุดใน **5** แท่งล่าสุด | ≤ 45% ของ R55 (จากบน) |\n| C3D | Rise from LL | LL ทั้ง window → Close ล่าสุด | Rise ≤ 30% ของ R55 |\n| C4D | Launch impulse | สูงสุด 55 แท่ง | Consecutive bearish body ≥ 25% R55 ใน 2–8 แท่ง |\n| C5D | 25-bar lookback | 25 แท่งก่อน window | ไม่มี bullish bar body > **30%** ของ R55 |\n| C6D | ราคาต้น window | C6_START_BARS (5) แรกของเรา + lookback | Close ≥ **60%** ของ R55 จากล่าง |\n\n---\n\n**Changelog v3.7 → v3.8:**\n- **C6D fix**: `max(closes) >= level` (เดิม v3.7 = `<=` — semantic bug: downtrend setup ต้องเริ่มจากจุดสูง ไม่ใช่ต่ำ)\n- **C5D guard**: เพิ่ม short-circuit `len(lb) < 5 → True` ให้ตรงกับ C5 (UP)\n- UP path: ไม่มีการเปลี่ยนแปลง\n- SELL body filter (`*100` quirk): คงไว้เหมือนเดิม (notebook engine code = source of truth)\n\n---\n\n**Entry Uptrend (BUY):** Swing Low ใน zone 65–85% R55 → price แตะ level → BUY  \n**Entry Downtrend (SELL):** Swing High ใน zone 15–35% R55 → price แตะ level → SELL  \n**TP/SL:** Symmetric 50% × (Swing High − Entry) | R:R = 1.0 | Lot = Portfolio×10% ÷ SL(pip)\n\n---\n\n**หมายเหตุ:**  \n- `C4_MIN = 0.25` (ค่าเริ่มต้น) รองรับ continuation phase ที่ R55 เล็กลง  \n- `C5_MAX = 0.30` (30% R55) ไม่ใช้ 35%  \n- `C2` วัด **5 แท่ง** ล่าสุด ไม่ใช้ 10 แท่ง  \n- Anti-trend filter: detect_down/up_father (40–100% R55 ใน 1–8 แท่ง)\n"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "cell_md_v38_engine",
   "metadata": {},
   "source": [
    "## v3.8 Engine code (source of truth)\n\nNotebook reference — Python engine จริงอยู่ที่ `utils/xauusd_signal.py` (`_detect_uptrend_scanner` / `_detect_downtrend_scanner`) ตรงกับ Cell 3 ของ notebook นี้\n\n### Uptrend criteria\n```python\ndef check_c1(w, L55, R55):\n    val = (w['close'].iloc[-1] - L55) / R55\n    return val, val >= C1_MIN   # 0.60\n\ndef check_c2(w, L55, R55, n_bars=5):\n    val = (w['low'].iloc[-n_bars:].min() - L55) / R55\n    return val, val >= C2_MIN   # 0.55\n\ndef check_c3(w, R55):\n    val = (w['high'].max() - w['close'].iloc[-1]) / R55\n    return val, val <= C3_MAX   # 0.30\n\ndef check_c4(w, R55):\n    # consecutive bullish bars, body sum >= C4_MIN * R55 within 2-8 bars\n    ...\n\ndef check_c5(lb, R55):\n    if lb is None or len(lb) < 5: return 0.0, True, 'n/a'\n    # worst bearish body > C5_MAX * R55 → fail\n    ...\n\ndef check_c6(w, lb, L55, R55):\n    level = L55 + C6_MAX_START * R55     # 0.40 from below\n    # max(lookback + first 5 closes) <= level → pass\n    return ..., max_close <= level\n```\n\n### Downtrend criteria (v3.8 fixed at C6D)\n```python\ndef check_c1d(w, H55, R55):\n    val = (H55 - w['close'].iloc[-1]) / R55\n    return val, val >= C1_MIN   # 0.60 (same threshold, mirrored value)\n\ndef check_c2d(w, H55, R55, n_bars=5):\n    val = (H55 - w['high'].iloc[-n_bars:].max()) / R55\n    return val, val >= C2_MIN   # 0.55\n\ndef check_c3d(w, R55):\n    val = (w['close'].iloc[-1] - w['low'].min()) / R55\n    return val, val <= C3_MAX   # 0.30\n\ndef check_c4d(w, R55):\n    # consecutive bearish bars, body sum (pip) / (R55 pip) >= C4_MIN\n    # body = (open - close) * 100, R55 in USD so denominator = R55 * 100\n    ...\n\ndef check_c5d(lb, R55):\n    if lb is None or len(lb) < 5 or R55 < 1e-6:\n        return 0.0, True, 'n/a'\n    # worst bullish body > C5_MAX * R55 → fail\n    ...\n\ndef check_c6d(w, lb, H55, R55):\n    level = H55 - C6_MAX_START * R55     # 0.40 from top\n    start_closes = w['close'].iloc[:C6_START_BARS]\n    if lb is not None and len(lb) > 0:\n        all_closes = pd.concat([lb['close'], start_closes])\n    else:\n        all_closes = start_closes\n    # v3.8 FIX: max(closes) >= level (was <= in v3.7 — semantic bug)\n    # Downtrend setup needs an INITIAL PEAK at top of range, so at least one\n    # early close must reach into the top 40% of R55.\n    return ..., all_closes.max() >= level\n```\n\n### Simulate trades (entry-bar TP/SL check, v3.7+)\n```python\nfor bi in range(n):\n    # Check TP/SL on the entry bar itself (v3.7 fix from v3.4-v3.6 bug)\n    # Both-hit conflict resolves to whichever is closer to entry\n    # On equal distance, SL wins (conservative)\n    ...\n```\n\n### Stateful stop-segments (v3.7+)\n```python\n# On LOSS, add segment_id to stopped_*_segments\n# Next cycle refuses to fire on the same segment_id\n# Reset segment_id when trend criteria fail (segment ends)\n```\n\n### Anti-trend filter\n```python\ndef detect_up_father(bars, i, R55, max_bars=8, min_pct=40.0, max_pct=100.0):\n    # For SELL: refuse setup if there's a bullish father bar (close > open by\n    # 40-100% of R55 across 1-8 consecutive bars)\n    ...\n\ndef detect_down_father(bars, i, R55, max_bars=8, min_pct=40.0, max_pct=100.0):\n    # For BUY: refuse setup if there's a bearish father bar (40-100% R55)\n    ...\n```\n"
   ]
  }
 ]
}
