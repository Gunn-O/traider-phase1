"""
G4b — Google Sheets Logger

หน้าที่:
- Log ทุก trade decision ลง Google Sheets
- Sheet: "Trade Log"
- Columns: trade_id, timestamp, condition, pattern, action, entry, sl, tp1, lot, confidence, rsi, h1_trend, session, result, pnl, close_reason
"""

import os
from datetime import datetime
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# Import gspread (Google Sheets API)
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    print("Warning: gspread not installed - Google Sheets logging unavailable")


class SheetsLogger:
    """Google Sheets logger for trade decisions"""

    def __init__(self):
        """Initialize Sheets Logger"""
        self.enabled = os.getenv('SHEETS_ENABLED', 'false').lower() == 'true'
        self.sheets_id = os.getenv('GOOGLE_SHEETS_ID', '')
        self.credentials_path = os.getenv('GOOGLE_CREDENTIALS_JSON', './credentials.json')

        self.client = None
        self.sheet = None
        self.worksheet = None

        self.trade_counter = 0  # Counter for trade IDs

        if self.enabled:
            if not GSPREAD_AVAILABLE:
                raise RuntimeError("SHEETS_ENABLED=true but gspread not installed. Run: pip install gspread google-auth")

            if not self.sheets_id:
                raise ValueError("GOOGLE_SHEETS_ID required when SHEETS_ENABLED=true")

            if not os.path.exists(self.credentials_path):
                raise FileNotFoundError(f"Google credentials not found at: {self.credentials_path}")

            self._connect()

    def _connect(self):
        """Connect to Google Sheets"""
        try:
            # Define scopes
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]

            # Load credentials
            creds = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=scopes
            )

            # Create client
            self.client = gspread.authorize(creds)

            # Open spreadsheet
            self.sheet = self.client.open_by_key(self.sheets_id)

            # Get or create "Trade Log" worksheet
            try:
                self.worksheet = self.sheet.worksheet("Trade Log")
                print("✓ Connected to existing 'Trade Log' worksheet")
            except gspread.exceptions.WorksheetNotFound:
                # Create new worksheet with headers
                self.worksheet = self.sheet.add_worksheet(
                    title="Trade Log",
                    rows=1000,
                    cols=16
                )

                # Add headers
                headers = [
                    "trade_id",
                    "timestamp",
                    "condition",
                    "pattern",
                    "action",
                    "entry_price",
                    "sl_price",
                    "tp1_price",
                    "lot_size",
                    "confidence",
                    "rsi",
                    "h1_trend",
                    "session",
                    "result",
                    "pnl_usd",
                    "close_reason"
                ]

                self.worksheet.append_row(headers)
                print("✓ Created new 'Trade Log' worksheet with headers")

        except Exception as e:
            print(f"❌ Failed to connect to Google Sheets: {e}")
            self.enabled = False
            raise

    def _generate_trade_id(self) -> str:
        """
        สร้าง trade ID แบบ TRD-YYYYMMDD-NNN

        Returns:
            Trade ID string
        """
        self.trade_counter += 1
        date_str = datetime.now().strftime('%Y%m%d')
        return f"TRD-{date_str}-{self.trade_counter:03d}"

    def log_trade(self, decision: Dict, world_state: Dict) -> bool:
        """
        Log trade decision ลง Google Sheets

        Args:
            decision: Decision dict from G3
            world_state: World state from G1

        Returns:
            True if logged successfully
        """
        if not self.enabled:
            return False

        try:
            # Generate trade ID
            trade_id = self._generate_trade_id()

            # Extract values
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            condition = decision.get('condition', '')
            pattern = decision.get('pattern', '')
            action = decision.get('action', 'SKIP')
            entry_price = decision.get('entry', 0)
            sl_price = decision.get('sl', 0)
            tp1_price = decision.get('tp1', 0)
            lot_size = decision.get('lot_size', 0)
            confidence = decision.get('confidence', 0)
            rsi = world_state.get('rsi', 0)
            h1_trend = world_state.get('h1_trend', '')
            session = world_state.get('session', '')

            # Result (initially PENDING)
            result = 'PENDING'
            pnl_usd = 0
            close_reason = ''

            # Build row
            row = [
                trade_id,
                timestamp,
                condition,
                pattern,
                action,
                entry_price,
                sl_price,
                tp1_price,
                lot_size,
                confidence,
                rsi,
                h1_trend,
                session,
                result,
                pnl_usd,
                close_reason
            ]

            # Append to sheet
            self.worksheet.append_row(row)

            print(f"✓ Logged to Sheets: {trade_id} | {action} {condition}")
            return True

        except Exception as e:
            print(f"❌ Failed to log to Sheets: {e}")
            return False

    def update_trade_result(self, trade_id: str, result: str, pnl_usd: float, close_reason: str) -> bool:
        """
        Update trade result เมื่อ position ปิด

        Args:
            trade_id: Trade ID to update
            result: 'WIN' | 'LOSS'
            pnl_usd: P&L in USD
            close_reason: 'TP1' | 'TP2' | 'TP3' | 'SL'

        Returns:
            True if updated successfully
        """
        if not self.enabled:
            return False

        try:
            # Find row with matching trade_id
            cell = self.worksheet.find(trade_id)

            if cell:
                row_num = cell.row

                # Update columns N, O, P (result, pnl_usd, close_reason)
                self.worksheet.update_cell(row_num, 14, result)      # Column N
                self.worksheet.update_cell(row_num, 15, pnl_usd)     # Column O
                self.worksheet.update_cell(row_num, 16, close_reason) # Column P

                print(f"✓ Updated Sheets: {trade_id} → {result} ${pnl_usd:,.2f} ({close_reason})")
                return True
            else:
                print(f"⚠️  Trade ID not found: {trade_id}")
                return False

        except Exception as e:
            print(f"❌ Failed to update Sheets: {e}")
            return False


def log_trade_to_sheets(decision: Dict, world_state: Dict) -> bool:
    """
    Helper function to log trade

    Args:
        decision: Decision dict from G3
        world_state: World state from G1

    Returns:
        True if logged successfully
    """
    logger = SheetsLogger()
    return logger.log_trade(decision, world_state)


# Example usage and testing
if __name__ == "__main__":
    print("="*70)
    print("G4b GOOGLE SHEETS LOGGER TEST")
    print("="*70)

    # Check configuration
    enabled = os.getenv('SHEETS_ENABLED', 'false').lower() == 'true'
    sheets_id = os.getenv('GOOGLE_SHEETS_ID', '')
    creds_path = os.getenv('GOOGLE_CREDENTIALS_JSON', './credentials.json')

    print(f"\n📋 Configuration:")
    print(f"   SHEETS_ENABLED: {enabled}")
    print(f"   GOOGLE_SHEETS_ID: {sheets_id if sheets_id else '✗ Not set'}")
    print(f"   Credentials: {'✓ Found' if os.path.exists(creds_path) else '✗ Not found'}")

    if not enabled:
        print(f"\n⚠️  Sheets logging disabled (SHEETS_ENABLED=false)")
        print(f"   Set SHEETS_ENABLED=true in .env to test")
        exit(0)

    if not os.path.exists(creds_path):
        print(f"\n❌ Google credentials not found!")
        print(f"   Expected at: {creds_path}")
        print(f"\n💡 Steps to create credentials:")
        print(f"   1. Go to: https://console.cloud.google.com")
        print(f"   2. Create a Service Account")
        print(f"   3. Download JSON key → save as credentials.json")
        print(f"   4. Share your Google Sheet with service account email")
        exit(1)

    # Test data
    test_decision = {
        'action': 'BUY',
        'condition': 'A3',
        'pattern': 'B3',
        'entry': 4720.0,
        'sl': 4710.0,
        'tp1': 4750.0,
        'tp2': 4760.0,
        'tp3': 4770.0,
        'lot_size': 0.5,
        'confidence': 0.82
    }

    test_world_state = {
        'rsi': 36.5,
        'h1_trend': 'bullish',
        'session': 'London'
    }

    print(f"\n📝 Testing log_trade()...")

    try:
        logger = SheetsLogger()
        success = logger.log_trade(test_decision, test_world_state)

        if success:
            print(f"\n✅ Successfully logged test trade to Google Sheets!")
            print(f"   Check your sheet: https://docs.google.com/spreadsheets/d/{sheets_id}")
        else:
            print(f"\n✗ Failed to log trade")

    except Exception as e:
        print(f"\n❌ Error: {e}")

    print("\n" + "="*70)
