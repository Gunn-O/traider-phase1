"""
G2 — Pre-filter Agent (v2.1.1 — Signal Engine Compatible)

หน้าที่:
- ตรวจ active plan, loss limits, news flag
- สร้าง chart_context สำหรับ G3 (Reviewer mode)

Changes (v2.1.1):
- Works with Signal Engine output (signal object)
- Simplified setup checks (Signal Engine handles internal validation)
- Updated duplicate prevention to use signal.entry

Reference: TRAIDER_MASTER_PLAN_v2.1.md Section 5
"""

import logging
from typing import Dict

from config import RISK_CONFIG
from utils.strategy_loader import is_pattern_active

# Setup logging
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_reference_price(world_state: dict) -> float:
    """
    Get reference price for duplicate prevention

    With Signal Engine:
        - Use signal.entry as reference price

    Fallback (backward compatible with G1):
        - twin_candle → technical_price
        - breakout_follow → current_price
        - mai_ruay → mother_candle technical_price
        - others → current_price
    """
    # Priority: Use signal.entry if available
    signal = world_state.get('signal')
    if signal and hasattr(signal, 'entry'):
        return signal.entry

    # Fallback: Old logic for backward compatibility
    technique = world_state.get('technique_candidate', '')

    if technique == 'twin_candle':
        return world_state.get('twin_candle', {}).get('technical_price', 0)
    elif technique == 'breakout_follow':
        return world_state.get('current_price', 0)
    elif technique == 'mai_ruay':
        father = world_state.get('father_candle', {})
        mother = father.get('mother_candle', {})
        return mother.get('technical_price', 0)
    else:
        return world_state.get('current_price', 0)


# ============================================================================
# PRE-FILTER CHECKS
# ============================================================================

def prefilter_check(world_state: Dict, portfolio_state: Dict) -> Dict:
    """
    ตรวจสอบเบื้องต้นก่อนส่งให้ G3

    Args:
        world_state: output จาก G1
        portfolio_state: Portfolio state dict

    Returns:
        {
            'pre_approved': bool,
            'skip_reason': str,
            'chart_context': dict
        }
    """
    # Check 1: Chart type unclear
    if world_state.get('chart_type') == 'unclear':
        logger.info("SKIP: Chart type unclear")
        return {
            'pre_approved': False,
            'skip_reason': 'กราฟไม่ชัด (unclear)',
            'chart_context': {}
        }

    # Check 1b: Quality threshold (ประหยัด Claude calls)
    quality = world_state.get('quality', 0)
    if quality < 0.50:  # Strategy v2.1: chart_quality < 0.5 → SKIP
        logger.info(f"SKIP: Quality too low ({quality:.2f} < 0.50)")
        return {
            'pre_approved': False,
            'skip_reason': f'Quality {quality:.2f} ต่ำเกิน (ต้อง ≥ 0.50)',
            'chart_context': {}
        }

    # Check 2: มี active plan ของ pattern เดียวกันอยู่
    # Per-pattern slot — Mountain + MAI_RUAY trade ขนานกันได้ ไม่บล็อกกัน
    signal_pattern = world_state.get('signal').pattern if world_state.get('signal') else ''
    active_plans = portfolio_state.get('active_plans_by_pattern', {}) or {}
    pattern_plan = active_plans.get(signal_pattern, '')
    if pattern_plan and pattern_plan != 'ไม่มีแผนที่เปิดอยู่':
        logger.info(f"SKIP: {signal_pattern} active plan exists ({pattern_plan})")
        return {
            'pre_approved': False,
            'skip_reason': f'{signal_pattern} มีแผนที่เปิดอยู่: {pattern_plan}',
            'chart_context': {}
        }

    # Check 2b: MaiRuay v2 — ยัง "1 plan ต่อครั้ง" รวม pending limits
    # Notebook run_backtest:929 `if open_positions or pending_limits or _just_closed: continue`
    # — pending limits ที่ค้างใน broker ถือว่า plan ยังไม่จบ. Block new signal
    # ของ pattern เดียวกันจนกว่า limits จะ fill หมด/cancel.
    pending_by_pat = portfolio_state.get('pending_limits_by_pattern', {}) or {}
    if pending_by_pat.get(signal_pattern, 0) > 0:
        _cnt = pending_by_pat[signal_pattern]
        logger.info(f"SKIP: {signal_pattern} has {_cnt} pending LIMIT(s) — wait to fill/cancel first")
        return {
            'pre_approved': False,
            'skip_reason': f'{signal_pattern} มี LIMIT ค้าง {_cnt} ไม้ (ยังไม่เปิดได้)',
            'chart_context': {}
        }

    # Check 3: News flag
    news_flag = portfolio_state.get('news_flag', False)
    if news_flag:
        logger.info("SKIP: News event active")
        return {
            'pre_approved': False,
            'skip_reason': 'มีข่าวเศรษฐกิจ high impact',
            'chart_context': {}
        }

    # Check 4: Loss limits (50% permanent block)
    total_loss_pct = portfolio_state.get('total_loss_pct', 0)
    if total_loss_pct > RISK_CONFIG['max_loss_50pct']:
        logger.error("SKIP: Permanent block (loss > 50%)")
        return {
            'pre_approved': False,
            'skip_reason': f'ขาดทุนรวม > 50% — BLOCK ถาวร',
            'chart_context': {}
        }

    # Check 5: Signal validation (Signal Engine only returns when there's a valid setup)
    signal = world_state.get('signal')
    chart_type = world_state.get('chart_type')
    technique_candidate = world_state.get('technique_candidate', 'skip')

    if signal is None:
        # Signal Engine found pattern but no valid entry point
        logger.info(f"SKIP: No signal (Signal Engine found {chart_type} but no entry setup)")
        return {
            'pre_approved': False,
            'skip_reason': f'ไม่มี Setup ที่ใช้ได้ ({chart_type})',
            'chart_context': {}
        }

    # Validate signal has required fields
    if not hasattr(signal, 'entry') or not hasattr(signal, 'sl') or not hasattr(signal, 'tp_order'):
        logger.error(f"SKIP: Invalid signal object (missing entry/sl/tp)")
        return {
            'pre_approved': False,
            'skip_reason': 'Signal ไม่ครบถ้วน',
            'chart_context': {}
        }

    # Validate R:R ratio — config-driven (default 0.0 for Cent account data collection)
    min_rr = RISK_CONFIG.get('min_rr_ratio', 0.0)
    if min_rr > 0 and signal.rr < min_rr:
        logger.info(f"SKIP: R:R too low ({signal.rr:.2f} < {min_rr})")
        return {
            'pre_approved': False,
            'skip_reason': f'R:R ต่ำเกิน ({signal.rr:.2f} < {min_rr})',
            'chart_context': {}
        }

    # Check 5b: V65 Strategy active check
    pattern_name = signal.pattern
    if not is_pattern_active(pattern_name):
        logger.info(f"SKIP: Pattern '{pattern_name}' is not active in strategy config")
        return {
            'pre_approved': False,
            'skip_reason': f'Pattern {pattern_name} ปิดการใช้งาน (ดูที่ Strategy Manager)',
            'chart_context': {}
        }

    # Check 6: Duplicate Prevention
    # ป้องกันการเปิด plan ซ้ำเมื่อ setup ยังไม่เปลี่ยน (ใช้ signal.entry เป็น reference)
    #
    # MaiRuay v2 R2 bypass: ไม้รวยรอบ 2 (is_round2=True) ออกแบบให้เข้าใกล้ R1
    # ที่เพิ่ง SL — entry อาจห่างจาก R1 น้อยกว่า threshold 50 pip. ถ้าเช็ค
    # duplicate ตามปกติ R2 จะถูก block ผิด เพราะ R1 ยังค้างอยู่ใน last_technical_price.
    # Notebook spec อนุญาต R2 เข้าทันที — bypass check ตรงนี้.
    current_entry = signal.entry  # Use signal.entry from Signal Engine
    last_tech_price = float(portfolio_state.get('last_technical_price', 0))
    current_chart = world_state.get('chart_type', '')
    last_chart = portfolio_state.get('last_plan_chart_type', '')
    is_round2 = bool(getattr(signal, 'is_round2', False))

    logger.info(f"Duplicate check: pattern={signal.pattern}, current_entry={current_entry:.2f}, "
                f"last_tech={last_tech_price:.2f}, current_chart={current_chart}, last_chart={last_chart}, "
                f"is_round2={is_round2}")

    # Threshold: config-driven (default 50 pip = 0.50 USD)
    DUPLICATE_THRESHOLD = RISK_CONFIG.get('duplicate_pip_threshold', 50) / 100.0  # pip → USD

    # Block เมื่อ: ราคาใกล้กัน AND chart type เดิม AND ไม่ใช่ R2
    if (not is_round2
        and current_entry > 0
        and last_tech_price > 0
        and current_chart == last_chart
        and abs(current_entry - last_tech_price) < DUPLICATE_THRESHOLD):

        price_diff = abs(current_entry - last_tech_price)
        logger.info(f"SKIP: Setup เดิม ({signal.pattern}, entry={current_entry:.2f} ≈ last {last_tech_price:.2f}, diff={price_diff:.2f})")
        return {
            'pre_approved': False,
            'skip_reason': f'Setup เดิม entry={current_entry:.2f} ยังไม่เปลี่ยน (ห่าง {price_diff:.2f} < {DUPLICATE_THRESHOLD})',
            'chart_context': {}
        }
    if is_round2:
        logger.info(f"R2 bypass: duplicate check skipped (MaiRuay v2 ไม้แก้หลัง SL)")

    # Log why duplicate-prevention passed
    if current_entry == 0:
        logger.debug("No entry price → allow")
    elif last_tech_price == 0:
        logger.info("First plan (last_tech=0) → allow")
    elif current_chart != last_chart:
        logger.info(f"Chart type changed ({last_chart} → {current_chart}) → allow")
    elif abs(current_entry - last_tech_price) >= DUPLICATE_THRESHOLD:
        price_diff = abs(current_entry - last_tech_price)
        logger.info(f"Entry moved enough (diff={price_diff:.2f} >= {DUPLICATE_THRESHOLD}) → allow duplicate check")

    # Check 6b: Cooldown — ห่างจาก signal ก่อนหน้า ≥ N bars (M5: 3 = 15 min, M1: 15)
    # R2 bypass: MaiRuay v2 ไม้แก้หลัง SL ออกแบบให้เข้าทันที (ภายใน 16 bars จาก R1)
    cooldown_bars = RISK_CONFIG.get('cooldown_bars', 0)
    if cooldown_bars > 0 and not is_round2:
        last_signal_bar = portfolio_state.get('last_signal_bar', 0) or 0
        current_bar = portfolio_state.get('current_bar', 0) or 0
        if last_signal_bar > 0 and current_bar > 0:
            bars_diff = current_bar - last_signal_bar
            if 0 < bars_diff < cooldown_bars:
                logger.info(f"SKIP: Cooldown active ({bars_diff} < {cooldown_bars} bars)")
                return {
                    'pre_approved': False,
                    'skip_reason': f'Cooldown: ห่าง signal ก่อน {bars_diff} bars (ต้อง ≥ {cooldown_bars})',
                    'chart_context': {}
                }

    # Check 7: Removed — Signal Engine handles touch validation internally

    # สร้าง chart_context
    chart_context = build_chart_context(world_state)

    logger.info("✅ Pre-filter APPROVED")
    return {
        'pre_approved': True,
        'skip_reason': '',
        'chart_context': chart_context
    }


def build_chart_context(world_state: Dict) -> Dict:
    """
    สร้าง chart_context สรุปข้อมูลสำหรับ G3

    Returns:
        {
            'timeframe': str,
            'chart_type': str,
            'technique': str,
            'quality': float,
            'range_pip': int,
            'current_price': float,
            'session': str
        }
    """
    return {
        'timeframe': world_state.get('selected_tf', world_state.get('timeframe', 'M5')),
        'chart_type': world_state.get('chart_type', 'unclear'),
        'technique': world_state.get('technique_candidate', 'skip'),
        'quality': world_state.get('quality', 0.0),  # Fixed: use 'quality' not 'chart_quality'
        'range_pip': world_state.get('range', {}).get('pip', 0),
        'current_price': world_state.get('current_price', 0),
        'session': world_state.get('session', 'Unknown')
    }


# ============================================================================
# MAIN CLASS
# ============================================================================

class G2Prefilter:
    """
    G2 Pre-filter Agent

    Usage:
        prefilter = G2Prefilter()
        result = prefilter.check(world_state, portfolio_state)
    """

    def __init__(self, config: Dict = None):
        """
        Args:
            config: {'verbose': bool}
        """
        self.config = config or {}
        self.verbose = self.config.get('verbose', False)
        logger.info("G2Prefilter initialized")

    def check(self, world_state: Dict, portfolio_state: Dict) -> Dict:
        """
        ตรวจสอบและสร้าง chart_context

        Returns:
            {
                'pre_approved': bool,
                'skip_reason': str,
                'chart_context': dict
            }
        """
        result = prefilter_check(world_state, portfolio_state)

        if self.verbose:
            if result['pre_approved']:
                logger.info(f"Pre-approved: {result['chart_context']}")
            else:
                logger.info(f"Skipped: {result['skip_reason']}")

        return result


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("G2 PRE-FILTER TEST")
    print("="*70)

    # Mock world_state
    world_state = {
        'selected_tf': 'H1',
        'chart_type': 'uptrend',
        'chart_quality': 0.82,
        'technique_candidate': 'twin_candle',
        'range': {'pip': 6550},
        'current_price': 3241.20,
        'session': 'London'
    }

    # Test scenarios
    scenarios = [
        ("Normal (should pass)", {
            'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
            'consecutive_loss': 0,
            'total_loss_pct': 0.0,
            'news_flag': False
        }),
        ("Unclear chart", {
            'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
            'consecutive_loss': 0,
            'total_loss_pct': 0.0
        }),
        ("Has active plan", {
            'active_plan_id': 'PLAN-20260408-001',
            'consecutive_loss': 0,
            'total_loss_pct': 0.0
        }),
        ("News event", {
            'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
            'news_flag': True,
            'consecutive_loss': 0,
            'total_loss_pct': 0.0
        })
    ]

    prefilter = G2Prefilter(config={'verbose': True})

    for name, portfolio in scenarios:
        print(f"\n📝 Scenario: {name}")

        # Modify world_state for "Unclear chart" scenario
        if name == "Unclear chart":
            test_world = {**world_state, 'chart_type': 'unclear'}
        else:
            test_world = world_state

        result = prefilter.check(test_world, portfolio)
        print(f"   Pre-approved: {result['pre_approved']}")
        if not result['pre_approved']:
            print(f"   Skip reason: {result['skip_reason']}")
        else:
            print(f"   Chart context: {result['chart_context']}")

    print("\n" + "="*70)
