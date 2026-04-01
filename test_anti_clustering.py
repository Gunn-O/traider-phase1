#!/usr/bin/env python3
"""
ทดสอบ anti-clustering logic
รัน pipeline 2 ครั้งติดกัน → ครั้งที่ 2 ควรถูกบล็อค
"""

import os
import time
from dotenv import load_dotenv
from main import TraiderMainLoop

load_dotenv()

def test_anti_clustering():
    """ทดสอบการป้องกัน signal ซ้ำ"""

    print("🧪 Testing Anti-Clustering Logic\n")

    os.environ['DATA_MODE'] = 'simulate'

    trader = TraiderMainLoop()

    # รันครั้งที่ 1
    print("\n" + "="*70)
    print("🔵 RUN #1: Should SEND signal")
    print("="*70 + "\n")
    trader.run_pipeline()

    # รอ 3 วินาที
    print("\n⏱️  Waiting 3 seconds...\n")
    time.sleep(3)

    # รันครั้งที่ 2 (ควรถูกบล็อค)
    print("\n" + "="*70)
    print("🔴 RUN #2: Should be BLOCKED by anti-clustering")
    print("="*70 + "\n")
    trader.run_pipeline()

    print("\n" + "="*70)
    print("✅ Test completed!")
    print("="*70)
    print("\n💡 Expected result:")
    print("   - Run #1: Signal sent")
    print("   - Run #2: BLOCKED (cooldown period)")


if __name__ == "__main__":
    test_anti_clustering()
