"""
Backtest Jan-Feb 2025 (Trending Period)

รัน backtest ช่วงที่ทองขึ้นแรง เพื่อทดสอบ A1/A2 uptrend/downtrend conditions
"""

from backtest_full import FullBacktest
from datetime import datetime

def main():
    print("\n" + "="*70)
    print("BACKTEST: JAN-FEB 2025 (TRENDING PERIOD)")
    print("="*70)

    # Jan-Feb 2025 period
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 2, 28)

    print(f"\nPeriod: {start_date.date()} to {end_date.date()}")
    print(f"Expected: Strong uptrend → A1 conditions should appear")
    print(f"Agent: Mock Agent")
    print(f"\n{'='*70}\n")

    # Run backtest
    bt = FullBacktest(
        use_claude_api=False,  # Use Mock
        verbose=False,
        debug_rejections=0
    )

    try:
        results = bt.run(start_date, end_date)

        # Print summary
        bt.print_summary()

        # Save results
        bt.save_results('backtest/results/backtest_jan_feb_2025.json')

    except Exception as e:
        print(f"\n❌ Error during backtest:")
        print(f"   {str(e)}")
        print(f"\n💡 Note: yfinance has 60-day limit for intraday data")
        print(f"   Cannot fetch data older than 60 days")
        print(f"   Current date: {datetime.now().date()}")
        print(f"   Requested: {start_date.date()} - {end_date.date()}")
        print(f"\n   Suggestion: Use 'simulate' mode with recent data only")
        print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
