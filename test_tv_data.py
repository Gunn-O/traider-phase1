#!/usr/bin/env python3
"""ทดสอบ TradingView Data Feed"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

try:
    from tvDatafeed.main import TvDatafeed, Interval

    username = os.getenv('TV_USERNAME')
    password = os.getenv('TV_PASSWORD')

    print('🔍 Testing TradingView Data Feed...\n')
    print(f'Username: {username}')
    print(f'Password: {"*" * len(password) if password else "Not set"}')

    tv = TvDatafeed(username, password)

    # ดึงข้อมูล XAUUSD
    print('\nFetching XAUUSD from TradingView/OANDA...')
    data = tv.get_hist(
        symbol='XAUUSD',
        exchange='OANDA',
        interval=Interval.in_5_minute,
        n_bars=10
    )

    if data is not None and not data.empty:
        last_price = data['close'].iloc[-1]
        last_time = data.index[-1]

        print(f'\n✅ SUCCESS!')
        print(f'   Last Price: ${last_price:.2f}')
        print(f'   Time: {last_time}')
        print(f'   Bars received: {len(data)}')

        print(f'\n📊 Last 3 candles:')
        print(data[['open', 'high', 'low', 'close']].tail(3).to_string())
    else:
        print('❌ No data received')

except ImportError as e:
    print(f'❌ Import Error: {e}')
    print('\nTry installing:')
    print('   pip install git+https://github.com/rongardF/tvdatafeed.git')

except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
