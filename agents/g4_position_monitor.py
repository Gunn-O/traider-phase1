"""
G4c — Position Monitor

หน้าที่:
- ตรวจทุก candle close ว่า hit SL/TP หรือไม่
- Update Sheets: PENDING → WIN/LOSS + close_price, pnl, timestamp
- คำนวณและ update Trailing SL ถ้า TP > 3000 pip
- Fix Trade ID duplicate (ใช้ microsecond)
- เพิ่ม logging ทุก action

Reference: TRAIDER_MASTER_PLAN_v2.1.md Section 7
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
import uuid

from config import RISK_CONFIG

# Setup logging
logger = logging.getLogger(__name__)


def check_positions_on_candle_close(candle: dict, open_orders: List[dict]) -> List[dict]:
    """
    เรียกทุก candle close (M5 หรือ TF ที่ใช้)
    ตรวจแต่ละ order ว่า hit SL หรือ TP ไหม

    กฎ: ถ้า High/Low ของแท่งครอบทั้ง SL และ TP
    → ดู Open ก่อน: ถ้า BUY และ Low ≤ SL ก่อน Open → SL hit
    → ในทางปฏิบัติ simulate: ถ้า gap ไม่ชัด → ถือว่า SL hit ก่อน (conservative)

    Args:
        candle: {
            'timestamp': datetime,
            'open': float,
            'high': float,
            'low': float,
            'close': float
        }
        open_orders: list of order dicts with 'result': 'PENDING'

    Returns:
        list of update dicts:
        [
            {
                'trade_id': str,
                'type': 'close' | 'trailing_sl_update',
                'result': 'WIN' | 'LOSS',  # ถ้า type='close'
                'close_price': float,
                'close_reason': 'SL_HIT' | 'TP_HIT',
                'pnl_usd': float,
                'timestamp_close': str,
                'new_sl': float  # ถ้า type='trailing_sl_update'
            }
        ]
    """
    updates = []

    for order in open_orders:
        if order.get('result') != 'PENDING':
            continue

        action = order['action']
        entry = order['entry_price']
        sl = order.get('sl_price', order.get('sl'))  # รองรับทั้ง sl_price และ sl
        tp = order.get('tp_price', order.get('tp'))
        lot = order.get('lot_size', order.get('lot', 0.01))
        trade_id = order['trade_id']

        # Check SL/TP hit
        sl_hit = False
        tp_hit = False

        if action == 'BUY':
            sl_hit = candle['low'] <= sl
            tp_hit = candle['high'] >= tp
        elif action == 'SELL':
            sl_hit = candle['high'] >= sl
            tp_hit = candle['low'] <= tp
        else:
            logger.warning(f"Unknown action '{action}' for trade {trade_id}")
            continue

        # ถ้า hit ทั้ง SL และ TP ในแท่งเดียว → conservative = SL hit ก่อน
        if sl_hit and tp_hit:
            logger.info(f"[{trade_id}] Both SL and TP hit in same candle → Conservative: SL hit")
            result = 'LOSS'
            close_price = sl
            close_reason = 'SL_HIT'
        elif sl_hit:
            result = 'LOSS'
            close_price = sl
            close_reason = 'SL_HIT'
            logger.info(f"[{trade_id}] SL hit at {close_price}")
        elif tp_hit:
            result = 'WIN'
            close_price = tp
            close_reason = 'TP_HIT'
            logger.info(f"[{trade_id}] TP hit at {close_price}")
        else:
            # ไม่ hit อะไร → ตรวจ Trailing SL
            trailing_update = check_trailing_sl(order, candle)
            if trailing_update:
                updates.append({
                    'trade_id': trade_id,
                    'type': 'trailing_sl_update',
                    'new_sl': trailing_update
                })
                logger.info(f"[{trade_id}] Trailing SL updated to {trailing_update}")
            continue

        # คำนวณ P&L
        pnl = calc_pnl(action, entry, close_price, lot)

        updates.append({
            'trade_id': trade_id,
            'type': 'close',
            'result': result,
            'close_price': close_price,
            'close_reason': close_reason,
            'pnl_usd': pnl,
            'timestamp_close': candle['timestamp'].isoformat() if isinstance(candle['timestamp'], datetime) else candle['timestamp']
        })

        logger.info(f"[{trade_id}] Closed: {result} | P&L: ${pnl:.2f} | Reason: {close_reason}")

    return updates


def check_trailing_sl(order: dict, candle: dict) -> Optional[float]:
    """
    ตรวจและคำนวณ Trailing SL ใหม่

    Branches:
    - Mountain (order has 'trail_meta'): 3-stage v67 trailing (TP1/TP2/TP2+20%H)
    - Other patterns (MAI_RUAY, etc.): no trailing (returns None)

    Args:
        order: Order dict
        candle: Current candle with high/low/close

    Returns:
        new_sl (float) ถ้าต้อง update, None ถ้าไม่ต้อง
    """
    trail_meta = order.get('trail_meta')
    if trail_meta:
        return _check_mountain_trailing(order, candle, trail_meta)
    return None  # Per spec: only Mountain has trailing


def _check_mountain_trailing(order: dict, candle: dict, trail_meta: dict) -> Optional[float]:
    """
    Mountain v67 3-stage trailing — BUY only.

    Stages:
        0 → 1: high ≥ TP1       → SL = tech + 5%H
        1 → 2: high ≥ TP2_base  → SL = TP1
        2 → 3: high ≥ TP2+20%H  → SL = TP2

    Mutates trail_meta['stage'] in-place when stage transition fires.
    Returns new SL (rounded) or None if no transition.
    """
    if order.get('action') != 'BUY':
        return None  # Mountain is BUY only

    high = candle.get('high', candle.get('close', 0))
    if high <= 0:
        return None

    stage = int(trail_meta.get('stage', 0))
    tp1   = float(trail_meta.get('tp1') or 0)
    tp2   = float(trail_meta.get('tp2_base') or trail_meta.get('tp2') or 0)
    tech  = float(trail_meta.get('tech_point') or trail_meta.get('base_lo') or 0)
    h_usd = float(trail_meta.get('height') or 0) / 100.0  # pip → USD

    new_sl = None
    new_stage = stage

    if stage == 0 and tp1 > 0 and high >= tp1:
        new_sl = tech + h_usd * 0.05    # tech + 5%H
        new_stage = 1
    elif stage == 1 and tp2 > 0 and high >= tp2:
        new_sl = tp1                     # SL = TP1
        new_stage = 2
    elif stage == 2 and tp2 > 0:
        tp2_plus20 = tp2 + h_usd * 0.20  # TP2 + 20%H
        if high >= tp2_plus20:
            new_sl = tp2                 # SL = TP2
            new_stage = 3

    if new_sl is None:
        return None

    # Only move SL UP for BUY (never tighten worse)
    current_sl = order.get('trailing_sl', order.get('sl_price', order.get('sl')))
    if new_sl <= current_sl:
        return None

    trail_meta['stage'] = new_stage  # advance state
    return round(new_sl, 2)


def calc_pnl(action: str, entry: float, close: float, lot: float) -> float:
    """
    คำนวณ P&L
    P&L = (close - entry) × lot × 100 สำหรับ BUY
    P&L = (entry - close) × lot × 100 สำหรับ SELL

    Args:
        action: 'BUY' | 'SELL'
        entry: Entry price
        close: Close price
        lot: Lot size

    Returns:
        P&L (USD)
    """
    if action == 'BUY':
        pnl = (close - entry) * lot * 100
    elif action == 'SELL':
        pnl = (entry - close) * lot * 100
    else:
        logger.error(f"Unknown action '{action}' in calc_pnl")
        return 0.0

    return round(pnl, 2)


# ID prefix per mode (user spec):
#   PT- = Paper Trade (backtest)
#   SM- = Simulation Trade (live data, no real orders)
#   RT- = Real Trade (live order to broker)
_MODE_PREFIX = {
    'backtest': 'PT',
    'simulate': 'SM',
    'live':     'RT',
}


def generate_trade_id(plan_id: str, order_num: int, candle_time=None, mode='simulate') -> str:
    """
    สร้าง unique trade_id
    Format: {prefix}-YYYYMMDD-HHMMSS-uuuuuu-N
    prefix: PT (backtest) | SM (simulate) | RT (live)
    uuuuuu = microsecond เพื่อป้องกัน duplicate

    Args:
        plan_id: e.g. PT-PLAN-...  / SM-PLAN-...  / RT-PLAN-...
        order_num: 1, 2, 3
        candle_time: Optional datetime, defaults to now
        mode: 'backtest' | 'simulate' | 'live'

    Returns:
        trade_id (str)
    """
    dt = candle_time if candle_time else datetime.now()
    timestamp = dt.strftime('%Y%m%d-%H%M%S')
    microsec = str(dt.microsecond).zfill(6)[:6]
    prefix = _MODE_PREFIX.get(mode, 'SM')
    return f"{prefix}-{timestamp}-{microsec}-{order_num}"


def generate_plan_id(candle_time=None, mode='simulate') -> str:
    """
    สร้าง unique plan_id
    Format: {prefix}-PLAN-YYYYMMDD-HHMMSS-uuuuuu
    prefix: PT (backtest) | SM (simulate) | RT (live)

    Args:
        candle_time: Optional datetime, defaults to now
        mode: 'backtest' | 'simulate' | 'live'

    Returns:
        plan_id (str)
    """
    dt = candle_time if candle_time else datetime.now()
    timestamp = dt.strftime('%Y%m%d-%H%M%S')
    microsec = str(dt.microsecond).zfill(6)[:6]
    prefix = _MODE_PREFIX.get(mode, 'SM')
    return f"{prefix}-PLAN-{timestamp}-{microsec}"


class PositionMonitor:
    """
    Position Monitor Class
    ใช้ track open positions และ update เมื่อ hit SL/TP
    """

    def __init__(self, sheets_logger=None):
        """
        Args:
            sheets_logger: G4 SheetsLogger instance (optional)
        """
        self.sheets_logger = sheets_logger
        self.open_orders = []
        logger.info("PositionMonitor initialized")

    def add_orders(self, orders: List[dict]):
        """เพิ่ม orders เข้า tracking list"""
        self.open_orders.extend(orders)
        logger.info(f"Added {len(orders)} orders to monitor (total: {len(self.open_orders)})")

    def check_and_update(self, candle: dict):
        """
        ตรวจและ update positions ตาม candle ปัจจุบัน

        Args:
            candle: Current candle dict

        Returns:
            List of closed trades (with updated result, pnl, etc.)
        """
        if not self.open_orders:
            return []

        pending_orders = [o for o in self.open_orders if o.get('result') == 'PENDING']
        if not pending_orders:
            return []

        logger.info(f"Checking {len(pending_orders)} pending orders...")

        updates = check_positions_on_candle_close(candle, pending_orders)

        if not updates:
            return []

        # Track closed plan IDs and closed trades to return
        closed_plan_ids = set()
        closed_trades = []

        # Apply updates
        for update in updates:
            trade_id = update['trade_id']

            if update['type'] == 'close':
                # Update order in memory
                for order in self.open_orders:
                    if order['trade_id'] == trade_id:
                        order['result'] = update['result']
                        order['close_price'] = update['close_price']
                        order['close_reason'] = update['close_reason']
                        order['pnl_usd'] = update['pnl_usd']
                        order['timestamp_close'] = update['timestamp_close']
                        # Track plan_id for portfolio update
                        if 'plan_id' in order:
                            closed_plan_ids.add(order['plan_id'])
                        # Add to closed trades list (for return value)
                        closed_trades.append(order.copy())
                        break

                # Update Sheets
                if self.sheets_logger:
                    try:
                        self.sheets_logger.update_order_close(
                            trade_id=trade_id,
                            result=update['result'],
                            close_price=update['close_price'],
                            close_reason=update['close_reason'],
                            pnl_usd=update['pnl_usd'],
                            timestamp_close=update['timestamp_close']
                        )
                        logger.info(f"[{trade_id}] Sheets updated: {update['result']}")
                    except Exception as e:
                        logger.error(f"[{trade_id}] Failed to update Sheets: {e}")

            elif update['type'] == 'trailing_sl_update':
                # Update trailing SL in memory
                for order in self.open_orders:
                    if order['trade_id'] == trade_id:
                        order['trailing_sl'] = update['new_sl']
                        order['sl_price'] = update['new_sl']  # อัพเดท SL เป็นค่าใหม่
                        break

                # Update Sheets
                if self.sheets_logger:
                    try:
                        self.sheets_logger.update_trailing_sl(trade_id, update['new_sl'])
                        logger.info(f"[{trade_id}] Trailing SL updated to {update['new_sl']}")
                    except Exception as e:
                        logger.error(f"[{trade_id}] Failed to update trailing SL: {e}")

        # Check if any plans are fully closed and update portfolio state
        if closed_plan_ids and self.sheets_logger:
            self._update_portfolio_after_closes(closed_plan_ids)

        # Return list of closed trades for caller to process
        return closed_trades

    def get_open_orders(self) -> List[dict]:
        """Return list of orders ที่ยังเปิดอยู่"""
        return [o for o in self.open_orders if o.get('result') == 'PENDING']

    def get_closed_orders(self) -> List[dict]:
        """Return list of orders ที่ปิดแล้ว"""
        return [o for o in self.open_orders if o.get('result') in ['WIN', 'LOSS']]

    def clear_closed_orders(self):
        """ลบ orders ที่ปิดแล้วออกจาก memory (รวม CANCELLED)"""
        before = len(self.open_orders)
        self.open_orders = [o for o in self.open_orders if o.get('result') == 'PENDING']
        cleared = before - len(self.open_orders)
        if cleared > 0:
            logger.info(f"Cleared {cleared} closed orders from memory")

    def _update_portfolio_after_closes(self, closed_plan_ids: set):
        """
        Update portfolio state หลังปิด orders
        - Clear active_plan_id ถ้าทุก order ใน plan ปิดแล้ว
        - Update consecutive_loss counter
        - Update realized_pnl_usd
        """
        for plan_id in closed_plan_ids:
            # Get all orders for this plan
            plan_orders = [o for o in self.open_orders if o.get('plan_id') == plan_id]

            # Check if all orders in plan are closed
            all_closed = all(o.get('result') in ['WIN', 'LOSS'] for o in plan_orders)

            if all_closed:
                # Calculate plan result
                plan_pnl = sum(o.get('pnl_usd', 0) for o in plan_orders)
                plan_result = 'WIN' if plan_pnl > 0 else 'LOSS'

                logger.info(f"[{plan_id}] Plan fully closed: {plan_result} (P&L: ${plan_pnl:.2f})")

                # Get current portfolio state
                try:
                    portfolio_state = self.sheets_logger.get_portfolio_state()

                    # Clear active plan (and multi-plan fields)
                    if portfolio_state.get('active_plan_id') == plan_id:
                        portfolio_state['active_plan_id'] = ''
                        portfolio_state['open_plans_count'] = 0
                        portfolio_state['total_risk_pct'] = 0.0
                        portfolio_state['open_orders_count'] = 0
                        portfolio_state['total_open_lot'] = 0.0
                        logger.info(f"[{plan_id}] Cleared active plan from portfolio state")

                    # Update consecutive loss
                    if plan_result == 'LOSS':
                        portfolio_state['consecutive_loss'] = portfolio_state.get('consecutive_loss', 0) + 1
                    else:
                        portfolio_state['consecutive_loss'] = 0  # Reset on WIN

                    # Update realized P&L
                    portfolio_state['realized_pnl_usd'] = portfolio_state.get('realized_pnl_usd', 0) + plan_pnl

                    # Update portfolio state in sheets
                    self.sheets_logger.update_portfolio_state(portfolio_state)
                    logger.info(f"[{plan_id}] Portfolio state updated (consecutive_loss={portfolio_state['consecutive_loss']})")

                except Exception as e:
                    logger.error(f"[{plan_id}] Failed to update portfolio state: {e}")
