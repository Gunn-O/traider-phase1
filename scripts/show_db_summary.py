"""Quick summary of LocalDB after backtest"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.local_db import LocalDB

db = LocalDB()
s = db.get_summary()
print('=== BACKTEST RESULTS ===')
print(f'  Total trades : {s.get("total", 0) or 0}')
print(f'  Wins         : {s.get("wins", 0) or 0}')
print(f'  Losses       : {s.get("losses", 0) or 0}')
print(f'  Win rate     : {(s.get("wr_pct", 0) or 0):.1f}%')
print(f'  Net PNL USD  : {(s.get("net_pnl", 0) or 0):+.2f}')

print()
print('=== BY PATTERN ===')
for p in db.get_summary_by_pattern():
    pat = p.get('pattern', '')
    tot = p.get('total', 0)
    w = p.get('wins', 0)
    l = p.get('losses', 0)
    net = p.get('net_pnl_usd', 0) or 0
    print(f'  {pat:<14} total={tot} W={w} L={l} net={net:+.2f}')

trades = db.get_all_trades()
print()
print(f'=== ALL {len(trades)} TRADES ===')
for i, t in enumerate(trades, 1):
    ts = (t.get('timestamp_open') or '')[:19].replace('T', ' ')
    pat = (t.get('chart_type') or '').upper()
    a = t.get('action', '')
    e = t.get('entry_price', 0) or 0
    rr = t.get('rr_ratio', 0) or 0
    r = t.get('result', '-')
    pnl = t.get('pnl_usd', 0) or 0
    print(f'  {i:>3} {ts:<20} {pat:<12} {a:<5} entry={e:8.3f} RR={rr:5.2f} {r:<8} pnl={pnl:+8.2f}')

db.close()
