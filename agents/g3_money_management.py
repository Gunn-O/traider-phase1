"""
G3b — Money Management Agent (v2.1)

หน้าที่:
- คำนวณ lot size ตามสูตรใหม่
- สูตร: lot = เสียได้ (USD) / SL (pip)
- เสียได้ = balance × 10% per plan
- แนะนำจำนวน order (1-3)

Reference: TRAIDER_MASTER_PLAN_v2.1.md Section 2
"""

import logging
from typing import Dict

from config import calc_lot, RISK_CONFIG

# Setup logging
logger = logging.getLogger(__name__)


# ============================================================================
# LOT CALCULATION (ใช้จาก config.py)
# ============================================================================

def calculate_lot_for_decision(decision: Dict, balance: float,
                                winrate_test: bool = False) -> Dict:
    """
    คำนวณ lot สำหรับ decision

    Args:
        decision: {
            'action': 'BUY' | 'SELL',
            'entry': float,
            'sl': float,
            'tp': float
        }
        balance: Account balance (USD)
        winrate_test: ถ้า True ใช้ 0.01 lot เสมอ

    Returns:
        {
            'lot_total': float,
            'lot_per_order': float,
            'suggested_orders': int (1-3),
            'max_loss_usd': float
        }
    """
    if decision.get('action') == 'SKIP':
        return {
            'lot_total': 0,
            'lot_per_order': 0,
            'suggested_orders': 0,
            'max_loss_usd': 0
        }

    # คำนวณ SL distance (pip)
    entry = decision.get('entry', 0)
    sl = decision.get('sl', 0)

    if entry <= 0 or sl <= 0:
        logger.warning("Invalid entry or SL")
        return {'lot_total': 0.01, 'lot_per_order': 0.01,
                'suggested_orders': 1, 'max_loss_usd': 0}

    sl_distance = abs(entry - sl)
    sl_pip = int(sl_distance * 100)  # 1 pip = 0.01 USD

    # เรียก calc_lot จาก config.py
    result = calc_lot(balance, sl_pip, winrate_test)

    logger.info(f"Lot calculation: balance=${balance:.2f}, sl={sl_pip}pip → "
                f"lot_total={result['lot_total']}, orders={result['suggested_orders']}")

    return result


def validate_lot_limits(lot_total: float) -> bool:
    """
    ตรวจสอบว่า lot อยู่ในขอบเขตที่อนุญาต

    Args:
        lot_total: Lot ทั้งหมด

    Returns:
        True ถ้าผ่านเกณฑ์
    """
    if lot_total < 0.01:
        logger.warning(f"Lot too small: {lot_total} < 0.01")
        return False

    if lot_total > 10.0:
        logger.warning(f"Lot too large: {lot_total} > 10.0")
        return False

    return True


def create_order_plan(decision: Dict, lot_info: Dict, world_state: Dict = None) -> Dict:
    """
    สร้างแผน order (1 แผน = 1 order เท่านั้น)

    Args:
        decision: Decision dict from G3a
        lot_info: output จาก calculate_lot_for_decision()
        world_state: Not used (kept for compatibility)

    Returns:
        {
            'plan_id': str,  # สร้างจาก main.py
            'lot_total': float,
            'total_orders': 1,
            'orders': [
                {'order_num': 1, 'lot': lot_total, 'entry': ..., ...}
            ]
        }
    """
    action = decision['action']
    entry = decision['entry']
    sl = decision['sl']
    tp = decision['tp']
    lot_total = lot_info['lot_total']

    # 1 plan = 1 order เสมอ
    order = {
        'order_num': 1,
        'order_type': 'MARKET',
        'action': action,
        'entry': entry,
        'sl': sl,
        'tp': tp,
        'lot': lot_total,  # ใช้ lot เต็มจำนวน
        'rr_ratio': decision.get('rr_ratio', 0)
    }

    logger.info(f"Order 1 (MARKET): {action} @ {entry:.2f}, sl={sl:.2f}, tp={tp:.2f}, lot={lot_total}, R:R={order['rr_ratio']:.2f}")

    return {
        'lot_total': lot_total,
        'total_orders': 1,
        'max_loss_usd': lot_info['max_loss_usd'],
        'orders': [order]
    }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("G3b MONEY MANAGEMENT v2.1 TEST")
    print("="*70)

    # Test cases
    test_decision = {
        'action': 'BUY',
        'entry': 3050.00,
        'sl': 3041.00,  # 900 pip SL
        'tp': 3080.00
    }

    test_balance = 300  # $300
    print(f"\n📊 Test Scenario:")
    print(f"   Balance: ${test_balance:.2f}")
    print(f"   Entry: ${test_decision['entry']:.2f}")
    print(f"   SL: ${test_decision['sl']:.2f}")
    sl_usd = abs(test_decision['entry'] - test_decision['sl'])
    print(f"   SL Distance: {sl_usd:.2f} USD = {int(sl_usd*100)} pip")

    # Normal mode
    print("\n--- Normal Mode ---")
    lot_info = calculate_lot_for_decision(test_decision, test_balance, winrate_test=False)
    print(f"   Lot Total: {lot_info['lot_total']}")
    print(f"   Lot per Order: {lot_info['lot_per_order']}")
    print(f"   Suggested Orders: {lot_info['suggested_orders']}")
    print(f"   Max Loss: ${lot_info['max_loss_usd']:.2f}")

    # Winrate test mode
    print("\n--- Winrate Test Mode ---")
    lot_info_test = calculate_lot_for_decision(test_decision, test_balance, winrate_test=True)
    print(f"   Lot Total: {lot_info_test['lot_total']}")
    print(f"   Lot per Order: {lot_info_test['lot_per_order']}")
    print(f"   Suggested Orders: {lot_info_test['suggested_orders']}")

    # Create order plan
    print("\n--- Order Plan ---")
    plan = create_order_plan(test_decision, lot_info)
    print(f"   Orders count: {len(plan['orders'])}")
    for order in plan['orders']:
        print(f"   Order {order['order_num']}: {order['lot']} lot")

    print("\n" + "="*70)
