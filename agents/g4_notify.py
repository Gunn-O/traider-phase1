"""
G4a — LINE Messaging API Agent (v2.1)

หน้าที่:
- ส่งการแจ้งเตือนผ่าน LINE Messaging API (ภาษาไทย)
- แจ้งเมื่อเปิด/ปิด plan
- แจ้งเมื่อถูก Guardian block
- แจ้งสรุปประจำวัน

Reference: TRAIDER_MASTER_PLAN_v2.1.md Section 6
"""

import os
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

from utils.constants import get_chart_type_name_th, get_technique_name_th, get_tf_direction

load_dotenv()
logger = logging.getLogger(__name__)


class LineNotify:
    """
    LINE Notify Agent for Tra(i)der Phase I v2.1

    Usage:
        notifier = LineNotify()
        notifier.send_plan_open(plan_id, orders, decision, world_state)
        notifier.send_plan_close(plan_id, result, pnl_usd)
    """

    def __init__(self):
        """Initialize LINE Messaging API"""
        self.enabled = os.getenv('LINE_NOTIFY_ENABLED', 'false').lower() == 'true'
        self.token = os.getenv('LINE_CHANNEL_TOKEN', '')
        self.user_id = os.getenv('LINE_USER_ID', '')

        if self.enabled:
            if not self.token or not self.user_id:
                raise ValueError("LINE_CHANNEL_TOKEN and LINE_USER_ID required when LINE_NOTIFY_ENABLED=true")
            logger.info("LINE Messaging API enabled")
        else:
            logger.info("LINE Messaging API disabled (LINE_NOTIFY_ENABLED=false)")

    def send_message(self, message: str) -> bool:
        """
        ส่งข้อความผ่าน LINE Messaging API

        Args:
            message: ข้อความที่จะส่ง

        Returns:
            True if success
        """
        if not self.enabled:
            return False

        try:
            url = 'https://api.line.me/v2/bot/message/push'
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.token}'
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

            response = requests.post(url, headers=headers, json=payload, timeout=10)

            if response.status_code == 200:
                logger.info("✓ LINE message sent")
                return True
            else:
                logger.error(f"LINE API failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send LINE message: {e}")
            return False

    # ========================================================================
    # PLAN NOTIFICATIONS
    # ========================================================================

    def send_plan_open(self, plan_id: str, orders: List[Dict],
                       decision: Dict, world_state: Dict) -> bool:
        """
        แจ้งเตือนเมื่อเปิด plan ใหม่

        Args:
            plan_id: PLAN-YYYYMMDD-NNN
            orders: list of order dicts
            decision: Claude decision dict
            world_state: G1 output

        Returns:
            True if success
        """
        if not self.enabled:
            return False

        try:
            # สร้างข้อความ
            chart_type_th = get_chart_type_name_th(world_state.get('chart_type', 'unclear'))
            technique_th = get_technique_name_th(world_state.get('technique_candidate', 'skip'))
            action_th = get_tf_direction(decision['action'])
            tf = world_state.get('selected_tf', 'M5')

            message = f"""
🤖 Tra(i)der — เปิดแผนใหม่

📋 Plan: {plan_id}
📊 Chart: {chart_type_th} ({tf})
🎯 Technique: {technique_th}
💹 Direction: {action_th}

🔢 Orders: {len(orders)}
💰 Entry: ${decision['entry']:.2f}
🛡️ SL: ${decision['sl']:.2f}
🎯 TP: ${decision['tp']:.2f}
📈 R:R: {decision.get('rr_ratio', 0):.2f}
💪 Confidence: {decision.get('confidence', 0):.0%}

📝 Reason: {decision.get('reason', '')[:100]}
"""

            return self.send_message(message.strip())

        except Exception as e:
            logger.error(f"Failed to send plan_open notification: {e}")
            return False

    def send_plan_close(self, plan_id: str, result: str, pnl_usd: float,
                        close_reason: str, orders_count: int) -> bool:
        """
        แจ้งเตือนเมื่อปิด plan

        Args:
            plan_id: PLAN-YYYYMMDD-NNN
            result: 'WIN' | 'LOSS'
            pnl_usd: P&L in USD
            close_reason: 'TP_HIT' | 'SL_HIT' | 'MANUAL'
            orders_count: จำนวน orders ที่ปิด

        Returns:
            True if success
        """
        if not self.enabled:
            return False

        try:
            # กำหนด emoji ตามผล
            if result == 'WIN':
                emoji = '✅'
                result_th = 'ชนะ'
            else:
                emoji = '❌'
                result_th = 'แพ้'

            # กำหนด close reason ภาษาไทย
            reason_map = {
                'TP_HIT': 'ถึง TP',
                'SL_HIT': 'ชน SL',
                'MANUAL': 'ปิดเอง'
            }
            reason_th = reason_map.get(close_reason, close_reason)

            # กำหนดสีตาม P&L
            pnl_display = f"+${pnl_usd:.2f}" if pnl_usd >= 0 else f"-${abs(pnl_usd):.2f}"

            message = f"""
{emoji} Tra(i)der — ปิดแผน ({result_th})

📋 Plan: {plan_id}
🔢 Orders: {orders_count}
💰 P&L: {pnl_display}
🏁 Reason: {reason_th}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

            return self.send_message(message.strip())

        except Exception as e:
            logger.error(f"Failed to send plan_close notification: {e}")
            return False

    # ========================================================================
    # GUARDIAN BLOCK NOTIFICATIONS
    # ========================================================================

    def send_guardian_block(self, block_reason: str, blocked_by: str,
                            portfolio_state: Dict) -> bool:
        """
        แจ้งเตือนเมื่อถูก Guardian block

        Args:
            block_reason: เหตุผลที่ block
            blocked_by: block condition ที่ trigger
            portfolio_state: Portfolio state dict

        Returns:
            True if success
        """
        if not self.enabled:
            return False

        try:
            message = f"""
⚠️ Tra(i)der — BLOCKED

🚫 Reason: {block_reason}
🔍 Blocked by: {blocked_by}

📊 Portfolio State:
  • Consecutive loss: {portfolio_state.get('consecutive_loss', 0)}
  • Total loss: {portfolio_state.get('total_loss_pct', 0):.1%}
  • Open orders: {portfolio_state.get('open_orders_count', 0)}

⚠️ ระบบหยุดเทรดชั่วคราว
"""

            return self.send_message(message.strip())

        except Exception as e:
            logger.error(f"Failed to send guardian_block notification: {e}")
            return False

    # ========================================================================
    # DAILY SUMMARY
    # ========================================================================

    def send_daily_summary(self, summary: Dict) -> bool:
        """
        ส่งสรุปประจำวัน

        Args:
            summary: {
                'date': str,
                'total_plans': int,
                'win_count': int,
                'loss_count': int,
                'win_rate': float,
                'total_pnl_usd': float,
                'best_plan': str,
                'worst_plan': str
            }

        Returns:
            True if success
        """
        if not self.enabled:
            return False

        try:
            win_rate = summary.get('win_rate', 0)
            total_pnl = summary.get('total_pnl_usd', 0)
            pnl_display = f"+${total_pnl:.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):.2f}"

            # กำหนด emoji ตามผล
            if total_pnl > 0:
                emoji = '🎉'
            elif total_pnl == 0:
                emoji = '➖'
            else:
                emoji = '📉'

            message = f"""
{emoji} Tra(i)der — สรุปประจำวัน

📅 Date: {summary.get('date', '')}

📊 Performance:
  • Total plans: {summary.get('total_plans', 0)}
  • Win: {summary.get('win_count', 0)} | Loss: {summary.get('loss_count', 0)}
  • Win rate: {win_rate:.1%}

💰 P&L: {pnl_display}

🏆 Best: {summary.get('best_plan', 'N/A')}
⚠️  Worst: {summary.get('worst_plan', 'N/A')}
"""

            return self.send_message(message.strip())

        except Exception as e:
            logger.error(f"Failed to send daily_summary notification: {e}")
            return False

    # ========================================================================
    # SYSTEM NOTIFICATIONS
    # ========================================================================

    def send_system_start(self, mode: str, balance: float) -> bool:
        """แจ้งเมื่อระบบเริ่มทำงาน"""
        if not self.enabled:
            return False

        message = f"""
🚀 Tra(i)der Phase I v2.1

⚙️  Mode: {mode}
💰 Balance: ${balance:,.2f}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ System started
"""
        return self.send_message(message.strip())

    def send_system_stop(self) -> bool:
        """แจ้งเมื่อระบบหยุดทำงาน"""
        if not self.enabled:
            return False

        message = f"""
🛑 Tra(i)der Phase I v2.1

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⏹️  System stopped
"""
        return self.send_message(message.strip())

    def send_error(self, error_msg: str) -> bool:
        """แจ้งเมื่อเกิด error"""
        if not self.enabled:
            return False

        message = f"""
🚨 Tra(i)der — ERROR

❌ {error_msg[:200]}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message.strip())


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("LINE MESSAGING API TEST")
    print("="*70)

    notifier = LineNotify()

    if not notifier.enabled:
        print("\n⚠️  LINE_NOTIFY_ENABLED=false")
        print("Set LINE_NOTIFY_ENABLED=true in .env to test")
        exit(0)

    print(f"\n📱 LINE Configuration:")
    print(f"   Enabled: {notifier.enabled}")
    print(f"   Channel Token: {'✓' if notifier.token else '✗'}")
    print(f"   User ID: {'✓' if notifier.user_id else '✗'}")

    # Test 1: System start
    print("\n[1] Testing system_start...")
    notifier.send_system_start('winrate_test', 10000.0)

    # Test 2: Plan open
    print("\n[2] Testing plan_open...")
    test_orders = [
        {'trade_id': 'TRD-001', 'action': 'BUY', 'entry': 3050.0, 'sl': 3041.0, 'tp': 3080.0, 'lot': 0.01}
    ]
    test_decision = {
        'action': 'BUY',
        'entry': 3050.0,
        'sl': 3041.0,
        'tp': 3080.0,
        'rr_ratio': 3.33,
        'confidence': 0.82,
        'reason': 'แท่งคู่สวย + เทรนขึ้นชัด H1'
    }
    test_world_state = {
        'selected_tf': 'H1',
        'chart_type': 'uptrend',
        'technique_candidate': 'twin_candle'
    }
    notifier.send_plan_open('PLAN-20260408-001', test_orders, test_decision, test_world_state)

    # Test 3: Guardian block
    print("\n[3] Testing guardian_block...")
    test_portfolio = {
        'consecutive_loss': 3,
        'total_loss_pct': 0.15,
        'open_orders_count': 0
    }
    notifier.send_guardian_block('Consecutive loss ≥ 3', 'consecutive_loss', test_portfolio)

    # Test 4: Plan close (WIN)
    print("\n[4] Testing plan_close (WIN)...")
    notifier.send_plan_close('PLAN-20260408-001', 'WIN', 30.0, 'TP_HIT', 1)

    # Test 5: Daily summary
    print("\n[5] Testing daily_summary...")
    test_summary = {
        'date': '2026-04-08',
        'total_plans': 5,
        'win_count': 3,
        'loss_count': 2,
        'win_rate': 0.60,
        'total_pnl_usd': 45.50,
        'best_plan': 'PLAN-20260408-001 (+30.00)',
        'worst_plan': 'PLAN-20260408-003 (-15.50)'
    }
    notifier.send_daily_summary(test_summary)

    print("\n" + "="*70)
    print("✅ All tests completed! Check LINE app for messages")
    print("="*70)
