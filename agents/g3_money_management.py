"""
G3b — Money Management Agent

หน้าที่:
- คำนวณ lot size จาก risk per trade
- สูตร: lot = (account_balance × risk_pct) / (sl_distance × point_value)
- จำกัด max/min lot ตาม risk profile
"""

from typing import Dict, Optional


def calculate_lot_size(decision: Dict, account_balance: float,
                      risk_profile: Optional[Dict] = None) -> float:
    """
    คำนวณ lot size จาก risk per trade

    Args:
        decision: Decision dict from G3a (with entry and sl)
        account_balance: Current account balance (USD)
        risk_profile: Risk profile dict:
            - risk_per_trade_pct: Risk % per trade (default: 1.5)
            - min_lot: Minimum lot size (default: 0.01)
            - max_lot: Maximum lot size (default: 1.00)

    Returns:
        Calculated lot size (rounded to 2 decimals)

    Formula:
        lot = (account_balance × risk_pct) / (sl_distance × pip_value_per_lot)

        For XAUUSD:
        - 1 lot = 100 oz
        - 1 point = $0.01 move per oz
        - Pip value per lot = sl_distance_points × $0.1 per point per 0.01 lot
    """
    risk_profile = risk_profile or {}
    risk_pct = risk_profile.get('risk_per_trade_pct', 1.5) / 100  # Convert to decimal
    min_lot = risk_profile.get('min_lot', 0.01)
    max_lot = risk_profile.get('max_lot', 1.00)

    # Extract values
    entry = decision.get('entry', 0)
    sl = decision.get('sl', 0)

    if entry <= 0 or sl <= 0:
        return min_lot

    # Calculate SL distance in points
    sl_distance = abs(entry - sl)

    if sl_distance == 0:
        return min_lot

    # Risk amount in USD
    risk_amount = account_balance * risk_pct

    # For XAUUSD: point value ≈ $0.10 per 0.01 lot per point
    # So for 1 lot: point value = $10 per point
    # pip_value_per_lot = sl_distance × 10 (for 1 lot)
    pip_value_per_lot = sl_distance * 10

    # Calculate lot
    if pip_value_per_lot > 0:
        raw_lot = risk_amount / pip_value_per_lot
    else:
        raw_lot = min_lot

    # Round to 2 decimals
    lot = round(raw_lot, 2)

    # Apply limits
    lot = max(min_lot, min(lot, max_lot))

    return lot


# Example usage
if __name__ == "__main__":
    print("="*70)
    print("G3b MONEY MANAGEMENT TEST")
    print("="*70)

    # Test cases
    test_decision = {
        'entry': 3050.00,
        'sl': 3030.00,  # 20 points SL
        'tp1': 3090.00
    }

    test_balance = 10000  # $10,000
    test_risk_profile = {
        'risk_per_trade_pct': 1.5,  # 1.5% risk
        'min_lot': 0.01,
        'max_lot': 1.00
    }

    print(f"\n📊 Test Scenario:")
    print(f"   Account Balance: ${test_balance:,.2f}")
    print(f"   Risk per Trade: {test_risk_profile['risk_per_trade_pct']}%")
    print(f"   Entry: ${test_decision['entry']:.2f}")
    print(f"   SL: ${test_decision['sl']:.2f}")
    print(f"   SL Distance: {abs(test_decision['entry'] - test_decision['sl']):.2f} points")

    lot_size = calculate_lot_size(test_decision, test_balance, test_risk_profile)

    print(f"\n✓ Calculated Lot Size: {lot_size}")

    # Calculate actual risk
    sl_distance = abs(test_decision['entry'] - test_decision['sl'])
    actual_risk_usd = lot_size * sl_distance * 10  # $10 per point per lot
    actual_risk_pct = (actual_risk_usd / test_balance) * 100

    print(f"   Actual Risk: ${actual_risk_usd:.2f} ({actual_risk_pct:.2f}%)")

    # Test edge cases
    print(f"\n📝 Edge Cases:")

    # Small SL
    small_sl_decision = {'entry': 3050.00, 'sl': 3045.00}
    lot = calculate_lot_size(small_sl_decision, test_balance, test_risk_profile)
    print(f"   Small SL (5pts): lot = {lot}")

    # Large SL
    large_sl_decision = {'entry': 3050.00, 'sl': 2950.00}
    lot = calculate_lot_size(large_sl_decision, test_balance, test_risk_profile)
    print(f"   Large SL (100pts): lot = {lot}")

    print("\n" + "="*70)
