#!/usr/bin/env python3
"""
Tra(i)der Phase I v4.3 — Main Trading Loop

Pipeline: G1 → G2 → G3a (Analyst) → G3b (Risk Manager) → G3c (Guardian) → G4
Agents: A (Analyst), B (Risk Manager), C (Weekly), D (Monthly), Reflector (Daily)

V4.3 Updates:
- Twin Candle dual-role system (Swing + Entry with beauty scoring)
- Agent A uses System Prompt V4.3
- Reflector: Daily Python-only reflection ($0)
- Beauty score tracking throughout pipeline

Usage:
    python main.py --winrate-test  # Winrate test mode (0.01 lot)
    python main.py --simulate      # Simulate mode (normal lot)
    python main.py --backtest --start 2026-01-01 --end 2026-03-31
    python main.py --backtest --start 2026-04-04 --end 2026-04-10 --log-sheets  # Backtest with Sheets logging

Reference: XAUUSD_AI_Trading_System_v2.1.md, XAUUSD_System_PromptV43.md
"""

import os
import sys
import argparse
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List
from dotenv import load_dotenv

# Import agents (v4.3 — 4-Agent Architecture with Reflector)
from agents.g1_pattern_detector import G1PatternDetector  # DEPRECATED — use signal_engine instead
from agents.g2_prefilter import G2Prefilter
from agents.g3_analyst import G3AnalystAgent, build_grounding, verify_analyst_decision
from agents.g3_risk_manager import G3RiskManagerAgent, build_risk_context, verify_risk_decision
from agents.g4_weekly_strategist import G4WeeklyStrategist, aggregate_weekly_stats, should_run_weekly
from agents.g4_monthly_evolver import G4MonthlyEvolver, aggregate_monthly_stats, should_run_monthly
from agents.g4_reflector import Reflector, should_run_daily
from agents.g3_risk_gate import guardian_check  # Legacy guardian (still used)
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
        "symbol": "XAUUSDm",
        "trading_tf": "M5",
        "balance": 0.0
    }
    def update_bot_state(updates): pass
    def add_log(msg): pass

# Load environment
load_dotenv()

# Setup logging (force=True to override any previous config)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('traider.log'),
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
        symbol: Trading symbol (e.g., 'XAUUSDm', 'XAUUSD')

    Returns:
        PaperBroker instance if mode='paper', None otherwise
    """
    if mode == 'paper':
        logger.info(f"📄 Creating PaperBroker (mode={mode}, symbol={symbol})")
        return PaperBroker(symbol=symbol)
    else:
        # For 'micro' and 'live' modes, return None (use MT5 directly)
        logger.info(f"💹 Using MT5 direct trading (mode={mode}, symbol={symbol})")
        return None


# ============================================================================
# MAIN TRAIDER CLASS
# ============================================================================

class TraiderMainLoop:
    """Main trading loop for Tra(i)der Phase I v4.3 (4-Agent Architecture + Reflector)"""

    def __init__(self, args):
        """
        Initialize trading system

        Args:
            args: Parsed command-line arguments
        """
        self.args = args
        self.mode = 'winrate_test' if args.winrate_test else 'simulate'
        self.is_backtest = args.backtest if hasattr(args, 'backtest') else False

        # Use symbol from bot_state (from dashboard) or fallback to env var
        self.symbol = bot_state.get("symbol", os.getenv('BACKTEST_SYMBOL', 'XAUUSDm'))
        self.balance = float(os.getenv('ACCOUNT_BALANCE', '300'))

        # Get trading mode from bot_state (from dashboard)
        self.trading_mode = bot_state.get("mode", "paper")

        # Update bot_state with balance
        update_bot_state({"balance": self.balance})

        logger.info("="*70)
        logger.info("🤖 Tra(i)der Phase I v4.3 — AI Trading System (4-Agent + Reflector)")
        logger.info("="*70)
        logger.info(f"Mode: {self.mode}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Balance: ${self.balance:,.2f}")
        if self.is_backtest:
            logger.info(f"Backtest mode: Sheets logging {'ENABLED' if args.log_sheets else 'DISABLED'}")
        logger.info("="*70)

        # Initialize data connector (V4.3: auto-detect MT5 or TradingView)
        logger.info(f"📡 Initializing data connector...")
        self.connector = create_connector(
            mode="auto",
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

        # Initialize agents (v4.3 — 4-Agent Architecture + Reflector)
        logger.info("🤖 Initializing agents (V4.3: 4-Agent + Reflector)...")
        # G1 DEPRECATED — kept for backward compatibility, use Signal Engine instead
        # self.g1 = G1PatternDetector(config={'verbose': True})
        self.g2 = G2Prefilter(config={'verbose': True})

        # Agent A: Analyst (V4.20 Reviewer Mode)
        self.analyst = G3AnalystAgent(
            system_prompt_path='strategy/XAUUSD_System_Prompt_Reviewer.md',
            api_key=os.getenv('ANTHROPIC_API_KEY'),
            config={'verbose': True}
        )
        logger.info("✓ Agent A (Analyst) initialized — Reviewer Mode V4.20")

        # Agent B: Risk Manager (replaces g3_money_management.py)
        self.risk_manager = G3RiskManagerAgent(
            api_key=os.getenv('ANTHROPIC_API_KEY'),
            config={'verbose': True}
        )
        logger.info("✓ Agent B (Risk Manager) initialized — using Haiku")

        # Agent C: Weekly Strategist (new)
        self.weekly_strategist = G4WeeklyStrategist(
            api_key=os.getenv('ANTHROPIC_API_KEY'),
            config={'verbose': True}
        )
        logger.info("✓ Agent C (Weekly Strategist) initialized")

        # Agent D: Monthly Evolver (new)
        self.monthly_evolver = G4MonthlyEvolver(
            api_key=os.getenv('ANTHROPIC_API_KEY'),
            config={'verbose': True}
        )
        logger.info("✓ Agent D (Monthly Evolver) initialized")

        # Initialize G4
        # Enable sheets if: (1) simulate mode OR (2) backtest with --log-sheets flag
        sheets_enabled_override = None
        if self.is_backtest and hasattr(args, 'log_sheets'):
            sheets_enabled_override = args.log_sheets

        self.sheets_logger = SheetsLogger(enabled_override=sheets_enabled_override)
        self.position_monitor = PositionMonitor(sheets_logger=self.sheets_logger)
        logger.info("✓ Position Monitor initialized")

        # Set references for API server
        from api_server import set_sheets_logger, set_position_monitor, set_connector
        set_sheets_logger(self.sheets_logger)
        set_position_monitor(self.position_monitor)
        set_connector(self.connector)

        # Reflector: Daily reflection (Python only - $0)
        self.reflector = Reflector(sheets_logger=self.sheets_logger)
        logger.info("✓ Reflector initialized (Python only — $0 cost)")

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

        logger.info("✓ All agents initialized")

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

        # Step 0: Monitor existing positions (check SL/TP)
        logger.info("\n[STEP 0] Monitoring positions...")
        self.monitor_positions(current_candle=current_candle)

        # CRITICAL: Load portfolio state
        # - Backtest mode: Use in-memory cache for last_technical_price (duplicate prevention)
        #   Reload other fields from Sheets (active_plan_id, consecutive_loss updated by monitor)
        # - Simulate/Live mode: Reload from Sheets (to get fresh state)
        if hasattr(self, 'portfolio_state_cache'):
            # Backtest mode: Use in-memory cache for critical fields (prevent Sheets sync race)
            # 1. Load fresh state from Sheets (for consecutive_loss, realized_pnl, etc.)
            portfolio_state = self.sheets_logger.get_portfolio_state()

            # 2. Override critical fields from cache (always use cache, never Sheets)
            #    - active_plan_id: Prevents duplicate plans (Sheets sync delay)
            #    - last_technical_price: Prevents duplicate twin_candle (Sheets sync delay)
            #    - last_plan_chart_type: Used with last_technical_price
            portfolio_state['active_plan_id'] = self.portfolio_state_cache.get('active_plan_id', '')
            portfolio_state['last_technical_price'] = self.portfolio_state_cache.get('last_technical_price', 0.0)
            portfolio_state['last_plan_chart_type'] = self.portfolio_state_cache.get('last_plan_chart_type', '')

            # 3. Check if plan closed (clear cache if no pending orders)
            pending_count = len(self.position_monitor.get_open_orders())
            if pending_count == 0 and portfolio_state['active_plan_id']:
                logger.info(f"Plan {portfolio_state['active_plan_id']} fully closed → clearing cache")
                portfolio_state['active_plan_id'] = ''
                self.portfolio_state_cache['active_plan_id'] = ''

            # 4. Update cache with current state
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

        # Reflector — รันทุกวัน (Python only, $0)
        if should_run_daily(self.last_daily_date, current_date):
            logger.info("\n[Reflector] Running daily reflection...")
            history = self.sheets_logger.get_recent_trades(limit=50) if self.sheets_logger.enabled else []
            reflection_result = self.reflector.update(trade_history=history, force=False)
            self.reflection_summary = reflection_result['reflection_summary']
            logger.info(f"✓ Daily reflection: {self.reflection_summary}")
            self.last_daily_date = current_date

        # Weekly Strategist (Agent C) — รันทุก 7 วัน
        if should_run_weekly(self.last_weekly_date, current_date):
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
        if should_run_monthly(self.last_monthly_date, current_date):
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
        logger.info("\n[STEP 2] Signal Engine (M5 Single TF)...")
        world_state = run_signal_engine(
            candles_by_tf=candles_by_tf,
            portfolio=self.balance,
            mountain_state=self.mountain_state
        )

        # Update mountain_state from Signal Engine output
        self.mountain_state = world_state.get('mountain_state')

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

        if world_state.get('chart_type') == 'unclear':
            skip_reason = world_state.get('skip_reason', 'Chart unclear')
            logger.info(f"❌ SKIP: {skip_reason}")
            return

        signal = world_state.get('signal')
        if signal:
            logger.info(f"✓ Signal Engine: {signal.pattern} {signal.direction} → Entry={signal.entry:.2f}, "
                        f"SL={signal.sl:.2f}, TP={signal.tp_order:.2f}, R:R={signal.rr:.2f}, Lot={signal.lot}")
        else:
            logger.info(f"✓ Signal Engine: {world_state.get('chart_type')} (quality={world_state.get('quality', 0):.2f}) — No trade signal")

        # Step 3: G2 Pre-filter
        logger.info("\n[STEP 3] G2 Pre-filter...")
        # Note: portfolio_state already reloaded after Step 0
        prefilter_result = self.g2.check(world_state, portfolio_state)

        if not prefilter_result['pre_approved']:
            logger.info(f"❌ SKIP: {prefilter_result['skip_reason']}")
            update_session_stats(self.session_stats, None, g2_blocked=True)
            return

        logger.info("✓ G2: Pre-filter PASSED")

        # Step 3a: Agent A — Analyst (with Grounding + Post-verify)
        logger.info("\n[STEP 3a] Agent A — Analyst...")

        # Build grounding (Python คำนวณค่าสำคัญก่อนส่ง Claude)
        grounding = build_grounding(world_state, self.balance)
        logger.info(f"  Grounding: technical_price={grounding['technical_price']:.2f}, "
                    f"SL ref=10%:{grounding['sl_reference']['10pct_range_pip']:.0f}pip, "
                    f"20%:{grounding['sl_reference']['20pct_range_pip']:.0f}pip")

        # Call Agent A
        analyst_result = self.analyst.decide(
            world_state=world_state,
            balance=self.balance,
            portfolio_state=portfolio_state,
            reflection_summary=self.reflection_summary,
            grounding=grounding
        )

        if not analyst_result['success']:
            logger.error("❌ Agent A failed")
            return

        decision = analyst_result['decision']
        llm_log = analyst_result['llm_log']
        verify_errors = analyst_result['verify_errors']

        # Update session stats
        update_session_stats(
            self.session_stats,
            llm_log,
            opened_plan=(decision.get('action') != 'SKIP'),
            g2_blocked=False
        )

        # Log token usage
        logger.info(
            f"💰 Agent A: {llm_log.get('total_tokens', 0):,} tokens | "
            f"Cost: ${llm_log.get('cost_usd', 0):.4f} | "
            f"Cache: {'✅ HIT' if llm_log.get('cache_hit') else '❌ MISS'} | "
            f"Session: ${self.session_stats['total_cost_usd']:.4f}"
        )

        # Warning if cost is abnormally high
        if llm_log.get('cost_usd', 0) > 0.030:
            logger.warning(
                f"⚠️  Cost สูงผิดปกติ: ${llm_log['cost_usd']:.4f}/call "
                f"(target ≤ $0.020) — cache อาจไม่ทำงาน"
            )

        # Log verify errors (if any)
        if verify_errors:
            logger.warning(f"⚠️  Agent A verify errors: {verify_errors}")

        if decision.get('action') == 'SKIP':
            logger.info(f"❌ SKIP: {decision.get('skip_reason', 'Agent A decided to skip')}")
            return

        logger.info(f"✓ Agent A: {decision['action']} @ {decision['entry']:.2f} "
                    f"(SL={decision['sl']:.2f}, TP={decision['tp']:.2f}, R:R={decision.get('rr_ratio', 0):.2f})")

        # Step 3b: Agent B — Risk Manager
        logger.info("\n[STEP 3b] Agent B — Risk Manager...")

        # Build risk context (Python คำนวณก่อนส่ง Haiku)
        risk_context = build_risk_context(
            decision=decision,
            balance=self.balance,
            portfolio_state=portfolio_state,
            weekly_stats=self.weekly_stats
        )

        logger.info(f"  Risk Context: base_lot={risk_context['base_lot']:.2f}, "
                    f"consecutive_loss={risk_context['consecutive_loss']}, "
                    f"weekly_wr={risk_context['weekly_winrate']:.1%}")

        # Call Agent B
        risk_result = self.risk_manager.approve(
            decision=decision,
            risk_context=risk_context
        )

        if not risk_result['approved']:
            logger.warning(f"❌ Agent B REJECTED: {risk_result['reason']}")
            return

        lot = risk_result['lot']
        adjusted = risk_result.get('adjusted', False)

        logger.info(f"✓ Agent B: Approved lot={lot:.2f} "
                    f"{'(adjusted)' if adjusted else ''}")

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
            'max_loss_usd': risk_context['max_loss_usd'],
            'orders': [order]
        }

        logger.info(f"✓ Order created: {order['action']} @ {order['entry']:.2f}, "
                    f"lot={lot:.2f}, R:R={order['rr_ratio']:.2f}")

        # Determine mode for plan/trade ID prefix
        id_mode = 'backtest' if self.is_backtest else 'simulate'
        plan_id = generate_plan_id(candle_time=candle_time, mode=id_mode)

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
            orders_with_ids.append(order)

        # Prepare decision for Sheets (add 'technique' field from 'setup')
        decision_for_sheets = decision.copy()
        decision_for_sheets['technique'] = decision.get('setup', 'none')  # Agent A uses 'setup', Sheets uses 'technique'

        # Log to Sheets
        self.sheets_logger.log_plan_open(plan_id, orders_with_ids, decision_for_sheets, world_state, llm_log, candle_time=candle_time)

        # Execute trades via broker (if paper mode)
        if self.broker is not None:
            logger.info(f"\n[Broker] Executing {len(orders_with_ids)} orders via PaperBroker...")
            for order in orders_with_ids:
                ticket = self.broker.open_position(
                    action=order['action'],
                    lot=order['lot'],
                    sl=order['sl'],
                    tp=order['tp'],
                    plan_id=plan_id,
                    candle_time=candle_time,
                    trade_id=order['trade_id'],
                    entry_price=order.get('entry')  # For backtest mode
                )
                if ticket:
                    order['broker_ticket'] = ticket  # Store ticket for tracking
                    logger.info(f"✓ Order {order['trade_id']} opened as ticket #{ticket}")
                else:
                    logger.error(f"✗ Failed to open order {order['trade_id']}")

        # Add to position monitor
        self.position_monitor.add_orders(orders_with_ids)

        # Update portfolio state (14 fields)
        portfolio_state['active_plan_id'] = plan_id
        portfolio_state['open_plans_count'] = 1  # Currently single plan only
        portfolio_state['total_risk_pct'] = RISK_CONFIG['risk_per_plan_pct']  # 0.10 (10%)
        portfolio_state['open_orders_count'] = len(orders_with_ids)
        portfolio_state['total_open_lot'] = lot  # From Agent B

        # Update last technical price (for duplicate prevention)
        # Always save (0.0 if no twin_candle, disables duplicate prevention for non-twin techniques)
        portfolio_state['last_technical_price'] = world_state.get('twin_candle', {}).get('technical_price', 0.0)
        portfolio_state['last_plan_chart_type'] = world_state.get('chart_type', '')

        logger.info(f"Portfolio state updated: last_technical_price={portfolio_state['last_technical_price']:.2f}, "
                    f"chart_type={portfolio_state['last_plan_chart_type']}")

        self.sheets_logger.update_portfolio_state(portfolio_state)

        # CRITICAL: Update cache immediately in backtest mode (prevent Sheets sync race)
        if hasattr(self, 'portfolio_state_cache'):
            self.portfolio_state_cache['active_plan_id'] = plan_id
            self.portfolio_state_cache['last_technical_price'] = portfolio_state['last_technical_price']
            self.portfolio_state_cache['last_plan_chart_type'] = portfolio_state['last_plan_chart_type']
            logger.info(f"✓ Cache updated: active_plan={plan_id}, last_tech={portfolio_state['last_technical_price']:.2f}")

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
            # Use optimized method: fetch M5, resample to H4/H1/M30/M15
            candles_by_tf = self.connector.get_all_timeframes_optimized(
                self.symbol,
                base_tf='M5',
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

            # Update broker positions (check SL/TP with real prices)
            current_price = current_candle.get('close') if current_candle else None
            newly_closed = self.broker.update_positions(candle_time, current_price=current_price)

            # Sync closed positions to PositionMonitor
            if newly_closed:
                logger.info(f"📄 PaperBroker closed {len(newly_closed)} positions")
                for broker_pos in newly_closed:
                    trade_id = broker_pos['trade_id']

                    # Find matching order in PositionMonitor
                    for order in open_orders:
                        if order['trade_id'] == trade_id:
                            # Update order state
                            order['result'] = broker_pos['result']
                            order['close_price'] = broker_pos['close_price']
                            order['close_reason'] = broker_pos['close_reason']
                            order['pnl_usd'] = broker_pos['pnl']
                            order['timestamp_close'] = broker_pos['close_time']

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

    def _resample_m5_to_all_tf(self, m5_candles: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Resample M5 candles to all timeframes (for backtest)

        Args:
            m5_candles: List of M5 candles (at least 55 candles recommended)

        Returns:
            {
                'H4': [candles],
                'H1': [candles],
                'M30': [candles],
                'M15': [candles],
                'M5': [candles],
                'M1': []  # Skip M1 in backtest
            }
        """
        import pandas as pd

        if len(m5_candles) < 20:
            return {}

        # Convert to DataFrame
        df = pd.DataFrame(m5_candles)
        df['time'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('time')

        # Resample to other timeframes
        result = {}
        TF_MINUTES = {'H4': 240, 'H1': 60, 'M30': 30, 'M15': 15, 'M5': 5}

        for tf in ['H4', 'H1', 'M30', 'M15', 'M5']:
            if tf == 'M5':
                # Use original M5 data
                df_resampled = df.copy()
            else:
                # Resample
                freq = f'{TF_MINUTES[tf]}min'
                df_resampled = df.resample(freq).agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()

            # Take last 55 bars
            df_final = df_resampled.tail(CANDLES_LOOKBACK).reset_index()

            # Convert back to list of dicts
            candles = df_final.to_dict('records')
            for candle in candles:
                if 'time' in candle:
                    candle['timestamp'] = candle['time']

            result[tf] = candles

        # Skip M1 in backtest (can't downsample from M5)
        result['M1'] = []

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

        Note: ต้องใช้ DATA_MODE=backtest ใน .env
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

        try:
            # Fetch M5 candles for date range using start_date/end_date parameters
            # This will fetch all candles in the range (not just recent candles)
            logger.info(f"Fetching M5 candles for date range {start_date} → {end_date}...")
            all_m5_candles = self.connector.get_latest_candles(
                self.symbol,
                timeframe='M5',
                count=None,  # Not used when start_date/end_date provided
                start_date=start,
                end_date=end
            )

            if not all_m5_candles:
                logger.error("❌ No M5 candles fetched for date range")
                return

            logger.info(f"✓ Fetched {len(all_m5_candles)} M5 candles")
            logger.info(f"   First: {all_m5_candles[0]['timestamp']}")
            logger.info(f"   Last: {all_m5_candles[-1]['timestamp']}")

        except Exception as e:
            logger.error(f"Failed to fetch M5 candles: {e}")
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

            # Resample M5 slice to all timeframes
            candles_by_tf = self._resample_m5_to_all_tf(m5_slice)

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

        # Summary
        logger.info("\n" + "="*70)
        logger.info("📊 BACKTEST SUMMARY")
        logger.info("="*70)
        logger.info(f"Period: {start_date} → {end_date}")
        logger.info(f"Total candles: {len(all_m5_candles)}")
        logger.info(f"Processed signals: {total_signals}")
        logger.info(f"Total plans: {self.session_stats['total_plans']}")

        # Read from Google Sheets for full results
        portfolio_state = self.sheets_logger.get_portfolio_state()
        logger.info(f"Win rate: Check Google Sheets")
        logger.info(f"Total P&L: ${portfolio_state.get('realized_pnl_usd', 0):.2f}")

        # Check for pending orders
        pending = [o for o in self.position_monitor.open_orders if o.get('result') == 'PENDING']
        if pending:
            logger.warning(
                f"⚠️  {len(pending)} orders ยัง PENDING ตอนจบ backtest "
                f"— อาจต้องขยาย end_date ให้ plan มีโอกาสปิด"
            )

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
            # Run continuously
            logger.info("Running in continuous mode... (press Ctrl+C to stop)")
            while True:
                traider.run_once()
                traider.monitor_positions()
                time.sleep(300)  # Wait 5 minutes (M5 candle close)

    except KeyboardInterrupt:
        logger.info("\n\n👋 Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
