#!/usr/bin/env python3
"""
Debug G1 Uptrend Detection

ตรวจสอบว่าทำไม G1 ไม่ detect A1 uptrend
ช่วง 19:44-22:26 ราคาขึ้น 4,734 → 4,771
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

from agents.g1_signal_logic import G1MarketScanner
from utils import create_connector, detect_trend

load_dotenv()


def debug_uptrend_detection():
    """Debug uptrend detection logic"""

    print("="*70)
    print("🔍 DEBUG G1 UPTREND DETECTION")
    print("="*70)

    # เชื่อมต่อ TradingView
    print("\n📡 Connecting to TradingView...")
    os.environ['DATA_MODE'] = 'simulate'
    connector = create_connector('simulate')

    tv_username = os.getenv('TV_USERNAME')
    tv_password = os.getenv('TV_PASSWORD')
    connector.connect(tv_username=tv_username, tv_password=tv_password)

    # ดึงข้อมูล
    print("📊 Fetching M5 and H1 data...")
    m5_df = connector.get_candles('XAUUSD', 5, 80)
    h1_df = connector.get_candles('XAUUSD', 60, 20)

    if m5_df.empty or h1_df.empty:
        print("❌ Failed to fetch data")
        return

    current_price = float(m5_df.iloc[-1]['close'])
    print(f"✓ Current Price: ${current_price:,.2f}")
    print(f"✓ M5 candles: {len(m5_df)}")
    print(f"✓ H1 candles: {len(h1_df)}")

    # === ตรวจสอบ Trends ===
    print(f"\n{'='*70}")
    print("1️⃣  TREND DETECTION")
    print(f"{'='*70}")

    # M5 Trend
    m5_trend = detect_trend(m5_df, method='combined')
    print(f"\n📈 M5 Trend (80 candles): {m5_trend}")

    # M5 Trend ละเอียด
    m5_close = m5_df['close'].values
    m5_price_change = m5_close[-1] - m5_close[0]
    m5_price_change_pct = (m5_price_change / m5_close[0]) * 100
    print(f"   Price Change: ${m5_price_change:+.2f} ({m5_price_change_pct:+.2f}%)")
    print(f"   Start: ${m5_close[0]:.2f} → End: ${m5_close[-1]:.2f}")

    # H1 Trend
    h1_trend = detect_trend(h1_df, method='combined')
    print(f"\n📊 H1 Trend (20 candles): {h1_trend}")

    h1_close = h1_df['close'].values
    h1_price_change = h1_close[-1] - h1_close[0]
    h1_price_change_pct = (h1_price_change / h1_close[0]) * 100
    print(f"   Price Change: ${h1_price_change:+.2f} ({h1_price_change_pct:+.2f}%)")
    print(f"   Start: ${h1_close[0]:.2f} → End: ${h1_close[-1]:.2f}")

    # === ตรวจสอบ A1 Uptrend Logic ===
    print(f"\n{'='*70}")
    print("2️⃣  A1 UPTREND CRITERIA CHECK")
    print(f"{'='*70}")

    # Condition 1: M5 trend must be bullish
    cond1_pass = m5_trend == 'bullish'
    print(f"\n✓ Condition 1: M5 trend == 'bullish'")
    print(f"   Result: {cond1_pass} (actual: {m5_trend})")

    # Condition 2: H1 trend must be bullish or sideways
    cond2_pass = h1_trend in ['bullish', 'sideways']
    print(f"\n✓ Condition 2: H1 trend in ['bullish', 'sideways']")
    print(f"   Result: {cond2_pass} (actual: {h1_trend})")

    # Condition 3 & 4: Higher Highs and Higher Lows
    print(f"\n✓ Condition 3 & 4: Higher Highs > 6 AND Higher Lows > 6")

    highs = m5_df['high'].values
    lows = m5_df['low'].values

    # นับ HH และ HL (เทียบกับ 10 แท่งก่อนหน้า)
    hh_count = sum(1 for i in range(10, len(highs)) if highs[i] > highs[i-10])
    hl_count = sum(1 for i in range(10, len(lows)) if lows[i] > lows[i-10])

    print(f"   Higher Highs: {hh_count} (need > 6)")
    print(f"   Higher Lows: {hl_count} (need > 6)")

    cond3_pass = hh_count > 6
    cond4_pass = hl_count > 6

    print(f"   HH Pass: {cond3_pass}")
    print(f"   HL Pass: {cond4_pass}")

    # === สรุป ===
    print(f"\n{'='*70}")
    print("3️⃣  SUMMARY")
    print(f"{'='*70}")

    all_pass = cond1_pass and cond2_pass and cond3_pass and cond4_pass

    print(f"\n📋 A1 Uptrend Detection:")
    print(f"   1. M5 bullish: {'✅' if cond1_pass else '❌'}")
    print(f"   2. H1 bullish/sideways: {'✅' if cond2_pass else '❌'}")
    print(f"   3. Higher Highs > 6: {'✅' if cond3_pass else '❌'} ({hh_count})")
    print(f"   4. Higher Lows > 6: {'✅' if cond4_pass else '❌'} ({hl_count})")
    print(f"\n   Result: {'✅ A1_UPTREND' if all_pass else '❌ NOT A1'}")

    if not all_pass:
        print(f"\n💡 Why NOT A1 Uptrend:")
        if not cond1_pass:
            print(f"   ⚠️  M5 trend is '{m5_trend}' (not bullish)")
        if not cond2_pass:
            print(f"   ⚠️  H1 trend is '{h1_trend}' (not bullish/sideways)")
        if not cond3_pass:
            print(f"   ⚠️  Only {hh_count} Higher Highs (need > 6)")
        if not cond4_pass:
            print(f"   ⚠️  Only {hl_count} Higher Lows (need > 6)")

    # === แสดงกราฟ 10 แท่งล่าสุด ===
    print(f"\n{'='*70}")
    print("4️⃣  LAST 10 CANDLES (M5)")
    print(f"{'='*70}")

    last_10 = m5_df.tail(10)
    print(f"\n{'Time':<20} {'High':>10} {'Low':>10} {'Close':>10} {'HH':>5} {'HL':>5}")
    print("-" * 70)

    for i in range(len(last_10)):
        idx = len(m5_df) - 10 + i
        row = last_10.iloc[i]

        # เช็คว่าเป็น HH/HL หรือไม่
        is_hh = ''
        is_hl = ''
        if idx >= 10:
            if highs[idx] > highs[idx-10]:
                is_hh = '✓'
            if lows[idx] > lows[idx-10]:
                is_hl = '✓'

        time_str = row['time'].strftime('%Y-%m-%d %H:%M') if hasattr(row['time'], 'strftime') else str(row['time'])
        print(f"{time_str:<20} {row['high']:>10.2f} {row['low']:>10.2f} {row['close']:>10.2f} {is_hh:>5} {is_hl:>5}")

    # === ตรวจสอบ detect_trend threshold ===
    print(f"\n{'='*70}")
    print("5️⃣  DETECT_TREND DETAILS")
    print(f"{'='*70}")

    print(f"\n🔍 Checking what thresholds detect_trend uses...")
    print(f"   (This function is in utils/indicators.py)")
    print(f"   Current result: M5 = {m5_trend}, H1 = {h1_trend}")

    # คำนวณ EMA slopes
    if 'ema20' not in m5_df.columns:
        m5_df['ema20'] = m5_df['close'].ewm(span=20, adjust=False).mean()
    if 'ema50' not in m5_df.columns:
        m5_df['ema50'] = m5_df['close'].ewm(span=50, adjust=False).mean()

    ema20_slope = m5_df['ema20'].iloc[-1] - m5_df['ema20'].iloc[-10]
    ema50_slope = m5_df['ema50'].iloc[-1] - m5_df['ema50'].iloc[-10]

    print(f"\n📊 M5 EMA Slopes (last 10 candles):")
    print(f"   EMA20: {ema20_slope:+.2f}")
    print(f"   EMA50: {ema50_slope:+.2f}")

    print(f"\n" + "="*70)
    print("✅ Debug completed!")
    print("="*70)

    # Clean up
    connector.disconnect()


if __name__ == "__main__":
    debug_uptrend_detection()
