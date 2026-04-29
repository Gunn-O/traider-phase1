"""
Simulated Execution

คำนวณผลลัพธ์ของ trade (WIN/LOSS/BE) โดยไม่ execute จริง
ใช้ราคาย้อนหลังจาก subsequent candles เพื่อตรวจสอบว่า hit SL หรือ TP

Phase I: ใช้สำหรับ backtest เท่านั้น
Phase II: จะมี real MT5 execution
"""

from typing import Dict, List, Tuple, Optional


def calculate_simulated_result(
    decision: Dict,
    subsequent_candles: List[Dict],
    max_duration_candles: int = 48  # 4 hours for M5 = 48 candles
) -> Tuple[str, float, float, str, int]:
    """
    คำนวณ WIN/LOSS/BE โดยไม่ execute จริง

    Args:
        decision: Decision dict with action, entry, sl, tp1-3, lot
        subsequent_candles: List of candles หลัง signal
        max_duration_candles: Max candles to check (default: 48 = 4 hours)

    Returns:
        Tuple of:
        - result: "WIN" | "LOSS" | "BE" | "TIMEOUT" | "PENDING"
        - pnl_usd: P&L in USD (MUST be negative for LOSS, positive for WIN)
        - exit_price: Actual exit price
        - close_reason: "TP1_HIT" | "TP2_HIT" | "TP3_HIT" | "SL_HIT" | "TIMEOUT" | "PENDING"
        - duration_candles: Duration in candles
    """
    action = decision.get('action', 'SKIP')
    entry = decision.get('entry', 0)
    sl = decision.get('sl', 0)
    tp1 = decision.get('tp1', 0)
    tp2 = decision.get('tp2', 0)
    tp3 = decision.get('tp3', 0)
    lot = decision.get('lot', 0)

    if action not in ['BUY', 'SELL']:
        return 'PENDING', 0.0, entry, 'INVALID_ACTION', 0

    if not subsequent_candles:
        return 'PENDING', 0.0, entry, 'NO_DATA', 0

    # Limit duration
    candles_to_check = subsequent_candles[:max_duration_candles]

    # Check each candle
    for i, candle in enumerate(candles_to_check, 1):
        high = candle.get('high', 0)
        low = candle.get('low', 0)

        if action == 'BUY':
            # Check SL first (priority)
            if low <= sl:
                pnl = calculate_pnl('BUY', entry, sl, lot)
                # Validate: LOSS must have negative P&L
                assert pnl <= 0, f"BUY SL hit but P&L is positive: {pnl} (entry={entry}, sl={sl})"
                return 'LOSS', pnl, sl, 'SL_HIT', i

            # Check TP3 (best exit)
            if high >= tp3:
                pnl = calculate_pnl('BUY', entry, tp3, lot)
                # Validate: WIN must have positive P&L
                assert pnl > 0, f"BUY TP3 hit but P&L is not positive: {pnl} (entry={entry}, tp3={tp3})"
                return 'WIN', pnl, tp3, 'TP3_HIT', i

            # Check TP2
            if high >= tp2:
                pnl = calculate_pnl('BUY', entry, tp2, lot)
                assert pnl > 0, f"BUY TP2 hit but P&L is not positive: {pnl}"
                return 'WIN', pnl, tp2, 'TP2_HIT', i

            # Check TP1
            if high >= tp1:
                pnl = calculate_pnl('BUY', entry, tp1, lot)
                assert pnl > 0, f"BUY TP1 hit but P&L is not positive: {pnl}"
                return 'WIN', pnl, tp1, 'TP1_HIT', i

        elif action == 'SELL':
            # Check SL first
            if high >= sl:
                pnl = calculate_pnl('SELL', entry, sl, lot)
                # Validate: LOSS must have negative P&L
                assert pnl <= 0, f"SELL SL hit but P&L is positive: {pnl} (entry={entry}, sl={sl})"
                return 'LOSS', pnl, sl, 'SL_HIT', i

            # Check TP3
            if low <= tp3:
                pnl = calculate_pnl('SELL', entry, tp3, lot)
                assert pnl > 0, f"SELL TP3 hit but P&L is not positive: {pnl}"
                return 'WIN', pnl, tp3, 'TP3_HIT', i

            # Check TP2
            if low <= tp2:
                pnl = calculate_pnl('SELL', entry, tp2, lot)
                assert pnl > 0, f"SELL TP2 hit but P&L is not positive: {pnl}"
                return 'WIN', pnl, tp2, 'TP2_HIT', i

            # Check TP1
            if low <= tp1:
                pnl = calculate_pnl('SELL', entry, tp1, lot)
                assert pnl > 0, f"SELL TP1 hit but P&L is not positive: {pnl}"
                return 'WIN', pnl, tp1, 'TP1_HIT', i

    # Timeout - close at current price
    last_candle = candles_to_check[-1]
    last_close = last_candle.get('close', entry)
    pnl = calculate_pnl(action, entry, last_close, lot)

    result = 'BE' if abs(pnl) < 10 else ('WIN' if pnl > 0 else 'LOSS')

    return result, pnl, last_close, 'TIMEOUT', len(candles_to_check)


def calculate_pnl(action: str, entry: float, exit_price: float, lot: float) -> float:
    """
    คำนวณ P&L in USD

    Args:
        action: "BUY" or "SELL"
        entry: Entry price
        exit_price: Exit price
        lot: Lot size

    Returns:
        P&L in USD

    Formula for XAUUSD:
        - 1 lot = 100 oz
        - 1 point = $0.01 move per oz
        - P&L = (exit - entry) × lot × 100 oz × $0.01 per oz per point
        - Simplified: P&L = (exit - entry) × lot × $10 per point
    """
    if action == 'BUY':
        price_diff = exit_price - entry
    elif action == 'SELL':
        price_diff = entry - exit_price
    else:
        return 0.0

    # For XAUUSD: $10 per point per lot
    pnl = price_diff * lot * 10

    return round(pnl, 2)


def calculate_rr_ratio(decision: Dict) -> float:
    """
    คำนวณ R:R ratio (Risk:Reward)

    Args:
        decision: Decision dict with entry, sl, tp1

    Returns:
        R:R ratio (e.g., 2.5 means 1:2.5)
    """
    entry = decision.get('entry', 0)
    sl = decision.get('sl', 0)
    tp1 = decision.get('tp1', 0)

    if entry <= 0 or sl <= 0 or tp1 <= 0:
        return 0.0

    risk = abs(entry - sl)
    reward = abs(tp1 - entry)

    if risk > 0:
        return round(reward / risk, 2)
    return 0.0


# Example usage
if __name__ == "__main__":
    print("="*70)
    print("SIMULATED EXECUTION TEST")
    print("="*70)

    # Test decision (BUY)
    test_decision = {
        'action': 'BUY',
        'entry': 3050.00,
        'sl': 3030.00,
        'tp1': 3090.00,
        'tp2': 3110.00,
        'tp3': 3130.00,
        'lot': 0.15
    }

    print(f"\n📊 Test Decision:")
    print(f"   Action: {test_decision['action']}")
    print(f"   Entry: ${test_decision['entry']:.2f}")
    print(f"   SL: ${test_decision['sl']:.2f}")
    print(f"   TP1/2/3: ${test_decision['tp1']:.2f} / ${test_decision['tp2']:.2f} / ${test_decision['tp3']:.2f}")
    print(f"   Lot: {test_decision['lot']}")

    rr = calculate_rr_ratio(test_decision)
    print(f"   R:R Ratio: 1:{rr}")

    # Scenario 1: TP1 hit
    print(f"\n📈 Scenario 1: TP1 Hit")
    candles_tp1 = [
        {'high': 3060, 'low': 3045, 'close': 3055},
        {'high': 3070, 'low': 3055, 'close': 3065},
        {'high': 3095, 'low': 3065, 'close': 3092},  # TP1 hit
    ]

    result, pnl, exit_price, reason, duration = calculate_simulated_result(
        test_decision, candles_tp1
    )

    print(f"   Result: {result}")
    print(f"   P&L: ${pnl:.2f}")
    print(f"   Exit: ${exit_price:.2f}")
    print(f"   Reason: {reason}")
    print(f"   Duration: {duration} candles")

    # Scenario 2: SL hit
    print(f"\n📉 Scenario 2: SL Hit")
    candles_sl = [
        {'high': 3055, 'low': 3040, 'close': 3045},
        {'high': 3048, 'low': 3025, 'close': 3028},  # SL hit
    ]

    result, pnl, exit_price, reason, duration = calculate_simulated_result(
        test_decision, candles_sl
    )

    print(f"   Result: {result}")
    print(f"   P&L: ${pnl:.2f}")
    print(f"   Exit: ${exit_price:.2f}")
    print(f"   Reason: {reason}")
    print(f"   Duration: {duration} candles")

    # Scenario 3: TP3 hit (best scenario)
    print(f"\n🎯 Scenario 3: TP3 Hit")
    candles_tp3 = [
        {'high': 3070, 'low': 3048, 'close': 3065},
        {'high': 3100, 'low': 3065, 'close': 3095},
        {'high': 3120, 'low': 3090, 'close': 3115},
        {'high': 3135, 'low': 3110, 'close': 3132},  # TP3 hit
    ]

    result, pnl, exit_price, reason, duration = calculate_simulated_result(
        test_decision, candles_tp3
    )

    print(f"   Result: {result}")
    print(f"   P&L: ${pnl:.2f}")
    print(f"   Exit: ${exit_price:.2f}")
    print(f"   Reason: {reason}")
    print(f"   Duration: {duration} candles")

    # Scenario 4: Timeout
    print(f"\n⏱  Scenario 4: Timeout (4 hours)")
    candles_timeout = [
        {'high': 3060, 'low': 3045, 'close': 3055}
    ] * 48  # 48 candles = 4 hours
    candles_timeout[-1]['close'] = 3070  # End at 3070

    result, pnl, exit_price, reason, duration = calculate_simulated_result(
        test_decision, candles_timeout
    )

    print(f"   Result: {result}")
    print(f"   P&L: ${pnl:.2f}")
    print(f"   Exit: ${exit_price:.2f}")
    print(f"   Reason: {reason}")
    print(f"   Duration: {duration} candles")

    print("\n" + "="*70)
