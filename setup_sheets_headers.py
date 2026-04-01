#!/usr/bin/env python3
"""
Setup Google Sheets Headers

สร้างหัวตารางใน Sheet "Trade Log"
"""

import os
from dotenv import load_dotenv

load_dotenv()

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("❌ gspread not installed")
    print("Run: pip install gspread google-auth")
    exit(1)


def setup_headers():
    """สร้างหัวตารางใน Trade Log sheet"""

    print("="*70)
    print("📊 GOOGLE SHEETS HEADER SETUP")
    print("="*70)

    # Load config
    sheets_id = os.getenv('GOOGLE_SHEETS_ID', '')
    creds_path = os.getenv('GOOGLE_CREDENTIALS_JSON', './credentials.json')

    if not sheets_id:
        print("\n❌ GOOGLE_SHEETS_ID not found in .env")
        exit(1)

    if not os.path.exists(creds_path):
        print(f"\n❌ Credentials file not found: {creds_path}")
        exit(1)

    print(f"\n📋 Configuration:")
    print(f"   Sheets ID: {sheets_id}")
    print(f"   Credentials: {creds_path}")

    # Connect
    print(f"\n🔗 Connecting to Google Sheets...")

    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]

        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheets_id)

        print(f"   ✓ Connected to: {sheet.title}")

    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        exit(1)

    # Get or create "Trade Log" worksheet
    try:
        worksheet = sheet.worksheet("Trade Log")
        print(f"\n📄 Found existing 'Trade Log' worksheet")

        # ถามว่าจะ clear หรือไม่
        response = input("   Clear existing data and recreate headers? (y/n): ")
        if response.lower() != 'y':
            print("   Cancelled.")
            return

        worksheet.clear()
        print("   ✓ Cleared existing data")

    except gspread.exceptions.WorksheetNotFound:
        print(f"\n📄 Creating new 'Trade Log' worksheet...")
        worksheet = sheet.add_worksheet(title="Trade Log", rows=1000, cols=16)
        print(f"   ✓ Created")

    # Define headers
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

    print(f"\n✏️  Writing headers...")
    print(f"   Columns: {len(headers)}")

    # Write headers
    worksheet.append_row(headers)

    # Format headers (bold, background color)
    worksheet.format('A1:P1', {
        'textFormat': {'bold': True},
        'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
    })

    print(f"   ✓ Headers written")

    # Set column widths
    print(f"\n🎨 Formatting columns...")

    # Set widths
    worksheet.set_column_width('A', 150)  # trade_id
    worksheet.set_column_width('B', 160)  # timestamp
    worksheet.set_column_width('C', 120)  # condition
    worksheet.set_column_width('D', 80)   # pattern
    worksheet.set_column_width('E', 60)   # action
    worksheet.set_column_width('F', 90)   # entry_price
    worksheet.set_column_width('G', 90)   # sl_price
    worksheet.set_column_width('H', 90)   # tp1_price
    worksheet.set_column_width('I', 80)   # lot_size
    worksheet.set_column_width('J', 90)   # confidence
    worksheet.set_column_width('K', 60)   # rsi
    worksheet.set_column_width('L', 100)  # h1_trend
    worksheet.set_column_width('M', 100)  # session
    worksheet.set_column_width('N', 80)   # result
    worksheet.set_column_width('O', 90)   # pnl_usd
    worksheet.set_column_width('P', 100)  # close_reason

    print(f"   ✓ Column widths set")

    print(f"\n{'='*70}")
    print(f"✅ Setup completed!")
    print(f"{'='*70}")
    print(f"\n🔗 View your sheet:")
    print(f"   https://docs.google.com/spreadsheets/d/{sheets_id}")
    print(f"\n💡 Next steps:")
    print(f"   1. Set SHEETS_ENABLED=true in .env")
    print(f"   2. Run: python main.py")
    print(f"   3. Check sheet for logged trades")


if __name__ == "__main__":
    setup_headers()
