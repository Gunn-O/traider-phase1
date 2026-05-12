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
    bot_id          TEXT,
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
    created_at      TEXT DEFAULT (datetime('now')),
    -- Data-collection extras (2026-05-11): feed Risk/Money-mgmt design
    mae_pip            REAL DEFAULT 0,   -- max adverse excursion while open (pip)
    mfe_pip            REAL DEFAULT 0,   -- max favorable excursion while open (pip)
    r55_pip_at_open    REAL,             -- 55-bar range at entry (volatility context)
    pattern_details_json TEXT,           -- json.dumps(signal.details) for pattern tuning
    -- Scanner v3.4 stop_segments support (2026-05-12)
    scanner_segment_id TEXT              -- ISO timestamp of first bar in trend segment; used to skip same-segment entries after LOSS
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id          TEXT,
    snapshot_time   TEXT,
    active_plan_id  TEXT,
    balance         REAL,
    realized_pnl    REAL,
    consecutive_loss INTEGER,
    total_loss_pct  REAL,
    raw_json        TEXT
);

-- One row per bot — survives launcher restarts (used to restore consecutive_loss,
-- total_loss_pct, today_pnl, last_signal_time after WU reboot or crash).
CREATE TABLE IF NOT EXISTS bot_state_snapshots (
    bot_id              TEXT PRIMARY KEY,
    snapshot_time       TEXT NOT NULL,
    consecutive_loss    INTEGER DEFAULT 0,
    total_loss_pct      REAL DEFAULT 0,
    today_pnl           REAL DEFAULT 0,
    realized_pnl_usd    REAL DEFAULT 0,
    last_signal_time    TEXT,
    last_candle_time    TEXT,
    state_json          TEXT
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

"""

# Indexes are applied AFTER `_ensure_bot_id_column` so an upgrade from the
# pre-bot_id schema doesn't fail trying to create idx_trades_bot_id before the
# column exists.
SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_trades_result    ON trades(result);
CREATE INDEX IF NOT EXISTS idx_trades_plan_id   ON trades(plan_id);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp_open);
CREATE INDEX IF NOT EXISTS idx_trades_bot_id    ON trades(bot_id);
CREATE INDEX IF NOT EXISTS idx_psnap_bot_id     ON portfolio_snapshots(bot_id);
"""


def _ensure_bot_id_column(conn: sqlite3.Connection, table: str) -> None:
    """Idempotent ALTER for existing DBs created before bot_id was introduced."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if "bot_id" not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN bot_id TEXT")
        logger.info(f"✓ LocalDB: ALTER {table} ADD COLUMN bot_id")


# Columns added 2026-05-11 for richer trade analytics. Existing DBs will get
# them via idempotent ALTER, so the live SIM/LIVE DB doesn't need to be
# recreated. Pair `(col_name, ddl_fragment)` so the ALTER reproduces the type.
_EXTRA_TRADE_COLUMNS = [
    ("mae_pip",              "REAL DEFAULT 0"),
    ("mfe_pip",              "REAL DEFAULT 0"),
    ("r55_pip_at_open",      "REAL"),
    ("pattern_details_json", "TEXT"),
    ("scanner_segment_id",   "TEXT"),
]


def _ensure_extra_trade_columns(conn: sqlite3.Connection) -> None:
    """Idempotent ALTERs for the analytics columns added 2026-05-11."""
    cur = conn.execute("PRAGMA table_info(trades)")
    existing = {row[1] for row in cur.fetchall()}
    for name, ddl in _EXTRA_TRADE_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {name} {ddl}")
            logger.info(f"✓ LocalDB: ALTER trades ADD COLUMN {name}")


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
        # 30s timeout for the SQLite-level lock retry; WAL gives us readers/writers
        # in parallel so two bots writing concurrently don't trip "database is locked".
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        # Backfill bot_id column for DBs created before this refactor, THEN
        # create indexes (one of them references bot_id).
        _ensure_bot_id_column(self.conn, "trades")
        _ensure_bot_id_column(self.conn, "portfolio_snapshots")
        _ensure_extra_trade_columns(self.conn)
        self.conn.executescript(SCHEMA_INDEXES)
        self.conn.commit()
        logger.info(f"✓ LocalDB initialized: {db_path} (WAL, busy_timeout=5000)")

    # ══════════════════════════════════════════════════════════════
    # Trade operations
    # ══════════════════════════════════════════════════════════════

    def insert_trade(self, trade: dict):
        """
        Insert new trade (PENDING)

        Args:
            trade: Trade dict. `bot_id` is optional (legacy backtest paths omit it).
        """
        self.conn.execute("""
            INSERT OR REPLACE INTO trades
            (trade_id, bot_id, plan_id, order_num, timestamp_open, timeframe, chart_type,
             technique, action, entry_price, sl_price, tp_price,
             lot_size, lot_total_plan, rr_ratio, confidence, rsi_14,
             session, ai_reason, llm_tokens, llm_cost_usd, result, trailing_sl,
             r55_pip_at_open, pattern_details_json, scanner_segment_id)
            VALUES
            (:trade_id, :bot_id, :plan_id, :order_num, :timestamp_open, :timeframe, :chart_type,
             :technique, :action, :entry_price, :sl_price, :tp_price,
             :lot_size, :lot_total_plan, :rr_ratio, :confidence, :rsi_14,
             :session, :ai_reason, :llm_tokens, :llm_cost_usd, :result, :trailing_sl,
             :r55_pip_at_open, :pattern_details_json, :scanner_segment_id)
        """, {
            'trade_id': trade['trade_id'],
            'bot_id': trade.get('bot_id'),
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
            'trailing_sl': trade.get('trailing_sl', trade['sl_price']),
            'r55_pip_at_open': trade.get('r55_pip_at_open'),
            'pattern_details_json': trade.get('pattern_details_json'),
            'scanner_segment_id': trade.get('scanner_segment_id'),
        })
        self.conn.commit()

    def update_trade_result(self, trade_id: str, result: str,
                           pnl: float, close_price: float,
                           close_time, close_reason: str,
                           mae_pip: Optional[float] = None,
                           mfe_pip: Optional[float] = None):
        """
        Update trade when closed

        Args:
            trade_id: Trade ID
            result: 'WIN' | 'LOSS' | 'PENDING_EXPIRED'
            pnl: P&L in USD
            close_price: Close price
            close_time: Close timestamp (datetime or str)
            close_reason: 'SL_HIT' | 'TP_HIT' | 'BACKTEST_END'
            mae_pip: max adverse excursion in pips (optional — for analytics)
            mfe_pip: max favorable excursion in pips (optional — for analytics)
        """
        if isinstance(close_time, datetime):
            close_time = close_time.isoformat()

        if mae_pip is not None or mfe_pip is not None:
            self.conn.execute("""
                UPDATE trades SET
                    result = ?, pnl_usd = ?, close_reason = ?,
                    close_price = ?, timestamp_close = ?,
                    mae_pip = COALESCE(?, mae_pip),
                    mfe_pip = COALESCE(?, mfe_pip)
                WHERE trade_id = ?
            """, (result, pnl, close_reason,
                  close_price, str(close_time),
                  mae_pip, mfe_pip, trade_id))
        else:
            self.conn.execute("""
                UPDATE trades SET
                    result = ?, pnl_usd = ?, close_reason = ?,
                    close_price = ?, timestamp_close = ?
                WHERE trade_id = ?
            """, (result, pnl, close_reason,
                  close_price, str(close_time), trade_id))
        self.conn.commit()

    def update_mae_mfe(self, trade_id: str, mae_pip: float, mfe_pip: float):
        """Bump the running MAE/MFE for an open trade. No-op if either value
        is less than what's already stored (we want max-so-far)."""
        self.conn.execute("""
            UPDATE trades SET
                mae_pip = MAX(COALESCE(mae_pip, 0), ?),
                mfe_pip = MAX(COALESCE(mfe_pip, 0), ?)
            WHERE trade_id = ?
        """, (mae_pip, mfe_pip, trade_id))
        self.conn.commit()

    def update_trailing_sl(self, trade_id: str, new_sl: float):
        """Update trailing SL"""
        self.conn.execute(
            "UPDATE trades SET trailing_sl = ? WHERE trade_id = ?",
            (new_sl, trade_id)
        )
        self.conn.commit()

    def get_pending_trades(self, bot_id: Optional[str] = None) -> List[dict]:
        """Get PENDING trades, optionally filtered by bot_id."""
        if bot_id:
            cur = self.conn.execute(
                "SELECT * FROM trades WHERE result='PENDING' AND bot_id=? ORDER BY timestamp_open",
                (bot_id,),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM trades WHERE result='PENDING' ORDER BY timestamp_open"
            )
        return [dict(r) for r in cur.fetchall()]

    def get_all_trades(self, bot_id: Optional[str] = None) -> List[dict]:
        if bot_id:
            cur = self.conn.execute(
                "SELECT * FROM trades WHERE bot_id=? ORDER BY timestamp_open", (bot_id,),
            )
        else:
            cur = self.conn.execute("SELECT * FROM trades ORDER BY timestamp_open")
        return [dict(r) for r in cur.fetchall()]

    def get_recent_trades(self, limit: int = 100, bot_id: Optional[str] = None) -> List[dict]:
        if bot_id:
            cur = self.conn.execute(
                "SELECT * FROM trades WHERE bot_id=? ORDER BY timestamp_open DESC LIMIT ?",
                (bot_id, limit),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM trades ORDER BY timestamp_open DESC LIMIT ?", (limit,),
            )
        return [dict(r) for r in cur.fetchall()]

    # ══════════════════════════════════════════════════════════════
    # Summary & Analytics
    # ══════════════════════════════════════════════════════════════

    def get_summary(self, bot_id: Optional[str] = None) -> dict:
        """Aggregate stats. Filter to one bot via bot_id, or return cross-bot total."""
        where = "WHERE bot_id=?" if bot_id else ""
        params = (bot_id,) if bot_id else ()
        cur = self.conn.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result='WIN'  THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result='PENDING' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN result='PENDING_EXPIRED' THEN 1 ELSE 0 END) as expired,
                SUM(CASE WHEN result IN ('WIN','LOSS')
                    THEN pnl_usd ELSE 0 END) as net_pnl,
                AVG(CASE WHEN result='WIN' THEN pnl_usd END) as avg_win,
                AVG(CASE WHEN result='LOSS' THEN pnl_usd END) as avg_loss
            FROM trades {where}
        """, params)
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

    def get_equity_curve(self, initial_balance: float = 1000.0,
                         bot_id: Optional[str] = None) -> List[dict]:
        """Equity curve over WIN/LOSS rows. Filter to one bot via bot_id."""
        if bot_id:
            cur = self.conn.execute("""
                SELECT timestamp_close, pnl_usd, result
                FROM trades
                WHERE result IN ('WIN','LOSS') AND bot_id=?
                ORDER BY timestamp_close
            """, (bot_id,))
        else:
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
    # Bot state persistence (cross-restart durability for SIM/LIVE bots)
    # ══════════════════════════════════════════════════════════════

    def upsert_bot_state(self, bot_id: str, state: dict) -> None:
        """Save a bot's running counters so they survive launcher restarts."""
        self.conn.execute("""
            INSERT INTO bot_state_snapshots
              (bot_id, snapshot_time, consecutive_loss, total_loss_pct,
               today_pnl, realized_pnl_usd, last_signal_time, last_candle_time, state_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bot_id) DO UPDATE SET
              snapshot_time    = excluded.snapshot_time,
              consecutive_loss = excluded.consecutive_loss,
              total_loss_pct   = excluded.total_loss_pct,
              today_pnl        = excluded.today_pnl,
              realized_pnl_usd = excluded.realized_pnl_usd,
              last_signal_time = excluded.last_signal_time,
              last_candle_time = excluded.last_candle_time,
              state_json       = excluded.state_json
        """, (
            bot_id,
            datetime.now().isoformat(),
            int(state.get('consecutive_loss', 0)),
            float(state.get('total_loss_pct', 0)),
            float(state.get('today_pnl', 0)),
            float(state.get('realized_pnl_usd', 0)),
            state.get('last_signal_time'),
            state.get('last_candle_time'),
            json.dumps(state.get('extras', {})),
        ))
        self.conn.commit()

    def get_bot_state(self, bot_id: str) -> Optional[dict]:
        cur = self.conn.execute(
            "SELECT * FROM bot_state_snapshots WHERE bot_id=?", (bot_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d['extras'] = json.loads(d.pop('state_json') or '{}')
        except Exception:
            d['extras'] = {}
        return d

    # ══════════════════════════════════════════════════════════════
    # Utility
    # ══════════════════════════════════════════════════════════════

    def clear_trades(self, bot_id: Optional[str] = None):
        """Clear trades. With bot_id only that bot's rows; otherwise wipe all."""
        if bot_id:
            self.conn.execute("DELETE FROM trades WHERE bot_id=?", (bot_id,))
            logger.info(f"✓ LocalDB: Cleared trades for bot {bot_id}")
        else:
            self.conn.execute("DELETE FROM trades")
            logger.info("✓ LocalDB: Cleared all trades")
        self.conn.commit()

    def vacuum(self):
        """Optimize database"""
        self.conn.execute("VACUUM")
        self.conn.commit()

    def close(self):
        """Close database connection"""
        self.conn.close()
        logger.info("✓ LocalDB: Connection closed")
