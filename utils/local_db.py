"""
SQLite local database สำหรับ backtest
Sheets ใช้เฉพาะ SIM/LIVE เท่านั้น

Reference: CLAUDE.md Phase II — Backtest ใช้ LocalDB, SIM/LIVE ใช้ Sheets
"""
import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.getenv('LOCAL_DB_PATH', 'traider_backtest.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id        TEXT PRIMARY KEY,
    plan_id         TEXT,
    order_num       INTEGER DEFAULT 1,
    timestamp_open  TEXT,
    timeframe       TEXT,
    chart_type      TEXT,
    technique       TEXT,
    action          TEXT,
    entry_price     REAL,
    sl_price        REAL,
    tp_price        REAL,
    lot_size        REAL,
    lot_total_plan  REAL,
    rr_ratio        REAL,
    confidence      REAL DEFAULT 0,
    rsi_14          REAL DEFAULT 50,
    session         TEXT,
    ai_reason       TEXT,
    llm_tokens      INTEGER DEFAULT 0,
    llm_cost_usd    REAL DEFAULT 0,
    result          TEXT DEFAULT 'PENDING',
    pnl_usd         REAL DEFAULT 0,
    close_reason    TEXT,
    close_price     REAL,
    timestamp_close TEXT,
    trailing_sl     REAL,
    human_action    TEXT,
    human_agree     TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_time   TEXT,
    active_plan_id  TEXT,
    balance         REAL,
    realized_pnl    REAL,
    consecutive_loss INTEGER,
    total_loss_pct  REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id      TEXT PRIMARY KEY,
    start_date  TEXT,
    end_date    TEXT,
    engine      TEXT,
    status      TEXT DEFAULT 'running',
    total       INTEGER DEFAULT 0,
    wins        INTEGER DEFAULT 0,
    losses      INTEGER DEFAULT 0,
    pending     INTEGER DEFAULT 0,
    expired     INTEGER DEFAULT 0,
    net_pnl_usd REAL DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_result ON trades(result);
CREATE INDEX IF NOT EXISTS idx_trades_plan_id ON trades(plan_id);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp_open);
"""


class LocalDB:
    """
    SQLite database for backtest results

    Usage:
        db = LocalDB()
        db.insert_trade(trade_dict)
        db.update_trade_result(trade_id, 'WIN', 100.0, ...)
        summary = db.get_summary()
        db.close()
    """

    def __init__(self, db_path: str = DB_PATH):
        """
        Initialize SQLite database

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        logger.info(f"✓ LocalDB initialized: {db_path}")

    # ══════════════════════════════════════════════════════════════
    # Trade operations
    # ══════════════════════════════════════════════════════════════

    def insert_trade(self, trade: dict):
        """
        Insert new trade (PENDING)

        Args:
            trade: Trade dict with all required fields
        """
        self.conn.execute("""
            INSERT OR REPLACE INTO trades
            (trade_id, plan_id, order_num, timestamp_open, timeframe, chart_type,
             technique, action, entry_price, sl_price, tp_price,
             lot_size, lot_total_plan, rr_ratio, confidence, rsi_14,
             session, ai_reason, llm_tokens, llm_cost_usd, result, trailing_sl)
            VALUES
            (:trade_id, :plan_id, :order_num, :timestamp_open, :timeframe, :chart_type,
             :technique, :action, :entry_price, :sl_price, :tp_price,
             :lot_size, :lot_total_plan, :rr_ratio, :confidence, :rsi_14,
             :session, :ai_reason, :llm_tokens, :llm_cost_usd, :result, :trailing_sl)
        """, {
            'trade_id': trade['trade_id'],
            'plan_id': trade['plan_id'],
            'order_num': trade.get('order_num', 1),
            'timestamp_open': trade['timestamp_open'],
            'timeframe': trade.get('timeframe', 'M5'),
            'chart_type': trade.get('chart_type', ''),
            'technique': trade.get('technique', ''),
            'action': trade['action'],
            'entry_price': trade['entry_price'],
            'sl_price': trade['sl_price'],
            'tp_price': trade['tp_price'],
            'lot_size': trade['lot_size'],
            'lot_total_plan': trade.get('lot_total_plan', trade['lot_size']),
            'rr_ratio': trade.get('rr_ratio', 0),
            'confidence': trade.get('confidence', 0),
            'rsi_14': trade.get('rsi_14', 50),
            'session': trade.get('session', ''),
            'ai_reason': trade.get('ai_reason', ''),
            'llm_tokens': trade.get('llm_tokens', 0),
            'llm_cost_usd': trade.get('llm_cost_usd', 0),
            'result': trade.get('result', 'PENDING'),
            'trailing_sl': trade.get('trailing_sl', trade['sl_price'])
        })
        self.conn.commit()

    def update_trade_result(self, trade_id: str, result: str,
                           pnl: float, close_price: float,
                           close_time, close_reason: str):
        """
        Update trade when closed

        Args:
            trade_id: Trade ID
            result: 'WIN' | 'LOSS' | 'PENDING_EXPIRED'
            pnl: P&L in USD
            close_price: Close price
            close_time: Close timestamp (datetime or str)
            close_reason: 'SL_HIT' | 'TP_HIT' | 'BACKTEST_END'
        """
        if isinstance(close_time, datetime):
            close_time = close_time.isoformat()

        self.conn.execute("""
            UPDATE trades SET
                result = ?, pnl_usd = ?, close_reason = ?,
                close_price = ?, timestamp_close = ?
            WHERE trade_id = ?
        """, (result, pnl, close_reason,
              close_price, str(close_time), trade_id))
        self.conn.commit()

    def update_trailing_sl(self, trade_id: str, new_sl: float):
        """Update trailing SL"""
        self.conn.execute(
            "UPDATE trades SET trailing_sl = ? WHERE trade_id = ?",
            (new_sl, trade_id)
        )
        self.conn.commit()

    def get_pending_trades(self) -> List[dict]:
        """Get all PENDING trades"""
        cur = self.conn.execute(
            "SELECT * FROM trades WHERE result = 'PENDING' ORDER BY timestamp_open"
        )
        return [dict(r) for r in cur.fetchall()]

    def get_all_trades(self, run_id: str = None) -> List[dict]:
        """Get all trades"""
        cur = self.conn.execute("SELECT * FROM trades ORDER BY timestamp_open")
        return [dict(r) for r in cur.fetchall()]

    def get_recent_trades(self, limit: int = 100) -> List[dict]:
        """Get recent trades (newest first)"""
        cur = self.conn.execute(
            "SELECT * FROM trades ORDER BY timestamp_open DESC LIMIT ?",
            (limit,)
        )
        return [dict(r) for r in cur.fetchall()]

    # ══════════════════════════════════════════════════════════════
    # Summary & Analytics
    # ══════════════════════════════════════════════════════════════

    def get_summary(self) -> dict:
        """
        Get overall backtest summary

        Returns:
            {
                'total': int,
                'wins': int,
                'losses': int,
                'pending': int,
                'expired': int,
                'net_pnl': float,
                'avg_win': float,
                'avg_loss': float,
                'wr_pct': float
            }
        """
        cur = self.conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result='WIN'  THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result='PENDING' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN result='PENDING_EXPIRED' THEN 1 ELSE 0 END) as expired,
                -- net_pnl นับเฉพาะ WIN/LOSS เท่านั้น (ไม่รวม PENDING_EXPIRED)
                SUM(CASE WHEN result IN ('WIN','LOSS')
                    THEN pnl_usd ELSE 0 END) as net_pnl,
                AVG(CASE WHEN result='WIN' THEN pnl_usd END) as avg_win,
                AVG(CASE WHEN result='LOSS' THEN pnl_usd END) as avg_loss
            FROM trades
        """)
        row = dict(cur.fetchone())
        wins = row['wins'] or 0
        losses = row['losses'] or 0
        total_closed = wins + losses
        row['wr_pct'] = wins / total_closed * 100 if total_closed else 0
        return row

    def get_summary_by_pattern(self) -> List[dict]:
        """
        Get summary grouped by pattern

        Returns:
            List of dicts with pattern, total, wins, losses, net_pnl, etc.
        """
        cur = self.conn.execute("""
            SELECT
                chart_type as pattern,
                COUNT(*) as total,
                SUM(CASE WHEN result='WIN'  THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(pnl_usd) as net_pnl_usd,
                SUM(CASE WHEN result='WIN'  THEN pnl_usd ELSE 0 END) as gross_win,
                SUM(CASE WHEN result='LOSS' THEN pnl_usd ELSE 0 END) as gross_loss,
                AVG(CASE WHEN result IN ('WIN','LOSS') THEN pnl_usd END) as avg_pnl
            FROM trades
            WHERE result IN ('WIN','LOSS')
            GROUP BY chart_type
            ORDER BY total DESC
        """)
        return [dict(r) for r in cur.fetchall()]

    def get_equity_curve(self, initial_balance: float = 1000.0) -> List[dict]:
        """
        Get equity curve (balance over time)

        Args:
            initial_balance: Starting balance

        Returns:
            List of {'timestamp': str, 'balance': float}
        """
        cur = self.conn.execute("""
            SELECT timestamp_close, pnl_usd, result
            FROM trades
            WHERE result IN ('WIN','LOSS')
            ORDER BY timestamp_close
        """)
        rows = cur.fetchall()
        balance = initial_balance
        curve = [{'timestamp': 'start', 'balance': balance, 'result': 'START'}]

        for r in rows:
            balance += r['pnl_usd']
            curve.append({
                'timestamp': r['timestamp_close'],
                'balance': round(balance, 2),
                'result': r['result']
            })

        return curve

    # ══════════════════════════════════════════════════════════════
    # Utility
    # ══════════════════════════════════════════════════════════════

    def clear_trades(self):
        """ล้าง trades ก่อนรัน backtest ใหม่"""
        self.conn.execute("DELETE FROM trades")
        self.conn.commit()
        logger.info("✓ LocalDB: Cleared all trades")

    def vacuum(self):
        """Optimize database"""
        self.conn.execute("VACUUM")
        self.conn.commit()

    def close(self):
        """Close database connection"""
        self.conn.close()
        logger.info("✓ LocalDB: Connection closed")
