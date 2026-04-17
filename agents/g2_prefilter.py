"""
G2 — Pre-filter Agent (v2.1)

หน้าที่:
- ตรวจ active plan, loss limits, news flag
- สร้าง chart_context สำหรับ G3

Reference: TRAIDER_MASTER_PLAN_v2.1.md Section 5
"""

import logging
from typing import Dict

from config import RISK_CONFIG

# Setup logging
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_reference_price(world_state: dict) -> float:
    """
    Get reference price for duplicate prevention (works for all techniques)

    Returns:
        float: Reference price for comparison
            - twin_candle → technical_price
            - breakout_follow → current_price
            - mai_ruay → mother_candle technical_price
            - others → current_price
    """
    technique = world_state.get('technique_candidate', '')

    if technique == 'twin_candle':
        return world_state.get('twin_candle', {}).get('technical_price', 0)
    elif technique == 'breakout_follow':
        # ใช้ current_price เพราะ breakout ไม่มี technical_price
        return world_state.get('current_price', 0)
    elif technique == 'mai_ruay':
        # ใช้ mother_candle technical_price
        father = world_state.get('father_candle', {})
        mother = father.get('mother_candle', {})
        return mother.get('technical_price', 0)
    else:
        # Fallback: ใช้ current_price
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
    if quality < 0.65:
        logger.info(f"SKIP: Quality too low ({quality:.2f} < 0.65)")
        return {
            'pre_approved': False,
            'skip_reason': f'Quality {quality:.2f} ต่ำเกิน (ต้อง ≥ 0.65)',
            'chart_context': {}
        }

    # Check 2: มี active plan อยู่
    active_plan = portfolio_state.get('active_plan_id')
    if active_plan and active_plan != 'ไม่มีแผนที่เปิดอยู่':
        logger.info(f"SKIP: Active plan exists ({active_plan})")
        return {
            'pre_approved': False,
            'skip_reason': f'มีแผนที่เปิดอยู่: {active_plan}',
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

    # Check 5: Setup Pre-check (ประหยัด Claude calls)
    chart_type = world_state.get('chart_type')
    technique_candidate = world_state.get('technique_candidate', 'skip')

    # ถ้า technique_candidate = 'skip' → ไม่มี setup
    if technique_candidate == 'skip':
        logger.info("SKIP: No technique candidate (G1 found no setup)")
        return {
            'pre_approved': False,
            'skip_reason': 'ไม่มี Setup ที่ใช้ได้',
            'chart_context': {}
        }

    # Check setup สำหรับ uptrend/downtrend
    if chart_type in ['uptrend', 'downtrend']:
        twin_candle = world_state.get('twin_candle', {})
        father_candle = world_state.get('father_candle', {})

        has_twin = twin_candle.get('found', False)
        has_father = father_candle.get('found', False)

        # ต้องมีอย่างน้อย 1 setup
        if not has_twin and not has_father:
            logger.info(f"SKIP: {chart_type} but no twin_candle and no father_candle")
            return {
                'pre_approved': False,
                'skip_reason': f'{chart_type} แต่ไม่มีแท่งคู่และไม่มีกรอบตามเจ้า',
                'chart_context': {}
            }

    # Check setup สำหรับ mountain
    elif chart_type == 'mountain':
        chart_detail = world_state.get('chart_detail', {})
        tolerance_ok = chart_detail.get('tolerance_ok', False)

        # ราคาต้องถึงฐานด้านขวาแล้ว
        if not tolerance_ok:
            logger.info("SKIP: Mountain but price not at right base (tolerance_ok=False)")
            return {
                'pre_approved': False,
                'skip_reason': 'ภูเขายังไม่จบ ราคายังไม่ลงถึงฐานด้านขวา',
                'chart_context': {}
            }

    # Check 6: Duplicate Prevention (ALL techniques, not just twin_candle)
    # ป้องกันการเปิด plan ซ้ำเมื่อ setup ยังไม่เปลี่ยน
    current_tech_price = get_reference_price(world_state)
    last_tech_price = float(portfolio_state.get('last_technical_price', 0))
    current_chart = world_state.get('chart_type', '')
    last_chart = portfolio_state.get('last_plan_chart_type', '')

    logger.info(f"Duplicate check: technique={technique_candidate}, current_tech={current_tech_price:.2f}, "
                f"last_tech={last_tech_price:.2f}, current_chart={current_chart}, last_chart={last_chart}")

    # Threshold: 0.30 USD (30 pip)
    DUPLICATE_THRESHOLD = 0.30

    # Block เมื่อ: ราคาใกล้กัน AND chart type เดิม
    if (current_tech_price > 0
        and last_tech_price > 0
        and current_chart == last_chart
        and abs(current_tech_price - last_tech_price) < DUPLICATE_THRESHOLD):

        price_diff = abs(current_tech_price - last_tech_price)
        logger.info(f"SKIP: Setup เดิม ({technique_candidate}, tech={current_tech_price:.2f} ≈ last {last_tech_price:.2f}, diff={price_diff:.2f})")
        return {
            'pre_approved': False,
            'skip_reason': f'Setup เดิม {current_tech_price:.2f} ยังไม่เปลี่ยน (ห่าง {price_diff:.2f} < {DUPLICATE_THRESHOLD}, chart เดิม)',
            'chart_context': {}
        }
    else:
        # Log why it passed
        if current_tech_price == 0:
            logger.debug("No reference price → allow")
        elif last_tech_price == 0:
            logger.info("First plan (last_tech=0) → allow")
        elif current_chart != last_chart:
            logger.info(f"Chart type changed ({last_chart} → {current_chart}) → allow")
        elif abs(current_tech_price - last_tech_price) >= DUPLICATE_THRESHOLD:
            price_diff = abs(current_tech_price - last_tech_price)
            logger.info(f"Price moved enough (diff={price_diff:.2f} >= {DUPLICATE_THRESHOLD}) → allow")

    # Check 7: Touch Validation (ตาม Strategy v2.1)
    # "รอให้ราคาวกกลับมาแตะจุดเทคนิค ±100-300 pip"
    if technique_candidate in ['twin_candle', 'mai_ruay']:
        current_price = world_state.get('current_price', 0)

        if current_tech_price > 0 and current_price > 0:
            price_diff = abs(current_price - current_tech_price)

            # Touch range: 1.0-3.0 USD (100-300 pip)
            TOUCH_MIN = 1.0   # 100 pip - ราคาใกล้จุดเทคนิคเกินไป (ยังไม่ย่อมา)
            TOUCH_MAX = 3.0   # 300 pip - ราคาห่างจากจุดเทคนิคเกินไป (ยังไม่แตะ)

            if price_diff < TOUCH_MIN:
                # ราคายังอยู่ที่จุดเทคนิค (ยังไม่ออกไป) หรือใกล้เกินไป
                logger.info(f"SKIP: ราคาใกล้จุดเทคนิคเกินไป (current={current_price:.2f}, tech={current_tech_price:.2f}, diff={price_diff:.2f} < {TOUCH_MIN})")
                return {
                    'pre_approved': False,
                    'skip_reason': f'ราคายังไม่ออกจากจุดเทคนิค (ห่างแค่ {price_diff:.2f} < {TOUCH_MIN})',
                    'chart_context': {}
                }
            elif price_diff > TOUCH_MAX:
                # ราคาห่างจากจุดเทคนิคเกินไป (ยังไม่ย่อกลับมา)
                logger.info(f"SKIP: ราคาห่างจากจุดเทคนิคเกินไป (current={current_price:.2f}, tech={current_tech_price:.2f}, diff={price_diff:.2f} > {TOUCH_MAX})")
                return {
                    'pre_approved': False,
                    'skip_reason': f'ราคาปัจจุบัน {current_price:.2f} ห่างจากจุดเทคนิค {current_tech_price:.2f} มาก ({price_diff:.2f} > {TOUCH_MAX})',
                    'chart_context': {}
                }
            else:
                # ราคาอยู่ในช่วง 100-300 pip จากจุดเทคนิค (ถูกต้อง)
                logger.info(f"✅ Touch OK: current={current_price:.2f}, tech={current_tech_price:.2f}, diff={price_diff:.2f} (in range {TOUCH_MIN}-{TOUCH_MAX})")

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
