#!/usr/bin/env python3
"""
ทดสอบ pipeline ครั้งเดียว (ไม่ใช่ loop)

รัน: python test_pipeline.py
"""

import os
from dotenv import load_dotenv
from main import TraiderMainLoop

load_dotenv()


def test_single_run():
    """ทดสอบรัน pipeline ครั้งเดียว"""

    print("🧪 Testing Tra(i)der Pipeline (Single Run)\n")

    # ตรวจสอบ DATA_MODE
    data_mode = os.getenv('DATA_MODE', 'simulate')

    if data_mode == 'backtest':
        print("⚠️  Current DATA_MODE=backtest")
        print("   Switching to simulate mode for testing...")
        os.environ['DATA_MODE'] = 'simulate'

    # สร้าง trading system
    trader = TraiderMainLoop()

    # รัน pipeline ครั้งเดียว
    print("\n" + "="*70)
    print("Running pipeline once...")
    print("="*70 + "\n")

    trader.run_pipeline()

    print("\n" + "="*70)
    print("✅ Test completed!")
    print("="*70)


if __name__ == "__main__":
    test_single_run()
