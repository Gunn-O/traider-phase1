#!/usr/bin/env python3
"""
Tra(i)der Phase II — Main Trading Loop

Per-trade pipeline (Python only — no AI per cycle):
    Signal Engine → G2 Pre-filter → AUTO_APPROVE → Lot from Signal Engine
                  → G3c Guardian (Python rules) → Execute → MT5

AI scope (separate cadence, not per-trade):
    - Weekly Strategist  : weekly review of stats + parameter suggestions
    - Monthly Evolver    : monthly proposal of strategy updates (human approves)

Usage:
    python main.py --winrate-test  # Winrate test mode (0.01 lot)
    python main.py --simulate      # Simulate mode (normal lot)
    python main.py --backtest --start 2026-01-01 --end 2026-03-31
    python main.py --backtest --start 2026-04-04 --end 2026-04-10 --log-sheets  # Backtest with Sheets logging

Reference: CLAUDE.md (Phase II Architecture)
"""

import os
import sys
import argparse
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List
from dotenv import load_dotenv

# Import agents (Phase II — Signal Engine Architecture)
# REMOVED: g1_pattern_detector, g3_analyst, g3_risk_manager, g4_reflector (Phase I cleanup)
from agents.g2_prefilter import G2Prefilter
from agents.g4_weekly_strategist import G4WeeklyStrategist, aggregate_weekly_stats, should_run_weekly
from agents.g4_monthly_evolver import G4MonthlyEvolver, aggregate_monthly_stats, should_run_monthly
from agents.g3_risk_gate import guardian_check
from agents.g4_sheets_logger import SheetsLogger
from agents.g4_position_monitor import PositionMonitor, generate_plan_id, generate_trade_id
from agents.paper_broker import PaperBroker

# Import utils
from utils.data_connector import create_connector
from utils.signal_engine import run_signal_engine  # NEW — replaces G1
from config import TIMEFRAMES, CANDLES_LOOKBACK, RISK_CONFIG

# Import bot_state from api_server (shared state)
try:
    from api_server import bot_state, update_bot_state, add_log
except ImportError:
    # Fallback if api_server not available (for command-line mode)
    bot_state = {
        "status": "stopped",
        "symbol": "XAUUSDc",
        "trading_tf": "M5",
        "balance": 0.0
    }
    def update_bot_state(updates): pass
    def add_log(msg): pass

# ─── Multi-bot event reporting (POST events back to api_server) ────────
# api_server sets these env vars when spawning the subprocess via /api/start.
# When running from CLI (no api_server) both are empty → events become no-ops.
import json as _json_post
import urllib.request as _urlreq_post

_BOT_ID = os.getenv("TRAIDER_BOT_ID", "")
_API_URL = os.getenv("TRAIDER_API_URL", "")


def post_bot_event(event_type: str, msg: str = "", data: dict = None) -> None:
    """Send a SIGNAL/SKIP/PLAN_OPENED/PLAN_CLOSED event to api_server so the
    Dashboard can show what this bot is doing in real time. Best-effort: any
    error is swallowed so trading isn't impacted by API hiccups."""
    if not _BOT_ID or not _API_URL:
        return
    try:
        body = _json_post.dumps({"type": event_type, "msg": msg, "data": data or {}}).encode()
        req = _urlreq_post.Request(
            f"{_API_URL}/api/bots/{_BOT_ID}/event",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        _urlreq_post.urlopen(req, timeout=2).read()
    except Exception:
        pass


def post_bot_heartbeat(data: dict) -> None:
    """Per-cycle snapshot push so the Dashboard sees 'alive' updates without
    flooding the events panel. Overwrites previous heartbeat — only the latest
    tick matters. Best-effort like post_bot_event."""
    if not _BOT_ID or not _API_URL:
        return
    try:
        body = _json_post.dumps(data).encode()
        req = _urlreq_post.Request(
            f"{_API_URL}/api/bots/{_BOT_ID}/heartbeat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        _urlreq_post.urlopen(req, timeout=2).read()
    except Exception:
        pass

# Load environment (override=True to ensure .env takes precedence over shell)
load_dotenv(override=True)

# Setup logging (force=True to override any previous config)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        # encoding='utf-8' so emoji/Thai chars don't get dropped on cp874 systems
        logging.FileHandler('traider.log', encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def update_session_stats(stats: dict, llm_log: dict, opened_plan: bool = False,
                          g2_blocked: bool = False):
    """
    อัปเดต session stats หลังแต่ละ cycle

    Args:
        stats: session_stats dict
        llm_log: LLM log from G3a decision (None if G2 blocked)
        opened_plan: True if plan was opened
        g2_blocked: True if G2 blocked before Claude
    """
    if llm_log and llm_log.get('action') not in ['ERROR', 'CREDIT_EXHAUSTED', 'RATE_LIMIT']:
        stats['total_calls'] += 1
        stats['total_tokens'] += llm_log.get('total_tokens', 0)
        stats['total_cost_usd'] += llm_log.get('cost_usd', 0)
        if llm_log.get('cache_hit'):
            stats['cache_hits'] += 1
        else:
            stats['cache_miss'] += 1

    if opened_plan:
        stats['total_plans'] += 1
    else:
        stats['total_skips'] += 1

    if g2_blocked:
        stats['total_g2_blocks'] += 1


def calc_breakeven(session_stats: dict, balance: float) -> dict:
    """
    Calculate break-even analysis for API costs vs trading profits

    Args:
        session_stats: Session statistics dict
        balance: Account balance

    Returns:
        Dict with break-even metrics
    """
    total_cost = session_stats['total_cost_usd']
    total_calls = session_stats['total_calls']
    total_plans = session_stats['total_plans']

    # Cost per call and per plan
    cost_per_call = total_cost / total_calls if total_calls > 0 else 0
    cost_per_plan = total_cost / total_plans if total_plans > 0 else 0

    # Skip calls that didn't open a plan
    skip_calls = total_calls - total_plans
    skip_call_cost = cost_per_call * skip_calls

    # API cost allocated per plan (including skip costs)
    api_cost_per_plan = total_cost / total_plans if total_plans > 0 else 0

    # Max loss per plan (10% risk per plan)
    max_loss_per_plan = balance * 0.10

    # Break-even win rate calculation
    # Formula: win_rate = (avg_loss + api_cost) / (avg_profit + avg_loss)
    # Assumptions:
    # - avg_profit = max_loss_per_plan × R:R
    # - avg_loss = max_loss_per_plan

    avg_loss = max_loss_per_plan

    # R:R 1:1
    avg_profit_rr1 = max_loss_per_plan * 1.0
    breakeven_winrate_rr1 = (avg_loss + api_cost_per_plan) / (avg_profit_rr1 + avg_loss) if total_plans > 0 else 0

    # R:R 1.5:1
    avg_profit_rr15 = max_loss_per_plan * 1.5
    breakeven_winrate_rr15 = (avg_loss + api_cost_per_plan) / (avg_profit_rr15 + avg_loss) if total_plans > 0 else 0

    # R:R 2:1
    avg_profit_rr2 = max_loss_per_plan * 2.0
    breakeven_winrate_rr2 = (avg_loss + api_cost_per_plan) / (avg_profit_rr2 + avg_loss) if total_plans > 0 else 0

    return {
        'cost_per_call': cost_per_call,
        'cost_per_plan': cost_per_plan,
        'skip_call_cost': skip_call_cost,
        'api_cost_per_plan': api_cost_per_plan,
        'max_loss_per_plan': max_loss_per_plan,
        'breakeven_winrate_rr1': breakeven_winrate_rr1,
        'breakeven_winrate_rr15': breakeven_winrate_rr15,
        'breakeven_winrate_rr2': breakeven_winrate_rr2,
    }


def print_session_summary(stats: dict, balance: float):
    """แสดงสรุป session ท้าย run"""
    if stats['total_calls'] == 0:
        logger.info("\n📊 No API calls made in this session")
        return

    be = calc_breakeven(stats, balance)
    calls = stats['total_calls']
    cache_rate = stats['cache_hits'] / calls if calls > 0 else 0

    logger.info("=" * 60)
    logger.info("📊 SESSION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"API Calls:       {calls:>6}")
    logger.info(f"  Cache HIT  ✅  {stats['cache_hits']:>6}  ({cache_rate:.0%})")
    logger.info(f"  Cache MISS ❌  {stats['cache_miss']:>6}")
    logger.info(f"Total Tokens:    {stats['total_tokens']:>6,}")
    logger.info(f"Total Cost:      ${stats['total_cost_usd']:>8.4f}")
    logger.info(f"Cost/Call:       ${be['cost_per_call']:>8.4f}")
    logger.info("-" * 60)
    logger.info(f"G2 Blocked:      {stats['total_g2_blocks']:>6}  (ไม่ถึง Claude)")
    logger.info(f"Plans Opened:    {stats['total_plans']:>6}")
    logger.info(f"Skips by Claude: {stats['total_skips']:>6}")
    logger.info(f"Skip API Cost:   ${be['skip_call_cost']:>8.4f}  ← เสียโดยไม่เปิด plan")
    logger.info(f"Cost/Plan:       ${be['cost_per_plan']:>8.4f}")
    logger.info("-" * 60)

    if stats['total_plans'] > 0:
        logger.info(f"💡 BREAK-EVEN  (Balance: ${balance:.0f}, Risk: 10%/plan)")
        logger.info(f"  R:R 1:1  → Win Rate ≥ {be['breakeven_winrate_rr1']:.1%}")
        logger.info(f"  R:R 1.5  → Win Rate ≥ {be['breakeven_winrate_rr15']:.1%}")
        logger.info(f"  R:R 2.0  → Win Rate ≥ {be['breakeven_winrate_rr2']:.1%}")
    else:
        logger.info(f"⚠️  No plans opened — เสีย ${stats['total_cost_usd']:.4f} โดยไม่ได้เทรด")

    logger.info("=" * 60)


# ============================================================================
# BROKER FACTORY
# ============================================================================

def create_broker(mode: str, symbol: str):
    """
    Create broker instance based on trading mode

    Args:
        mode: Trading mode ('paper', 'micro', 'live')
        symbol: Trading symbol (e.g., 'XAUUSDc', 'XAUUSD')

    Returns:
        PaperBroker if mode='paper'
        MT5LiveBroker if mode in ('micro', 'live') — sends real orders to MT5
    """
    if mode == 'paper':
        logger.info(f"📄 Creating PaperBroker (mode={mode}, symbol={symbol})")
        return PaperBroker(symbol=symbol)
    if mode in ('micro', 'live'):
        from agents.mt5_live_broker import MT5LiveBroker
        logger.info(f"💹 Creating MT5LiveBroker (mode={mode}, symbol={symbol}) — REAL ORDERS")
        return MT5LiveBroker(symbol=symbol, mode=mode)
    raise ValueError(f"Unknown trading mode: {mode}")


# ============================================================================
# MAIN TRAIDER CLASS
# ============================================================================

class TraiderMainLoop:
    """Main trading loop for Tra(i)der Phase I v4.3 (4-Agent Architecture + Reflector)"""

    @staticmethod
    def _confirm_real_trade():
        """Block start ของ live/micro mode จนกว่า user จะพิมพ์ 'I UNDERSTAND' 2 ครั้ง"""
        import sys
        msg1 = (
            "\n" + "!"*72 + "\n"
            "  REAL TRADING MODE — โหมดนี้จะส่ง order จริงไปที่ MT5 (เงินจริง)\n"
            "  หากระบบ malfunction อาจสูญเสียเงินทั้งหมดในบัญชี\n"
            "  ห้ามรันถ้ายังไม่ได้ทดสอบ paper/backtest จนแน่ใจ\n"
            + "!"*72 + "\n"
        )
        sys.stderr.write(msg1)
        try:
            r1 = input("ยืนยันครั้งที่ 1 — พิมพ์ 'I UNDERSTAND' (case-sensitive): ").strip()
            if r1 != "I UNDERSTAND":
                raise SystemExit("LIVE mode aborted: confirmation 1 failed")
            r2 = input("ยืนยันครั้งที่ 2 — พิมพ์ 'I UNDERSTAND' อีกครั้ง: ").strip()
            if r2 != "I UNDERSTAND":
                raise SystemExit("LIVE mode aborted: confirmation 2 failed")
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("LIVE mode aborted by user")
        sys.stderr.write("✅ Live trade confirmed.\n\n")

    def __init__(self, args):
        """
        Initialize trading system

        Args:
            args: Parsed command-line arguments
        """
        self.args = args
        self.mode = 'winrate_test' if args.winrate_test else 'simulate'
        self.is_backtest = args.backtest if hasattr(args, 'backtest') else False

        # CLI args win over bot_state (subprocesses don't share bot_state with api_server)
        self.symbol = (
            getattr(args, 'symbol', None)
            or bot_state.get("symbol")
            or os.getenv('BACKTEST_SYMBOL', 'XAUUSDc')
        )
        self.balance = float(os.getenv('ACCOUNT_BALANCE', '300'))

        self.trading_mode = (
            getattr(args, 'mode', None)
            or bot_state.get("mode", "paper")
        )

        # Real-money safety: require explicit confirmation 2x for live/micro modes
        # Skipped when --no-confirm (api_server-spawned subprocess) or in backtest
        if self.trading_mode in ('micro', 'live') and not self.is_backtest:
            if not getattr(args, 'no_confirm', False):
                self._confirm_real_trade()
            else:
                logger.warning(
                    f"⚠️  Real-money mode {self.trading_mode!r} bypassing 2x confirmation "
                    f"(--no-confirm) — caller is responsible for prior user confirmation."
                )

        # Update bot_state with balance
        update_bot_state({"balance": self.balance})

        logger.info("="*70)
        logger.info("🤖 Tra(i)der Phase I v4.3 — AI Trading System (4-Agent + Reflector)")
        logger.info("="*70)
        logger.info(f"Mode (label):   {self.mode}")
        logger.info(f"Trading mode:   {self.trading_mode}  (paper=sim / micro=cent / live=real)")
        logger.info(f"Symbol:         {self.symbol}")
        logger.info(f"Active TF:      {os.getenv('BACKTEST_TIMEFRAME', 'M5').upper()}  (env BACKTEST_TIMEFRAME)")
        logger.info(f"Data source:    {getattr(args, 'data_source', 'auto')}")
        logger.info(f"Balance (.env): ${self.balance:,.2f}")
        if self.is_backtest:
            logger.info(f"Backtest mode: Sheets logging {'ENABLED' if args.log_sheets else 'DISABLED'}")
        logger.info("="*70)

        # Initialize data connector — honor --data-source CLI arg (auto/mt5/yf/tv)
        ds_mode = getattr(args, 'data_source', None) or 'auto'
        logger.info(f"📡 Initializing data connector (requested: {ds_mode})...")
        self.connector = create_connector(
            mode=ds_mode,
            symbol=self.symbol
        )

        # Determine data source for logging (V4.3: use source_name property)
        from agents.paper_broker import PaperBroker
        from utils.data_connector import MT5Connector, YFinanceConnector, TVConnector

        # Use source_name property (all connectors have this now)
        data_source = getattr(self.connector, 'source_name', 'Unknown')

        # Log with appropriate icon
        if isinstance(self.connector, MT5Connector):
            logger.info("📊 Data source: MT5 Terminal")
        elif isinstance(self.connector, YFinanceConnector):
            logger.info("📊 Data source: yfinance (GC=F Gold Futures)")
        elif isinstance(self.connector, TVConnector):
            logger.info("📺 Data source: TradingView (OANDA)")
        else:
            # Legacy DataConnector (should not happen in V4.3)
            data_source = "Legacy"
            logger.warning("⚠️ Using legacy DataConnector")

        # Update bot_state with data source
        update_bot_state({"data_source_actual": data_source})
        logger.info("✓ Data connector ready")

        # Initialize agents (Phase II — Signal Engine Architecture, Python-only per-trade)
        logger.info("🤖 Initializing agents (Phase II: Signal Engine, no AI per trade)...")

        # G2: Pre-filter (active)
        self.g2 = G2Prefilter(config={'verbose': True})

        # Phase II: per-trade decision is fully deterministic (Python only).
        # Signal Engine produces entry/SL/TP/lot → AUTO_APPROVE → Guardian.
        # No Claude Reviewer per signal; no Risk Manager (Haiku) per signal.
        # AI runs only on weekly/monthly cadence (Strategist / Evolver below).

        # Weekly Strategist + Monthly Evolver need ANTHROPIC_API_KEY.
        # .env documents the key as optional, and these agents only run on
        # weekly/monthly schedules — skip init (with warning) when the key is
        # absent so the bot can still start for paper/python-decision runs.
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        if anthropic_key:
            self.weekly_strategist = G4WeeklyStrategist(api_key=anthropic_key, config={'verbose': True})
            logger.info("✓ Weekly Strategist initialized")
            self.monthly_evolver = G4MonthlyEvolver(api_key=anthropic_key, config={'verbose': True})
            logger.info("✓ Monthly Evolver initialized")
        else:
            self.weekly_strategist = None
            self.monthly_evolver = None
            logger.warning("⚠️ ANTHROPIC_API_KEY not set — Weekly Strategist & Monthly Evolver disabled")

        # Initialize G4
        # Backtest mode: Disable Sheets by default (use LocalDB instead)
        # SIM/LIVE mode: Use .env SHEETS_ENABLED setting
        # Backtest with --log-sheets: Enable Sheets (for final flush)
        if self.is_backtest:
            # Backtest: Disable Sheets unless --log-sheets explicitly passed
            sheets_enabled_override = args.log_sheets if hasattr(args, 'log_sheets') else False
        else:
            # SIM/LIVE: Use .env setting
            sheets_enabled_override = None

        self.sheets_logger = SheetsLogger(enabled_override=sheets_enabled_override)
        logger.info(f"📊 SheetsLogger: enabled={self.sheets_logger.enabled}, sheets_id={self.sheets_logger.sheets_id[:20]}..." if self.sheets_logger.sheets_id else f"📊 SheetsLogger: enabled={self.sheets_logger.enabled}, sheets_id=None")

        # Initialize LocalDB:
        #   - Backtest: scratch DB that gets cleared per run
        #   - SIM/LIVE under api_server: persistent DB that survives launcher restarts
        # Separate paths so a backtest doesn't wipe live bot history.
        if self.is_backtest:
            from utils.local_db import LocalDB
            self.local_db = LocalDB(db_path='traider_backtest.db')
            self.local_db.clear_trades()
            if self.sheets_logger.enabled:
                self.sheets_logger.set_batch_mode(True)
            logger.info("✓ Backtest mode: LocalDB + Sheets batch mode")
        elif _BOT_ID:
            from utils.local_db import LocalDB
            self.local_db = LocalDB(db_path='traider_sim.db')
            # bot_state restore happens after portfolio_state_cache is initialized.
        else:
            self.local_db = None

        self.position_monitor = PositionMonitor(sheets_logger=self.sheets_logger)
        logger.info("✓ Position Monitor initialized")

        # Set references for API server
        from api_server import set_sheets_logger, set_position_monitor, set_connector
        set_sheets_logger(self.sheets_logger)
        set_position_monitor(self.position_monitor)
        set_connector(self.connector)

        # Phase II: Reflector removed (not needed in backtest)
        self.reflector = None

        # Initialize Broker (Paper/Micro/Live)
        self.broker = create_broker(self.trading_mode, self.symbol)

        # Weekly/Monthly/Daily state tracking
        self.last_weekly_date = None
        self.last_monthly_date = None
        self.last_daily_date = None  # V4.3: For Reflector
        self.weekly_stats = {}
        self.reflection_summary = "No history yet — trade normally"

        # Mountain state tracking (for Round 2 detection)
        self.mountain_state = None  # Will be updated by Signal Engine
        # Notebook v3.4 stateful Scanner — segment tracking + stop_segments.
        # Loaded from bot_state_snapshots.state_json on startup; persisted on
        # each plan_closed event so a launcher restart preserves it.
        self.scanner_state: Optional[dict] = None

        # Initialize session stats tracking
        self.session_stats = {
            'total_calls': 0,
            'total_tokens': 0,
            'total_cost_usd': 0.0,
            'cache_hits': 0,
            'cache_miss': 0,
            'total_plans': 0,
            'total_skips': 0,
            'total_g2_blocks': 0,
        }

        # Initialize portfolio state cache (for backtest mode duplicate prevention)
        # Seed from LocalDB if a previous run for this bot_id was persisted, so
        # guardian counters (consecutive_loss, total_loss_pct) survive restarts.
        self.portfolio_state_cache = {}
        if self.local_db and _BOT_ID:
            saved = self.local_db.get_bot_state(_BOT_ID)
            if saved:
                self.portfolio_state_cache.update({
                    'consecutive_loss': saved.get('consecutive_loss', 0),
                    'total_loss_pct':   saved.get('total_loss_pct', 0),
                    'realized_pnl_usd': saved.get('realized_pnl_usd', 0),
                })
                logger.info(
                    f"✓ Bot state restored from LocalDB for {_BOT_ID}: "
                    f"consec_loss={saved.get('consecutive_loss', 0)}, "
                    f"realized_pnl=${saved.get('realized_pnl_usd', 0):.2f}"
                )

        logger.info("✓ All agents initialized")

    def _record_scanner_loss_segment(self, closed_trade: dict) -> None:
        """If a closed Scanner trade is a LOSS, add its segment_id to the
        scanner-state stop list (UP or DOWN bucket based on action). The next
        cycle will refuse to fire a new Scanner signal in that same segment."""
        seg = closed_trade.get('scanner_segment_id')
        if not seg or closed_trade.get('result') != 'LOSS' or self.scanner_state is None:
            return
        action = str(closed_trade.get('action', '')).upper()
        if action == 'BUY':
            bucket = self.scanner_state.setdefault('stopped_up_segments', [])
            direction = 'UP'
        elif action == 'SELL':
            bucket = self.scanner_state.setdefault('stopped_down_segments', [])
            direction = 'DOWN'
        else:
            return
        if seg not in bucket:
            bucket.append(seg)
            logger.info(f"Scanner: marked {direction} segment {seg} STOPPED after LOSS")

    def run_once(self, candle_time=None, candles_by_tf=None, current_candle=None):
        """
        Run pipeline once (for testing or backtest single point)

        Args:
            candle_time: Optional datetime for backtest (uses this for timestamps instead of datetime.now())
            candles_by_tf: Optional pre-fetched candles (for backtest to avoid re-fetching)
            current_candle: Optional current M5 candle (for backtest position monitoring)

        Pipeline:
        1. Fetch data 6 TF
        2. G1: Pattern detection + select best setup
        3. G2: Pre-filter
        4. G3a: Claude decision
        5. G3b: Calc lot
        6. G3c: Guardian check
        7. G4: Log + Monitor
        """
        logger.info("\n" + "="*70)
        logger.info("🔄 Starting trading cycle...")
        logger.info("="*70)

        # Step 0: Monitor positions (ต้องรันทุก candle ก่อน pipeline)
        logger.info("\n[STEP 0] Monitoring positions...")
        closed = None  # Initialize before if-else block
        if current_candle:
            # check_and_update() expects candle dict (not separate params)
            closed = self.position_monitor.check_and_update(candle=current_candle)
            if closed:
                for t in closed:
                    logger.info(
                        f"✅ Position closed: {t['trade_id']} "
                        f"{t['result']} pnl={t.get('pnl', 0):.2f} "
                        f"reason={t.get('close_reason')} @ {t.get('close_price')}"
                    )

                    post_bot_event("plan_closed", f"{t['result']} {t.get('close_reason', '')}", {
                        "plan_id": t.get('plan_id', ''),
                        "trade_id": t.get('trade_id', ''),
                        "result": t.get('result', ''),
                        "close_reason": t.get('close_reason', ''),
                        "close_price": t.get('close_price', 0),
                        "pnl": t.get('pnl_usd', t.get('pnl', 0)),
                    })

                    # Update LocalDB whenever it's available (backtest always; SIM/LIVE
                    # only when running under api_server with a bot_id).
                    if self.local_db:
                        self.local_db.update_trade_result(
                            trade_id=t['trade_id'],
                            result=t['result'],
                            pnl=t.get('pnl_usd', t.get('pnl', 0)),
                            close_price=t.get('close_price', 0),
                            close_time=t.get('timestamp_close', candle_time),
                            close_reason=t.get('close_reason', ''),
                            mae_pip=t.get('mae_pip'),
                            mfe_pip=t.get('mfe_pip'),
                        )

                    # Notebook v3.4 stop_segments: on LOSS of a Scanner trade,
                    # mark its segment so the detector blocks new entries in
                    # that same trend segment until the trend resets.
                    self._record_scanner_loss_segment(t)
                    # Persist bot counters so a launcher restart doesn't reset
                    # consecutive_loss / realized_pnl mid-session.
                    if self.local_db and _BOT_ID:
                        self.local_db.upsert_bot_state(_BOT_ID, {
                            'consecutive_loss': self.portfolio_state_cache.get('consecutive_loss', 0),
                            'total_loss_pct':   self.portfolio_state_cache.get('total_loss_pct', 0),
                            'realized_pnl_usd': self.portfolio_state_cache.get('realized_pnl_usd', 0),
                            'last_candle_time': str(candle_time) if candle_time else None,
                        })
        else:
            # Fallback to old monitor_positions for simulate mode
            self.monitor_positions(current_candle=current_candle)

        # CRITICAL: Load portfolio state
        # - Backtest mode: Use in-memory cache for last_technical_price (duplicate prevention)
        #   Reload other fields from Sheets (active_plan_id, consecutive_loss updated by monitor)
        # - Simulate/Live mode: Reload from Sheets (to get fresh state)
        if self.is_backtest:
            # Backtest mode: Use in-memory cache for critical fields (prevent Sheets sync race)
            # 1. Load fresh state from Sheets (for consecutive_loss, realized_pnl, etc.)
            portfolio_state = self.sheets_logger.get_portfolio_state()

            # 2. Update from Step 0 closed trades (if any)
            if current_candle and candle_time and closed:
                for t in closed:
                    if t.get('result') == 'LOSS':
                        portfolio_state['consecutive_loss'] = portfolio_state.get('consecutive_loss', 0) + 1
                    elif t.get('result') == 'WIN':
                        portfolio_state['consecutive_loss'] = 0
                    portfolio_state['realized_pnl_usd'] = portfolio_state.get('realized_pnl_usd', 0) + t.get('pnl', 0)

            # 3. Override critical fields from cache (always use cache, never Sheets)
            #    - active_plan_id: Prevents duplicate plans (Sheets sync delay)
            #    - last_technical_price: Prevents duplicate twin_candle (Sheets sync delay)
            #    - last_plan_chart_type: Used with last_technical_price
            portfolio_state['active_plan_id'] = self.portfolio_state_cache.get('active_plan_id', '')
            portfolio_state['last_technical_price'] = self.portfolio_state_cache.get('last_technical_price', 0.0)
            portfolio_state['last_plan_chart_type'] = self.portfolio_state_cache.get('last_plan_chart_type', '')
            portfolio_state['last_signal_bar'] = self.portfolio_state_cache.get('last_signal_bar', 0)
            portfolio_state['current_bar'] = getattr(self, '_current_bar_idx', 0)
            portfolio_state['active_plans_by_pattern'] = dict(
                self.portfolio_state_cache.get('active_plans_by_pattern', {}) or {}
            )

            # 4. Check if plan closed (clear cache if no pending orders)
            pending_count = len(self.position_monitor.get_open_orders())
            if pending_count == 0 and portfolio_state['active_plan_id']:
                logger.info(f"Plan {portfolio_state['active_plan_id']} fully closed → clearing cache")
                portfolio_state['active_plan_id'] = ''
                self.portfolio_state_cache['active_plan_id'] = ''

            # 4b. Per-pattern slot cleanup — clear pattern slot whose orders all closed
            open_orders = self.position_monitor.get_open_orders()
            open_patterns = set()
            for o in open_orders:
                p = (o.get('pattern') or o.get('chart_type') or '').upper()
                if p:
                    open_patterns.add(p)
            cleaned_pat_map = {
                pat: pid for pat, pid in portfolio_state['active_plans_by_pattern'].items()
                if pat in open_patterns
            }
            if len(cleaned_pat_map) != len(portfolio_state['active_plans_by_pattern']):
                cleared = set(portfolio_state['active_plans_by_pattern']) - set(cleaned_pat_map)
                logger.info(f"Per-pattern cache cleanup — cleared: {sorted(cleared)}")
            portfolio_state['active_plans_by_pattern'] = cleaned_pat_map
            self.portfolio_state_cache['active_plans_by_pattern'] = dict(cleaned_pat_map)

            # 5. Update cache with current state
            self.portfolio_state_cache = portfolio_state
            logger.debug(f"Cache: active_plan={portfolio_state['active_plan_id']}, "
                        f"pending={pending_count}, last_tech={portfolio_state['last_technical_price']:.2f}")
        else:
            # Simulate/Live mode: reload from Sheets
            portfolio_state = self.sheets_logger.get_portfolio_state()
            logger.debug(f"Simulate mode: reloaded from Sheets")

        # Debug: Log portfolio state for Guardian checks
        logger.info(f"Portfolio state: active_plan={portfolio_state.get('active_plan_id', '')}, "
                    f"last_tech_price={portfolio_state.get('last_technical_price', 0):.2f}")

        # Step 0b: Daily/Weekly/Monthly triggers
        current_date = candle_time.date() if candle_time else datetime.now().date()

        # Phase II: Reflector removed (not needed in backtest)
        # Daily reflection skipped in Phase II

        # Weekly Strategist — รันทุก 7 วัน (analysis only)
        if self.weekly_strategist and should_run_weekly(self.last_weekly_date, current_date):
            logger.info("\n[Agent C] Running Weekly Strategist...")
            history = self.sheets_logger.get_recent_trades(limit=100) if self.sheets_logger.enabled else []
            stats = aggregate_weekly_stats(history)

            if not stats.get("insufficient_data"):
                weekly_result = self.weekly_strategist.analyze(stats)
                self.weekly_stats = stats
                self.reflection_summary = weekly_result["performance_context"]
                logger.info(f"✓ Weekly analysis: {weekly_result['overall_assessment']}")
                logger.info(f"  Reflection: {self.reflection_summary}")

            self.last_weekly_date = current_date

        # Monthly Evolver (Agent D) — รันทุก 30 วัน
        if self.monthly_evolver and should_run_monthly(self.last_monthly_date, current_date):
            logger.info("\n[Agent D] Running Monthly Evolver...")
            history = self.sheets_logger.get_recent_trades(limit=200) if self.sheets_logger.enabled else []
            stats = aggregate_monthly_stats(history)

            if not stats.get("insufficient_data"):
                monthly_result = self.monthly_evolver.analyze(stats)
                logger.info(f"✓ Monthly analysis: {len(monthly_result['proposals'])} proposals")
                if monthly_result['proposals']:
                    logger.info(f"  ⚠️ Proposals saved — human review required")

            self.last_monthly_date = current_date

        # Step 1: Fetch data
        if candles_by_tf is None:
            logger.info("\n[STEP 1] Fetching market data...")
            candles_by_tf = self._fetch_data_all_tf()
        else:
            logger.info("\n[STEP 1] Fetching market data...")
            # Log pre-fetched data from backtest
            for tf in TIMEFRAMES:
                if tf in candles_by_tf and candles_by_tf[tf]:
                    logger.info(f"✓ {tf}: {len(candles_by_tf[tf])} candles (resampled)")
                else:
                    logger.warning(f"⚠ {tf}: no data")

        if not candles_by_tf:
            logger.error("Failed to fetch data")
            return

        # CRITICAL: Extract candle_time and current_candle from fetched data (simulate mode fix)
        # In simulate mode, candle_time=None → need to use latest candle timestamp
        # In backtest mode, candle_time and current_candle are already passed in
        if candle_time is None or current_candle is None:
            # Get timestamp and current_candle from first available TF (usually M5)
            for tf in TIMEFRAMES:
                if tf in candles_by_tf and candles_by_tf[tf]:
                    last_candle = candles_by_tf[tf][-1]  # Most recent candle

                    # Extract candle_time if needed
                    if candle_time is None and 'timestamp' in last_candle:
                        candle_time = last_candle['timestamp']
                        if isinstance(candle_time, str):
                            from dateutil import parser
                            candle_time = parser.parse(candle_time)
                        logger.debug(f"Extracted candle_time from {tf}: {candle_time.isoformat()}")

                    # Extract current_candle if needed (for position monitoring)
                    if current_candle is None:
                        current_candle = last_candle
                        logger.debug(f"Extracted current_candle from {tf}")

                    break

        # Step 2: Signal Engine (replaces G1 Pattern Detection)
        active_tf = os.getenv('BACKTEST_TIMEFRAME', 'M5').upper()
        logger.info(f"\n[STEP 2] Signal Engine ({active_tf} Single TF)...")
        world_state = run_signal_engine(
            candles_by_tf=candles_by_tf,
            portfolio=self.balance,
            mountain_state=self.mountain_state,
            scanner_state=self.scanner_state,
        )

        # Update state from Signal Engine output (mutated in place by detectors)
        self.mountain_state = world_state.get('mountain_state')
        self.scanner_state = world_state.get('scanner_state')

        # Update latest_candle for dashboard chart
        if current_candle and candle_time:
            try:
                update_bot_state({
                    "latest_candle": {
                        "time": int(candle_time.timestamp()),
                        "open": current_candle.get("open", 0),
                        "high": current_candle.get("high", 0),
                        "low": current_candle.get("low", 0),
                        "close": current_candle.get("close", 0),
                    }
                })
            except Exception as e:
                logger.debug(f"Failed to update latest_candle: {e}")

        # ── Tier 1 heartbeat: per-cycle snapshot for Dashboard ────────
        # Posted EVERY cycle (including "Chart unclear" skips) so the UI knows
        # the bot is alive and processing. Lives in bots[id]['heartbeat'] —
        # not in the events panel.
        signal_obj = world_state.get('signal')
        chart_type_hb = world_state.get('chart_type', 'unclear')
        post_bot_heartbeat({
            "tf": active_tf,
            "candle_time": candle_time.isoformat() if candle_time else None,
            "candle_close": current_candle.get("close") if current_candle else None,
            "candle_high": current_candle.get("high") if current_candle else None,
            "candle_low": current_candle.get("low") if current_candle else None,
            "R55_usd": world_state.get('range', {}).get('usd'),
            "R55_pip": world_state.get('range', {}).get('pip'),
            "session": world_state.get('session'),
            "chart_type": chart_type_hb,
            "skip_reason": world_state.get('skip_reason'),
            # Tier 2: per-strategy SKIP reasons (only present when that
            # strategy ran and didn't fire a signal). Empty dict = a signal
            # fired (or no strategy was active for this TF).
            "skip_reasons": world_state.get('skip_reasons', {}),
            "signal_pattern": signal_obj.pattern if signal_obj else None,
            "signal_direction": signal_obj.direction if signal_obj else None,
            "signal_rr": round(signal_obj.rr, 2) if signal_obj else None,
            "active_plan": (portfolio_state or {}).get('active_plan_id'),
            "balance": self.balance,
        })

        if chart_type_hb == 'unclear':
            skip_reason = world_state.get('skip_reason', 'Chart unclear')
            logger.info(f"❌ SKIP: {skip_reason}")
            # Heartbeat above carries the skip_reason — no event needed here.
            return

        signal = signal_obj
        if signal:
            logger.info(f"✓ Signal Engine: {signal.pattern} {signal.direction} → Entry={signal.entry:.2f}, "
                        f"SL={signal.sl:.2f}, TP={signal.tp_order:.2f}, R:R={signal.rr:.2f}, Lot={signal.lot}")
            post_bot_event("signal_detected", f"{signal.pattern} {signal.direction}", {
                "pattern": signal.pattern, "direction": signal.direction,
                "entry": signal.entry, "sl": signal.sl, "tp": signal.tp_order,
                "rr": signal.rr, "lot": signal.lot,
            })
        else:
            chart_type = world_state.get('chart_type')
            logger.info(f"✓ Signal Engine: {chart_type} (quality={world_state.get('quality', 0):.2f}) — No trade signal")
            # Same rationale — "no setup" is the steady state, not a notification.

        # Step 3: G2 Pre-filter
        logger.info("\n[STEP 3] G2 Pre-filter...")
        # Note: portfolio_state already reloaded after Step 0
        prefilter_result = self.g2.check(world_state, portfolio_state)

        if not prefilter_result['pre_approved']:
            logger.info(f"❌ SKIP: {prefilter_result['skip_reason']}")
            post_bot_event("signal_skipped", prefilter_result['skip_reason'], {"stage": "g2_prefilter", "reason": prefilter_result['skip_reason']})
            update_session_stats(self.session_stats, None, g2_blocked=True)
            return

        logger.info("✓ G2: Pre-filter PASSED")

        # Step 3a: Decision — AUTO_APPROVE (Signal Engine is authoritative)
        # Phase II: no Claude per trade. Signal Engine output is taken as-is and
        # only re-checked by G3c Guardian (Python rules) below.
        logger.info("\n[STEP 3a] Decision: AUTO_APPROVE (no AI call)")

        signal = world_state.get('signal')
        if not signal:
            logger.error("❌ No signal from Signal Engine")
            return

        # Decision dict kept for compatibility with downstream Sheets/LocalDB writers.
        decision = {
            'action': signal.direction,
            'entry': signal.entry,
            'sl': signal.sl,
            'tp': signal.tp_order,
            'lot': signal.lot,
            'rr_ratio': signal.rr,
            'confidence': 1.0,  # Signal Engine is deterministic
            'setup': signal.pattern.lower() if hasattr(signal, 'pattern') else 'unknown',
            'skip_reason': None
        }

        # llm_log kept for Sheets/LocalDB schema compatibility — always $0/no tokens.
        llm_log = {
            'action': 'AUTO_APPROVE',
            'total_tokens': 0,
            'cost_usd': 0.0,
            'cache_hit': False
        }

        logger.info(f"✓ Signal Engine: {decision['action']} @ {decision['entry']:.2f} "
                    f"(SL={decision['sl']:.2f}, TP={decision['tp']:.2f}, R:R={decision.get('rr_ratio', 0):.2f})")

        # Step 3b: Lot sizing — Signal Engine is authoritative (no AI per trade).
        # Same path for BACKTEST / SIM / LIVE: take signal.lot, override to 0.01
        # only when WINRATE_TEST=true. Risk Manager (Haiku) was removed —
        # criteria are fully captured in the Python strategies.
        signal = world_state.get('signal')
        lot = signal.lot if signal and hasattr(signal, 'lot') else 0.01
        if os.getenv('WINRATE_TEST', 'false').lower() == 'true':
            lot = 0.01
        logger.info(f"\n[STEP 3b] Lot from Signal Engine: {lot:.2f} (no AI call)")

        # Step 3c: Guardian Check (legacy — final safety check)
        logger.info("\n[STEP 3c] Guardian Risk Gate...")

        # Create lot_info for guardian (compatibility)
        lot_info = {
            'lot_total': lot,
            'suggested_orders': 1
        }

        guardian_result = guardian_check(decision, lot_info, portfolio_state)

        if not guardian_result['approved']:
            logger.warning(f"❌ Guardian BLOCK: {guardian_result['block_reason']} (by {guardian_result['blocked_by']})")
            return

        logger.info("✓ Guardian: APPROVED")

        # Step 4: Create Order Plan
        logger.info("\n[STEP 4] Creating Order Plan...")

        # Calculate max_loss_usd from Signal Engine data (backtest-compatible)
        signal = world_state.get('signal')
        if signal and hasattr(signal, 'risk_pip'):
            max_loss_usd = (signal.risk_pip / 100.0) * lot
        else:
            # Fallback: calculate from entry-SL distance
            sl_distance_pip = abs(decision['entry'] - decision['sl']) * 100
            max_loss_usd = (sl_distance_pip / 100.0) * lot

        # Create order (1 order per plan)
        order = {
            'order_num': 1,
            'order_type': 'MARKET',
            'action': decision['action'],
            'entry': decision['entry'],
            'sl': decision['sl'],
            'tp': decision['tp'],
            'lot': lot,
            'rr_ratio': decision.get('rr_ratio', 0)
        }

        plan = {
            'lot_total': lot,
            'total_orders': 1,
            'max_loss_usd': max_loss_usd,
            'orders': [order]
        }

        logger.info(f"✓ Order created: {order['action']} @ {order['entry']:.2f}, "
                    f"lot={lot:.2f}, R:R={order['rr_ratio']:.2f}")

        # Determine mode for plan/trade ID prefix
        # PT- backtest | SM- simulate (paper broker, real-time data) | RT- live (real orders)
        if self.trading_mode in ('micro', 'live'):
            id_mode = 'live'
        elif self.is_backtest:
            id_mode = 'backtest'
        else:
            id_mode = 'simulate'
        plan_id = generate_plan_id(candle_time=candle_time, mode=id_mode)

        # Mountain trailing metadata — attach signal.details to orders for 3-stage trailing
        # MAI_RUAY / others: trail_meta = None → position_monitor skips trailing (per user spec)
        signal = world_state.get('signal')
        is_mountain = signal and getattr(signal, 'pattern', '').upper() == 'MOUNTAIN'

        # Generate trade IDs for each order and set initial state
        orders_with_ids = []
        for order in plan['orders']:
            order['trade_id'] = generate_trade_id(plan_id, order['order_num'], candle_time=candle_time, mode=id_mode)
            order['plan_id'] = plan_id  # Required for portfolio state updates
            order['result'] = 'PENDING'  # Required for PositionMonitor
            order['entry_price'] = order['entry']  # Alias for compatibility
            order['sl_price'] = order['sl']
            order['tp_price'] = order['tp']
            order['lot_size'] = order['lot']
            # Attach trail_meta — Mountain only. Each order gets its own dict so stage tracks per-order.
            if is_mountain:
                d = signal.details or {}
                order['trail_meta'] = {
                    'stage':      0,
                    'tp1':        float(d.get('tp1') or 0),
                    'tp2_base':   float(d.get('tp2_base') or d.get('tp2') or 0),
                    'tech_point': float(d.get('tech_point') or d.get('base_lo') or 0),
                    'height':     float(d.get('height') or 0),  # pip
                }
            orders_with_ids.append(order)

        # Prepare decision for Sheets (add 'technique' field from signal.pattern)
        decision_for_sheets = decision.copy()
        decision_for_sheets['technique'] = (
            signal.pattern.lower()
            if signal and hasattr(signal, 'pattern')
            else decision.get('setup', 'none')
        )

        # ── Execute via broker FIRST — never log/track an order MT5 rejected ──
        # Previously we logged Sheets/LocalDB + added to position_monitor BEFORE
        # the broker call, which left zombie PENDING rows when MT5 returned
        # "Invalid stops" or similar. Those zombies kept active_plan_id pinned
        # and blocked future Mountain/MaiRuay signals.
        if self.broker is not None:
            logger.info(f"\n[Broker] Executing {len(orders_with_ids)} order(s)...")
            trail_meta = None
            if signal and getattr(signal, 'pattern', '').upper() == 'MOUNTAIN':
                trail_meta = getattr(signal, 'details', None) or {}
            for order in orders_with_ids:
                ticket = self.broker.open_position(
                    action=order['action'],
                    lot=order['lot'],
                    sl=order['sl'],
                    tp=order['tp'],
                    plan_id=plan_id,
                    candle_time=candle_time,
                    trade_id=order['trade_id'],
                    entry_price=order.get('entry'),
                    trail_meta=trail_meta,
                )
                if ticket:
                    order['broker_ticket'] = ticket
                    logger.info(f"✓ Order {order['trade_id']} opened as ticket #{ticket}")
                else:
                    logger.error(f"✗ Failed to open order {order['trade_id']} — will not be tracked")

            orders_with_ids = [o for o in orders_with_ids if o.get('broker_ticket')]
            if not orders_with_ids:
                logger.warning("All orders failed at broker — aborting plan (no Sheets/DB/monitor entries)")
                return

        # Log to Sheets
        self.sheets_logger.log_plan_open(plan_id, orders_with_ids, decision_for_sheets, world_state, llm_log, candle_time=candle_time)

        # Log to LocalDB whenever it's available (backtest always; SIM/LIVE only
        # when running under api_server with a bot_id assigned).
        # Snapshot analytics fields at the moment we open (used by both DB
        # insert and position_monitor attachment). R55 captures volatility;
        # signal.details carries pattern-specific strength (Mountain height,
        # MaiRuay father_pct, Scanner segment_id, etc.)
        import json as _json
        r55_at_open = (world_state.get('range') or {}).get('pip')
        sig_details = getattr(signal, 'details', None) if signal else None
        try:
            details_json = _json.dumps(sig_details, default=str) if sig_details else None
        except Exception:
            details_json = None
        # Scanner v3.4 segment_id — stored on each trade so the stop-on-loss
        # filter in scanner_state knows which segment was lost. None for
        # non-Scanner trades (Mountain / MaiRuay don't use segments).
        scanner_seg_id = (sig_details or {}).get('segment_id') if sig_details else None

        if self.local_db:
            for order in orders_with_ids:
                self.local_db.insert_trade({
                    'trade_id': order['trade_id'],
                    'bot_id': _BOT_ID or None,
                    'plan_id': plan_id,
                    'order_num': order.get('order_num', 1),
                    'timestamp_open': candle_time.isoformat() if candle_time else datetime.now().isoformat(),
                    'timeframe': world_state.get('selected_tf', 'M5'),
                    'chart_type': world_state.get('chart_type', ''),
                    'technique': decision_for_sheets.get('technique', ''),
                    'action': order['action'],
                    'entry_price': order['entry'],
                    'sl_price': order['sl'],
                    'tp_price': order['tp'],
                    'lot_size': order['lot'],
                    'lot_total_plan': lot,
                    'rr_ratio': decision.get('rr_ratio', 0),
                    'confidence': decision.get('confidence', 0),
                    'rsi_14': world_state.get('metadata', {}).get('rsi_14', 50),
                    'session': world_state.get('session', ''),
                    'ai_reason': decision.get('reason', ''),
                    'llm_tokens': llm_log.get('total_tokens', 0),
                    'llm_cost_usd': llm_log.get('cost_usd', 0),
                    'result': 'PENDING',
                    'trailing_sl': order['sl'],
                    'r55_pip_at_open': r55_at_open,
                    'pattern_details_json': details_json,
                    'scanner_segment_id': scanner_seg_id,
                })

        # Attach scanner_segment_id to each order dict before handing to the
        # position monitor — the close-path needs it to mark the segment as
        # STOPPED on a LOSS (notebook v3.4 stop_segments behavior).
        for _o in orders_with_ids:
            _o['scanner_segment_id'] = scanner_seg_id

        # Add to position monitor (only orders that actually went into MT5)
        self.position_monitor.add_orders(orders_with_ids)

        # Notify Dashboard about plan opened (per-order event so each leg shows up)
        for order in orders_with_ids:
            post_bot_event("plan_opened", f"{order.get('action', '?')} {order.get('lot_size', order.get('lot', 0))} lot", {
                "plan_id": plan_id,
                "trade_id": order.get('trade_id', ''),
                "action": order.get('action', ''),
                "entry": order.get('entry_price', order.get('entry', 0)),
                "sl": order.get('sl_price', order.get('sl', 0)),
                "tp": order.get('tp_price', order.get('tp', 0)),
                "lot": order.get('lot_size', order.get('lot', 0)),
                "pattern": (signal.pattern if signal else ''),
            })

        # Update portfolio state (14 fields)
        portfolio_state['active_plan_id'] = plan_id
        portfolio_state['open_plans_count'] = 1  # Currently single plan only
        portfolio_state['total_risk_pct'] = RISK_CONFIG['risk_per_plan_pct']  # 0.10 (10%)
        portfolio_state['open_orders_count'] = len(orders_with_ids)
        portfolio_state['total_open_lot'] = lot  # From Agent B

        # Update last technical price (for duplicate prevention)
        # Signal Engine provides entry price (not twin_candle)
        signal = world_state.get('signal')
        portfolio_state['last_technical_price'] = (
            signal.entry if signal and hasattr(signal, 'entry') else 0.0
        )
        portfolio_state['last_plan_chart_type'] = world_state.get('chart_type', '')

        logger.info(f"Portfolio state updated: last_technical_price={portfolio_state['last_technical_price']:.2f}, "
                    f"chart_type={portfolio_state['last_plan_chart_type']}")

        self.sheets_logger.update_portfolio_state(portfolio_state)

        # CRITICAL: Update cache immediately in backtest mode (prevent Sheets sync race)
        if hasattr(self, 'portfolio_state_cache'):
            self.portfolio_state_cache['active_plan_id'] = plan_id
            self.portfolio_state_cache['last_technical_price'] = portfolio_state['last_technical_price']
            self.portfolio_state_cache['last_plan_chart_type'] = portfolio_state['last_plan_chart_type']
            self.portfolio_state_cache['last_signal_bar'] = getattr(self, '_current_bar_idx', 0)
            # Per-pattern active plan map — แต่ละ strategy ถือ slot ของตัวเอง
            sig = world_state.get('signal')
            sig_pattern = sig.pattern if sig and hasattr(sig, 'pattern') else ''
            if sig_pattern:
                pat_map = dict(self.portfolio_state_cache.get('active_plans_by_pattern', {}) or {})
                pat_map[sig_pattern] = plan_id
                self.portfolio_state_cache['active_plans_by_pattern'] = pat_map
            logger.info(f"✓ Cache updated: active_plan={plan_id} (pattern={sig_pattern}), last_tech={portfolio_state['last_technical_price']:.2f}, last_signal_bar={self.portfolio_state_cache['last_signal_bar']}")

        # Update session stats (track total plans)
        update_session_stats(self.session_stats, llm_log, opened_plan=True)

        logger.info(f"✓ G4: Plan {plan_id} logged ({len(orders_with_ids)} orders)")
        logger.info("\n" + "="*70)
        logger.info("✅ Trading cycle completed successfully!")
        logger.info("="*70)

    def _fetch_data_all_tf(self) -> Dict:
        """
        Fetch data for all 6 timeframes (OPTIMIZED)

        New approach: Fetch M5 once, resample to other TFs
        Reduces API calls from 6 → 2 (M5 + M1)

        Returns:
            {
                'H4': [55 candles],
                'H1': [55 candles],
                ...
            }
        """
        try:
            # Active TF follows env BACKTEST_TIMEFRAME (set by /api/start with user's TopBar selection)
            active_tf = os.getenv('BACKTEST_TIMEFRAME', 'M5').upper()

            # Use optimized method: fetch active TF directly (avoid resample mismatch)
            candles_by_tf = self.connector.get_all_timeframes_optimized(
                self.symbol,
                base_tf=active_tf,
                count=CANDLES_LOOKBACK
            )

            # Log results
            for tf in TIMEFRAMES:
                if tf in candles_by_tf and candles_by_tf[tf]:
                    logger.info(f"✓ {tf}: {len(candles_by_tf[tf])} candles (resampled)")
                else:
                    logger.warning(f"⚠ {tf}: no data")

            return candles_by_tf

        except Exception as e:
            logger.error(f"Optimized fetch failed: {e}, falling back to individual fetches")

            # Fallback to old method if optimization fails
            candles_by_tf = {}
            for tf in TIMEFRAMES:
                try:
                    candles = self.connector.get_latest_candles(
                        self.symbol,
                        timeframe=tf,
                        count=CANDLES_LOOKBACK
                    )

                    if candles and len(candles) >= CANDLES_LOOKBACK:
                        candles_by_tf[tf] = candles
                        logger.info(f"✓ Fetched {tf}: {len(candles)} candles")
                    else:
                        logger.warning(f"⚠ {tf}: insufficient data")

                except Exception as e2:
                    logger.error(f"Failed to fetch {tf}: {e2}")

            return candles_by_tf

    def monitor_positions(self, current_candle=None):
        """
        Monitor open positions and update when hit SL/TP
        (เรียกทุก candle close หรือทุก cycle)

        Args:
            current_candle: Optional M5 candle for backtest (dict with high/low/close)
        """
        open_orders = self.position_monitor.get_open_orders()
        if not open_orders:
            return

        logger.info(f"\n[Position Monitor] Checking {len(open_orders)} open orders...")

        # Paper Mode: Use PaperBroker (real-time prices)
        if self.broker is not None:
            # Get candle_time for broker update
            if current_candle and 'timestamp' in current_candle:
                candle_time = current_candle['timestamp']
                if isinstance(candle_time, str):
                    from dateutil import parser
                    candle_time = parser.parse(candle_time)
            else:
                candle_time = datetime.now()

            # Update running MAE/MFE on every open order before the broker checks
            # for closes — this way the close event carries the final excursion
            # from the bar that triggered it (live mode doesn't iterate per
            # candle the way check_and_update does in backtest).
            if current_candle:
                from agents.g4_position_monitor import update_excursion_only
                update_excursion_only(open_orders, current_candle)

            # Update broker positions (check SL/TP with real prices)
            current_price = current_candle.get('close') if current_candle else None
            newly_closed = self.broker.update_positions(candle_time, current_price=current_price)

            # Sync closed positions to PositionMonitor + Sheets + LocalDB + Dashboard
            if newly_closed:
                logger.info(f"📄 Broker closed {len(newly_closed)} position(s)")
                for broker_pos in newly_closed:
                    broker_tid = broker_pos['trade_id']

                    # Match by prefix — many MT5 brokers truncate the position
                    # comment to 16 chars even though the docs say 31, so a
                    # full trade_id like "RT-20260511-124200-000000-1" comes
                    # back from history as "RT-20260511-1242". Use startswith
                    # so the original full id still maps to its close.
                    for order in open_orders:
                        order_tid = order.get('trade_id', '')
                        if order_tid == broker_tid or order_tid.startswith(broker_tid):
                            trade_id = order_tid  # canonical full id for downstream writes
                            # Update order state
                            order['result'] = broker_pos['result']
                            order['close_price'] = broker_pos['close_price']
                            order['close_reason'] = broker_pos['close_reason']
                            order['pnl_usd'] = broker_pos['pnl']
                            order['timestamp_close'] = broker_pos['close_time']

                            # Mark segment as STOPPED on a Scanner LOSS.
                            self._record_scanner_loss_segment({
                                'result': broker_pos['result'],
                                'scanner_segment_id': order.get('scanner_segment_id'),
                                'action': order.get('action'),
                                'trade_id': trade_id,
                            })

                            # Push close event to api_server so the Dashboard
                            # moves the order from Open → Closed in real time.
                            post_bot_event(
                                "plan_closed",
                                f"{broker_pos['result']} {broker_pos['close_reason']}",
                                {
                                    "plan_id": order.get('plan_id', ''),
                                    "trade_id": trade_id,
                                    "result": broker_pos['result'],
                                    "close_reason": broker_pos['close_reason'],
                                    "close_price": broker_pos['close_price'],
                                    "pnl": broker_pos['pnl'],
                                },
                            )

                            # Write the close to LocalDB (mirrors the
                            # check_and_update path; was missing here, so
                            # SIM/LIVE bots never cleared PENDING in DB).
                            if self.local_db:
                                try:
                                    # MAE/MFE were accumulated on the in-memory
                                    # order dict by update_excursion_only() during
                                    # the cycle loop (live mode), or by the candle
                                    # check in check_positions_on_candle_close().
                                    self.local_db.update_trade_result(
                                        trade_id=trade_id,
                                        result=broker_pos['result'],
                                        pnl=broker_pos['pnl'],
                                        close_price=broker_pos['close_price'],
                                        close_time=broker_pos['close_time'],
                                        close_reason=broker_pos['close_reason'],
                                        mae_pip=order.get('mae_pip'),
                                        mfe_pip=order.get('mfe_pip'),
                                    )
                                except Exception as e:
                                    logger.error(f"LocalDB update_trade_result failed for {trade_id}: {e}")
                            if self.local_db and _BOT_ID:
                                try:
                                    self.local_db.upsert_bot_state(_BOT_ID, {
                                        'consecutive_loss': self.portfolio_state_cache.get('consecutive_loss', 0),
                                        'total_loss_pct':   self.portfolio_state_cache.get('total_loss_pct', 0),
                                        'realized_pnl_usd': self.portfolio_state_cache.get('realized_pnl_usd', 0),
                                        'last_candle_time': broker_pos.get('close_time'),
                                    })
                                except Exception as e:
                                    logger.warning(f"upsert_bot_state failed: {e}")

                            # Update Sheets
                            if self.sheets_logger:
                                try:
                                    self.sheets_logger.update_order_close(
                                        trade_id=trade_id,
                                        result=broker_pos['result'],
                                        close_price=broker_pos['close_price'],
                                        close_reason=broker_pos['close_reason'],
                                        pnl_usd=broker_pos['pnl'],
                                        timestamp_close=broker_pos['close_time']
                                    )
                                    logger.info(f"✓ [{trade_id}] Sheets updated: {broker_pos['result']}")
                                except Exception as e:
                                    logger.error(f"✗ [{trade_id}] Failed to update Sheets: {e}")

                            break

                # Update portfolio state after closes
                if self.sheets_logger:
                    try:
                        # Get closed plan IDs
                        closed_plan_ids = {pos['plan_id'] for pos in newly_closed}

                        for plan_id in closed_plan_ids:
                            # Check if all orders in plan are closed
                            plan_orders = [o for o in self.position_monitor.open_orders
                                           if o.get('plan_id') == plan_id]
                            all_closed = all(o.get('result') in ['WIN', 'LOSS'] for o in plan_orders)

                            if all_closed:
                                plan_pnl = sum(o.get('pnl_usd', 0) for o in plan_orders)
                                plan_result = 'WIN' if plan_pnl > 0 else 'LOSS'

                                logger.info(f"[{plan_id}] Plan fully closed: {plan_result} (P&L: ${plan_pnl:.2f})")

                                # Update portfolio state
                                portfolio_state = self.sheets_logger.get_portfolio_state()

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
                                    portfolio_state['consecutive_loss'] = 0

                                # Update realized P&L
                                portfolio_state['realized_pnl_usd'] = portfolio_state.get('realized_pnl_usd', 0) + plan_pnl

                                self.sheets_logger.update_portfolio_state(portfolio_state)
                                logger.info(f"[{plan_id}] Portfolio state updated (consecutive_loss={portfolio_state['consecutive_loss']})")

                    except Exception as e:
                        logger.error(f"Failed to update portfolio state after closes: {e}")

            return

        # Backtest/Simulate Mode: Use candle-based monitoring
        # Get current candle
        if current_candle is None:
            latest = self.connector.get_latest_candles(self.symbol, timeframe='M5', count=1)
            if not latest:
                logger.warning("Cannot fetch latest candle for monitoring")
                return
            current_candle = latest[0]

        if not current_candle:
            return

        self.position_monitor.check_and_update(current_candle)

    def _resample_m5_to_all_tf(self, m5_candles: List[Dict], base_tf: str = 'M5') -> Dict[str, List[Dict]]:
        """
        Resample candles from base_tf → all larger timeframes (for backtest)

        Args:
            m5_candles: List of candles at base_tf (at least 55 candles recommended)
            base_tf: Source timeframe (M1, M5, etc.) — env BACKTEST_TIMEFRAME

        Returns:
            Dict {tf: [candles]} for base_tf and all larger TFs
        """
        import pandas as pd

        if len(m5_candles) < 20:
            return {}

        # Convert to DataFrame
        df = pd.DataFrame(m5_candles)
        df['time'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('time')

        TF_MINUTES = {'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30, 'H1': 60, 'H4': 240}
        base_min = TF_MINUTES.get(base_tf.upper(), 5)
        result: Dict[str, List[Dict]] = {}

        # Only resample to larger TFs (downsample), copy base as-is
        for tf, mins in TF_MINUTES.items():
            if mins < base_min:
                # Smaller than base — can't downsample, leave empty
                result[tf] = []
                continue
            if mins == base_min:
                df_resampled = df.copy()
            else:
                freq = f'{mins}min'
                df_resampled = df.resample(freq).agg({
                    'open': 'first', 'high': 'max', 'low': 'min',
                    'close': 'last', 'volume': 'sum'
                }).dropna()

            df_final = df_resampled.tail(CANDLES_LOOKBACK).reset_index()
            candles = df_final.to_dict('records')
            for candle in candles:
                if 'time' in candle:
                    candle['timestamp'] = candle['time']
            result[tf] = candles

        return result

    def run_backtest(self, start_date: str, end_date: str):
        """
        Run backtest mode

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Pipeline:
        - วนลูปตาม candles ย้อนหลัง (M5)
        - แต่ละ candle close → รัน pipeline
        - สะสม results → export สรุป
        """
        from datetime import datetime, timedelta
        import pandas as pd

        logger.info("="*70)
        logger.info("🔄 BACKTEST MODE")
        logger.info("="*70)
        logger.info(f"Period: {start_date} → {end_date}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Balance: ${self.balance:,.2f}")
        logger.info("="*70)

        # Parse dates
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            return

        # Validate date range (yfinance intraday limit = 60 days)
        days_diff = (end - start).days
        if days_diff > 60:
            logger.warning(f"⚠️  Date range > 60 days ({days_diff} days)")
            logger.warning("yfinance intraday data limited to last 60 days")
            logger.warning("Consider using hourly/daily intervals for older data")

        # Fetch all M5 candles for backtest period
        logger.info("\n📊 Fetching historical M5 candles...")
        logger.info(f"Using TradingView data ({self.symbol}/OANDA spot prices)")

        # Active timeframe — env override (default M5)
        backtest_tf = os.getenv('BACKTEST_TIMEFRAME', 'M5').upper()
        try:
            logger.info(f"Fetching {backtest_tf} candles for date range {start_date} → {end_date}...")
            all_m5_candles = self.connector.get_latest_candles(
                self.symbol,
                timeframe=backtest_tf,
                count=None,  # Not used when start_date/end_date provided
                start_date=start,
                end_date=end
            )

            if not all_m5_candles:
                logger.error(f"❌ No {backtest_tf} candles fetched for date range")
                return

            logger.info(f"✓ Fetched {len(all_m5_candles)} {backtest_tf} candles")
            logger.info(f"   First: {all_m5_candles[0]['timestamp']}")
            logger.info(f"   Last: {all_m5_candles[-1]['timestamp']}")

        except Exception as e:
            logger.error(f"Failed to fetch {backtest_tf} candles: {e}")
            import traceback
            traceback.print_exc()
            return

        # Load existing PENDING positions from Sheets (backtest continuity)
        logger.info("\n📋 Loading open positions from Sheets...")
        existing_trades = self.sheets_logger.get_pending_trades()
        if existing_trades:
            self.position_monitor.add_orders(existing_trades)
            logger.info(f"✓ Loaded {len(existing_trades)} open orders from previous run")
            for order in existing_trades:
                logger.info(f"  • {order['trade_id']}: {order['action']} @ {order['entry']} "
                           f"(SL: {order['sl']}, TP: {order['tp']})")
        else:
            logger.info("✓ No open positions to load (starting fresh)")

        # Load portfolio state ONCE before backtest loop (in-memory cache)
        # CRITICAL: Don't reload from Sheets every cycle (causes duplicate race condition)
        logger.info("\n💾 Loading portfolio state (cached for backtest)...")
        self.portfolio_state_cache = self.sheets_logger.get_portfolio_state()
        logger.info(f"✓ Cache initialized: active_plan={self.portfolio_state_cache.get('active_plan_id', '')}, "
                    f"last_tech={self.portfolio_state_cache.get('last_technical_price', 0):.2f}, "
                    f"chart_type={self.portfolio_state_cache.get('last_plan_chart_type', '')}")

        # Run backtest (loop through each M5 candle with forward walk)
        total_signals = 0
        total_plans = 0
        skipped_weekend = 0
        skipped_insufficient = 0

        for i, current_candle in enumerate(all_m5_candles):
            candle_time = current_candle.get('timestamp', datetime.now())
            self._current_bar_idx = i  # for cooldown tracking in G2

            # Skip weekends (Saturday=5, Sunday=6)
            if candle_time.weekday() >= 5:
                skipped_weekend += 1
                continue

            # Need at least 55 candles for analysis
            # Take 55 candles up to current index (not including future data!)
            start_idx = max(0, i - 54)
            m5_slice = all_m5_candles[start_idx:i+1]

            if len(m5_slice) < 20:
                skipped_insufficient += 1
                continue

            # Resample base_tf slice to all larger timeframes
            candles_by_tf = self._resample_m5_to_all_tf(m5_slice, base_tf=backtest_tf)

            if not candles_by_tf:
                continue

            # Log progress every 100 candles
            if (i + 1) % 100 == 0:
                logger.info(f"⏳ Processing candle {i+1}/{len(all_m5_candles)} ({candle_time})")

            # Run pipeline for this candle (with pre-fetched data)
            try:
                self.run_once(
                    candle_time=candle_time,
                    candles_by_tf=candles_by_tf,
                    current_candle=current_candle
                )
                total_signals += 1

            except Exception as e:
                logger.error(f"Error on {candle_time}: {e}")

        logger.info(f"\n⏭  Skipped {skipped_weekend} weekend candles")
        logger.info(f"⏭  Skipped {skipped_insufficient} candles (insufficient data)")

        # Force-close any remaining PENDING trades (backtest ended)
        if self.local_db:
            logger.info("\n🔄 Checking for PENDING trades to force-close...")
            pending_trades = self.local_db.get_pending_trades()

            if pending_trades:
                logger.warning(f"⚠️  {len(pending_trades)} PENDING trades at backtest end — force-closing as PENDING_EXPIRED")
                last_candle = all_m5_candles[-1]
                last_price = last_candle['close']
                last_time = last_candle.get('timestamp', datetime.now())

                for trade in pending_trades:
                    # PENDING_EXPIRED: P&L = 0 (ไม่นับ unrealized gains/losses)
                    # เหตุผล: backtest จบก่อนที่ position จะปิด → ไม่มี realized P&L
                    self.local_db.update_trade_result(
                        trade_id=trade['trade_id'],
                        result='PENDING_EXPIRED',
                        pnl=0,  # ← ต้องเป็น 0 เสมอ (ไม่คำนวณ unrealized)
                        close_price=last_price,
                        close_time=last_time,
                        close_reason='BACKTEST_END'
                    )
                    logger.info(f"  ✓ {trade['trade_id']}: PENDING_EXPIRED @ {last_price:.2f}")

            # Flush Sheets batch queue (write all pending updates)
            if self.sheets_logger.enabled:
                logger.info("\n📤 Flushing Sheets batch queue...")
                self.sheets_logger.set_batch_mode(False)  # This triggers flush

        # Summary (from LocalDB)
        if self.local_db:
            summary = self.local_db.get_summary()

            logger.info("\n" + "="*70)
            logger.info("📊 BACKTEST SUMMARY (LocalDB)")
            logger.info("="*70)
            logger.info(f"Period: {start_date} → {end_date}")
            logger.info(f"Total candles: {len(all_m5_candles)}")
            logger.info(f"Processed signals: {total_signals}")
            logger.info(f"Total trades: {summary['total']}")
            logger.info(f"  WIN: {summary['wins']} ({summary['wr_pct']:.1f}%)")
            logger.info(f"  LOSS: {summary['losses']}")
            logger.info(f"  PENDING: {summary['pending']}")
            logger.info(f"  PENDING_EXPIRED: {summary['expired']}")
            logger.info(f"Net P&L: ${summary['net_pnl']:.2f}")
            logger.info(f"Avg WIN: ${summary['avg_win']:.2f}" if summary['avg_win'] else "Avg WIN: N/A")
            logger.info(f"Avg LOSS: ${summary['avg_loss']:.2f}" if summary['avg_loss'] else "Avg LOSS: N/A")
            logger.info("="*70)

            # Pattern breakdown
            patterns = self.local_db.get_summary_by_pattern()
            if patterns:
                logger.info("\n📈 Pattern Breakdown:")
                for p in patterns:
                    total = p['total']
                    wins = p['wins']
                    wr = wins / total * 100 if total > 0 else 0
                    logger.info(f"  {p['pattern']:<15} {total:>3} trades  WR {wr:>5.1f}%  Net ${p['net_pnl_usd']:>8.2f}")

            # Check for remaining PENDING (should be 0 after force-close)
            if summary['pending'] > 0:
                logger.warning(f"\n⚠️  {summary['pending']} orders ยัง PENDING (unexpected!)")

        else:
            # Fallback to old summary (Sheets)
            logger.info("\n" + "="*70)
            logger.info("📊 BACKTEST SUMMARY")
            logger.info("="*70)
            logger.info(f"Period: {start_date} → {end_date}")
            logger.info(f"Total candles: {len(all_m5_candles)}")
            logger.info(f"Processed signals: {total_signals}")
            logger.info(f"Total plans: {self.session_stats['total_plans']}")
            logger.info("Win rate: Check Google Sheets")
            logger.info("="*70)

        # Print session summary with token usage and break-even analysis
        print_session_summary(self.session_stats, self.balance)

        # Check for remaining PENDING positions
        pending_remain = self.position_monitor.get_open_orders()
        if pending_remain:
            logger.warning("\n" + "="*70)
            logger.warning(f"⚠️  {len(pending_remain)} orders ยัง PENDING ตอนจบ backtest")
            logger.warning("="*70)
            for order in pending_remain:
                logger.warning(f"  • {order['trade_id']}: {order['action']} @ {order.get('entry', 0):.2f} "
                              f"(SL: {order.get('sl', 0):.2f}, TP: {order.get('tp', 0):.2f})")
            logger.warning("\n💡 แก้ไข:")
            logger.warning("  1. ขยาย --end-date ให้นานขึ้น (ให้ positions ปิด)")
            logger.warning("  2. หรือรัน backtest ต่อเนื่อง (จะ auto-load PENDING orders)")
            logger.warning("="*70)

        logger.info("\n✅ Backtest completed!")
        logger.info("📊 Full results: Check Google Sheets > Trade Log")


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='Tra(i)der Phase I v2.1')

    parser.add_argument('--winrate-test', action='store_true',
                        help='Winrate test mode (0.01 lot)')
    parser.add_argument('--simulate', action='store_true',
                        help='Simulate mode (default)')
    parser.add_argument('--backtest', action='store_true',
                        help='Backtest mode')
    parser.add_argument('--start', type=str,
                        help='Backtest start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str,
                        help='Backtest end date (YYYY-MM-DD)')
    parser.add_argument('--log-sheets', action='store_true',
                        help='Log to Google Sheets (for backtest mode)')
    parser.add_argument('--once', action='store_true',
                        help='Run once and exit (for testing)')
    parser.add_argument('--decision-engine',
                        choices=['claude', 'python'],
                        default='python',
                        help='Decision engine: claude (API) or python (rules-based, default)')

    # Trading mode CLI args (used when spawned from api_server /api/start) —
    # override bot_state values which are process-local and not shared across subprocesses.
    parser.add_argument('--mode', type=str, choices=['paper', 'micro', 'live'],
                        help='Trading mode: paper (sim) / micro (cent broker) / live (real broker)')
    parser.add_argument('--symbol', type=str,
                        help='Symbol e.g. XAUUSDc (override bot_state)')
    parser.add_argument('--tf', type=str, choices=['M1', 'M5', 'M15', 'M30', 'H1', 'H4'],
                        help='Timeframe (override bot_state)')
    parser.add_argument('--data-source', type=str, choices=['auto', 'mt5', 'yf', 'tv'],
                        default='auto', help='Data source for prices')
    parser.add_argument('--no-confirm', action='store_true',
                        help='Skip 2x real-money confirmation prompts (for headless / API-spawned runs)')

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()

    try:
        traider = TraiderMainLoop(args)

        if args.backtest:
            # Backtest mode
            if not args.start or not args.end:
                logger.error("❌ Backtest requires --start and --end dates")
                logger.error("Example: python main.py --backtest --start 2026-03-01 --end 2026-03-31")
                sys.exit(1)

            traider.run_backtest(args.start, args.end)

        elif args.once:
            # Run once and exit
            traider.run_once()

        else:
            # Run continuously — poll interval = active TF duration (capped 1h)
            # ตั้ง interval ตาม TF: M1=60s, M5=300s, M15=900s, M30=1800s, H1/H4=3600s
            tf_seconds = {
                'M1': 60, 'M5': 300, 'M15': 900,
                'M30': 1800, 'H1': 3600, 'H4': 3600,
            }
            active_tf = os.getenv('BACKTEST_TIMEFRAME', 'M5').upper()
            poll_secs = tf_seconds.get(active_tf, 300)
            logger.info(f"Running in continuous mode... TF={active_tf}, poll every {poll_secs}s (Ctrl+C to stop)")
            while True:
                traider.run_once()
                traider.monitor_positions()
                time.sleep(poll_secs)

    except KeyboardInterrupt:
        logger.info("\n\n👋 Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
