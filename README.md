# Tra(i)der - XAUUSD Trading Bot

**Phase I + Phase II**: Signal Engine + Backtest + Strategy Manager + Live Trading on MT5

Version: **V4.26** (V65 Mountain Pattern - Verified)

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation (Windows)](#installation-windows)
3. [MetaTrader 5 Setup](#metatrader-5-setup)
4. [Configuration](#configuration)
5. [Running the Bot](#running-the-bot)
6. [Web Dashboard](#web-dashboard)
7. [Troubleshooting](#troubleshooting)
8. [Project Structure](#project-structure)

---

## Prerequisites

### Required Software

- **Windows 10/11** (64-bit)
- **Python 3.10 or higher**
  - Download: https://www.python.org/downloads/
  - ✅ Check "Add Python to PATH" during installation
- **MetaTrader 5**
  - Download: https://www.metatrader5.com/en/download
  - Account: Demo or Live (XAUUSD broker)
- **Git for Windows**
  - Download: https://git-scm.com/download/win
- **Node.js 18+** (for frontend)
  - Download: https://nodejs.org/

### Optional
- **Visual Studio Code** - Recommended IDE
- **Google Chrome** - For web dashboard

---

## Installation (Windows)

### Step 1: Clone Repository

```bash
# Open Command Prompt or PowerShell
cd Desktop
git clone https://github.com/Gunn-O/traider-phase1.git
cd traider-phase1
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# You should see (venv) in your prompt
```

### Step 3: Install Python Dependencies

```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Install all dependencies
pip install -r requirements.txt

# Verify MT5 package installed
python -c "import MetaTrader5 as mt5; print(f'MT5 Version: {mt5.__version__}')"
```

**Expected output:**
```
MT5 Version: 5.0.45
```

### Step 4: Install Frontend Dependencies

```bash
# Navigate to frontend folder
cd frontend

# Install Node packages
npm install

# Go back to root
cd ..
```

### Step 5: Create Environment File

```bash
# Copy example environment file
copy .env.example .env

# Edit .env with your settings (see Configuration section)
notepad .env
```

---

## MetaTrader 5 Setup

### Step 1: Install and Login to MT5

1. **Download and Install MT5**
   - Download from: https://www.metatrader5.com/en/download
   - Run installer and follow prompts

2. **Create Demo Account or Login**
   - Open MT5
   - File → Login to Trade Account
   - Choose your broker (must support XAUUSD)
   - Enter credentials or create demo account

3. **Verify XAUUSD Symbol**
   - Right-click Market Watch → Symbols
   - Search for "XAUUSD" or "GOLD"
   - Enable the symbol
   - Check that M5 timeframe data is available

### Step 2: Enable Algo Trading

1. **Enable Auto Trading**
   - Click **"Auto Trading"** button in toolbar (should turn green)
   - Or: Tools → Options → Expert Advisors → Allow Algo Trading

2. **Configure Terminal Settings**
   - Tools → Options → Expert Advisors:
     - ✅ Allow algorithmic trading
     - ✅ Allow DLL imports
     - ✅ Allow WebRequest (add `https://api.anthropic.com`)

3. **Keep MT5 Running**
   - ⚠️ MT5 must be running and logged in for the bot to work
   - Do NOT close MT5 while bot is running

### Step 3: Test MT5 Connection

```bash
# Activate venv if not already
venv\Scripts\activate

# Test MT5 connection
python -c "import MetaTrader5 as mt5; mt5.initialize(); print('Connected:', mt5.account_info()); mt5.shutdown()"
```

**Expected output:**
```
Connected: AccountInfo(login=12345678, trade_mode=0, ...)
```

**If connection fails:**
- Make sure MT5 is running and logged in
- Check that you're using 64-bit Python (MT5 requires 64-bit)
- Verify: `python -c "import platform; print(platform.architecture())"`
- Should show: `('64bit', 'WindowsPE')`

---

## Configuration

### 1. Environment Variables (.env)

Edit `.env` file with your settings:

```bash
# ============================================
# ANTHROPIC API (Required for Live/SIM mode)
# ============================================
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx
# Get your API key: https://console.anthropic.com/

# ============================================
# ACCOUNT SETTINGS
# ============================================
ACCOUNT_BALANCE=1000   # Initial balance (USD)
WINRATE_TEST=false     # true = 0.01 lot all trades, false = normal

# ============================================
# RISK MANAGEMENT (Phase II Settings)
# ============================================
RISK_PER_PLAN_PCT=0.10        # 10% risk per plan (not 1.5%)
MIN_RR_RATIO=1.0              # Minimum R:R (1.0 recommended)
MAX_CONSECUTIVE_LOSS=3        # Stop after 3 losses
MAX_LOSS_30PCT=0.30           # Circuit breaker at 30% loss
MAX_LOSS_50PCT=0.50           # Hard stop at 50% loss

# ============================================
# MT5 SETTINGS
# ============================================
MT5_LOGIN=12345678         # Your MT5 account number
MT5_PASSWORD=YourPassword  # Your MT5 password
MT5_SERVER=YourBroker-Demo # Your broker server (e.g., ICMarkets-Demo)

# ============================================
# NOTIFICATIONS (Optional)
# ============================================
LINE_NOTIFY_ENABLED=false      # Set to true to enable LINE
LINE_NOTIFY_TOKEN=xxxxx        # Get token: https://notify-bot.line.me/

# ============================================
# GOOGLE SHEETS (Optional)
# ============================================
SHEETS_ENABLED=false           # Set to true to enable
SHEETS_ID=your-sheet-id        # Google Sheets ID

# ============================================
# LOGGING
# ============================================
LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR
```

### 2. Strategy Configuration (config/strategies.json)

Enable/disable trading patterns:

```json
{
  "version": "V4.26",
  "last_updated": "2026-04-30",
  "active_patterns": [
    "MOUNTAIN"
  ],
  "patterns": {
    "MOUNTAIN": {
      "name": "Mountain Pattern (V65)",
      "version": "V65",
      "direction": "BUY",
      "priority": 1,
      "implemented": true,
      "validations": [
        "Mountain size >= 10 bars",
        "No Low penetrate thresh_10 in 20-80% range",
        "Base to entry <= 42 bars",
        "SH count check if > 25 bars"
      ]
    }
  }
}
```

**To change active patterns:**
- Edit via Web Dashboard: http://localhost:3001/strategy
- Or edit `config/strategies.json` directly

---

## 🖱️ Windows Desktop Shortcuts (One-Click Launch)

For easy access, create desktop shortcuts that launch the application with one click:

### Quick Setup (Automatic)

Run this command in PowerShell (as Administrator):

```powershell
# Right-click PowerShell → Run as Administrator
cd Desktop\projects\traider-phase1
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\create_shortcuts.ps1
```

**This creates 4 shortcuts on your Desktop:**

1. **Traider Dashboard** 🚀 **(Recommended)**
   - Starts Backend + Frontend
   - Opens browser automatically
   - Everything in one click!

2. **Traider Bot** 🤖
   - Interactive menu to choose mode:
     - Backtest
     - Simulation
     - Live Trading
     - Winrate Test
     - Dashboard

3. **Traider Backend** ⚙️
   - Starts API server only
   - For advanced users

4. **Traider Frontend** 🎨
   - Starts dashboard only
   - Requires backend running separately

### Manual Setup (Alternative)

If automatic setup doesn't work, create shortcuts manually:

**For Dashboard (All-in-One):**
1. Right-click Desktop → New → Shortcut
2. Location: `C:\Users\YourName\Desktop\projects\traider-phase1\start_dashboard.bat`
3. Name: `Traider Dashboard`
4. Click Finish

**For Bot Launcher:**
1. Right-click Desktop → New → Shortcut
2. Location: `C:\Users\YourName\Desktop\projects\traider-phase1\start_bot.bat`
3. Name: `Traider Bot`
4. Click Finish

### 📂 Available Batch Files

You can also run these directly from the project folder:

| File | Description | Use Case |
|------|-------------|----------|
| `start_dashboard.bat` | Start everything + open browser | **Recommended for daily use** |
| `start_bot.bat` | Interactive menu launcher | Choose mode interactively |
| `start_backend.bat` | Backend API only | For development |
| `start_frontend.bat` | Frontend only | For development |

### 🎯 Recommended Workflow

**For Trading:**
1. Double-click **"Traider Dashboard"** on Desktop
2. Wait 10-15 seconds
3. Dashboard opens in browser automatically
4. Start trading!

**For Development:**
1. Use `start_backend.bat` in one terminal
2. Use `start_frontend.bat` in another terminal
3. Make changes and see live reload

---

## Running the Bot

### 1. Backtest Mode (No API calls, Historical Data)

Test strategy on historical data without using Claude API:

```bash
# Activate venv
venv\Scripts\activate

# Run backtest for specific date range
python main.py --backtest --start 2026-04-01 --end 2026-04-21 --no-ai

# Winrate test (0.01 lot all trades)
python main.py --winrate-test --no-ai
```

**Output:** CSV file with backtest results in project folder

### 2. Simulation Mode (Paper Trading with API)

Test with live data but no real orders:

```bash
# Make sure .env has:
# ANTHROPIC_API_KEY=sk-ant-...

# Run simulation
python main.py --simulate

# The bot will:
# - Connect to MT5 for live data
# - Detect signals with Signal Engine
# - Send to Claude Reviewer for approval
# - Log trades (no real orders)
```

### 3. Live Trading Mode (Real Money - CAREFUL!)

⚠️ **WARNING:** This places REAL orders with REAL money!

```bash
# Make sure .env has:
# MT5_LOGIN=your-real-account
# MT5_PASSWORD=your-password

# Run live (with 2 confirmations)
python main.py --live

# You will be asked to confirm TWICE before starting
```

**Safety Checklist Before Live:**
- [ ] Tested in backtest mode (win rate > 60%)
- [ ] Tested in simulation mode (at least 10 trades)
- [ ] MT5 connected to correct account
- [ ] Risk settings configured (10% per plan)
- [ ] LINE notifications enabled (optional but recommended)
- [ ] Small initial balance for testing

---

## Web Dashboard

### Start Dashboard

```bash
# Terminal 1: Start Backend API
venv\Scripts\activate
python api_server.py

# Terminal 2: Start Frontend
cd frontend
npm run dev
```

**Access:**
- Frontend: http://localhost:3001
- API Docs: http://localhost:8080/docs
- WebSocket: ws://localhost:8080/ws

### Available Pages

1. **Dashboard (/)** - Overview, active trades, performance
2. **Strategy Manager (/strategy)** - Toggle patterns, view validations
3. **Backtest (/backtest)** - Run backtests with custom parameters
4. **Settings** - Configure bot settings

---

## Troubleshooting

### MT5 Connection Issues

**Problem:** `MT5 initialization failed`

**Solutions:**
1. Make sure MT5 is **running and logged in**
2. Check you're using **64-bit Python**:
   ```bash
   python -c "import platform; print(platform.architecture())"
   # Should show: ('64bit', 'WindowsPE')
   ```
3. Reinstall MT5 package:
   ```bash
   pip uninstall MetaTrader5
   pip install MetaTrader5
   ```

**Problem:** `Symbol XAUUSD not found`

**Solutions:**
1. Right-click Market Watch → Symbols
2. Search "XAUUSD" or "GOLD"
3. Click "Show" to enable symbol
4. Different brokers use different names (XAU/USD, GOLD, etc.)

### API Issues

**Problem:** `ANTHROPIC_API_KEY not found`

**Solutions:**
1. Check `.env` file exists in project root
2. Make sure key starts with `sk-ant-api03-`
3. Get new key: https://console.anthropic.com/settings/keys

**Problem:** `Rate limit exceeded`

**Solutions:**
1. Using BACKTEST mode? Add `--no-ai` flag
2. Check your API usage: https://console.anthropic.com/settings/usage
3. Upgrade API plan if needed

### Installation Issues

**Problem:** `pip install failed`

**Solutions:**
1. Update pip: `python -m pip install --upgrade pip`
2. Install Visual C++ Build Tools if needed
3. Try installing packages one by one

**Problem:** `Module not found`

**Solutions:**
1. Make sure venv is activated: `venv\Scripts\activate`
2. Reinstall requirements: `pip install -r requirements.txt`

---

## Project Structure

```
traider-phase1/
├── agents/                    # Agent modules
│   ├── g2_prefilter.py       # Pre-filter before Claude
│   ├── g3_claude_reviewer.py # Claude reviewer (SIM/LIVE only)
│   ├── g3_risk_gate.py       # Risk management
│   ├── g4_position_monitor.py # Position tracking
│   ├── g4_notify.py          # LINE notifications
│   └── g4_sheets_logger.py   # Google Sheets logging
│
├── config/                    # Configuration files
│   └── strategies.json       # Pattern definitions
│
├── frontend/                  # React dashboard
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Strategy.jsx  # NEW: Pattern manager
│   │   │   └── Backtest.jsx
│   │   └── App.jsx
│   └── package.json
│
├── strategy/                  # Strategy documents
│   └── XAUUSD_System_Prompt_Reviewer.md
│
├── utils/                     # Core utilities
│   ├── xauusd_signal.py      # Signal Engine (V65 verified)
│   ├── swing_v414.py         # Swing detection
│   ├── signal_engine.py      # Signal coordination
│   ├── strategy_loader.py    # Strategy config loader
│   └── data_connector.py     # MT5 data connector
│
├── main.py                    # Main entry point
├── api_server.py             # FastAPI backend
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
├── .env                      # Your settings (create this)
│
├── BACKTEST_REPORT.md        # V65 Verification Report
├── CLAUDE.md                 # Agent instructions
└── README.md                 # This file
```

---

## Version History

### V4.26 (Current) - 2026-04-30
- ✅ Fixed 4 critical V65 validation bugs
- ✅ Verified against TradingView (100% signal match)
- ✅ Added Strategy Manager UI
- ✅ Mountain-only mode (Uptrend/Downtrend disabled)
- ✅ Ready for MT5 live testing

### V4.25 - Previous
- Signal Engine with impulse verification
- Backtest UI with validation

### V4.20 - Previous
- Reviewer Mode + React Frontend Migration

---

## Support & Resources

- **Documentation:** See `BACKTEST_REPORT.md` for V65 verification
- **Strategy Guide:** See `strategy/XAUUSD_System_Prompt_Reviewer.md`
- **Agent Instructions:** See `CLAUDE.md`
- **GitHub Issues:** https://github.com/Gunn-O/traider-phase1/issues

---

## Important Notes

### ⚠️ Risk Disclaimer

- **This bot trades with REAL MONEY in live mode**
- **Past performance does not guarantee future results**
- **Always test in BACKTEST and SIMULATION first**
- **Start with small amounts**
- **Use stop losses and risk management**
- **Never risk more than you can afford to lose**

### 📊 Backtest Results (V4.26)

Tested against TradingView data (Apr 1-21, 2026):
- **Trades:** 7 (exact match with TradingView)
- **Win Rate:** 71.4% (5W 2L)
- **Return:** +77.6%
- **First Signal:** Apr 7 05:30 @ 4627.385 ✅ (100% match)

**Note:** Win rate difference (71.4% vs TV 85.7%) is due to SL/TP execution timing, not logic errors. Signal detection is 100% accurate.

### 🔒 Security

- **Never commit `.env` file** (contains API keys)
- **Never share your ANTHROPIC_API_KEY**
- **Never share your MT5 password**
- **Use demo account first**

---

## Quick Start Checklist

- [ ] Install Python 3.10+ (64-bit)
- [ ] Install MetaTrader 5
- [ ] Clone repository
- [ ] Create virtual environment
- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Install frontend (`cd frontend && npm install`)
- [ ] Create `.env` file from `.env.example`
- [ ] Add ANTHROPIC_API_KEY to `.env`
- [ ] Configure MT5 credentials in `.env`
- [ ] Enable Algo Trading in MT5
- [ ] Test MT5 connection (`python -c "import MetaTrader5..."`)
- [ ] Create desktop shortcuts (`.\create_shortcuts.ps1` in PowerShell)
- [ ] Run backtest (`python main.py --backtest --no-ai`)
- [ ] Run simulation (`python main.py --simulate`)
- [ ] Start dashboard (double-click "Traider Dashboard" icon OR `python api_server.py` + `npm run dev`)
- [ ] Review results and configure risk settings
- [ ] (Optional) Enable LINE notifications
- [ ] Ready for live trading!

---

**Built with Claude Code** 🤖

Good luck and happy trading! 📈
