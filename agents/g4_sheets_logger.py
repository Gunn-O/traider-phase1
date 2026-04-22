"""
G4b — Google Sheets Logger (v2.1)

หน้าที่:
- Log trades ลง Google Sheets (Plan-based Schema)
- Sheet 1: Trade Log (23 columns)
- Sheet 2: Portfolio State (10 fields)

Reference: TRAIDER_MASTER_PLAN_v2.1.md Section 6
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

from config import TRADE_LOG_COLUMNS, PORTFOLIO_STATE_FIELDS

load_dotenv()
logger = logging.getLogger(__name__)

# Import gspread
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logger.warning("gspread not installed - Google Sheets logging unavailable")


class SheetsLogger:
    """
    Google Sheets Logger for Plan-based Trading

    Usage:
        logger = SheetsLogger()
        logger.log_plan_open(plan_id, orders, decision, world_state, llm_log)
        logger.update_order_close(trade_id, result, close_price, ...)
    """

    def __init__(self, enabled_override=None):
        """
        Initialize Sheets Logger

        Args:
            enabled_override: Optional bool to override SHEETS_ENABLED env var
                              (useful for backtest --log-sheets flag)
        """
        if enabled_override is not None:
            self.enabled = enabled_override
        else:
            self.enabled = os.getenv('SHEETS_ENABLED', 'false').lower() == 'true'

        self.sheets_id = os.getenv('GOOGLE_SHEETS_ID', '')
        self.credentials_path = os.getenv('GOOGLE_CREDENTIALS_JSON', './credentials.json')

        self.client = None
        self.sheet = None
        self.trade_log_ws = None
        self.portfolio_ws = None

        if self.enabled:
            if not GSPREAD_AVAILABLE:
                raise RuntimeError("SHEETS_ENABLED=true but gspread not installed")

            if not self.sheets_id:
                raise ValueError("GOOGLE_SHEETS_ID required")

            if not os.path.exists(self.credentials_path):
                raise FileNotFoundError(f"Credentials not found: {self.credentials_path}")

            self._connect()
        else:
            logger.info("Google Sheets logging disabled (SHEETS_ENABLED=false)")

    def _connect(self):
        """Connect to Google Sheets and initialize worksheets"""
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]

            creds = Credentials.from_service_account_file(
                self.credentials_path, scopes=scopes
            )

            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_key(self.sheets_id)

            # Initialize Trade Log worksheet
            self.trade_log_ws = self._get_or_create_worksheet(
                "Trade Log", TRADE_LOG_COLUMNS
            )

            # Initialize Portfolio State worksheet
            self.portfolio_ws = self._get_or_create_worksheet(
                "Portfolio State", PORTFOLIO_STATE_FIELDS, rows=20
            )

            logger.info("✓ Connected to Google Sheets")

        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            raise

    def _get_or_create_worksheet(self, title: str, headers: List[str],
                                   rows: int = 1000) -> gspread.Worksheet:
        """Get existing worksheet or create new one with headers"""
        try:
            ws = self.sheet.worksheet(title)
            logger.info(f"✓ Found existing worksheet: {title}")
            return ws
        except gspread.exceptions.WorksheetNotFound:
            ws = self.sheet.add_worksheet(
                title=title,
                rows=rows,
                cols=len(headers)
            )
            ws.append_row(headers)
            logger.info(f"✓ Created worksheet: {title}")
            return ws

    # ========================================================================
    # TRADE LOG METHODS
    # ========================================================================

    def log_plan_open(self, plan_id: str, orders: List[Dict],
                      decision: Dict, world_state: Dict,
                      llm_log: Dict, candle_time=None) -> bool:
        """
        Log แผนใหม่ (ทุก order ในแผน)

        Args:
            plan_id: PLAN-YYYYMMDD-NNN
            orders: list of order dicts (1-3 orders)
            decision: Claude decision dict
            world_state: G1 output
            llm_log: LLM usage log
            candle_time: Optional datetime for backtest

        Returns:
            True if success
        """
        if not self.enabled:
            return False

        try:
            rows = []
            for order in orders:
                row = self._build_trade_row(
                    plan_id, order, decision, world_state, llm_log, candle_time
                )
                rows.append(row)

            # Append all rows at once
            self.trade_log_ws.append_rows(rows)
            logger.info(f"✓ Logged plan {plan_id} ({len(orders)} orders)")
            return True

        except Exception as e:
            logger.error(f"Failed to log plan: {e}")
            return False

    def _build_trade_row(self, plan_id: str, order: Dict,
                         decision: Dict, world_state: Dict,
                         llm_log: Dict, candle_time=None) -> List:
        """Build single trade row according to TRADE_LOG_COLUMNS"""
        timestamp_open = (candle_time if candle_time else datetime.now()).isoformat()

        return [
            order['trade_id'],                                  # A: trade_id
            plan_id,                                            # B: plan_id
            order['order_num'],                                 # C: order_num
            timestamp_open,                                     # D: timestamp_open
            world_state.get('selected_tf', 'M5'),              # E: timeframe
            world_state.get('chart_type', 'unclear'),          # F: chart_type
            decision.get('technique', world_state.get('technique_candidate', 'skip')),  # G: technique
            order['action'],                                    # H: action
            order['entry'],                                     # I: entry_price
            order['sl'],                                        # J: sl_price
            order['tp'],                                        # K: tp_price
            order['lot'],                                       # L: lot_size
            order.get('lot_total', order['lot']),              # M: lot_total_plan
            decision.get('rr_ratio', 0),                       # N: rr_ratio
            decision.get('confidence', 0),                     # O: confidence
            world_state.get('metadata', {}).get('rsi_14', 50), # P: rsi_14
            world_state.get('session', 'Unknown'),             # Q: session
            decision.get('reason', ''),                        # R: ai_reason
            llm_log.get('total_tokens', 0),                    # S: llm_tokens
            llm_log.get('cost_usd', 0),                        # T: llm_cost_usd
            'PENDING',                                          # U: result
            0,                                                  # V: pnl_usd
            '',                                                 # W: close_reason
            0,                                                  # X: close_price
            '',                                                 # Y: timestamp_close
            order['sl'],                                        # Z: trailing_sl (initial = SL)
            '',                                                 # AA: human_action
            ''                                                  # AB: human_agree
        ]

    def update_order_close(self, trade_id: str, result: str,
                           close_price: float, close_reason: str,
                           pnl_usd: float, timestamp_close: str) -> bool:
        """
        Update order เมื่อปิด (PENDING → WIN/LOSS)

        Args:
            trade_id: TRD-YYYYMMDD-NNN
            result: 'WIN' | 'LOSS'
            close_price: ราคาปิด
            close_reason: 'TP_HIT' | 'SL_HIT' | 'MANUAL'
            pnl_usd: P&L (USD)
            timestamp_close: ISO timestamp

        Returns:
            True if success
        """
        if not self.enabled:
            return False

        try:
            # Find row by trade_id
            cell = self.trade_log_ws.find(trade_id)
            if not cell:
                logger.warning(f"Trade ID not found: {trade_id}")
                return False

            row_num = cell.row

            # Update columns U, V, W, X, Y
            updates = [
                {'range': f'U{row_num}', 'values': [[result]]},
                {'range': f'V{row_num}', 'values': [[pnl_usd]]},
                {'range': f'W{row_num}', 'values': [[close_reason]]},
                {'range': f'X{row_num}', 'values': [[close_price]]},
                {'range': f'Y{row_num}', 'values': [[timestamp_close]]}
            ]

            self.trade_log_ws.batch_update(updates)
            logger.info(f"✓ Updated {trade_id}: {result}")
            return True

        except Exception as e:
            logger.error(f"Failed to update order close: {e}")
            return False

    def update_trailing_sl(self, trade_id: str, new_sl: float) -> bool:
        """Update Trailing SL (column Z)"""
        if not self.enabled:
            return False

        try:
            cell = self.trade_log_ws.find(trade_id)
            if not cell:
                return False

            self.trade_log_ws.update_cell(cell.row, 26, new_sl)  # Col Z = 26
            logger.info(f"✓ Updated trailing SL for {trade_id}: {new_sl}")
            return True

        except Exception as e:
            logger.error(f"Failed to update trailing SL: {e}")
            return False

    def update_human_action(self, trade_id: str, human_action: str) -> bool:
        """Update human action (columns AA, AB)"""
        if not self.enabled:
            return False

        try:
            cell = self.trade_log_ws.find(trade_id)
            if not cell:
                return False

            row_num = cell.row
            # Get AI action from column H
            ai_action = self.trade_log_ws.cell(row_num, 8).value
            agree = 'TRUE' if ai_action == human_action else 'FALSE'

            updates = [
                {'range': f'AA{row_num}', 'values': [[human_action]]},
                {'range': f'AB{row_num}', 'values': [[agree]]}
            ]

            self.trade_log_ws.batch_update(updates)
            logger.info(f"✓ Updated human action for {trade_id}: {human_action}")
            return True

        except Exception as e:
            logger.error(f"Failed to update human action: {e}")
            return False

    # ========================================================================
    # PORTFOLIO STATE METHODS
    # ========================================================================

    def update_portfolio_state(self, portfolio_state: Dict) -> bool:
        """
        Update Portfolio State sheet (Sheet 2)

        Args:
            portfolio_state: {
                'active_plan_id': str,
                'open_plans_count': int,
                'total_risk_pct': float,
                'open_orders_count': int,
                'total_open_lot': float,
                'realized_pnl_usd': float,
                'unrealized_pnl_usd': float,
                'consecutive_loss': int,
                'total_loss_pct': float,
                'trading_blocked': bool,
                'block_reason': str,
                'last_updated': str,
                'last_technical_price': float,
                'last_plan_chart_type': str
            }

        Returns:
            True if success
        """
        if not self.enabled:
            return False

        try:
            # Update row 2 (row 1 = headers) - 14 fields total
            values = [[
                portfolio_state.get('active_plan_id', ''),                    # A
                portfolio_state.get('open_plans_count', 0),                   # B
                portfolio_state.get('total_risk_pct', 0.0),                   # C
                portfolio_state.get('open_orders_count', 0),                  # D
                portfolio_state.get('total_open_lot', 0.0),                   # E
                portfolio_state.get('realized_pnl_usd', 0.0),                 # F
                portfolio_state.get('unrealized_pnl_usd', 0.0),               # G
                portfolio_state.get('consecutive_loss', 0),                   # H
                portfolio_state.get('total_loss_pct', 0.0),                   # I
                portfolio_state.get('trading_blocked', False),                # J
                portfolio_state.get('block_reason', ''),                      # K
                datetime.now().isoformat(),                                   # L (last_updated)
                portfolio_state.get('last_technical_price', 0.0),             # M
                portfolio_state.get('last_plan_chart_type', '')               # N
            ]]

            self.portfolio_ws.update('A2:N2', values)
            logger.info("✓ Updated Portfolio State (14 fields)")
            return True

        except Exception as e:
            logger.error(f"Failed to update portfolio state: {e}")
            return False

    def get_portfolio_state(self) -> Dict:
        """
        Read Portfolio State from sheet (14 fields)

        Returns:
            portfolio_state dict
        """
        if not self.enabled:
            return self._default_portfolio_state()

        try:
            values = self.portfolio_ws.row_values(2)  # Row 2 = data
            if len(values) < 14:
                logger.warning(f"Portfolio state has {len(values)} columns, expected 14 - using defaults for missing")
                # Pad with empty values if schema not fully migrated
                values = values + [''] * (14 - len(values))

            return {
                'active_plan_id': values[0] if values[0] else 'ไม่มีแผนที่เปิดอยู่',        # A
                'open_plans_count': int(values[1]) if values[1] else 0,                      # B
                'total_risk_pct': float(values[2]) if values[2] else 0.0,                    # C
                'open_orders_count': int(values[3]) if values[3] else 0,                     # D
                'total_open_lot': float(values[4]) if values[4] else 0.0,                    # E
                'realized_pnl_usd': float(values[5]) if values[5] else 0.0,                  # F
                'unrealized_pnl_usd': float(values[6]) if values[6] else 0.0,                # G
                'consecutive_loss': int(values[7]) if values[7] else 0,                      # H
                'total_loss_pct': float(values[8]) if values[8] else 0.0,                    # I
                'trading_blocked': str(values[9]).upper() == 'TRUE' if values[9] else False, # J
                'block_reason': values[10] if values[10] else '',                            # K
                'last_updated': values[11] if values[11] else '',                            # L
                'last_technical_price': float(values[12]) if values[12] else 0.0,            # M
                'last_plan_chart_type': values[13] if values[13] else ''                     # N
            }

        except Exception as e:
            logger.error(f"Failed to read portfolio state: {e}")
            return self._default_portfolio_state()

    def _default_portfolio_state(self) -> Dict:
        """Return default portfolio state (14 fields)"""
        return {
            'active_plan_id': 'ไม่มีแผนที่เปิดอยู่',
            'open_plans_count': 0,
            'total_risk_pct': 0.0,
            'open_orders_count': 0,
            'total_open_lot': 0.0,
            'realized_pnl_usd': 0.0,
            'unrealized_pnl_usd': 0.0,
            'consecutive_loss': 0,
            'total_loss_pct': 0.0,
            'trading_blocked': False,
            'block_reason': '',
            'last_updated': '',
            'last_technical_price': 0.0,
            'last_plan_chart_type': ''
        }

    def get_pending_trades(self) -> List[Dict]:
        """
        ดึง trades ที่ result = PENDING จาก Trade Log
        สำหรับ load positions เข้า position_monitor ตอน backtest startup

        Returns:
            List of pending order dicts with required fields
        """
        if not self.enabled:
            return []

        try:
            all_rows = self.trade_log_ws.get_all_records()
            pending = [r for r in all_rows if r.get('result') == 'PENDING']

            logger.info(f"Found {len(pending)} PENDING trades in Sheets")

            # Convert to order format for position_monitor
            orders = []
            for row in pending:
                order = {
                    'trade_id': row.get('trade_id', ''),
                    'plan_id': row.get('plan_id', ''),
                    'order_num': row.get('order_num', 1),
                    'action': row.get('action', ''),
                    'entry': float(row.get('entry_price', 0)),
                    'entry_price': float(row.get('entry_price', 0)),
                    'sl': float(row.get('sl_price', 0)),
                    'sl_price': float(row.get('sl_price', 0)),
                    'tp': float(row.get('tp_price', 0)),
                    'tp_price': float(row.get('tp_price', 0)),
                    'lot': float(row.get('lot_size', 0.01)),
                    'lot_size': float(row.get('lot_size', 0.01)),
                    'result': 'PENDING',
                    'trailing_sl': float(row.get('trailing_sl', row.get('sl_price', 0)))
                }
                orders.append(order)
                logger.info(f"  Loaded: {order['trade_id']} | {order['action']} @ {order['entry']}")

            return orders

        except Exception as e:
            logger.error(f"Failed to load pending trades: {e}")
            return []

    def get_recent_trades(self, limit: int = 30) -> List[Dict]:
        """
        Get recent trade history from Google Sheets

        Args:
            limit: Number of trades to return (default: 30)

        Returns:
            List of trade dicts (newest first)
        """
        if not self.enabled:
            return []

        try:
            # Get all records from Trade Log
            records = self.trade_log_ws.get_all_records()

            # Reverse to get newest first
            records.reverse()

            # Return limited number
            return records[:limit]

        except Exception as e:
            logger.error(f"Failed to get recent trades: {e}")
            return []

    def clear_sheets(self, confirm: bool = False):
        """
        Clear all trades and reset portfolio state

        Args:
            confirm: Must be True to actually clear (safety)

        Returns:
            Dict with status
        """
        if not self.enabled:
            return {'success': False, 'message': 'Sheets logging disabled'}

        if not confirm:
            return {
                'success': False,
                'message': 'Must set confirm=True to clear sheets'
            }

        try:
            # Count current trades
            all_rows = self.trade_log_ws.get_all_values()
            trade_count = len(all_rows) - 1  # Exclude header

            logger.info(f"Clearing {trade_count} trades from Trade Log...")

            # Delete all rows except header
            if trade_count > 0:
                self.trade_log_ws.delete_rows(2, len(all_rows))
                logger.info(f"✓ Deleted {trade_count} trades")

            # Reset portfolio state
            initial_state = [
                'ไม่มีแผนที่เปิดอยู่',  # active_plan_id
                '0',                      # open_plans_count
                '0.00',                   # total_risk_pct
                '0',                      # open_orders_count
                '0.00',                   # total_open_lot
                '0.00',                   # realized_pnl_usd
                '0.00',                   # unrealized_pnl_usd
                '0',                      # consecutive_loss
                '0.00',                   # total_loss_pct
                'FALSE',                  # trading_blocked
                '',                       # block_reason
                '',                       # last_updated
                '0.00',                   # last_technical_price
                ''                        # last_plan_chart_type
            ]

            self.portfolio_ws.update('A2:N2', [initial_state])
            logger.info("✓ Portfolio state reset")

            return {
                'success': True,
                'message': f'Cleared {trade_count} trades and reset portfolio',
                'trades_cleared': trade_count
            }

        except Exception as e:
            logger.error(f"Failed to clear sheets: {e}")
            return {
                'success': False,
                'message': f'Error: {e}'
            }


# Alias for backward compatibility
G4SheetsLogger = SheetsLogger
