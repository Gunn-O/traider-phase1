#!/usr/bin/env python3
"""
Test Symbol Support in TradingView
Run: python test_symbol_support.py
"""

from tvdatafeed import TvDatafeed, Interval

print('🧪 Testing Symbol Support in TradingView...\n')

tv = TvDatafeed()

# Test XAUUSDm (Cent)
print('1️⃣ Testing XAUUSDm (Cent account):')
try:
    df = tv.get_hist(symbol='XAUUSDm', exchange='OANDA', interval=Interval.in_5_minute, n_bars=5)
    if df is not None and not df.empty:
        print(f'   ✅ XAUUSDm works — {len(df)} candles retrieved')
        print(f'   Last price: ${df["close"].iloc[-1]:.2f}')
    else:
        print('   ❌ XAUUSDm no data — may need to use XAUUSD instead')
except Exception as e:
    print(f'   ❌ XAUUSDm failed: {str(e)[:100]}')
    print('   → Will try XAUUSD instead')

print()

# Test XAUUSD (Real)
print('2️⃣ Testing XAUUSD (Real account):')
try:
    df = tv.get_hist(symbol='XAUUSD', exchange='OANDA', interval=Interval.in_5_minute, n_bars=5)
    if df is not None and not df.empty:
        print(f'   ✅ XAUUSD works — {len(df)} candles retrieved')
        print(f'   Last price: ${df["close"].iloc[-1]:.2f}')
    else:
        print('   ❌ XAUUSD no data')
except Exception as e:
    print(f'   ❌ XAUUSD failed: {str(e)[:100]}')

print()
print('='*70)
print('📊 Conclusion:')
print('='*70)
print('If XAUUSDm ❌ but XAUUSD ✅:')
print('  → TradingView does NOT have separate XAUUSDm symbol')
print('  → Need to map both symbols to XAUUSD in data_connector.py')
print('  → Symbol selection still works (UI only), but data comes from same source')
print()
print('If both ✅:')
print('  → TradingView has both symbols')
print('  → No changes needed — Good to go! 🚀')
print('='*70)
