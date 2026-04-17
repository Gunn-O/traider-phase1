#!/usr/bin/env python3
"""
Clear Google Sheets Data and Reinitialize Headers

Usage:
    python clear_sheets_data.py [--force]
"""

import os
import sys
import argparse
from dotenv import load_dotenv

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("❌ gspread not installed. Run: pip install gspread google-auth")
    sys.exit(1)

from config import TRADE_LOG_COLUMNS, PORTFOLIO_STATE_FIELDS


def clear_and_setup_sheets(force: bool = False):
    """Clear all data and setup fresh headers"""

    load_dotenv()

    # Get credentials
    sheets_id = os.getenv('GOOGLE_SHEETS_ID')
    credentials_path = os.getenv('GOOGLE_CREDENTIALS_JSON', './credentials.json')

    if not sheets_id:
        print("❌ GOOGLE_SHEETS_ID not found in .env")
        return False

    if not os.path.exists(credentials_path):
        print(f"❌ Credentials file not found: {credentials_path}")
        return False

    print("="*70)
    print("🧹 CLEARING GOOGLE SHEETS DATA")
    print("="*70)
    print(f"Sheets ID: {sheets_id}")
    print(f"Credentials: {credentials_path}")
    print()

    # Confirm (skip if --force)
    if not force:
        response = input("⚠️  This will DELETE ALL data in the sheets. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Cancelled")
            return False
    else:
        print("⚠️  --force mode: Skipping confirmation")

    try:
        # Connect
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]

        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheets_id)

        print("✓ Connected to Google Sheets")

        # Clear Sheet 1: Trade Log
        print("\n[1/2] Clearing Trade Log...")
        try:
            trade_log = sheet.worksheet("Trade Log")
            trade_log.clear()
            print("  ✓ Cleared all data")
        except gspread.exceptions.WorksheetNotFound:
            trade_log = sheet.add_worksheet(title="Trade Log", rows=1000, cols=len(TRADE_LOG_COLUMNS))
            print("  ✓ Created new worksheet")

        # Set headers
        trade_log.update('A1', [TRADE_LOG_COLUMNS])
        print(f"  ✓ Set headers ({len(TRADE_LOG_COLUMNS)} columns)")

        # Clear Sheet 2: Portfolio State
        print("\n[2/2] Clearing Portfolio State...")
        try:
            portfolio = sheet.worksheet("Portfolio State")
            portfolio.clear()
            print("  ✓ Cleared all data")
        except gspread.exceptions.WorksheetNotFound:
            portfolio = sheet.add_worksheet(title="Portfolio State", rows=20, cols=len(PORTFOLIO_STATE_FIELDS))
            print("  ✓ Created new worksheet")

        # Set headers
        portfolio.update('A1', [PORTFOLIO_STATE_FIELDS])
        print(f"  ✓ Set headers ({len(PORTFOLIO_STATE_FIELDS)} fields)")

        # Initialize Portfolio State with default values (14 fields)
        default_portfolio = [
            'ไม่มีแผนที่เปิดอยู่',  # A: active_plan_id
            '0',                      # B: open_plans_count
            '0.00',                   # C: total_risk_pct
            '0',                      # D: open_orders_count
            '0.00',                   # E: total_open_lot
            '0.00',                   # F: realized_pnl_usd
            '0.00',                   # G: unrealized_pnl_usd
            '0',                      # H: consecutive_loss
            '0.00',                   # I: total_loss_pct
            'FALSE',                  # J: trading_blocked
            '-',                      # K: block_reason
            '-',                      # L: last_updated
            '0.00',                   # M: last_technical_price
            '-'                       # N: last_plan_chart_type
        ]
        portfolio.update('A2:N2', [default_portfolio])
        print("  ✓ Initialized default portfolio state")

        print("\n" + "="*70)
        print("✅ Google Sheets cleared and reinitialized successfully!")
        print("="*70)
        print("\nNext steps:")
        print("  1. Run: python main.py --once --winrate-test")
        print("  2. Check Google Sheets for logged data")
        print()

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Clear Google Sheets data')
    parser.add_argument('--force', action='store_true',
                        help='Skip confirmation prompt')
    args = parser.parse_args()

    success = clear_and_setup_sheets(force=args.force)
    sys.exit(0 if success else 1)
