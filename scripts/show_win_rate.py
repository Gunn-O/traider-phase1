#!/usr/bin/env python3
"""
แสดง Win Rate จากข้อมูลใน Google Sheets
"""

import os
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()


def calculate_win_rate():
    """คำนวณ Win Rate จาก Google Sheets"""

    print("="*70)
    print("📊 WIN RATE CALCULATION")
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

    # Get all records
    records = worksheet.get_all_records()

    if len(records) == 0:
        print("\n📋 No trades yet")
        return

    # Statistics
    total_trades = len(records)
    pending = [r for r in records if r['result'] == 'PENDING']
    closed = [r for r in records if r['result'] in ['WIN', 'LOSS']]
    wins = [r for r in records if r['result'] == 'WIN']
    losses = [r for r in records if r['result'] == 'LOSS']

    total_pnl = sum(float(r['pnl_usd']) for r in closed)

    win_rate = (len(wins) / len(closed) * 100) if len(closed) > 0 else 0.0

    print(f"\n📊 STATISTICS")
    print(f"{'='*70}")
    print(f"Total Trades:     {total_trades}")
    print(f"  ├─ Pending:     {len(pending)}")
    print(f"  ├─ Closed:      {len(closed)}")
    print(f"  │  ├─ Win:      {len(wins)}")
    print(f"  │  └─ Loss:     {len(losses)}")
    print(f"")
    print(f"Win Rate:         {win_rate:.1f}% ({len(wins)}/{len(closed)})")
    print(f"Total P&L:        ${total_pnl:,.2f}")

    if len(wins) > 0:
        avg_win = sum(float(r['pnl_usd']) for r in wins) / len(wins)
        print(f"Average Win:      ${avg_win:,.2f}")

    if len(losses) > 0:
        avg_loss = sum(float(r['pnl_usd']) for r in losses) / len(losses)
        print(f"Average Loss:     ${avg_loss:,.2f}")

    print(f"{'='*70}")

    # Show all closed trades
    if len(closed) > 0:
        print(f"\n📋 CLOSED TRADES:")
        print(f"{'='*70}")
        for i, r in enumerate(closed, 1):
            result_emoji = "✅" if r['result'] == 'WIN' else "❌"
            print(f"{i}. {result_emoji} {r['trade_id']}: {r['action']} {r['condition']}")
            print(f"   Entry: ${r['entry_price']:.2f} → Close: {r['close_reason']}")
            print(f"   P&L: ${float(r['pnl_usd']):,.2f}")
            print()

    # Show pending trades
    if len(pending) > 0:
        print(f"\n⏳ PENDING TRADES:")
        print(f"{'='*70}")
        for i, r in enumerate(pending, 1):
            print(f"{i}. {r['trade_id']}: {r['action']} {r['condition']}")
            print(f"   Entry: ${r['entry_price']:.2f}")
            print(f"   SL: ${r['sl_price']:.2f} | TP1: ${r['tp1_price']:.2f}")
            print()

    print(f"{'='*70}")
    print(f"🔗 View Sheet: https://docs.google.com/spreadsheets/d/{sheets_id}")
    print(f"{'='*70}")


if __name__ == "__main__":
    calculate_win_rate()
