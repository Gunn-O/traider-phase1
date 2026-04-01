#!/usr/bin/env python3
"""
เทส LINE Messaging API ส่งจริง
รัน: python test_line_real.py
"""

from agents.g4_notify import LINENotifier
from dotenv import load_dotenv
import os

load_dotenv()

def test_line_send():
    """เทสส่งข้อความจริง"""

    print("="*70)
    print("🧪 LINE MESSAGING API TEST")
    print("="*70)

    # ตรวจสอบ credentials
    token = os.getenv('LINE_CHANNEL_TOKEN', '')
    user_id = os.getenv('LINE_USER_ID', '')
    enabled = os.getenv('LINE_NOTIFY_ENABLED', 'false').lower() == 'true'

    print(f"\n📋 Configuration Check:")
    print(f"   LINE_CHANNEL_TOKEN: {'✓ (set)' if token else '✗ (missing)'}")
    print(f"   LINE_USER_ID: {'✓ (set)' if user_id else '✗ (missing)'}")
    print(f"   LINE_NOTIFY_ENABLED: {enabled}")

    if not enabled:
        print("\n⚠️  LINE_NOTIFY_ENABLED=false")
        print("   กรุณาเปิดใน .env ก่อนเทสส่งจริง:")
        print("   LINE_NOTIFY_ENABLED=true")
        return

    if not token or not user_id:
        print("\n❌ Missing credentials!")
        print("   กรุณาตั้งค่าใน .env:")
        print("   LINE_CHANNEL_TOKEN=your_token")
        print("   LINE_USER_ID=Uxxxxxxxxxxxxx")
        return

    # สร้าง test decision
    test_decision = {
        'action': 'BUY',
        'condition': 'A3',
        'condition_name': 'ภูเขา + แนวเด้ง',
        'entry': 3050.0,
        'tp1': 3062.0,
        'tp2': 3068.0,
        'tp3': 3075.0,
        'sl': 3044.0,
        'lot_size': 0.58,
        'confidence': 0.82,
        'reasoning': 'ฐานภูเขาชัด RSI 36',
        'trend_h1': 'Bullish',
        'session': 'London'
    }

    # Preview message
    notifier = LINENotifier()
    message = notifier._format_signal_message(test_decision)

    print(f"\n📝 Message Preview:")
    print("─" * 70)
    print(message)
    print("─" * 70)

    # Confirm before sending
    response = input("\n❓ ส่งข้อความนี้ไปที่ LINE จริงๆ? (y/n): ")

    if response.lower() != 'y':
        print("⏸️  ยกเลิกการส่ง")
        return

    # Send
    print("\n📤 Sending to LINE...")
    success = notifier.send_signal(test_decision)

    if success:
        print("✅ ส่งสำเร็จ! เช็คใน LINE ได้เลย")
    else:
        print("❌ ส่งไม่สำเร็จ ลองเช็ค:")
        print("   1. Channel Access Token ถูกต้องไหม")
        print("   2. User ID ถูกต้องไหม (ต้องขึ้นต้นด้วย U)")
        print("   3. เพิ่มบอทเป็นเพื่อนแล้วหรือยัง")

    print("\n" + "="*70)


if __name__ == "__main__":
    test_line_send()
