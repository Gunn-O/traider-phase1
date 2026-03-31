"""
G2 — Quantitative Analysis Agent

หน้าที่:
- รับ world_state จาก G1
- คำนวณ scores: RSI zone score, S/R strength score, Trend alignment score
- รวม weighted score → confidence (0.0-1.0)
- Filter: ผ่านต่อเมื่อ confidence ≥ 0.70 เท่านั้น

Output: confidence_data → ส่งต่อ G3 (Decision Agent)
"""

from typing import Dict, Optional


# Default weights
DEFAULT_WEIGHTS = {
    "rsi": 0.30,    # 30% weight
    "sr": 0.40,     # 40% weight
    "trend": 0.30   # 30% weight
}


class G2QuantAnalyzer:
    """
    G2 Quantitative Analysis Agent

    คำนวณ confidence score จาก world_state
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize G2 Analyzer

        Args:
            config: Configuration dict:
                - weights: Dict with 'rsi', 'sr', 'trend' weights
                - min_confidence: Minimum confidence to pass (default: 0.70)
                - verbose: Print debug info (default: False)
        """
        self.config = config or {}
        self.weights = self.config.get('weights', DEFAULT_WEIGHTS)
        self.min_confidence = self.config.get('min_confidence', 0.70)
        self.verbose = self.config.get('verbose', False)

        # Validate weights
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01:
            print(f"Warning: Weights sum to {total_weight}, not 1.0. Normalizing...")
            for key in self.weights:
                self.weights[key] /= total_weight

    def analyze(self, world_state: Dict) -> Optional[Dict]:
        """
        วิเคราะห์และคำนวณ confidence score

        Args:
            world_state: Output จาก G1

        Returns:
            confidence_data Dict if confidence ≥ min_confidence, None otherwise
            {
                'confidence': float,
                'filter_pass': bool,
                'rsi_score': float,
                'sr_score': float,
                'trend_score': float,
                'breakdown': str
            }
        """
        # Calculate individual scores
        rsi_score = self._calculate_rsi_score(world_state)
        sr_score = self._calculate_sr_score(world_state)
        trend_score = self._calculate_trend_score(world_state)

        # Weighted confidence
        confidence = (
            rsi_score * self.weights['rsi'] +
            sr_score * self.weights['sr'] +
            trend_score * self.weights['trend']
        )

        confidence = round(confidence, 3)

        # Build breakdown
        breakdown = self._build_breakdown(world_state, rsi_score, sr_score, trend_score)

        # Debug logging
        if self.verbose:
            print(f"\n📊 G2 Quantitative Analysis:")
            print(f"   RSI Score:   {rsi_score:.3f} (weight: {self.weights['rsi']})")
            print(f"   S/R Score:   {sr_score:.3f} (weight: {self.weights['sr']})")
            print(f"   Trend Score: {trend_score:.3f} (weight: {self.weights['trend']})")
            print(f"   ─────────────────────────────")
            print(f"   Confidence:  {confidence:.3f}")
            print(f"   Threshold:   {self.min_confidence}")
            print(f"   Status:      {'✓ PASS' if confidence >= self.min_confidence else '✗ FAIL'}")

        # Filter check
        filter_pass = confidence >= self.min_confidence

        if not filter_pass:
            if self.verbose:
                print(f"   ⏭  Confidence too low - not sending to G3")
            return None

        # Return confidence data
        return {
            'confidence': confidence,
            'filter_pass': True,
            'rsi_score': round(rsi_score, 3),
            'sr_score': round(sr_score, 3),
            'trend_score': round(trend_score, 3),
            'breakdown': breakdown,
            'weights_used': self.weights.copy()
        }

    def _calculate_rsi_score(self, world_state: Dict) -> float:
        """
        คำนวณ RSI zone score (0.0-1.0)

        ตาม Strategy v5 RSI Rules:
        - ≤ 25: Extreme oversold → 1.0 (strongest)
        - 26-35: Oversold → 0.85
        - 36-44: Near oversold → 0.70
        - 45-54: Neutral → 0.30 (weakest)
        - 55-65: Momentum → 0.70 (BUY ตามเจ้า / SELL ที่ resistance)
        - 66-70: Strong momentum → 0.85
        - > 70: Overbought → 1.0 (for SELL)
        """
        rsi = world_state.get('rsi', 50)
        rsi_zone = world_state.get('rsi_zone', 'neutral')
        condition = world_state.get('condition_candidate', 'A6_unclear')

        # Extreme zones = strongest signals
        if rsi <= 25:
            return 1.0  # Extreme oversold - BUY แรงมาก
        elif rsi >= 75:
            return 1.0  # Extreme overbought - SELL แรงมาก

        # Strong zones
        elif rsi <= 35:
            return 0.85  # Oversold
        elif rsi >= 65:
            return 0.85  # Overbought / Strong momentum

        # Medium zones
        elif rsi <= 44:
            return 0.70  # Near oversold
        elif rsi >= 56:
            return 0.70  # Momentum zone

        # Neutral zone = weakest (except sideways)
        elif 45 <= rsi <= 54:
            # Sideways condition allows neutral RSI
            if condition in ['A4_sideways_up', 'A5_sideways_down']:
                return 0.50
            else:
                return 0.30  # Very weak for non-sideways

        else:
            return 0.50  # Fallback

    def _calculate_sr_score(self, world_state: Dict) -> float:
        """
        คำนวณ S/R strength score (0.0-1.0)

        Factors:
        1. จำนวน touches (ยิ่งมาก ยิ่งแข็ง)
        2. ระยะห่างจากราคาปัจจุบัน (ยิ่งใกล้ ยิ่งดี)
        3. S/R strength from detection algorithm
        """
        if not world_state.get('nearest_sr'):
            return 0.0  # ไม่มี S/R = score 0

        touches = world_state.get('sr_touches', 0)
        distance = world_state.get('sr_distance', 999)
        sr_strength = world_state.get('sr_strength', 0.0)

        # Score from touches (max at 4+ touches)
        touch_score = min(touches / 4.0, 1.0)

        # Score from distance (inverse - closer is better)
        # Distance 0-50 pts = score 1.0 -> 0.0
        distance_score = max(0.0, 1.0 - (distance / 50.0))

        # Combined score (weighted average)
        score = (
            touch_score * 0.4 +
            distance_score * 0.4 +
            sr_strength * 0.2
        )

        return min(1.0, score)

    def _calculate_trend_score(self, world_state: Dict) -> float:
        """
        คำนวณ trend alignment score (0.0-1.0)

        Logic:
        - H1 trend aligned with condition → 1.0 (strong)
        - H1 sideways → 0.60 (moderate)
        - H1 trend against condition → 0.30 (weak/risky)
        """
        h1_trend = world_state.get('h1_trend', 'sideways')
        condition = world_state.get('condition_candidate', 'A6_unclear')
        rsi = world_state.get('rsi', 50)

        # Determine expected action from condition
        if condition in ['A1_uptrend', 'A3_mountain', 'A4_sideways_up']:
            expected_direction = 'bullish'
        elif condition in ['A2_downtrend', 'A5_sideways_down']:
            expected_direction = 'bearish'
        else:  # A6_unclear
            expected_direction = 'neutral'

        # Check alignment
        if h1_trend == expected_direction:
            return 1.0  # Perfect alignment
        elif h1_trend == 'sideways':
            return 0.60  # Sideways allows both directions
        elif expected_direction == 'neutral':
            # A6 unclear - sideways trend is acceptable
            if h1_trend == 'sideways':
                return 0.70
            else:
                return 0.50
        else:
            # Trend against expected direction = risky
            return 0.30

    def _build_breakdown(self, world_state: Dict, rsi_score: float,
                        sr_score: float, trend_score: float) -> str:
        """
        สร้าง breakdown text อธิบาย confidence

        Returns:
            Human-readable explanation string
        """
        rsi = world_state.get('rsi', 50)
        rsi_zone = world_state.get('rsi_zone', 'neutral')

        sr_touches = world_state.get('sr_touches', 0)
        sr_distance = world_state.get('sr_distance', 0)
        sr_price = world_state.get('nearest_sr', 0)

        h1_trend = world_state.get('h1_trend', 'sideways')
        condition = world_state.get('condition_candidate', 'A6_unclear')

        parts = []

        # RSI part
        parts.append(f"RSI {rsi:.1f} ({rsi_zone})")

        # S/R part
        if sr_touches > 0:
            parts.append(f"S/R {sr_touches} touches at ${sr_price:.2f}")
        else:
            parts.append("No strong S/R")

        # Trend part
        parts.append(f"H1 {h1_trend} aligned with {condition}")

        return ", ".join(parts)


# Convenience function
def analyze_market(world_state: Dict, config: Optional[Dict] = None) -> Optional[Dict]:
    """
    Convenience function สำหรับวิเคราะห์ world_state

    Args:
        world_state: Output from G1
        config: Optional configuration

    Returns:
        confidence_data Dict or None
    """
    analyzer = G2QuantAnalyzer(config)
    return analyzer.analyze(world_state)


# Example usage
if __name__ == "__main__":
    from agents.g1_signal_logic import G1MarketScanner
    from utils import create_connector
    from dotenv import load_dotenv
    import json

    load_dotenv()

    print("="*70)
    print("G2 QUANTITATIVE ANALYSIS AGENT TEST")
    print("="*70)

    # Get market data
    print("\n📊 Fetching market data...")
    with create_connector('simulate') as conn:
        market_data = conn.get_latest_candles('XAUUSD', m5_count=100, h1_count=50)

    print(f"✓ Current price: ${market_data['current_price']:.2f}")

    # G1: Scan conditions
    print(f"\n🔍 G1: Scanning market conditions...")
    g1_scanner = G1MarketScanner(config={'verbose': True})
    world_state = g1_scanner.scan_conditions(market_data)

    if world_state:
        print(f"\n✅ G1 found candidate!")

        # G2: Analyze
        print(f"\n🔍 G2: Quantitative Analysis...")
        g2_analyzer = G2QuantAnalyzer(config={'verbose': True})
        confidence_data = g2_analyzer.analyze(world_state)

        if confidence_data:
            print(f"\n✅ G2 PASS - Sending to G3!")
            print(f"\n📋 Confidence Data:")
            print(json.dumps(confidence_data, indent=2))

            print(f"\n🎯 Ready for G3 (Decision Agent)")
        else:
            print(f"\n⏭  G2 blocked - confidence too low")

    else:
        print(f"\n⏭  G1: No candidate found")
        print(f"   Simulating G2 with mock world_state...")

        # Mock world_state for testing G2
        mock_state = {
            'symbol': 'XAUUSD',
            'price': 3050.48,
            'rsi': 36.2,
            'rsi_zone': 'near_oversold',
            'h1_trend': 'bullish',
            'condition_candidate': 'A3_mountain',
            'nearest_sr': 3050.00,
            'sr_distance': 0.48,
            'sr_touches': 3,
            'sr_strength': 0.92,
            'pattern_candidate': 'แนวเด้ง',
            'session': 'London'
        }

        print(f"\n📝 Mock world_state (example scenario):")
        print(json.dumps(mock_state, indent=2, ensure_ascii=False))

        g2_analyzer = G2QuantAnalyzer(config={'verbose': True})
        confidence_data = g2_analyzer.analyze(mock_state)

        if confidence_data:
            print(f"\n✅ G2 would PASS this scenario")
        else:
            print(f"\n⏭  G2 would block this scenario")

    print("\n" + "="*70)
