"""
G1 — Market Scanning Agent (Signal Logic)

หน้าที่:
- คำนวณ RSI(14), หา S/R levels
- ระบุ Condition A1-A6 (Uptrend, Downtrend, Mountain, Sideways, Unclear)
- ตรวจจับ pattern candidates และ spike
- News & Event filter (block ±30 min)
- Session detection (Asia/London/NY)

Output: world_state JSON → ส่งต่อ G2 เมื่อครบ ≥ 2/3 เงื่อนไข
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
import pytz

from utils import (
    calculate_rsi,
    detect_sr_levels,
    detect_trend,
    get_rsi_zone,
    find_nearest_sr_level,
    analyze_candle_pattern
)


# Constants
SR_BUFFER_POINTS = 50.0  # ระยะห่างสูงสุดจาก S/R ที่ถือว่า "ใกล้"
SPIKE_THRESHOLD = 0.60   # Spike ขนาดใหญ่ = 60% ของ 50 แท่งที่ผ่านมา
NEWS_BLOCK_MINUTES = 30  # Block ±30 นาที รอบข่าว

# High-impact news events (placeholder - ควรดึงจาก economic calendar API)
HIGH_IMPACT_EVENTS = [
    "NFP",           # Non-Farm Payrolls
    "FOMC",          # Federal Reserve Meeting
    "CPI",           # Consumer Price Index
    "Retail Sales",
    "GDP",
    "Interest Rate Decision"
]


class G1MarketScanner:
    """
    G1 Market Scanning Agent

    Scan market conditions และตรวจสอบว่าควรส่งต่อ G2 หรือไม่
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize G1 Scanner

        Args:
            config: Configuration dict with optional parameters:
                - sr_buffer_points: S/R distance threshold (default: 50.0)
                - spike_threshold: Spike detection threshold (default: 0.60)
                - news_block_minutes: News event block time (default: 30)
                - verbose: Print debug info (default: False)
        """
        self.config = config or {}
        self.sr_buffer = self.config.get('sr_buffer_points', SR_BUFFER_POINTS)
        self.spike_threshold = self.config.get('spike_threshold', SPIKE_THRESHOLD)
        self.news_block = self.config.get('news_block_minutes', NEWS_BLOCK_MINUTES)
        self.verbose = self.config.get('verbose', False)

    def scan_conditions(self, market_data: Dict) -> Optional[Dict]:
        """
        Main scanning function - ตรวจสอบ market conditions

        Args:
            market_data: Dict containing:
                - m5_ohlcv: List of M5 candles (80+)
                - h1_candles: List of H1 candles (20+)
                - current_price: Current market price
                - timestamp: Current timestamp
                - symbol: Symbol name (e.g., "XAUUSD")

        Returns:
            world_state Dict if ≥ 2/3 conditions met, None otherwise
        """
        # Convert to DataFrames
        m5_df = pd.DataFrame(market_data['m5_ohlcv'])
        h1_df = pd.DataFrame(market_data['h1_candles'])

        current_price = market_data['current_price']
        timestamp = market_data.get('timestamp', datetime.now().isoformat())
        symbol = market_data.get('symbol', 'XAUUSD')

        # === Calculate Indicators ===

        # RSI
        m5_df['rsi'] = calculate_rsi(m5_df, period=14)
        current_rsi = float(m5_df['rsi'].iloc[-1])
        rsi_zone = get_rsi_zone(current_rsi)

        # S/R Levels
        sr_levels = detect_sr_levels(m5_df, swing_window=5, zone_threshold=50, min_touches=2)
        nearest_sr = find_nearest_sr_level(current_price, sr_levels, max_distance=200)

        # H1 Trend
        h1_trend = detect_trend(h1_df, method='combined')

        # Session
        session = self._detect_session(timestamp)

        # News flag (placeholder)
        news_flag, news_event = self._check_news_event(timestamp)

        # Candle patterns
        latest_candle = market_data['m5_ohlcv'][-1]
        prev_candle = market_data['m5_ohlcv'][-2] if len(market_data['m5_ohlcv']) >= 2 else None
        pattern_analysis = analyze_candle_pattern(latest_candle, prev_candle)

        # Spike detection
        spike_detected, spike_ratio = self._detect_spike(m5_df)

        # Detect condition (A1-A6)
        condition_candidate = self._detect_condition(m5_df, h1_trend)

        # Pattern candidate
        pattern_candidate = self._identify_pattern_candidate(
            pattern_analysis,
            spike_detected,
            nearest_sr,
            current_rsi
        )

        # === Check 3 Conditions ===

        conditions_met = 0
        condition_details = []

        # เงื่อนไข 1: RSI zone ไม่ใช่โซนกลาง (45-54) เว้นแต่ sideways
        rsi_pass = not (45 <= current_rsi <= 54) or condition_candidate in ['A4_sideways_up', 'A5_sideways_down']
        if rsi_pass:
            conditions_met += 1
            condition_details.append(f"RSI {current_rsi:.1f} ({rsi_zone})")

        # เงื่อนไข 2: ราคาใกล้ S/R level
        sr_distance = nearest_sr['distance'] if nearest_sr else 999
        sr_pass = sr_distance <= self.sr_buffer
        if sr_pass:
            conditions_met += 1
            condition_details.append(f"Near S/R (${nearest_sr['price']:.2f}, {sr_distance:.1f}pts)")

        # เงื่อนไข 3: มี pattern candidate
        pattern_pass = pattern_candidate != "ไม่มี"
        if pattern_pass:
            conditions_met += 1
            condition_details.append(f"Pattern: {pattern_candidate}")

        # Debug logging
        if self.verbose:
            print(f"\n🔍 Condition Check:")
            print(f"   1. RSI: {'✓' if rsi_pass else '✗'} RSI={current_rsi:.1f} ({rsi_zone})")
            print(f"   2. S/R: {'✓' if sr_pass else '✗'} Distance={sr_distance:.1f}pts (threshold={self.sr_buffer})")
            print(f"   3. Pattern: {'✓' if pattern_pass else '✗'} {pattern_candidate}")
            print(f"   Result: {conditions_met}/3 conditions met")

        # === ตัดสินใจส่งต่อ G2 หรือไม่ ===

        if conditions_met < 2:
            # ไม่ครบเงื่อนไข - ไม่ส่งต่อ
            if self.verbose:
                print(f"   ⏭  Not enough conditions (need ≥2/3)")
            return None

        # ครบเงื่อนไข - สร้าง world_state
        world_state = {
            "symbol": symbol,
            "price": round(current_price, 2),
            "rsi": round(current_rsi, 2),
            "rsi_zone": rsi_zone,
            "h1_trend": h1_trend,
            "condition_candidate": condition_candidate,
            "pattern_candidate": pattern_candidate,
            "nearest_sr": round(nearest_sr['price'], 2) if nearest_sr else None,
            "sr_distance": round(sr_distance, 2),
            "sr_touches": nearest_sr['touches'] if nearest_sr else 0,
            "sr_type": nearest_sr['type'] if nearest_sr else None,
            "sr_strength": nearest_sr['strength'] if nearest_sr else 0.0,
            "spike_detected": spike_detected,
            "spike_ratio": round(spike_ratio, 3),
            "news_flag": news_flag,
            "news_event": news_event,
            "session": session,
            "spread_ok": True,  # Placeholder - ควรตรวจจาก broker feed
            "candles_checked": len(m5_df),
            "timestamp": timestamp,
            "conditions_met": conditions_met,
            "condition_details": condition_details,
            # Additional data for G2
            "candle_pattern": {
                "body_size": pattern_analysis['body_size'],
                "lower_wick": pattern_analysis['lower_wick'],
                "upper_wick": pattern_analysis['upper_wick'],
                "is_bullish": pattern_analysis['is_bullish'],
                "is_engulfing": pattern_analysis['is_engulfing'],
                "has_long_lower_wick": pattern_analysis['has_long_lower_wick'],
                "has_long_upper_wick": pattern_analysis['has_long_upper_wick']
            }
        }

        return world_state

    def _detect_condition(self, m5_df: pd.DataFrame, h1_trend: str) -> str:
        """
        ระบุ Condition A1-A6 จากรูปแบบกราฟ

        Returns:
            "A1_uptrend" | "A2_downtrend" | "A3_mountain" |
            "A4_sideways_up" | "A5_sideways_down" | "A6_unclear"
        """
        # ใช้ 80 แท่งล่าสุด
        df = m5_df.tail(80).copy()

        if len(df) < 50:
            return "A6_unclear"

        # คำนวณ trend ของ M5
        m5_trend = detect_trend(df, method='combined')

        # A1: Uptrend - ราคาขึ้นชัด + H1 bullish
        if m5_trend == 'bullish' and h1_trend in ['bullish', 'sideways']:
            # ตรวจสอบความต่อเนื่องของ uptrend
            highs = df['high'].values
            lows = df['low'].values

            # นับ higher highs และ higher lows
            hh_count = sum(1 for i in range(10, len(highs)) if highs[i] > highs[i-10])
            hl_count = sum(1 for i in range(10, len(lows)) if lows[i] > lows[i-10])

            if hh_count > 6 and hl_count > 6:
                return "A1_uptrend"

        # A2: Downtrend - ราคาลงชัด + H1 bearish
        if m5_trend == 'bearish' and h1_trend in ['bearish', 'sideways']:
            highs = df['high'].values
            lows = df['low'].values

            lh_count = sum(1 for i in range(10, len(highs)) if highs[i] < highs[i-10])
            ll_count = sum(1 for i in range(10, len(lows)) if lows[i] < lows[i-10])

            if lh_count > 6 and ll_count > 6:
                return "A2_downtrend"

        # A3: Mountain - ขึ้นแล้วลง (ใช้ 50 แท่ง)
        if len(df) >= 50:
            df_50 = df.tail(50)
            closes = df_50['close'].values

            # หา peak (จุดสูงสุด)
            mid_point = len(closes) // 2
            peak_region = closes[mid_point-10:mid_point+10]
            max_price = closes.max()
            max_idx = np.argmax(closes)

            # ตรวจสอบว่ามีลักษณะภูเขา: ขึ้นก่อน peak, ลงหลัง peak
            if mid_point-15 < max_idx < mid_point+15:
                left_trend = closes[:max_idx].mean() < closes[max_idx]
                right_trend = closes[max_idx:].mean() < closes[max_idx]

                # ฐานด้านขวาไม่ลอย (ราคาปัจจุบันอยู่ต่ำกว่า peak อย่างชัดเจน)
                current_vs_peak = (max_price - closes[-1]) / max_price

                # CRITICAL FIX: ตรวจสอบว่าหลัง peak แล้วราคา stabilize ที่ฐาน
                # ไม่ใช่ลงต่อเนื่อง (falling knife)
                recent_10 = closes[-10:]
                recent_trend = recent_10[-1] - recent_10[0]
                recent_volatility = np.std(recent_10)

                # ถ้าราคายังลงต่อเนื่องในแท่งล่าสุด → ไม่ใช่ mountain
                is_still_falling = recent_trend < -5.0  # ลงมากกว่า $5 ใน 10 แท่ง

                # ฐานต้องค่อนข้าง stable (volatility ต่ำ)
                is_base_stable = recent_volatility < (max_price * 0.008)  # < 0.8% ของ peak

                if left_trend and right_trend and current_vs_peak > 0.001:
                    # เช็คว่าไม่ใช่ falling knife
                    if not is_still_falling and is_base_stable:
                        # เช็คว่า H1 ไม่ bearish (ถ้า bearish แรง → ไม่ควรเข้า mountain BUY)
                        if h1_trend != 'bearish':
                            return "A3_mountain"

        # A4/A5: Sideways - ราคาสวิงออกข้าง
        if m5_trend == 'sideways':
            # ใช้ 30 แท่งล่าสุด
            recent = df.tail(30)
            price_range = recent['high'].max() - recent['low'].min()
            avg_price = recent['close'].mean()
            range_pct = (price_range / avg_price) * 100

            # Sideways = range แคบ (< 1.5% ของราคา)
            if range_pct < 1.5:
                # ดูว่ามาจากขาขึ้นหรือขาลง (50 แท่งก่อนหน้า)
                earlier = df.iloc[-60:-30] if len(df) >= 60 else df.iloc[:-30]
                if len(earlier) > 0:
                    earlier_trend = earlier['close'].iloc[-1] - earlier['close'].iloc[0]

                    if earlier_trend > 0:
                        return "A4_sideways_up"
                    else:
                        return "A5_sideways_down"

        # Default: A6 Unclear
        return "A6_unclear"

    def _identify_pattern_candidate(self, pattern_analysis: Dict, spike_detected: bool,
                                    nearest_sr: Optional[Dict], current_rsi: float) -> str:
        """
        ระบุ pattern candidate (B1/B2/B3)

        Returns:
            "ไม้รวย" | "ตามเจ้า" | "แนวเด้ง" | "ไม่มี"
        """
        # B1: ไม้รวย (Spike Reversal)
        if spike_detected:
            # ต้องมี long wick และอยู่ที่ S/R
            if nearest_sr and nearest_sr.get('distance', 999) < SR_BUFFER_POINTS:
                if pattern_analysis['has_long_lower_wick'] and current_rsi <= 55:
                    return "ไม้รวย"
                elif pattern_analysis['has_long_upper_wick'] and current_rsi >= 45:
                    return "ไม้รวย"

        # B3: แนวเด้ง (Key Level Bounce)
        if nearest_sr and nearest_sr.get('touches', 0) >= 2:
            # ราคาแตะ S/R + มี rejection candle
            if nearest_sr.get('distance', 999) < SR_BUFFER_POINTS:
                if pattern_analysis['has_long_lower_wick'] or pattern_analysis['has_long_upper_wick']:
                    return "แนวเด้ง"
                if pattern_analysis['is_engulfing']:
                    return "แนวเด้ง"

        # B2: ตามเจ้า (Smart Money Follow) - ต้องดูจาก breakout + retest
        # ยากตรวจใน G1 - ปล่อยให้ Claude ใน G3 ตัดสินใจ

        return "ไม่มี"

    def _detect_spike(self, m5_df: pd.DataFrame) -> Tuple[bool, float]:
        """
        ตรวจจับ spike ขนาดใหญ่

        Returns:
            (spike_detected: bool, spike_ratio: float)
        """
        if len(m5_df) < 50:
            return False, 0.0

        # ใช้ 50 แท่งล่าสุด
        df = m5_df.tail(50)

        # คำนวณ average range ของ 50 แท่ง
        df['range'] = df['high'] - df['low']
        avg_range = df['range'].mean()

        # ดูแท่งล่าสุด 5 แท่ง
        recent_ranges = df['range'].tail(5)
        max_recent_range = recent_ranges.max()

        # Spike = range ใหญ่กว่า threshold
        spike_ratio = max_recent_range / avg_range if avg_range > 0 else 0
        spike_detected = spike_ratio >= self.spike_threshold

        return spike_detected, spike_ratio

    def _detect_session(self, timestamp: str) -> str:
        """
        ระบุ trading session (Asia/London/NY)

        Args:
            timestamp: ISO format timestamp

        Returns:
            "Asia" | "London" | "NY" | "Off-hours"
        """
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            # Convert to UTC
            if dt.tzinfo is None:
                dt = pytz.UTC.localize(dt)
            else:
                dt = dt.astimezone(pytz.UTC)

            hour = dt.hour

            # Session times (UTC)
            # Asia: 00:00 - 09:00 UTC
            # London: 08:00 - 17:00 UTC
            # NY: 13:00 - 22:00 UTC

            if 0 <= hour < 9:
                return "Asia"
            elif 8 <= hour < 17:
                if 8 <= hour < 13:
                    return "London"
                else:
                    return "London/NY"  # Overlap
            elif 13 <= hour < 22:
                return "NY"
            else:
                return "Off-hours"

        except Exception as e:
            print(f"Warning: Failed to parse timestamp {timestamp}: {e}")
            return "Unknown"

    def _check_news_event(self, timestamp: str) -> Tuple[bool, str]:
        """
        ตรวจสอบว่ามี high-impact news event ใกล้เวลานี้หรือไม่

        Args:
            timestamp: ISO format timestamp

        Returns:
            (news_flag: bool, event_name: str)

        Note:
            Phase I ใช้ placeholder - ควรเชื่อมต่อกับ Economic Calendar API
            เช่น: https://www.forexfactory.com/calendar
        """
        # TODO: Phase II - เชื่อม Economic Calendar API
        # ตอนนี้ return False เสมอ
        return False, ""

        # Example implementation with API:
        # try:
        #     dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        #
        #     # Query economic calendar
        #     events = get_upcoming_events(dt, window_minutes=self.news_block)
        #
        #     for event in events:
        #         if event['impact'] == 'HIGH':
        #             return True, event['name']
        #
        #     return False, ""
        # except:
        #     return False, ""


# Helper function
def scan_market(market_data: Dict, config: Optional[Dict] = None) -> Optional[Dict]:
    """
    Convenience function สำหรับ scan market

    Args:
        market_data: Market data dict
        config: Optional configuration

    Returns:
        world_state Dict or None
    """
    scanner = G1MarketScanner(config)
    return scanner.scan_conditions(market_data)


# Example usage
if __name__ == "__main__":
    from utils import create_connector
    from dotenv import load_dotenv
    import json

    load_dotenv()

    print("="*70)
    print("G1 MARKET SCANNING AGENT TEST")
    print("="*70)

    # Get market data
    print("\n📊 Fetching market data...")
    with create_connector('simulate') as conn:
        market_data = conn.get_latest_candles('XAUUSD', m5_count=100, h1_count=50)

    print(f"✓ M5 candles: {len(market_data['m5_ohlcv'])}")
    print(f"✓ H1 candles: {len(market_data['h1_candles'])}")
    print(f"✓ Current price: ${market_data['current_price']:.2f}")

    # Scan conditions
    print(f"\n🔍 Scanning market conditions...")
    scanner = G1MarketScanner(config={'verbose': True})
    world_state = scanner.scan_conditions(market_data)

    if world_state:
        print(f"\n✅ CANDIDATE FOUND! ({world_state['conditions_met']}/3 conditions met)")
        print(f"\n📋 World State:")
        print(json.dumps(world_state, indent=2, ensure_ascii=False))

        print(f"\n🎯 Summary:")
        print(f"   Condition: {world_state['condition_candidate']}")
        print(f"   Pattern: {world_state['pattern_candidate']}")
        print(f"   RSI: {world_state['rsi']} ({world_state['rsi_zone']})")
        print(f"   H1 Trend: {world_state['h1_trend']}")
        print(f"   Session: {world_state['session']}")

        if world_state['nearest_sr']:
            print(f"   Nearest S/R: ${world_state['nearest_sr']} "
                  f"({world_state['sr_type']}, {world_state['sr_distance']:.1f}pts away)")

        print(f"\n✓ Ready to send to G2 (Quantitative Analysis)")

    else:
        print(f"\n⏭  No candidate found (conditions not met)")
        print(f"   Waiting for next M5 candle...")

    print("\n" + "="*70)
