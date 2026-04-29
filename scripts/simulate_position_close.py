#!/usr/bin/env python3
"""
จำลองการปิด position ด้วยตนเอง

ใช้เมื่อต้องการ force close position ที่ค้างอยู่
เพื่อดูการคำนวณ win rate
"""

import os
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()


def manually_close_position():
    """Close position ด้วยตนเอง"""

    print("="*70)
    print("🔧 MANUAL POSITION CLOSE")
    print("="*70)

    sheets_id = os.getenv('GOOGLE_SHEETS_ID')
    creds_path = os.getenv('GOOGLE_CREDENTIALS_JSON')

    if not sheets_id or not os.path.exists(creds_path):
        print("❌ Configuration error")
        return

    # Connect
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheets_id)
    worksheet = sheet.worksheet('Trade Log')

    # Get pending trades
    records = worksheet.get_all_records()
    pending = [r for r in records if r['result'] == 'PENDING']

    if len(pending) == 0:
        print("\n✓ No pending trades to close")
        return

    print(f"\n📋 Found {len(pending)} pending trade(s):")
    for i, r in enumerate(pending, 1):
        print(f"\n{i}. {r['trade_id']}: {r['action']} {r['condition']}")
        print(f"   Entry: ${r['entry_price']:.2f}")
        print(f"   SL: ${r['sl_price']:.2f} | TP1: ${r['tp1_price']:.2f}")

    print(f"\n{'='*70}")
    trade_id = input("Enter trade_id to close (or 'cancel'): ").strip()

    if trade_id.lower() == 'cancel':
        print("Cancelled.")
        return

    # Find the trade
    selected = None
    for r in pending:
        if r['trade_id'] == trade_id:
            selected = r
            break

    if not selected:
        print(f"❌ Trade ID not found: {trade_id}")
        return

    # Show close options
    print(f"\n💰 Close options for {trade_id}:")
    print(f"   1. TP1 @ ${selected['tp1_price']:.2f}")
    print(f"   2. SL @ ${selected['sl_price']:.2f}")
    print(f"   3. Custom price")

    choice = input("\nSelect (1/2/3): ").strip()

    if choice == '1':
        close_price = float(selected['tp1_price'])
        close_reason = 'TP1'
    elif choice == '2':
        close_price = float(selected['sl_price'])
        close_reason = 'SL'
    elif choice == '3':
        close_price = float(input("Enter close price: "))
        close_reason = input("Enter close reason (TP1/TP2/TP3/SL/Manual): ")
    else:
        print("Invalid choice")
        return

    # Calculate P&L
    entry = float(selected['entry_price'])
    lot_size = float(selected['lot_size'])

    if selected['action'] == 'BUY':
        pnl = (close_price - entry) * lot_size * 10
    else:  # SELL
        pnl = (entry - close_price) * lot_size * 10

    result = 'WIN' if pnl > 0 else 'LOSS'

    print(f"\n📊 Summary:")
    print(f"   Close Price: ${close_price:.2f}")
    print(f"   P&L: ${pnl:,.2f}")
    print(f"   Result: {result}")

    confirm = input(f"\n✓ Confirm close? (y/n): ").strip().lower()

    if confirm != 'y':
        print("Cancelled.")
        return

    # Update sheet
    try:
        # Find the row
        cell = worksheet.find(trade_id)
        if cell:
            row_num = cell.row

            # Update columns N, O, P
            worksheet.update_cell(row_num, 14, result)       # result
            worksheet.update_cell(row_num, 15, pnl)          # pnl_usd
            worksheet.update_cell(row_num, 16, close_reason) # close_reason

            print(f"\n✅ Updated successfully!")
            print(f"   Trade: {trade_id}")
            print(f"   Result: {result}")
            print(f"   P&L: ${pnl:,.2f}")
        else:
            print(f"❌ Could not find trade in sheet")

    except Exception as e:
        print(f"❌ Error updating sheet: {e}")


if __name__ == "__main__":
    manually_close_position()
