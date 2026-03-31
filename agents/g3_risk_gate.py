"""
G3c — Guardian Agent (Risk Gate)

หน้าที่:
- ตรวจสอบ risk limits ก่อน approve signal
- Max Drawdown, Daily Loss, Max Open Trades
- Confidence threshold, R:R ratio
- News events
- Blocked conditions

Output: approved (True/False) + reason
"""

from typing import Dict, Optional


def guardian_check(decision: Dict, lot: float, account_state: Dict,
                  risk_profile: Dict) -> Dict:
    """
    ตรวจสอบ risk profile ก่อน approve signal

    Args:
        decision: Decision dict from G3a
        lot: Calculated lot size from G3b
        account_state: Current account state:
            - balance: Current balance
            - daily_pnl_pct: Daily P&L %
            - total_dd_pct: Total drawdown %
            - open_trades: Number of open trades
            - news_active: News event active
        risk_profile: Risk profile:
            - max_dd_pct: Max drawdown % (default: 5.0)
            - max_daily_loss_pct: Max daily loss % (default: 3.0)
            - max_open_trades: Max open trades (default: 2)
            - min_confidence: Min confidence (default: 0.70)
            - min_rr_ratio: Min R:R ratio (default: 2.0)
            - blocked_conditions: List of blocked conditions (default: [])

    Returns:
        Dict:
            - approved: bool
            - reason: str
            - adjusted_lot: float (0 if blocked)
            - blocked_condition: str
    """
    reasons = []

    # 1. Max Daily Drawdown
    daily_pnl = account_state.get('daily_pnl_pct', 0)
    max_daily_loss = risk_profile.get('max_daily_loss_pct', 3.0)

    if daily_pnl <= -max_daily_loss:
        reasons.append(f"Daily loss limit reached: {daily_pnl:.1f}% (max: -{max_daily_loss}%)")

    # 2. Max Total Drawdown
    total_dd = account_state.get('total_dd_pct', 0)
    max_dd = risk_profile.get('max_dd_pct', 5.0)

    if total_dd >= max_dd:
        reasons.append(f"Max DD reached: {total_dd:.1f}% (max: {max_dd}%)")

    # 3. Max Open Trades
    open_trades = account_state.get('open_trades', 0)
    max_trades = risk_profile.get('max_open_trades', 2)

    if open_trades >= max_trades:
        reasons.append(f"Max open trades: {open_trades}/{max_trades}")

    # 4. Confidence threshold
    confidence = decision.get('confidence', 0)
    min_confidence = risk_profile.get('min_confidence', 0.70)

    if confidence < min_confidence:
        reasons.append(f"Confidence too low: {confidence:.3f} < {min_confidence}")

    # 5. R:R ratio
    entry = decision.get('entry', 0)
    sl = decision.get('sl', 0)
    tp1 = decision.get('tp1', 0)

    if entry > 0 and sl > 0 and tp1 > 0:
        sl_distance = abs(entry - sl)
        tp_distance = abs(tp1 - entry)
        rr = tp_distance / sl_distance if sl_distance > 0 else 0

        min_rr = risk_profile.get('min_rr_ratio', 2.0)
        if rr < min_rr:
            reasons.append(f"R:R too low: {rr:.2f} < {min_rr}")
    else:
        reasons.append("Invalid entry/sl/tp levels")

    # 6. News flag
    news_active = account_state.get('news_active', False)
    if news_active:
        reasons.append("High-impact news event active")

    # 7. Blocked conditions
    condition = decision.get('chart_condition', '')
    blocked = risk_profile.get('blocked_conditions', [])

    if condition in blocked:
        reasons.append(f"Condition blocked by user: {condition}")

    # Determine approval
    approved = len(reasons) == 0

    return {
        'approved': approved,
        'reason': ' | '.join(reasons) if reasons else 'All checks passed',
        'adjusted_lot': lot if approved else 0.0,
        'blocked_condition': condition if not approved else ''
    }


# Example usage
if __name__ == "__main__":
    print("="*70)
    print("G3c GUARDIAN (RISK GATE) TEST")
    print("="*70)

    # Test decision
    test_decision = {
        'chart_condition': 'A3_mountain',
        'action': 'BUY',
        'entry': 3050.00,
        'sl': 3030.00,
        'tp1': 3090.00,
        'tp2': 3110.00,
        'tp3': 3130.00,
        'confidence': 0.86
    }

    test_lot = 0.15

    # Test Scenario 1: All good
    print(f"\n📊 Scenario 1: Normal conditions")
    account_state = {
        'balance': 10000,
        'daily_pnl_pct': -0.5,
        'total_dd_pct': 1.2,
        'open_trades': 0,
        'news_active': False
    }

    risk_profile = {
        'max_dd_pct': 5.0,
        'max_daily_loss_pct': 3.0,
        'max_open_trades': 2,
        'min_confidence': 0.70,
        'min_rr_ratio': 2.0,
        'blocked_conditions': []
    }

    result = guardian_check(test_decision, test_lot, account_state, risk_profile)
    print(f"   Approved: {result['approved']}")
    print(f"   Reason: {result['reason']}")
    print(f"   Lot: {result['adjusted_lot']}")

    # Test Scenario 2: Daily loss limit
    print(f"\n📊 Scenario 2: Daily loss limit hit")
    account_state['daily_pnl_pct'] = -3.5
    result = guardian_check(test_decision, test_lot, account_state, risk_profile)
    print(f"   Approved: {result['approved']}")
    print(f"   Reason: {result['reason']}")

    # Test Scenario 3: Max open trades
    print(f"\n📊 Scenario 3: Max open trades reached")
    account_state['daily_pnl_pct'] = -0.5
    account_state['open_trades'] = 2
    result = guardian_check(test_decision, test_lot, account_state, risk_profile)
    print(f"   Approved: {result['approved']}")
    print(f"   Reason: {result['reason']}")

    # Test Scenario 4: Low R:R
    print(f"\n📊 Scenario 4: R:R too low")
    account_state['open_trades'] = 0
    low_rr_decision = test_decision.copy()
    low_rr_decision['tp1'] = 3055.00  # Very close TP
    result = guardian_check(low_rr_decision, test_lot, account_state, risk_profile)
    print(f"   Approved: {result['approved']}")
    print(f"   Reason: {result['reason']}")

    # Test Scenario 5: Blocked condition
    print(f"\n📊 Scenario 5: Condition blocked")
    risk_profile['blocked_conditions'] = ['A3_mountain']
    result = guardian_check(test_decision, test_lot, account_state, risk_profile)
    print(f"   Approved: {result['approved']}")
    print(f"   Reason: {result['reason']}")

    print("\n" + "="*70)
