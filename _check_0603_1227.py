"""Pull the 2026-06-03 10:10 SELL trade details + MT5 actual candle data."""
import sqlite3, json
from datetime import datetime, timedelta

c = sqlite3.connect('traider_sim.db')
rows = c.execute("""
    SELECT trade_id, plan_id, timestamp_open, action, entry_price, sl_price, tp_price,
           lot_size, result, close_price, timestamp_close, pnl_usd, pattern_details_json,
           technique
    FROM trades
    WHERE timestamp_open LIKE '2026-06-03T10:10%'
    ORDER BY trade_id
""").fetchall()

print(f'{len(rows)} trades at 2026-06-03 10:10')
print('='*100)
for r in rows:
    tid, plan_id, t_open, action, e, sl, tp, lot, result, cp, t_close, pnl, det, tech = r
    print(f'\ntrade_id   : {tid}')
    print(f'plan_id    : {plan_id}')
    print(f'timestamp  : {t_open}  (= candle_time used by run_once)')
    print(f'technique  : {tech}')
    print(f'action     : {action}  lot={lot}')
    print(f'entry      : {e}')
    print(f'sl / tp    : {sl} / {tp}')
    print(f'result     : {result}  pnl=${pnl or 0:+.2f}')
    print(f'close      : {cp or "-"} @ {t_close or "-"}')
    if det:
        try:
            d = json.loads(det)
            print('pattern_details:')
            for k, v in d.items():
                print(f'  {k}: {v}')
        except Exception as e_p:
            print(f'  (parse err: {e_p})')

# Also pull actual MT5 candle data for 10:08, 10:09, 10:10 UTC
print()
print('='*100)
print('MT5 actual candles for 2026-06-03 10:05 → 10:15 UTC:')
print('='*100)
try:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f'mt5 init failed: {mt5.last_error()}')
    else:
        # broker time is usually GMT+3 for Exness. UTC 10:08 = broker 13:08
        from_t = datetime(2026, 6, 3, 10, 0)
        to_t   = datetime(2026, 6, 3, 10, 20)
        candles = mt5.copy_rates_range('XAUUSDc', mt5.TIMEFRAME_M1,
                                       from_t - timedelta(hours=12),
                                       to_t + timedelta(hours=12))
        if candles is None or len(candles) == 0:
            print('No MT5 candles')
        else:
            for k in candles:
                t = datetime.fromtimestamp(k['time'])
                body = (k['close'] - k['open']) * 100
                direction = 'BULL' if k['close'] > k['open'] else 'BEAR' if k['close'] < k['open'] else 'DOJI'
                # Match against user's UTC times of interest
                if 9 <= t.hour <= 14:
                    print(f'  {t.strftime("%H:%M")} O={k["open"]:.3f} H={k["high"]:.3f} L={k["low"]:.3f} '
                          f'C={k["close"]:.3f} body={body:+.1f}pip {direction}')
        mt5.shutdown()
except Exception as e:
    print(f'(MT5 query unavailable: {e})')
