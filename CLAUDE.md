# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tra(i)der** is an AI-powered trading system that uses Claude to execute XAUUSD (Gold) trading strategies. The system removes emotional decision-making by following a structured rule-based strategy and operates 24/7.

**Core Principle:** Two-layer architecture
1. **Strategy Layer** (read-only) - `strategy/XAUUSD_Strategy_v5.md` defines 6 trading conditions and 3 techniques
2. **System Layer** - 5 Agent Groups (G1-G5) execute the strategy via Claude API

## Phase I Focus (Current)

**Goal:** Prove AI can read strategy correctly via **Simulated Trading** (no real MT5 execution)

**KPI to pass:** Win Rate ≥ 60% for 4 consecutive weeks

**Key constraint:** Never modify Strategy Layer directly - it's read-only. Only G5 can propose changes after user approval.

## Architecture - 5 Agent Groups

Pipeline flow: `Market Data → G1 → G2 → G3 → G4 ⇄ G5`

- **G1: Market Scanning** - RSI(14), S/R levels, detect Conditions A1-A6, news filter
- **G2: Quantitative Analysis** - Score RSI/S/R/Trend → confidence 0.0-1.0 (filter: ≥0.70)
- **G3: Decision + MM + Guardian**
  - G3a: Claude Decision Agent (reads Strategy MD → BUY/SELL/SKIP)
  - G3b: Money Management (calculate lot size from risk %)
  - G3c: Guardian (enforce risk limits: max DD, daily loss, R:R, news block)
- **G4: Monitoring & Logging**
  - G4a: LINE Notify (Thai language messages)
  - G4b: Google Sheets Logger (Trade Log with simulated results)
- **G5: Weekly Learning** - Analyze performance → propose threshold adjustments

## Directory Structure

- `agents/` - G1-G5 implementations (will contain g1_signal_logic.py, g2_quant_analysis.py, etc.)
- `strategy/` - `XAUUSD_Strategy_v5.md` (Source of Truth - read-only)
- `utils/` - Data connectors, S/R detection, simulated result calculator
- `backtest/` - Backtest results (gitignored)
- `tests/` - Unit tests
- `logs/` - Runtime logs

## Environment Setup

1. Create a virtual environment and activate it:
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables by copying `.env.example` to `.env` and filling in:
   - `DATA_MODE` - **Critical:** "backtest" | "simulate" | "live"
   - `ANTHROPIC_API_KEY` - Claude API key (required for G3 Decision Agent)
   - `LINE_NOTIFY_TOKEN` - LINE notification token
   - `LINE_NOTIFY_ENABLED` - true/false (disable during backtest)
   - `GOOGLE_SHEETS_ID` / `GOOGLE_CREDENTIALS_JSON` - Google Sheets integration
   - `SHEETS_ENABLED` - true/false (disable during backtest)
   - `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` - MetaTrader5 credentials (live mode only, Windows)
   - `TV_USERNAME` / `TV_PASSWORD` - TradingView credentials (if using tvdatafeed)
   - Backtest parameters: `BACKTEST_START`, `BACKTEST_END`, `BACKTEST_SYMBOL`, `BACKTEST_TF`
   - Risk management: `ACCOUNT_BALANCE`, `RISK_PCT`

## Key Dependencies

- **anthropic** - Claude AI integration for trading decisions
- **tvdatafeed** - Fetches market data from TradingView
- **gspread** - Google Sheets integration for logging trades
- **ta** - Technical analysis indicators
- **pandas/numpy** - Data processing and analysis
- **schedule** - Task scheduling for live trading
- **pytest** - Testing framework

## Data Modes (utils/data_connector.py)

The system supports 3 data modes via `DATA_MODE` environment variable:

### simulate ⭐ RECOMMENDED for Phase I Development
- Data source: **yfinance** near real-time (~15 min delay)
- Symbol mapping: XAUUSD → GC=F (Gold Futures)
- Data range: Last 60 days automatically
- No MT5 required, works on macOS/Linux
- **Use this for developing and testing G1-G5 agents**
- Can enable LINE and Sheets for integration testing

```python
# No date parameters needed
connector = create_connector('simulate')
data = connector.get_latest_candles('XAUUSD', m5_count=80, h1_count=20)
```

### backtest ⚠️ Limited to 60 days
- Data source: **yfinance** historical data
- Symbol mapping: XAUUSD → GC=F
- **Limitation:** Intraday data (5m/15m/30m) available for last 60 days only
- For older historical data: use hourly/daily intervals or CSV files
- Requires: `BACKTEST_START` and `BACKTEST_END` dates (within 60 days)
- Disable: `LINE_NOTIFY_ENABLED=false`, `SHEETS_ENABLED=false`

```python
# Must be within last 60 days
start = datetime.now() - timedelta(days=30)
end = datetime.now()
data = connector.get_latest_candles('XAUUSD', 80, 20, start, end)
```

### live (Phase II only)
- Data source: **MetaTrader5** real-time API
- Requires: Windows OS + MT5 installed + valid credentials
- Symbol: XAUUSD (native MT5 symbol)
- Phase II feature (Phase I uses simulated execution only)

```python
connector.connect(login=12345, password='xxx', server='ICMarkets-Demo')
```

## Development Commands

Run tests:
```bash
pytest tests/
```

Run a specific test:
```bash
pytest tests/test_name.py::test_function_name
```

Activate virtual environment:
```bash
source venv/bin/activate
```

## Critical Development Rules

### Strategy Layer Rules
1. **NEVER modify `strategy/XAUUSD_Strategy_v5.md` directly** - it's the Source of Truth
2. **NEVER hardcode strategy rules in Python** - always read from Strategy MD
3. Only G5 (Evaluate & Relearn) can propose changes, and only after user approval

### Phase Discipline
4. **DO NOT implement Phase II/III features during Phase I** - follow the roadmap strictly
5. Phase I = Simulated trading only (no real MT5 order execution)
6. Must achieve Win Rate ≥ 60% for 4 weeks before Phase II

### Decision Rules (G3 Guardian)
7. **confidence < 0.70 = SKIP** - no exceptions
8. **R:R < 1:2 = SKIP** - no exceptions
9. **news_flag = true = SKIP** - block ±30 min around high-impact events
10. **SKIP if uncertain** - better to skip than trade incorrectly

### Risk Limits (Default)
- Max Drawdown: 5%
- Max Daily Loss: 3%
- Max Open Trades: 2
- Risk per Trade: 1.5%

### Token Usage
- G3 Decision Agent: ~250 tokens/call, ~10-15 calls/day
- Estimated cost: $0.02-0.06/day with claude-sonnet-4-5

## Important Notes

- Never commit `.env`, `credentials.json`, or `token.json` files (they contain sensitive credentials)
- Backtest results are stored in `backtest/results/` and are gitignored
- The project uses Thai language in LINE messages and some configuration comments
- Always test strategies in backtest mode before enabling live trading
- Symbol mapping: XAUUSD uses GC=F for yfinance (Gold Futures)
