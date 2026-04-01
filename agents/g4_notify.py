"""
G4a — LINE Notification Agent

หน้าที่:
- รับ decision จาก G3 และส่งแจ้งเตือนผ่าน LINE Messaging API
- รองรับ BUY/SELL/SKIP signals
- แสดงข้อมูลครบถ้วน: entry, TP levels, SL, lot size, confidence
"""

import os
import requests
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()


class LINENotifier:
    """LINE Messaging API client for sending trading signals"""

    def __init__(self):
        """Initialize LINE client with credentials from .env"""
        self.channel_token = os.getenv('LINE_CHANNEL_TOKEN', '')
        self.user_id = os.getenv('LINE_USER_ID', '')
        self.enabled = os.getenv('LINE_NOTIFY_ENABLED', 'false').lower() == 'true'
        self.api_url = 'https://api.line.me/v2/bot/message/push'

        if self.enabled and (not self.channel_token or not self.user_id):
            raise ValueError("LINE_CHANNEL_TOKEN and LINE_USER_ID required when LINE_NOTIFY_ENABLED=true")

    def _format_signal_message(self, decision: Dict) -> str:
        """
        Format trading signal message in Thai

        Args:
            decision: Decision dict from G3 containing:
                - action: 'BUY' | 'SELL' | 'SKIP'
                - condition: 'A1' | 'A2' | ... | 'A6'
                - condition_name: Thai condition name
                - entry: Entry price
                - tp1, tp2, tp3: Take profit levels
                - sl: Stop loss
                - lot_size: Position size
                - confidence: Confidence score (0.0-1.0)
                - reasoning: Decision reasoning
                - trend_h1: H1 trend (optional)
                - session: Trading session (optional)

        Returns:
            Formatted message string
        """
        action = decision.get('action', 'SKIP')
        condition = decision.get('condition', '')
        condition_name = decision.get('condition_name', '')
        entry = decision.get('entry', 0)
        tp1 = decision.get('tp1', 0)
        tp2 = decision.get('tp2', 0)
        tp3 = decision.get('tp3', 0)
        sl = decision.get('sl', 0)
        lot_size = decision.get('lot_size', 0)
        confidence = decision.get('confidence', 0)
        reasoning = decision.get('reasoning', '')
        trend_h1 = decision.get('trend_h1', '')
        session = decision.get('session', '')

        # Action emoji
        action_emoji = {
            'BUY': '🟢',
            'SELL': '🔴',
            'SKIP': '⏸️'
        }.get(action, '⚪')

        # Format prices
        entry_str = f"{entry:,.1f}" if entry else "—"
        tp1_str = f"{tp1:,.0f}" if tp1 else "—"
        tp2_str = f"{tp2:,.0f}" if tp2 else "—"
        tp3_str = f"{tp3:,.0f}" if tp3 else "—"
        sl_str = f"{sl:,.0f}" if sl else "—"
        lot_str = f"{lot_size:.2f}" if lot_size else "—"
        confidence_pct = int(confidence * 100) if confidence else 0

        # Build message
        if action == 'SKIP':
            message = f"""📊 Tra(i)der Signal
──────────────────
⏸️ SKIP | {condition} {condition_name}
Confidence: {confidence_pct}%
──────────────────
เหตุผล: {reasoning}"""
        else:
            # BUY or SELL
            message = f"""📊 Tra(i)der Signal
──────────────────
{action_emoji} {action} | {condition} {condition_name}
Entry: {entry_str}  | Confidence: {confidence_pct}%
TP1: {tp1_str}  TP2: {tp2_str}  TP3: {tp3_str}
SL: {sl_str}   | Lot: {lot_str}
──────────────────
เหตุผล: {reasoning}"""

            # Add optional fields
            if trend_h1:
                message += f"\nH1: {trend_h1}"
            if session:
                message += f" | Session: {session}"

        return message

    def send_signal(self, decision: Dict) -> bool:
        """
        Send trading signal via LINE Messaging API

        Args:
            decision: Decision dict from G3

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            print("⚠️  LINE notification disabled (LINE_NOTIFY_ENABLED=false)")
            return False

        if not self.channel_token or not self.user_id:
            print("❌ LINE credentials missing")
            return False

        try:
            message = self._format_signal_message(decision)

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.channel_token}'
            }

            payload = {
                'to': self.user_id,
                'messages': [
                    {
                        'type': 'text',
                        'text': message
                    }
                ]
            }

            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)

            if response.status_code == 200:
                print(f"✓ LINE notification sent: {decision.get('action')} {decision.get('condition')}")
                return True
            else:
                print(f"❌ LINE API error: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"❌ LINE notification failed: {e}")
            return False

    def send_custom_message(self, message: str) -> bool:
        """
        Send custom message via LINE

        Args:
            message: Custom message text

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.channel_token}'
            }

            payload = {
                'to': self.user_id,
                'messages': [
                    {
                        'type': 'text',
                        'text': message
                    }
                ]
            }

            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            return response.status_code == 200

        except Exception as e:
            print(f"❌ Failed to send custom message: {e}")
            return False


def notify_signal(decision: Dict) -> bool:
    """
    Helper function to send trading signal notification

    Args:
        decision: Decision dict from G3

    Returns:
        True if notification sent successfully
    """
    notifier = LINENotifier()
    return notifier.send_signal(decision)


# Example usage and testing
if __name__ == "__main__":
    print("="*70)
    print("G4a LINE NOTIFICATION TEST")
    print("="*70)

    # Test BUY signal
    test_buy_decision = {
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

    # Test SELL signal
    test_sell_decision = {
        'action': 'SELL',
        'condition': 'A2',
        'condition_name': 'แนวต้าน + Overbought',
        'entry': 3055.5,
        'tp1': 3045.0,
        'tp2': 3038.0,
        'tp3': 3030.0,
        'sl': 3062.0,
        'lot_size': 0.45,
        'confidence': 0.76,
        'reasoning': 'RSI 82 + ทดสอบ resistance 3x',
        'trend_h1': 'Bearish',
        'session': 'NY'
    }

    # Test SKIP signal
    test_skip_decision = {
        'action': 'SKIP',
        'condition': 'A1',
        'condition_name': 'Break S/R',
        'confidence': 0.65,
        'reasoning': 'Confidence ต่ำกว่า 70%'
    }

    notifier = LINENotifier()

    print(f"\n📱 LINE Configuration:")
    print(f"   Enabled: {notifier.enabled}")
    print(f"   Channel Token: {'✓' if notifier.channel_token else '✗'}")
    print(f"   User ID: {'✓' if notifier.user_id else '✗'}")

    print(f"\n📝 Test Message Formatting:\n")

    # Format messages without sending
    print("─" * 70)
    print("BUY Signal Example:")
    print("─" * 70)
    print(notifier._format_signal_message(test_buy_decision))

    print("\n" + "─" * 70)
    print("SELL Signal Example:")
    print("─" * 70)
    print(notifier._format_signal_message(test_sell_decision))

    print("\n" + "─" * 70)
    print("SKIP Signal Example:")
    print("─" * 70)
    print(notifier._format_signal_message(test_skip_decision))

    print("\n" + "="*70)

    # Uncomment to actually send test message (requires valid credentials)
    # if notifier.enabled:
    #     print("\n📤 Sending test notification...")
    #     success = notifier.send_signal(test_buy_decision)
    #     if success:
    #         print("✓ Test notification sent successfully!")
    #     else:
    #         print("✗ Failed to send test notification")
