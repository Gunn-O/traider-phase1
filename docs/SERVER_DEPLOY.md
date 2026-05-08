# Server Deployment Guide

> Deploy Tra(i)der bot to a Windows server for 24/7 live trading with MT5 + Exness Cent.

## Recommended VPS specs

| Item | Minimum | Recommended |
|---|---|---|
| OS | Windows Server 2019 | Windows Server 2022 |
| vCPU | 2 | 4 |
| RAM | 4 GB | 8 GB |
| Disk | 30 GB SSD | 60 GB SSD |
| Network | low latency to broker | < 50ms ping to Exness server |

**Forex VPS providers** (close to broker DCs): Beeks FX, ChicagoVPS, MyForexVPS, FXVM. ~$10-30/month.

Some brokers (Exness included) offer **free VPS** for accounts above a certain deposit threshold — check broker portal.

## Prerequisites (one-time, manual)

Install on the server before running setup script:

1. **Python 3.11.x** — https://python.org/downloads
   - ✅ Add to PATH during install
2. **Node.js 18+** — https://nodejs.org (LTS version)
   - ✅ Add to PATH
3. **Git for Windows** — https://git-scm.com/download/win
4. **MT5 EXNESS** — download from broker portal
   - Login with Cent account credentials
   - Tools → Options → Expert Advisors → ✅ Allow algorithmic trading

## Step 1 — Clone repo

```powershell
cd C:\
git clone https://github.com/Gunn-O/traider-phase1.git
cd traider-phase1
```

(Choose a path WITHOUT spaces or Thai characters — PyInstaller is fussy.)

## Step 2 — Run automated setup

```powershell
# Run as Administrator (for powercfg)
.\scripts\setup_server.ps1
```

The script will:
- ✅ Verify Python 3.11, Node 18+, MT5 path
- ✅ Create `venv\` + `pip install -r requirements.txt`
- ✅ `npm install` in `frontend\`
- ✅ Prompt for MT5 credentials → write `.env`
- ✅ Build `TraiderLauncher.exe` (~10 MB, takes 60-90s)
- ✅ Disable Windows sleep / hibernation
- ✅ Smoke-test imports

If anything fails it'll tell you exactly what to fix.

### Re-run options

```powershell
.\scripts\setup_server.ps1 -SkipDeps   # skip pip + npm (already done)
.\scripts\setup_server.ps1 -SkipExe    # skip PyInstaller rebuild
.\scripts\setup_server.ps1 -NoEnvPrompt # skip .env credential prompts
```

## Step 3 — MT5 manual setup

This must be done in the MT5 GUI (cannot automate fully):

1. Open **MT5 EXNESS** → login with `.env` credentials
2. Click **Algo Trading** button on toolbar — must turn **green ▶**
3. **Market Watch** panel: right-click → **Show All** → scroll to confirm `XAUUSDc`
   appears (not greyed out)
4. (Optional) **Tools → Options → Server**: ✅ Enable DDE server (not required, but
   helpful for debugging)
5. Close MT5 — `TraiderLauncher` will reopen it automatically

## Step 4 — Smoke test

```powershell
.\TraiderLauncher.exe
```

In the launcher window:
1. Click **▶ Start All**
2. Wait for 3 ✅ green statuses (MT5, Backend, Frontend)
3. Browser opens at http://localhost:3000

In the dashboard:
1. Verify **MT5 Live Data** panel shows:
   - 🟢 green pulsing dot
   - Account login + balance from `.env`
   - Live Bid/Ask updating
   - Last 10 candles populating
2. In TopBar, set: **Broker Trade · Cent · M1 · MT5**
3. Click **▶ START**
4. Tail `traider.log` — within 1 sec you should see:
   ```
   Trading mode:   micro
   Active TF:      M1
   Data source:    mt5
   📊 Data source: MT5 Terminal
   ✅ Pre-flight OK | account=...
   💹 MT5LiveBroker initialized | magic=10002
   Running in continuous mode... TF=M1, poll every 60s
   ```

If any of these are missing, see [Troubleshooting](#troubleshooting).

## Step 5 — Auto-start at logon

Run **as Administrator**:

```powershell
.\scripts\install_task_scheduler.ps1
```

This creates a Windows Task Scheduler entry `TraiderLauncher` that:
- Triggers at every user logon (30s delay)
- Runs at HIGHEST privilege
- Auto-restarts up to 3× if launcher crashes (5min interval)

Verify:
```powershell
Get-ScheduledTask -TaskName 'TraiderLauncher' | Format-List
```

Test without rebooting:
```powershell
Start-ScheduledTask -TaskName 'TraiderLauncher'
```

Uninstall:
```powershell
.\scripts\install_task_scheduler.ps1 -Uninstall
```

## Step 6 — Reboot test

```powershell
Restart-Computer
```

After reboot + automatic logon:
- Within 30s, TraiderLauncher window should appear
- Click ▶ Start All in launcher (still requires manual click for safety)
- Verify dashboard works as in Step 4

> **Note:** The launcher does NOT auto-click "Start All" — that's intentional.
> Trading mode requires deliberate user action. Bot still polls broker for tick data
> via the MT5 Live Data panel even before clicking START.

---

## Operational tasks

### Update bot from main branch

```powershell
cd C:\traider-phase1
git fetch origin
git pull origin main

# If launcher.py / config.py / agents/ changed → rebuild .exe
.\scripts\setup_server.ps1 -SkipDeps
```

If `requirements.txt` changed, drop `-SkipDeps`.

### Switch to Real account (from Cent)

1. In MT5: log out of Cent → log into Real account
2. Edit `.env`:
   ```
   MT5_LOGIN=<real account>
   MT5_PASSWORD=<real password>
   MT5_SERVER=Exness-MT5Real
   ACCOUNT_BALANCE=<real balance>
   ```
3. In dashboard, select **Broker Trade · Real**
4. Restart bot via UI (Stop → Start)

⚠️ Real mode uses magic 10003 (vs Cent's 10002) — orders are kept separate.
⚠️ The bot does NOT auto-translate Cent units to Real. Verify lot sizes are
sensible for the Real balance before going live.

### Monitor logs

`traider.log` (project root) is the bot's runtime log. Tail it:

```powershell
Get-Content traider.log -Wait -Tail 50
```

For long-running deployments, log rotation isn't built-in yet — manually archive
periodically:

```powershell
# Archive + reset (run weekly)
$ts = Get-Date -Format 'yyyy-MM-dd'
Move-Item traider.log "logs\traider-$ts.log"
```

### Stop bot completely

Two levels:

1. **Soft stop** (preserve open orders): UI → click ⏹ Stop Bot.
   Open positions stay (broker still manages SL/TP server-side).

2. **Hard stop** (kill everything): Launcher → ⏹ Stop All.
   Backend + Frontend killed. Bot subprocess killed via taskkill /F /T.
   MT5 Desktop stays running (intentional — you may want it for manual trades).

### Emergency close all positions

1. MT5 Desktop → Trade tab → Ctrl+A → right-click → **Close Position**
2. Click **Algo Trading** to turn it OFF (red) — bot can't open new orders

---

## Troubleshooting

### MT5 connection fails on `mt5.initialize()`

```
Error: mt5.initialize() failed: (-10003, 'IPC ...')
```

- Make sure MT5 Desktop is running and logged in
- Multiple MT5 instances confuse the IPC. Use only ONE MT5 terminal at a time
- If you have multiple MT5 installs, set `MT5_TERMINAL_PATH` in `.env` to point
  to the specific instance

### `account_info() returned None`

- MT5 is running but not logged in. Login manually first.
- Check `.env` MT5_LOGIN/PASSWORD — wrong credentials silently fail.

### Symbol XAUUSDc not visible

- MT5 Market Watch → right-click → Show All → find XAUUSDc → right-click → Show
- Some brokers hide XAUUSDc by default; your account must have permission to trade it

### Bot's mode_badge says BROKER • CENT but no orders fire

Read `traider.log`. Look for these gates:
- `Signal Engine: No setup found` — strategy didn't detect pattern (normal,
  expect ~1 plan / 3-4 hours on M1)
- `SKIP: Setup เดิม` — duplicate signal blocked by G2 (entry within ±50pip
  of previous)
- `Pre-flight OK` missing — MT5LiveBroker not initialized; check MT5 connection
- `⛔ Spread too wide` — current spread > 100 pip; market is in news / off-hours.
  Wait for normal hours (London/NY session)

### `port 8080 already in use`

Another bot or process is holding the port. Free it:

```powershell
netstat -ano -p TCP | findstr :8080
# Note the PID, then:
taskkill /F /PID <pid>
```

### TraiderLauncher.exe doesn't auto-start after reboot

- Verify task is registered: `Get-ScheduledTask -TaskName TraiderLauncher`
- Check task history: Task Scheduler GUI → Task Status → History tab
- Common cause: user is NOT auto-logged-in. Windows Server requires login by
  default. Either:
  - Configure auto-logon (search "netplwiz" → uncheck "Users must enter a
    user name and password")
  - Or change task trigger to "At system startup" + RunLevel SYSTEM (advanced;
    GUI app may not show)

### Encoding errors in `traider.log` (Thai chars / emoji)

Already fixed in V4.28 (FileHandler uses UTF-8). If you see them, you're on
old code — `git pull` then rebuild.

---

## File structure on server (after setup)

```
C:\traider-phase1\
├── .env                       ← secrets (gitignored)
├── TraiderLauncher.exe        ← built artifact (gitignored)
├── traider.log                ← runtime log (rotates? no — manual archive)
├── traider_backtest.db        ← SQLite, gitignored
├── venv\                      ← Python deps (gitignored)
├── frontend\
│   ├── node_modules\          ← gitignored
│   └── ...
├── scripts\
│   ├── setup_server.ps1       ← THIS deploy
│   ├── install_task_scheduler.ps1
│   └── ...
├── docs\
│   ├── SERVER_DEPLOY.md       ← THIS doc
│   └── LAUNCHER_GUIDE.html    ← user manual
├── strategies\
│   ├── mountain.py
│   └── mai_ruay.py
├── agents\
│   └── mt5_live_broker.py
└── main.py
```

## Security notes

- `.env` is gitignored — credentials never leave the server
- Backend binds to `127.0.0.1:8080` only — not exposed to public network
- Frontend binds to `localhost:3000` — same
- For remote dashboard access, use **RDP** to the server (don't expose ports)
- Magic numbers (10002 Cent, 10003 Real) isolate bot orders from manual trades
- Bot never modifies trades opened by the user (different magic = ignored)

## Limitations

- **Single TF only** — bot trades one TF per session. Restart to change.
- **Single symbol only** — XAUUSDc / XAUUSD per session. Restart to change.
- **Restart required after .env changes** — env is read at startup, not live
- **No log rotation** — manual archive required for long deployments
- **MT5 Desktop dependency** — Python uses MT5 IPC, requires terminal running
- **Sleep + bot don't mix** — disable sleep (auto-done by setup script) or
  trailing SL stage transitions will be missed mid-session

For 24/7 reliability, monitor `traider.log` weekly and verify recent activity.
