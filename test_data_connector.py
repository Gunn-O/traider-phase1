"""
Test script for DataConnector
Run: python test_data_connector.py
"""

from utils import create_connector
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


def test_simulate_mode():
    """Test simulate mode (recommended for Phase I)"""
    print("\n" + "="*60)
    print("TEST 1: SIMULATE MODE (Last 60 days)")
    print("="*60)

    try:
        with create_connector('simulate') as conn:
            data = conn.get_latest_candles('XAUUSD', m5_count=80, h1_count=20)

            print(f"✓ Symbol: {data['symbol']}")
            print(f"✓ Timestamp: {data['timestamp']}")
            print(f"✓ Current price: ${data['current_price']:.2f}")
            print(f"✓ M5 candles retrieved: {len(data['m5_ohlcv'])}")
            print(f"✓ H1 candles retrieved: {len(data['h1_candles'])}")

            if data['m5_ohlcv']:
                print(f"\n📊 Last 3 M5 candles:")
                for candle in data['m5_ohlcv'][-3:]:
                    print(f"   {candle['time']} | "
                          f"O:{candle['open']:7.2f} "
                          f"H:{candle['high']:7.2f} "
                          f"L:{candle['low']:7.2f} "
                          f"C:{candle['close']:7.2f}")

            print("\n✅ SIMULATE mode works perfectly!")
            return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def test_backtest_mode_recent():
    """Test backtest mode with recent dates (within 60 days)"""
    print("\n" + "="*60)
    print("TEST 2: BACKTEST MODE (Recent 30 days)")
    print("="*60)

    try:
        connector = create_connector('backtest')
        connector.connect()

        # Use recent dates within 60-day limit
        end = datetime.now()
        start = end - timedelta(days=30)

        print(f"Date range: {start.date()} to {end.date()}")

        data = connector.get_latest_candles(
            'XAUUSD',
            m5_count=80,
            h1_count=20,
            start_date=start,
            end_date=end
        )

        print(f"✓ M5 candles: {len(data['m5_ohlcv'])}")
        print(f"✓ H1 candles: {len(data['h1_candles'])}")
        print(f"✓ Current price: ${data['current_price']:.2f}")

        connector.disconnect()
        print("\n✅ BACKTEST mode (recent) works!")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def test_backtest_mode_old():
    """Test backtest mode with old dates (will fail - demonstrates limitation)"""
    print("\n" + "="*60)
    print("TEST 3: BACKTEST MODE (Old dates - Expected to FAIL)")
    print("="*60)

    try:
        connector = create_connector('backtest')
        connector.connect()

        # Use dates beyond 60-day limit (should fail)
        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 31)

        print(f"Date range: {start.date()} to {end.date()}")
        print("(This should fail due to yfinance 60-day limitation)")

        data = connector.get_latest_candles(
            'XAUUSD',
            m5_count=80,
            h1_count=20,
            start_date=start,
            end_date=end
        )

        print(f"✓ M5 candles: {len(data['m5_ohlcv'])}")
        connector.disconnect()
        return True

    except ValueError as e:
        print(f"\n⚠️  Expected error caught:")
        print(f"   {str(e).split('Solutions:')[0]}")
        print("\n💡 This is expected - use 'simulate' mode for Phase I development")
        return True
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("TRAIDER PHASE I - DATA CONNECTOR TEST SUITE")
    print("="*60)

    results = []

    # Test 1: Simulate mode (recommended)
    results.append(("Simulate mode", test_simulate_mode()))

    # Test 2: Backtest mode (recent dates)
    results.append(("Backtest mode (recent)", test_backtest_mode_recent()))

    # Test 3: Backtest mode (old dates - expected to fail)
    results.append(("Backtest mode (old)", test_backtest_mode_old()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")

    print("\n" + "="*60)
    print("RECOMMENDATION FOR PHASE I DEVELOPMENT:")
    print("="*60)
    print("Use 'simulate' mode in your .env file:")
    print("  DATA_MODE=simulate")
    print("\nThis provides 60 days of recent data without date restrictions.")
    print("Perfect for developing and testing G1-G5 agents!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
