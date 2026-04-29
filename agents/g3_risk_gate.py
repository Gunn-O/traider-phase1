"""
G3c — Guardian Risk Gate (v2.1)

หน้าที่:
- ตรวจสอบ 6 Block Conditions ก่อน approve signal
- ไม่ใช้ Cooldown timer (Position-based rules เท่านั้น)

Reference: TRAIDER_MASTER_PLAN_v2.1.md Section 4
"""

import logging
from typing import Dict

from config import RISK_CONFIG

# Setup logging
logger = logging.getLogger(__name__)


# ============================================================================
# GUARDIAN BLOCK RULES (v2.1)
# ============================================================================

def guardian_check(decision: Dict, lot_info: Dict,
                   portfolio_state: Dict) -> Dict:
    """
    ตรวจสอบ 6 Block Conditions

    Args:
        decision: {
            'action': 'BUY' | 'SELL' | 'SKIP',
            'rr_ratio': float,
            'entry': float,
            'sl': float,
            'tp': float
        }
        lot_info: {
            'lot_total': float,
            'suggested_orders': int
        }
        portfolio_state: {
            'active_plan_id': str,
            'consecutive_loss': int,
            'total_loss_pct': float,
            'trading_blocked': bool,
            'block_reason': str,
            'news_flag': bool (optional)
        }

    Returns:
        {
            'approved': bool,
            'block_reason': str,
            'blocked_by': str (rule name)
        }
    """
    if decision.get('action') == 'SKIP':
        return {'approved': False, 'block_reason': 'Decision is SKIP', 'blocked_by': 'decision'}

    # ============ Rule 1: มี Active Plan อยู่ ============
    active_plan = portfolio_state.get('active_plan_id')
    if active_plan and active_plan != 'ไม่มีแผนที่เปิดอยู่':
        logger.warning(f"BLOCK: Active plan exists ({active_plan})")
        return {
            'approved': False,
            'block_reason': f'มีแผนที่เปิดอยู่: {active_plan}',
            'blocked_by': 'active_plan'
        }

    # ============ Rule 2: Consecutive Loss >= 3 ============
    consecutive_loss = portfolio_state.get('consecutive_loss', 0)
    if consecutive_loss >= RISK_CONFIG['max_consecutive_loss']:
        logger.warning(f"BLOCK: Consecutive loss {consecutive_loss} >= {RISK_CONFIG['max_consecutive_loss']}")
        return {
            'approved': False,
            'block_reason': f'แพ้ติดกัน {consecutive_loss} ครั้ง',
            'blocked_by': 'consecutive_loss'
        }

    # ============ Rule 3: Total Loss > 30% ============
    total_loss_pct = portfolio_state.get('total_loss_pct', 0)
    if total_loss_pct > RISK_CONFIG['max_loss_30pct']:
        logger.warning(f"BLOCK: Total loss {total_loss_pct*100:.1f}% > 30%")
        return {
            'approved': False,
            'block_reason': f'ขาดทุนสะสม {total_loss_pct*100:.1f}% > 30%',
            'blocked_by': 'loss_30pct'
        }

    # ============ Rule 4: Total Loss > 50% (ถาวร) ============
    if total_loss_pct > RISK_CONFIG['max_loss_50pct']:
        logger.error(f"BLOCK PERMANENT: Total loss {total_loss_pct*100:.1f}% > 50%")
        return {
            'approved': False,
            'block_reason': f'ขาดทุนรวม {total_loss_pct*100:.1f}% > 50% — BLOCK ถาวร',
            'blocked_by': 'loss_50pct_permanent'
        }

    # ============ Rule 5: R:R < 1.0 ============
    rr_ratio = decision.get('rr_ratio', 0)
    if rr_ratio > 0 and rr_ratio < 1.0:
        logger.warning(f"BLOCK: R:R {rr_ratio:.2f} < 1.0")
        return {
            'approved': False,
            'block_reason': f'R:R = {rr_ratio:.2f} ต่ำกว่า 1.0',
            'blocked_by': 'rr_ratio'
        }

    # ============ Rule 5.5: Confidence < 0.50 (Soft Block) ============
    confidence = decision.get('confidence', 1.0)
    if 0 < confidence < 0.50:
        logger.warning(f"BLOCK: Confidence {confidence:.0%} < 50%")
        return {
            'approved': False,
            'block_reason': f'Confidence {confidence:.0%} ต่ำกว่า 50%',
            'blocked_by': 'confidence'
        }

    # ============ Rule 6: News Flag = True ============
    news_flag = portfolio_state.get('news_flag', False)
    if news_flag:
        logger.warning("BLOCK: News event active")
        return {
            'approved': False,
            'block_reason': 'มีข่าวเศรษฐกิจ high impact (block ±30 นาที)',
            'blocked_by': 'news_event'
        }

    # ============ Passed All Checks ============
    logger.info("✅ Guardian APPROVED")
    return {
        'approved': True,
        'block_reason': '',
        'blocked_by': ''
    }


def check_if_permanently_blocked(portfolio_state: Dict) -> bool:
    """
    ตรวจสอบว่า block ถาวรหรือไม่ (total loss > 50%)

    Returns:
        True ถ้า block ถาวร
    """
    total_loss_pct = portfolio_state.get('total_loss_pct', 0)
    return total_loss_pct > RISK_CONFIG['max_loss_50pct']


def reset_consecutive_loss(portfolio_state: Dict) -> Dict:
    """
    Reset consecutive loss counter (เรียกเมื่อ WIN)

    Args:
        portfolio_state: Portfolio state dict

    Returns:
        Updated portfolio_state
    """
    portfolio_state['consecutive_loss'] = 0
    logger.info("Consecutive loss counter reset to 0")
    return portfolio_state


def increment_consecutive_loss(portfolio_state: Dict) -> Dict:
    """
    เพิ่ม consecutive loss counter (เรียกเมื่อ LOSS)

    Args:
        portfolio_state: Portfolio state dict

    Returns:
        Updated portfolio_state
    """
    portfolio_state['consecutive_loss'] = portfolio_state.get('consecutive_loss', 0) + 1
    logger.info(f"Consecutive loss incremented to {portfolio_state['consecutive_loss']}")
    return portfolio_state


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("G3c GUARDIAN RISK GATE v2.1 TEST")
    print("="*70)

    # Test decision
    test_decision = {
        'action': 'BUY',
        'entry': 3050.00,
        'sl': 3041.00,
        'tp': 3080.00,
        'rr_ratio': 3.33
    }

    test_lot_info = {
        'lot_total': 0.03,
        'suggested_orders': 3
    }

    # Test scenarios
    scenarios = [
        ("Normal", {
            'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
            'consecutive_loss': 0,
            'total_loss_pct': 0.0,
            'trading_blocked': False,
            'news_flag': False
        }),
        ("Has active plan", {
            'active_plan_id': 'PLAN-20260408-001',
            'consecutive_loss': 0,
            'total_loss_pct': 0.0,
            'trading_blocked': False
        }),
        ("Consecutive loss = 3", {
            'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
            'consecutive_loss': 3,
            'total_loss_pct': 0.0,
            'trading_blocked': False
        }),
        ("Total loss > 30%", {
            'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
            'consecutive_loss': 0,
            'total_loss_pct': 0.35,
            'trading_blocked': False
        }),
        ("News event", {
            'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
            'consecutive_loss': 0,
            'total_loss_pct': 0.0,
            'trading_blocked': False,
            'news_flag': True
        })
    ]

    for name, portfolio in scenarios:
        print(f"\n📝 Scenario: {name}")
        result = guardian_check(test_decision, test_lot_info, portfolio)
        print(f"   Approved: {result['approved']}")
        if not result['approved']:
            print(f"   Reason: {result['block_reason']}")
            print(f"   Blocked by: {result['blocked_by']}")

    # Test R:R < 1.0
    print("\n📝 Scenario: R:R < 1.0")
    bad_rr_decision = {**test_decision, 'rr_ratio': 0.8}
    result = guardian_check(bad_rr_decision, test_lot_info, scenarios[0][1])
    print(f"   Approved: {result['approved']}")
    if not result['approved']:
        print(f"   Reason: {result['block_reason']}")

    print("\n" + "="*70)
