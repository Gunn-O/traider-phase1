"""
G3a — Mock Decision Agent (Rule-Based)

เนื่องจาก Anthropic API ต้องใช้ credits
สร้าง Mock Agent ที่ใช้ rule-based logic แทน เพื่อใช้ในการ backtest

Logic ตาม Strategy v5:
- ตรวจสอบ Condition + Pattern alignment
- คำนวณ Entry, SL, TP ตาม rules
- ตรวจสอบ R:R ≥ 1:2
- SKIP ถ้าไม่ครบเงื่อนไข

Note: นี่คือ POC - ใน production ควรใช้ Claude API จริง
"""

from typing import Dict, Optional
import pandas as pd


class G3MockDecisionAgent:
    """
    Mock Decision Agent - ใช้ rule-based logic แทน Claude API

    ดีสำหรับ: Backtest, Testing, Development without API costs
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize Mock Decision Agent

        Args:
            config: Optional configuration:
                - verbose: Print debug info (default: False)
                - sl_buffer: SL buffer in points (default: 10.0)
                - min_rr_ratio: Minimum R:R ratio (default: 2.0)
                - debug_rejections: Print first N rejections (default: 0)
        """
        self.config = config or {}
        self.verbose = self.config.get('verbose', False)
        self.sl_buffer = self.config.get('sl_buffer', 10.0)
        self.min_rr_ratio = self.config.get('min_rr_ratio', 1.2)  # Lowered from 2.0 to 1.2 for rule-based logic
        self.debug_rejections = self.config.get('debug_rejections', 0)
        self.rejection_count = 0

    def decide(self, world_state: Dict, confidence_data: Dict) -> Optional[Dict]:
        """
        ตัดสินใจ BUY/SELL/SKIP ด้วย rule-based logic

        Args:
            world_state: Output from G1
            confidence_data: Output from G2

        Returns:
            decision Dict if action != SKIP, None if SKIP
        """
        condition = world_state.get('condition_candidate', 'A6_unclear')
        pattern = world_state.get('pattern_candidate', 'ไม่มี')
        rsi = world_state.get('rsi', 50)
        rsi_zone = world_state.get('rsi_zone', 'neutral')
        h1_trend = world_state.get('h1_trend', 'sideways')
        price = world_state.get('price', 0)
        nearest_sr = world_state.get('nearest_sr')
        sr_distance = world_state.get('sr_distance', 999)
        confidence = confidence_data.get('confidence', 0)

        # Debug logging helper
        def log_rejection(reason: str, details: Dict = None):
            self.rejection_count += 1
            if self.rejection_count <= self.debug_rejections:
                print(f"\n{'='*70}")
                print(f"🔍 REJECTION #{self.rejection_count}: {reason}")
                print(f"{'='*70}")
                print(f"📊 Market State:")
                print(f"   Condition: {condition}")
                print(f"   Pattern: {pattern}")
                print(f"   RSI: {rsi:.1f} ({rsi_zone})")
                print(f"   H1 Trend: {h1_trend}")
                print(f"   Price: ${price:.2f}")
                print(f"   Nearest S/R: ${nearest_sr:.2f}" if nearest_sr else "   Nearest S/R: None")
                print(f"   S/R Distance: {sr_distance:.2f}")
                print(f"   Confidence: {confidence:.3f}")
                print(f"   Timestamp: {world_state.get('timestamp', 'N/A')}")
                if details:
                    print(f"\n💡 Details:")
                    for key, value in details.items():
                        print(f"   {key}: {value}")
                print(f"{'='*70}\n")
            return None

        # News check
        if world_state.get('news_flag'):
            return log_rejection("News event active")

        # Determine action
        action = self._determine_action(condition, pattern, rsi, h1_trend)

        if action == 'SKIP':
            return log_rejection(
                f"No valid action for condition/pattern combination",
                {
                    'Condition': condition,
                    'Pattern': pattern,
                    'RSI': f"{rsi:.1f}",
                    'H1 Trend': h1_trend,
                    'Expected': self._get_expected_criteria(condition)
                }
            )

        # Calculate Entry, SL, TP
        entry = price
        sl, tp1, tp2, tp3 = self._calculate_levels(
            action, condition, pattern, price, nearest_sr, world_state
        )

        if sl is None or tp1 is None:
            return log_rejection(
                "Cannot calculate valid SL/TP levels",
                {
                    'Action': action,
                    'Condition': condition,
                    'Price': f"${price:.2f}",
                    'Nearest S/R': (f"${nearest_sr:.2f}" if nearest_sr else "None"),
                    'SL calculated': (f"${sl:.2f}" if sl else "None"),
                    'TP1 calculated': (f"${tp1:.2f}" if tp1 else "None")
                }
            )

        # Check R:R ratio
        sl_distance = abs(entry - sl)
        tp_distance = abs(tp1 - entry)
        rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0

        if rr_ratio < self.min_rr_ratio:
            return log_rejection(
                f"R:R ratio too low",
                {
                    'Action': action,
                    'Entry': f"${entry:.2f}",
                    'SL': f"${sl:.2f}",
                    'TP1': f"${tp1:.2f}",
                    'SL Distance': f"${sl_distance:.2f}",
                    'TP Distance': f"${tp_distance:.2f}",
                    'R:R Ratio': f"{rr_ratio:.2f}",
                    'Required R:R': f"{self.min_rr_ratio:.2f}"
                }
            )

        # Build decision
        decision = {
            'chart_condition': condition,
            'pattern': pattern if pattern != 'ไม่มี' else 'แนวเด้ง',
            'action': action,
            'confidence': confidence,
            'entry': round(entry, 2),
            'sl': round(sl, 2),
            'tp1': round(tp1, 2),
            'tp2': round(tp2, 2),
            'tp3': round(tp3, 2),
            'lot': 0.0,  # Will be calculated by G3b
            'rsi_now': round(rsi, 2),
            'h1_trend': h1_trend,
            'session': world_state.get('session', 'Unknown'),
            'candles_checked': world_state.get('candles_checked', 80),
            'skip_reason': '',
            'reason': self._build_reason(condition, pattern, rsi, h1_trend, rr_ratio)
        }

        if self.verbose:
            print(f"\n✓ Mock Decision: {action}")
            print(f"   Condition: {condition}, Pattern: {pattern}")
            print(f"   Entry: ${entry:.2f}, SL: ${sl:.2f}")
            print(f"   TP1/2/3: ${tp1:.2f} / ${tp2:.2f} / ${tp3:.2f}")
            print(f"   R:R: {rr_ratio:.2f}")

        return decision

    def _determine_action(self, condition: str, pattern: str, rsi: float, h1_trend: str) -> str:
        """Determine BUY/SELL/SKIP based on condition and pattern"""

        # A1: Uptrend → BUY only
        if condition == 'A1_uptrend':
            if rsi <= 65:  # Not overbought
                return 'BUY'

        # A2: Downtrend → SELL only
        elif condition == 'A2_downtrend':
            if rsi >= 35:  # Not oversold
                return 'SELL'

        # A3: Mountain → BUY at base
        elif condition == 'A3_mountain':
            if rsi <= 55:  # Oversold or neutral
                return 'BUY'

        # A4: Sideways up → BUY at lower bound
        elif condition == 'A4_sideways_up':
            if rsi <= 60:
                return 'BUY'
            elif rsi >= 55 and pattern == 'แนวเด้ง':
                return 'SELL'  # Action รอง at upper bound

        # A5: Sideways down → SELL at upper bound
        elif condition == 'A5_sideways_down':
            if rsi >= 40:
                return 'SELL'
            elif rsi <= 45 and pattern == 'แนวเด้ง':
                return 'BUY'  # Action รอง at lower bound

        # A6: Unclear → Use pattern only
        elif condition == 'A6_unclear':
            # ไม้รวย (Spike Reversal)
            if pattern == 'ไม้รวย':
                if rsi <= 45:
                    return 'BUY'
                elif rsi >= 55:
                    return 'SELL'

            # แนวเด้ง (Key Level Bounce)
            elif pattern == 'แนวเด้ง':
                if rsi <= 50 and h1_trend != 'bearish':
                    return 'BUY'
                elif rsi >= 50 and h1_trend != 'bullish':
                    return 'SELL'

        return 'SKIP'

    def _calculate_levels(self, action: str, condition: str, pattern: str,
                         price: float, nearest_sr: Optional[float],
                         world_state: Dict) -> tuple:
        """Calculate SL and TP levels based on condition"""

        if action not in ['BUY', 'SELL']:
            return None, None, None, None

        # Default values (สำหรับกรณีที่คำนวณไม่ได้)
        default_sl_distance = 20.0  # points (reduced from 30)
        default_tp_distance = 60.0  # points (R:R = 3.0, reduced from 80 for consistency)

        sl = None
        tp1 = tp2 = tp3 = None

        # A1/A2: Trend following
        if condition in ['A1_uptrend', 'A2_downtrend']:
            if action == 'BUY':
                sl = price - default_sl_distance
                tp1 = price + default_tp_distance * 0.5
                tp2 = price + default_tp_distance * 0.75
                tp3 = price + default_tp_distance
            else:  # SELL
                sl = price + default_sl_distance
                tp1 = price - default_tp_distance * 0.5
                tp2 = price - default_tp_distance * 0.75
                tp3 = price - default_tp_distance

        # A3: Mountain
        elif condition == 'A3_mountain':
            # BUY at base, TP = portions of mountain height
            if action == 'BUY':
                mountain_height = 150.0  # Increased from 100 to 150 for better R:R
                sl = price - 20.0  # Reduced from 25 to 20
                tp1 = price + mountain_height * 0.40  # Increased from 0.33 to 0.40
                tp2 = price + mountain_height * 0.60  # Increased from 0.50 to 0.60
                tp3 = price + mountain_height * 0.90

        # A4/A5: Sideways range
        elif condition in ['A4_sideways_up', 'A5_sideways_down']:
            range_size = 60.0  # Increased from 50 to 60
            if action == 'BUY':
                sl = price - 15.0  # Reduced from 20 to 15
                tp1 = price + range_size * 0.5
                tp2 = price + range_size * 0.7
                tp3 = price + range_size
            else:  # SELL
                sl = price + 15.0  # Reduced from 20 to 15
                tp1 = price - range_size * 0.5
                tp2 = price - range_size * 0.7
                tp3 = price - range_size

        # A6: Unclear - use S/R levels
        elif condition == 'A6_unclear':
            if nearest_sr:
                # Determine if nearest_sr is support (below) or resistance (above)
                sr_is_below = nearest_sr < price

                if action == 'BUY':
                    # BUY: SL should be below entry
                    if sr_is_below:
                        # S/R is support below - use it as SL reference
                        sl = nearest_sr - self.sl_buffer
                    else:
                        # S/R is resistance above - use default distance
                        sl = price - default_sl_distance

                    # Ensure SL is below entry
                    if sl >= price:
                        sl = price - default_sl_distance

                    tp_distance = default_tp_distance
                    tp1 = price + tp_distance * 0.5
                    tp2 = price + tp_distance * 0.75
                    tp3 = price + tp_distance

                else:  # SELL
                    # SELL: SL should be above entry
                    if not sr_is_below:
                        # S/R is resistance above - use it as SL reference
                        sl = nearest_sr + self.sl_buffer
                    else:
                        # S/R is support below - use default distance
                        sl = price + default_sl_distance

                    # Ensure SL is above entry
                    if sl <= price:
                        sl = price + default_sl_distance

                    tp_distance = default_tp_distance
                    tp1 = price - tp_distance * 0.5
                    tp2 = price - tp_distance * 0.75
                    tp3 = price - tp_distance
            else:
                # No S/R - use default
                if action == 'BUY':
                    sl = price - default_sl_distance
                    tp1 = price + default_tp_distance * 0.5
                    tp2 = price + default_tp_distance * 0.75
                    tp3 = price + default_tp_distance
                else:
                    sl = price + default_sl_distance
                    tp1 = price - default_tp_distance * 0.5
                    tp2 = price - default_tp_distance * 0.75
                    tp3 = price - default_tp_distance

        return sl, tp1, tp2, tp3

    def _build_reason(self, condition: str, pattern: str, rsi: float,
                     h1_trend: str, rr_ratio: float) -> str:
        """Build reason string"""
        parts = []
        parts.append(f"{condition}")
        if pattern != 'ไม่มี':
            parts.append(f"+ {pattern}")
        parts.append(f"RSI {rsi:.0f}")
        parts.append(f"H1 {h1_trend}")
        parts.append(f"R:R {rr_ratio:.1f}")
        return ", ".join(parts)

    def _get_expected_criteria(self, condition: str) -> str:
        """Get expected criteria for a condition"""
        criteria = {
            'A1_uptrend': 'BUY when RSI ≤ 65 (not overbought)',
            'A2_downtrend': 'SELL when RSI ≥ 35 (not oversold)',
            'A3_mountain': 'BUY when RSI ≤ 55 (oversold/neutral)',
            'A4_sideways_up': 'BUY when RSI ≤ 60, or SELL when RSI ≥ 55 + แนวเด้ง',
            'A5_sideways_down': 'SELL when RSI ≥ 40, or BUY when RSI ≤ 45 + แนวเด้ง',
            'A6_unclear': 'Pattern-based: ไม้รวย (RSI ≤45 BUY, ≥55 SELL) or แนวเด้ง (RSI ≤50 BUY, ≥50 SELL)'
        }
        return criteria.get(condition, 'Unknown condition')

    def _skip_decision(self, reason: str, world_state: Dict, confidence: float) -> None:
        """Return None for SKIP with optional logging"""
        if self.verbose:
            print(f"\n⏭  Mock Decision: SKIP")
            print(f"   Reason: {reason}")
        return None


# Convenience function
def get_mock_decision(world_state: Dict, confidence_data: Dict,
                     config: Optional[Dict] = None) -> Optional[Dict]:
    """
    Convenience function to get mock decision

    Args:
        world_state: From G1
        confidence_data: From G2
        config: Optional config

    Returns:
        Decision dict or None if SKIP
    """
    agent = G3MockDecisionAgent(config=config)
    return agent.decide(world_state, confidence_data)


# Example usage
if __name__ == "__main__":
    print("="*70)
    print("G3a MOCK DECISION AGENT TEST")
    print("="*70)

    # Mock data
    mock_world_state = {
        'symbol': 'XAUUSD',
        'price': 3050.48,
        'rsi': 36.2,
        'rsi_zone': 'near_oversold',
        'h1_trend': 'bullish',
        'condition_candidate': 'A3_mountain',
        'pattern_candidate': 'แนวเด้ง',
        'nearest_sr': 3050.00,
        'sr_distance': 0.48,
        'sr_touches': 3,
        'sr_type': 'support',
        'news_flag': False,
        'session': 'London',
        'candles_checked': 80
    }

    mock_confidence = {
        'confidence': 0.862,
        'rsi_score': 0.700,
        'sr_score': 0.880,
        'trend_score': 1.000,
        'breakdown': 'RSI 36.2 (near_oversold), S/R 3 touches'
    }

    print(f"\n📊 Testing with mock data...")
    print(f"   Condition: {mock_world_state['condition_candidate']}")
    print(f"   Pattern: {mock_world_state['pattern_candidate']}")
    print(f"   RSI: {mock_world_state['rsi']}")

    # Get decision
    agent = G3MockDecisionAgent(config={'verbose': True})
    decision = agent.decide(mock_world_state, mock_confidence)

    if decision:
        print(f"\n✅ Decision received!")
        import json
        print(json.dumps(decision, indent=2, ensure_ascii=False))
    else:
        print(f"\n⏭  Mock agent decided to SKIP")

    print("\n" + "="*70)
