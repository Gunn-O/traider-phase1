"""
G3a — Pure Python Decision Engine (v2.1)

Replaces Claude API with deterministic rules-based logic.

หน้าที่:
- รับ world_state จาก G1 → ตัดสินใจ BUY/SELL/SKIP
- คำนวณ Entry/SL/TP ตาม Strategy v2.1
- Enforce R:R >= 1.0
- Deterministic (same input = same output)

Reference:
- CLAUDE_CODE_PROMPT_G3_PYTHON_MIGRATION.md
- G3_RULES_CHEATSHEET.md
- strategy/XAUUSD_AI_Trading_System_v2.1.md Part 2-3
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from agents.g3_claude_decision import validate_decision

# Setup logging
logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

# SL/TP calculation constants
SL_DEFAULT_PCT = 0.15           # 15% Range (midpoint of 10-20%)
SL_WICK_BUFFER_PCT = 0.05       # 5% Range beyond wick
TP_OBSTACLE_BUFFER = 1.0        # 1.0 USD (100 pip) before obstacle
TP_DEFAULT_PCT = 0.50           # 50% Range default TP
MOUNTAIN_SL_PCT = 0.075         # 7.5% Range below base
BREAKOUT_SL_PCT = 0.50          # 50% of box size
MAI_RUAY_SL_BUFFER = 0.05       # 5% Range beyond father+mother wicks


# ============================================================================
# MAIN CLASS
# ============================================================================

class G3PythonDecision:
    """
    Pure Python Decision Engine (drop-in replacement for G3ClaudeDecisionAgent)

    Usage:
        engine = G3PythonDecision()
        result = engine.decide(world_state, balance, portfolio_state)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Args:
            config: Optional config dict with 'verbose' flag
        """
        self.config = config or {}
        self.verbose = self.config.get('verbose', False)
        logger.info("G3PythonDecision initialized (Pure Python, no API)")

    def decide(self, world_state: Dict, balance: float,
               portfolio_state: Dict) -> Dict:
        """
        Make trading decision based on world_state from G1.

        Returns same shape as G3ClaudeDecisionAgent.decide():
        {
            'decision': {...},
            'llm_log': {...},
            'validation': {...},
            'success': bool
        }
        """
        technique = world_state.get('technique_candidate', 'skip')
        chart_type = world_state.get('chart_type', 'unclear')

        start_time = time.time()

        try:
            if technique == 'skip':
                decision = self._skip('No setup available (G1 skip)')
            elif chart_type == 'unclear' and technique != 'mai_ruay':
                # Mai ruay can work with unclear chart, others cannot
                decision = self._skip('Chart unclear')
            elif technique == 'twin_candle':
                if chart_type == 'mountain':
                    decision = self._decide_mountain(world_state)
                else:
                    decision = self._decide_twin_candle(world_state)
            elif technique == 'breakout_follow':
                decision = self._decide_breakout_follow(world_state)
            elif technique == 'mai_ruay':
                decision = self._decide_mai_ruay(world_state)
            else:
                decision = self._skip(f'Unknown technique: {technique}')

        except Exception as e:
            logger.error(f"G3PythonDecision error: {e}", exc_info=True)
            decision = self._skip(f'Python engine error: {type(e).__name__}')

        latency = round(time.time() - start_time, 4)

        # Build llm_log (zeros for tokens/cost since no API)
        llm_log = self._build_llm_log(decision, latency)

        # Validate using same validator as Claude engine
        validation = validate_decision(decision, world_state, balance)

        if not validation['valid']:
            logger.warning(f"G3-Python validation failed: {validation['errors']}")
            decision = self._skip(f"Validation: {', '.join(validation['errors'])[:40]}")
            # Re-build llm_log for SKIP
            llm_log = self._build_llm_log(decision, latency)

        return {
            'decision': decision,
            'llm_log': llm_log,
            'validation': validation,
            'success': True  # Always True — SKIP is also a successful decision
        }

    # ========================================================================
    # TECHNIQUE HANDLERS
    # ========================================================================

    def _decide_twin_candle(self, world_state: Dict) -> Dict:
        """
        Twin Candle technique (แท่งคู่)

        Applies to: uptrend, downtrend, sideway_up, sideway_down

        Strategy Reference: Part 2.2, 2.3, 2.4, 2.5
        """
        twin = world_state.get('twin_candle', {})
        if not twin.get('found'):
            return self._skip('No twin candle found')

        technical_price = twin.get('technical_price', 0)
        if technical_price == 0:
            return self._skip('Twin candle technical_price = 0')

        range_usd = world_state['range']['usd']
        current_price = world_state.get('current_price', 0)
        chart_type = world_state['chart_type']

        # 1. Determine direction
        if chart_type == 'uptrend':
            action = 'BUY'
        elif chart_type == 'downtrend':
            action = 'SELL'
        elif chart_type in ['sideway_down', 'sideway_up']:
            action = self._sideway_direction(world_state, chart_type)
            if action == 'SKIP':
                return self._skip('Price in middle of sideway box')
        else:
            return self._skip(f'Chart {chart_type} not supported for twin_candle')

        # 2. Entry = technical_price
        entry = technical_price

        # 3. SL: 15% Range from entry, adjust for wicks
        sl = self._calc_sl_twin_candle(entry, action, range_usd, world_state)

        # 4. TP: find obstacle before it, set TP just before
        tp = self._calc_tp_with_obstacle(entry, sl, action, world_state, range_usd)

        # 5. Enforce R:R >= 1.0
        rr = self._calc_rr(action, entry, sl, tp)
        if rr < 1.0:
            # Try extending TP
            tp = self._extend_tp_to_rr_1(action, entry, sl, world_state, range_usd)
            rr = self._calc_rr(action, entry, sl, tp)
            if rr < 1.0:
                return self._skip(f'R:R {rr:.2f} < 1.0 even with max TP')

        # 6. Build decision
        return self._build_decision(
            chart_type=chart_type,
            technique='twin_candle',
            action=action,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=f"{chart_type} twin @ {entry:.2f}, R:R={rr:.2f}"
        )

    def _decide_mai_ruay(self, world_state: Dict) -> Dict:
        """
        Mai Ruay technique (ไม้รวย - Father + Mother)

        Applies to: uptrend, downtrend, unclear (with valid father candle)

        Strategy Reference: Part 3.2
        """
        father = world_state.get('father_candle', {})
        if not father or not father.get('found') or not father.get('is_valid'):
            return self._skip('No valid father candle')

        mother = father.get('mother_candle', {})
        if not mother or not mother.get('valid'):
            return self._skip('Mother candle invalid')

        # Skip if mother is too big
        if mother.get('body_ratio', 0) > 0.30:
            return self._skip(f"Mother too big ({mother['body_ratio']*100:.0f}%)")

        # Direction: inverse of father
        if father['direction'] == 'down':
            action = 'BUY'
        elif father['direction'] == 'up':
            action = 'SELL'
        else:
            return self._skip('Unknown father direction')

        # Chart direction guard — don't play against strong trend
        chart_type = world_state['chart_type']
        if chart_type == 'uptrend' and action == 'SELL':
            return self._skip('Mai ruay SELL against uptrend')
        if chart_type == 'downtrend' and action == 'BUY':
            return self._skip('Mai ruay BUY against downtrend')

        # Entry = mother's technical_price
        entry = mother.get('technical_price', 0)
        if entry == 0:
            return self._skip('Mother technical_price = 0')

        range_usd = world_state['range']['usd']

        # SL: beyond father+mother combined wick + 5% Range
        sl = self._calc_mai_ruay_sl(world_state, father, entry, action, range_usd)

        # TP: 1/3, 1/2, or near father start
        tp = self._calc_mai_ruay_tp(world_state, father, entry, sl, action, range_usd)

        if tp is None:
            return self._skip('Mai ruay: no TP satisfies R:R >= 1.0')

        rr = self._calc_rr(action, entry, sl, tp)

        return self._build_decision(
            chart_type=chart_type,
            technique='mai_ruay',
            action=action,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=f"Mai ruay {action} @ {entry:.2f} (father {father['direction']}), R:R={rr:.2f}"
        )

    def _decide_breakout_follow(self, world_state: Dict) -> Dict:
        """
        Breakout Follow technique (กรอบตามเจ้า)

        Applies to: uptrend, downtrend, mountain

        Strategy Reference: Part 3.1
        """
        box = world_state.get('chart_detail', {}).get('breakout_box', {})
        if not box.get('found'):
            return self._skip('No breakout box')

        # Check box size
        if box.get('box_pct', 1.0) > 0.35:
            return self._skip(f"Box too big ({box['box_pct']*100:.0f}% > 35%)")

        breakout_dir = box.get('breakout_direction')
        if not breakout_dir:
            return self._skip('Price still inside box (no breakout)')

        chart_type = world_state['chart_type']

        # Direction check
        if chart_type == 'uptrend' and breakout_dir == 'up':
            action = 'BUY'
        elif chart_type == 'downtrend' and breakout_dir == 'down':
            action = 'SELL'
        elif chart_type == 'mountain' and breakout_dir == 'up':
            action = 'BUY'
        else:
            return self._skip(f'Breakout {breakout_dir} against {chart_type}')

        box_size = box['box_high'] - box['box_low']
        entry = world_state.get('current_price', 0)
        range_usd = world_state['range']['usd']

        # SL = 50% of box inside
        sl_distance = box_size * BREAKOUT_SL_PCT
        if action == 'BUY':
            sl = entry - sl_distance
        else:
            sl = entry + sl_distance

        # TP = box_size (1:1 measured move), adjust for obstacles
        tp_distance = box_size
        if action == 'BUY':
            tp = entry + tp_distance
        else:
            tp = entry - tp_distance

        # Adjust for obstacles
        tp_adjusted = self._calc_tp_with_obstacle(entry, sl, action, world_state, range_usd)
        # Use closer TP (safer)
        if action == 'BUY':
            tp = min(tp, tp_adjusted)
        else:
            tp = max(tp, tp_adjusted)

        rr = self._calc_rr(action, entry, sl, tp)
        if rr < 1.0:
            return self._skip(f'Breakout R:R {rr:.2f} < 1.0')

        return self._build_decision(
            chart_type=chart_type,
            technique='breakout_follow',
            action=action,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=f"Breakout {breakout_dir} @ {entry:.2f}, box={box_size:.2f}, R:R={rr:.2f}"
        )

    def _decide_mountain(self, world_state: Dict) -> Dict:
        """
        Mountain technique (ภูเขา - special twin candle case)

        Applies only to: mountain

        Strategy Reference: Part 1.6
        """
        detail = world_state.get('chart_detail', {})

        if not detail.get('tolerance_ok'):
            return self._skip('Mountain: price not at right base yet')

        action = 'BUY'  # Mountain = BUY ONLY

        left_base = detail.get('left_base_price', 0)
        peak = detail.get('peak_price', 0)

        if left_base == 0 or peak == 0:
            return self._skip('Mountain: missing base or peak price')

        range_usd = world_state['range']['usd']

        # Entry = left_base (or twin candle base if found for precision)
        twin_base = detail.get('twin_candle_base', {})
        if twin_base.get('found'):
            entry = twin_base.get('technical_price', left_base)
        else:
            entry = left_base

        # SL = 7.5% Range below left base
        sl = left_base - (range_usd * MOUNTAIN_SL_PCT)
        # Check for long wicks
        sl = self._adjust_sl_for_wick(sl, world_state, direction='below', range_usd=range_usd)

        # TP: 1/3, 1/2, or near peak (choose based on R:R and obstacles)
        height = peak - left_base
        tp1 = entry + (height * 0.33)
        tp2 = entry + (height * 0.50)
        tp3 = peak - (range_usd * 0.02)  # 2% before peak

        tp = self._pick_best_tp([tp1, tp2, tp3], entry, sl, action, world_state, range_usd)

        if tp is None:
            return self._skip('Mountain: TP not achievable (R:R < 1.0)')

        rr = self._calc_rr(action, entry, sl, tp)

        return self._build_decision(
            chart_type='mountain',
            technique='twin_candle',  # Mountain uses twin at base
            action=action,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=f"Mountain @ base {entry:.2f}, peak {peak:.2f}, R:R={rr:.2f}"
        )

    # ========================================================================
    # HELPER FUNCTIONS - SL CALCULATION
    # ========================================================================

    def _calc_sl_twin_candle(self, entry: float, action: str, range_usd: float,
                             world_state: Dict) -> float:
        """Calculate SL for twin candle (15% Range, adjust for wicks)."""
        sl_distance = range_usd * SL_DEFAULT_PCT

        if action == 'BUY':
            sl = entry - sl_distance
            sl = self._adjust_sl_for_wick(sl, world_state, direction='below', range_usd=range_usd)
        else:  # SELL
            sl = entry + sl_distance
            sl = self._adjust_sl_for_wick(sl, world_state, direction='above', range_usd=range_usd)

        return round(sl, 2)

    def _adjust_sl_for_wick(self, sl: float, world_state: Dict,
                           direction: str, range_usd: float) -> float:
        """
        Adjust SL if wicks extend beyond it.

        Args:
            sl: Current SL
            direction: 'below' (for BUY) or 'above' (for SELL)
            range_usd: Range for buffer calculation

        Returns:
            Adjusted SL
        """
        ohlc = world_state.get('ohlc_last_10', [])
        if not ohlc or len(ohlc) < 3:
            return sl

        # Check last 3 candles
        recent_candles = ohlc[-3:]

        if direction == 'below':
            # BUY: check if any low wick extends below SL
            lowest_wick = min(c['low'] for c in recent_candles)
            if lowest_wick < sl:
                # Move SL below the wick + 5% Range buffer
                sl = lowest_wick - (range_usd * SL_WICK_BUFFER_PCT)
                logger.info(f"SL adjusted for wick below: {sl:.2f}")
        else:  # above
            # SELL: check if any high wick extends above SL
            highest_wick = max(c['high'] for c in recent_candles)
            if highest_wick > sl:
                # Move SL above the wick + 5% Range buffer
                sl = highest_wick + (range_usd * SL_WICK_BUFFER_PCT)
                logger.info(f"SL adjusted for wick above: {sl:.2f}")

        return round(sl, 2)

    def _calc_mai_ruay_sl(self, world_state: Dict, father: Dict, entry: float,
                         action: str, range_usd: float) -> float:
        """
        Calculate SL for mai_ruay (beyond father+mother wicks + 5% Range).

        Strategy: SL beyond combined father+mother wick, or SL2 if wick too long.
        """
        ohlc = world_state.get('ohlc_last_10', [])
        if not ohlc:
            # Fallback: 20% Range from entry
            if action == 'BUY':
                return round(entry - (range_usd * 0.20), 2)
            else:
                return round(entry + (range_usd * 0.20), 2)

        # Find father candles (last N candles based on candle_count)
        candle_count = father.get('candle_count', 3)
        # Father + mother = candle_count + 1
        relevant_candles = ohlc[-(candle_count + 1):]

        if action == 'BUY':
            # Father down → find lowest low
            lowest = min(c['low'] for c in relevant_candles)
            sl = lowest - (range_usd * MAI_RUAY_SL_BUFFER)

            # Check SL2: if wick too long (>35% Range), use midpoint
            wick_length = entry - lowest
            if wick_length > range_usd * 0.35:
                # SL2: halfway in the wick
                sl = entry - (wick_length * 0.5)
                logger.info(f"Mai ruay: using SL2 (wick too long {wick_length:.2f})")
        else:  # SELL
            # Father up → find highest high
            highest = max(c['high'] for c in relevant_candles)
            sl = highest + (range_usd * MAI_RUAY_SL_BUFFER)

            wick_length = highest - entry
            if wick_length > range_usd * 0.35:
                sl = entry + (wick_length * 0.5)
                logger.info(f"Mai ruay: using SL2 (wick too long {wick_length:.2f})")

        return round(sl, 2)

    # ========================================================================
    # HELPER FUNCTIONS - TP CALCULATION
    # ========================================================================

    def _calc_tp_with_obstacle(self, entry: float, sl: float, action: str,
                               world_state: Dict, range_usd: float) -> float:
        """
        Calculate TP considering obstacles.

        Default: 50% Range from entry
        Adjust: if obstacle found, set TP before it
        """
        # Default TP: 50% of Range
        default_tp_distance = range_usd * TP_DEFAULT_PCT

        if action == 'BUY':
            default_tp = entry + default_tp_distance
            # Find obstacles ABOVE entry
            obstacle = self._find_obstacle(direction='above', entry=entry, world_state=world_state)
            if obstacle:
                # TP = obstacle - 100 pip buffer
                obstacle_based_tp = obstacle - TP_OBSTACLE_BUFFER
                tp = min(default_tp, obstacle_based_tp)
            else:
                tp = default_tp
        else:  # SELL
            default_tp = entry - default_tp_distance
            # Find obstacles BELOW entry
            obstacle = self._find_obstacle(direction='below', entry=entry, world_state=world_state)
            if obstacle:
                # TP = obstacle + 100 pip buffer
                obstacle_based_tp = obstacle + TP_OBSTACLE_BUFFER
                tp = max(default_tp, obstacle_based_tp)
            else:
                tp = default_tp

        return round(tp, 2)

    def _calc_mai_ruay_tp(self, world_state: Dict, father: Dict, entry: float,
                         sl: float, action: str, range_usd: float) -> Optional[float]:
        """
        Calculate TP for mai_ruay (1/3, 1/2, or near father start).

        Pick shortest TP that passes R:R >= 1.0 and no obstacle.
        """
        # Find father start/end prices
        ohlc = world_state.get('ohlc_last_10', [])
        candle_count = father.get('candle_count', 3)
        if len(ohlc) < candle_count + 1:
            # Fallback: use default TP
            return self._calc_tp_with_obstacle(entry, sl, action, world_state, range_usd)

        relevant_candles = ohlc[-(candle_count + 1):-1]  # Exclude mother (last candle)

        if action == 'BUY':
            # Father down: start=high, end=low
            father_start = max(c['high'] for c in relevant_candles)
            father_end = min(c['low'] for c in relevant_candles)
            father_size = father_start - father_end

            # TP candidates
            tp1 = entry + (father_size * 0.33)
            tp2 = entry + (father_size * 0.50)
            tp3 = father_start - (range_usd * 0.02)
        else:  # SELL
            # Father up: start=low, end=high
            father_start = min(c['low'] for c in relevant_candles)
            father_end = max(c['high'] for c in relevant_candles)
            father_size = father_end - father_start

            tp1 = entry - (father_size * 0.33)
            tp2 = entry - (father_size * 0.50)
            tp3 = father_start + (range_usd * 0.02)

        # Pick best TP
        return self._pick_best_tp([tp1, tp2, tp3], entry, sl, action, world_state, range_usd)

    def _pick_best_tp(self, tp_candidates: List[float], entry: float, sl: float,
                     action: str, world_state: Dict, range_usd: float) -> Optional[float]:
        """
        Pick TP that:
        1. Has R:R >= 1.0
        2. Is NOT past an obstacle
        3. Prefers shorter TP (higher winrate)
        """
        valid_tps = []

        for tp in tp_candidates:
            # Check R:R
            rr = self._calc_rr(action, entry, sl, tp)
            if rr < 1.0:
                continue

            # Check obstacle
            if action == 'BUY':
                obstacle = self._find_obstacle('above', entry, world_state)
                if obstacle and tp > obstacle - TP_OBSTACLE_BUFFER:
                    continue
            else:  # SELL
                obstacle = self._find_obstacle('below', entry, world_state)
                if obstacle and tp < obstacle + TP_OBSTACLE_BUFFER:
                    continue

            valid_tps.append(tp)

        if not valid_tps:
            return None

        # Pick shortest valid TP (highest winrate)
        if action == 'BUY':
            return round(min(valid_tps), 2)
        else:
            return round(max(valid_tps), 2)

    def _extend_tp_to_rr_1(self, action: str, entry: float, sl: float,
                          world_state: Dict, range_usd: float) -> float:
        """
        Extend TP to achieve R:R = 1.0 (as last resort).

        Max extension: up to box edge or range limit.
        """
        risk = abs(entry - sl)
        # TP for R:R = 1.0
        if action == 'BUY':
            tp = entry + risk
            # Cap at high of range
            range_high = world_state['range']['high']
            tp = min(tp, range_high - (range_usd * 0.02))
        else:  # SELL
            tp = entry - risk
            # Cap at low of range
            range_low = world_state['range']['low']
            tp = max(tp, range_low + (range_usd * 0.02))

        return round(tp, 2)

    def _find_obstacle(self, direction: str, entry: float, world_state: Dict) -> Optional[float]:
        """
        Find nearest obstacle in given direction.

        Args:
            direction: 'above' or 'below'
            entry: Entry price
            world_state: Contains swing_points

        Returns:
            Nearest obstacle price or None
        """
        swings = world_state.get('swing_points', {'highs': [], 'lows': []})

        if direction == 'above':
            # Obstacles ABOVE entry
            candidates = [p for _, p in swings.get('highs', []) if p > entry]
            return min(candidates) if candidates else None
        else:  # below
            # Obstacles BELOW entry
            candidates = [p for _, p in swings.get('lows', []) if p < entry]
            return max(candidates) if candidates else None

    # ========================================================================
    # HELPER FUNCTIONS - DIRECTION & UTILITIES
    # ========================================================================

    def _sideway_direction(self, world_state: Dict, chart_type: str) -> str:
        """
        Determine action for sideway charts based on current position.

        Returns: 'BUY', 'SELL', or 'SKIP'
        """
        detail = world_state.get('chart_detail', {})
        position = detail.get('current_position', 'middle')

        if position == 'middle':
            return 'SKIP'

        # sideway_up: BUY at bottom, SELL at top
        # sideway_down: same logic
        if position == 'near_bottom':
            return 'BUY'
        elif position == 'near_top':
            return 'SELL'
        else:
            return 'SKIP'

    def _calc_rr(self, action: str, entry: float, sl: float, tp: float) -> float:
        """Calculate Risk:Reward ratio."""
        if action == 'BUY':
            risk = entry - sl
            reward = tp - entry
        else:  # SELL
            risk = sl - entry
            reward = entry - tp

        if risk <= 0:
            return 0.0
        return round(reward / risk, 2)

    # ========================================================================
    # HELPER FUNCTIONS - OUTPUT BUILDERS
    # ========================================================================

    def _build_decision(self, chart_type: str, technique: str, action: str,
                       entry: float, sl: float, tp: float, reason: str) -> Dict:
        """Build standardized decision dict."""
        entry = round(entry, 2)
        sl = round(sl, 2)
        tp = round(tp, 2)

        rr = self._calc_rr(action, entry, sl, tp)
        sl_pip = int(abs(entry - sl) * 100)
        tp_pip = int(abs(tp - entry) * 100)

        return {
            'chart_type': chart_type,
            'technique': technique,
            'action': action,
            'confidence': 0.8,  # Default confidence (G1 already filtered quality)
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'rr_ratio': rr,
            'sl_pip': sl_pip,
            'tp_pip': tp_pip,
            'reason': reason[:80]  # Truncate to 80 chars
        }

    def _skip(self, reason: str) -> Dict:
        """Build SKIP decision."""
        return {
            'action': 'SKIP',
            'skip_reason': reason[:60]  # Truncate to 60 chars
        }

    def _build_llm_log(self, decision: Dict, latency: float) -> Dict:
        """Build LLM log for session stats (zeros for token/cost)."""
        return {
            'timestamp': datetime.now().isoformat(),
            'model': 'python_rules',
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_creation_tokens': 0,
            'cache_read_tokens': 0,
            'total_tokens': 0,
            'cache_hit': False,
            'cost_usd': 0.0,
            'latency_sec': latency,
            'action': decision.get('action'),
            'confidence': decision.get('confidence', 0.8),
            'reason': (decision.get('reason') or decision.get('skip_reason', ''))[:100],
            'engine': 'python'
        }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("G3 PYTHON DECISION ENGINE TEST")
    print("="*70)

    # Mock world_state
    world_state = {
        'selected_tf': 'H1',
        'chart_type': 'uptrend',
        'technique_candidate': 'twin_candle',
        'quality': 0.75,
        'range': {'high': 4750, 'low': 4600, 'usd': 150, 'pip': 15000},
        'current_price': 4715,
        'twin_candle': {
            'found': True,
            'technical_price': 4700.50,
            'body_pct': 0.08
        },
        'father_candle': {'found': False},
        'chart_detail': {
            'slope_angle': 46.5,
            'hh_hl': {'hh_count': 4, 'hl_count': 4, 'consecutive': True}
        },
        'swing_points': {
            'highs': [(10, 4720), (25, 4735), (45, 4748)],
            'lows': [(5, 4605), (20, 4650), (40, 4695)]
        },
        'ohlc_last_10': [
            {'open': 4700, 'high': 4705, 'low': 4698, 'close': 4703},
            {'open': 4703, 'high': 4708, 'low': 4700, 'close': 4706},
            {'open': 4706, 'high': 4712, 'low': 4704, 'close': 4710},
        ]
    }

    portfolio_state = {
        'active_plan_id': '',
        'consecutive_loss': 0,
        'total_loss_pct': 0.0
    }

    engine = G3PythonDecision(config={'verbose': True})
    result = engine.decide(world_state, balance=300, portfolio_state=portfolio_state)

    print(f"\n📊 Result:")
    print(f"   Action: {result['decision'].get('action')}")
    if result['decision'].get('action') != 'SKIP':
        print(f"   Entry: {result['decision'].get('entry')}")
        print(f"   SL: {result['decision'].get('sl')}")
        print(f"   TP: {result['decision'].get('tp')}")
        print(f"   R:R: {result['decision'].get('rr_ratio')}")
    else:
        print(f"   Reason: {result['decision'].get('skip_reason')}")

    print(f"\n💰 Cost: ${result['llm_log']['cost_usd']}")
    print(f"⚡ Latency: {result['llm_log']['latency_sec']*1000:.1f}ms")
    print(f"🔧 Engine: {result['llm_log']['engine']}")

    print("\n" + "="*70)
