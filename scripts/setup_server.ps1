<#
.SYNOPSIS
    Tra(i)der — Automated Windows Server Setup
.DESCRIPTION
    One-shot setup after `git clone` on a fresh Windows server:
      1. Pre-flight checks (Python 3.11, Node 18+, MT5)
      2. Python venv + pip install -r requirements.txt
      3. npm install (frontend)
      4. .env scaffolding (prompts user for MT5 credentials)
      5. Build TraiderLauncher.exe via PyInstaller
      6. Disable sleep / hibernation
      7. Smoke test (verify all components importable)

    Run from repo root:  .\scripts\setup_server.ps1
    Idempotent — safe to re-run; skips steps already done.

.PARAMETER SkipDeps
    Skip pip + npm install (use if dependencies already installed).
.PARAMETER SkipExe
    Skip PyInstaller build (use if .exe already up-to-date).
.PARAMETER NoEnvPrompt
    Don't prompt for MT5 credentials — leave .env placeholders.
.EXAMPLE
    .\scripts\setup_server.ps1
.EXAMPLE
    .\scripts\setup_server.ps1 -SkipDeps -SkipExe
#>

[CmdletBinding()]
param(
    [switch] $SkipDeps,
    [switch] $SkipExe,
    [switch] $NoEnvPrompt
)

$ErrorActionPreference = 'Stop'

# ── Helpers ──────────────────────────────────────────────────
function Write-Step($msg)  { Write-Host "`n[~] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "[X] $msg" -ForegroundColor Red }

function Test-Cmd($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

# ── Locate repo root ─────────────────────────────────────────
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot
Write-Host "===== Tra(i)der Server Setup =====" -ForegroundColor White
Write-Host "Repo root: $repoRoot`n"

# ── Step 1: Prerequisites ────────────────────────────────────
Write-Step "Checking prerequisites..."

$missing = @()

if (Test-Cmd python) {
    $pyver = (python --version 2>&1).ToString().Trim()
    if ($pyver -match '3\.11\.') {
        Write-Ok "$pyver"
    } else {
        Write-Warn "$pyver (expected 3.11.x — may work but untested)"
    }
} else { $missing += 'Python 3.11' }

if (Test-Cmd node) {
    $nodever = (node --version).Trim()
    $major = [int]($nodever -replace '^v','' -split '\.')[0]
    if ($major -ge 18) { Write-Ok "Node $nodever" }
    else { Write-Warn "Node $nodever (need 18+)" }
} else { $missing += 'Node.js 18+' }

if (-not (Test-Cmd npm)) { $missing += 'npm' }
if (-not (Test-Cmd git)) { $missing += 'git' }

# Detect MT5
$mt5Candidates = @(
    "C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
    "C:\Program Files\MetaTrader 5\terminal64.exe",
    "C:\Program Files (x86)\MetaTrader 5\terminal64.exe"
)
$mt5Path = $mt5Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($mt5Path) {
    Write-Ok "MT5: $mt5Path"
} else {
    $missing += 'MT5 EXNESS terminal64.exe (install MT5 first)'
}

if ($missing.Count -gt 0) {
    Write-Err "Missing prerequisites:"
    $missing | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
    exit 1
}

# ── Step 2: Python venv ──────────────────────────────────────
Write-Step "Python virtual environment..."
$venvPython = Join-Path $repoRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host "    Creating venv..."
    python -m venv venv
    if (-not (Test-Path $venvPython)) { Write-Err "venv creation failed"; exit 1 }
}
Write-Ok "venv ready"

if (-not $SkipDeps) {
    Write-Host "    Upgrading pip..."
    & $venvPython -m pip install --upgrade pip --quiet
    Write-Host "    Installing requirements (this may take 2-5 min)..."
    & $venvPython -m pip install -r requirements.txt --quiet
    Write-Ok "Python dependencies installed"

    # Verify MetaTrader5 importable
    & $venvPython -c "import MetaTrader5; print('MT5 lib OK', MetaTrader5.__version__)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "import MetaTrader5 failed — required for live trading"
        exit 1
    }
    Write-Ok "MetaTrader5 module importable"
} else {
    Write-Warn "Skipped pip install (--SkipDeps)"
}

# ── Step 3: Frontend ─────────────────────────────────────────
Write-Step "Frontend (npm install)..."
if (-not $SkipDeps) {
    Push-Location frontend
    if (Test-Path node_modules) {
        Write-Ok "node_modules exists — skipping (delete to force reinstall)"
    } else {
        Write-Host "    Running npm install..."
        npm install --silent
        if (-not (Test-Path node_modules)) { Pop-Location; Write-Err "npm install failed"; exit 1 }
        Write-Ok "node_modules installed"
    }
    Pop-Location
} else {
    Write-Warn "Skipped npm install (--SkipDeps)"
}

# ── Step 4: .env ─────────────────────────────────────────────
Write-Step ".env file..."
$envPath = Join-Path $repoRoot '.env'

if (Test-Path $envPath) {
    Write-Ok ".env already exists — leaving untouched (delete to regenerate)"
} else {
    if ($NoEnvPrompt) {
        Write-Warn ".env missing + --NoEnvPrompt set — creating with placeholders"
        $login    = '<MT5_LOGIN>'
        $password = '<MT5_PASSWORD>'
        $server   = 'Exness-MT5Real25'
        $balance  = '1000'
    } else {
        Write-Host ""
        Write-Host "    Enter MT5 broker credentials (will be saved to .env):" -ForegroundColor Yellow
        $login    = Read-Host "    MT5 login (account number)"
        $passSec  = Read-Host "    MT5 password" -AsSecureString
        $password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passSec))
        $server   = Read-Host "    MT5 server [Exness-MT5Real25]"
        if (-not $server) { $server = 'Exness-MT5Real25' }
        $balance  = Read-Host "    Account balance shown in MT5 (raw number)"
        if (-not $balance) { $balance = '1000' }
    }

    @"
# Tra(i)der Server .env — auto-generated $(Get-Date -Format 'yyyy-MM-dd HH:mm')

# Anthropic API (optional — leave empty if not using Claude reviewer)
ANTHROPIC_API_KEY=

# Notification / logging integrations
LINE_NOTIFY_ENABLED=false
LINE_CHANNEL_TOKEN=
LINE_USER_ID=
SHEETS_ENABLED=false
GOOGLE_SHEETS_ID=
GOOGLE_CREDENTIALS_JSON=./credentials.json

# MT5 broker
MT5_LOGIN=$login
MT5_PASSWORD=$password
MT5_SERVER=$server
MT5_TERMINAL_PATH=$mt5Path

# TradingView (optional fallback data source)
TV_USERNAME=
TV_PASSWORD=

# Risk
ACCOUNT_BALANCE=$balance
RISK_PCT=10
LOG_LEVEL=INFO
"@ | Set-Content -Path $envPath -Encoding UTF8

    Write-Ok ".env created (review/edit if needed)"
}

# ── Step 5: Build TraiderLauncher.exe ────────────────────────
Write-Step "Build TraiderLauncher.exe..."
$exePath = Join-Path $repoRoot 'TraiderLauncher.exe'

if ($SkipExe) {
    Write-Warn "Skipped exe build (--SkipExe)"
} elseif ((Test-Path $exePath) -and ((Get-Item $exePath).LastWriteTime -gt (Get-Item launcher.py).LastWriteTime)) {
    Write-Ok ".exe is newer than launcher.py — skipping (delete .exe to force rebuild)"
} else {
    Write-Host "    Running PyInstaller (60-90 sec)..."
    & $venvPython -m PyInstaller --noconfirm --onefile --windowed `
        --name TraiderLauncher `
        --add-data "config\strategies.json;config" `
        --hidden-import tkinter `
        launcher.py 2>&1 | Out-Null

    $distExe = Join-Path $repoRoot 'dist\TraiderLauncher.exe'
    if (-not (Test-Path $distExe)) { Write-Err "Build failed — check PyInstaller output"; exit 1 }
    Copy-Item $distExe $exePath -Force
    Write-Ok "TraiderLauncher.exe built ($([math]::Round((Get-Item $exePath).Length / 1MB, 1)) MB)"
}

# ── Step 6: Disable sleep ────────────────────────────────────
Write-Step "Disable sleep / hibernation..."
try {
    powercfg /change standby-timeout-ac 0   2>&1 | Out-Null
    powercfg /change hibernate-timeout-ac 0 2>&1 | Out-Null
    powercfg /change monitor-timeout-ac 0   2>&1 | Out-Null
    Write-Ok "Power settings: never sleep on AC"
} catch {
    Write-Warn "powercfg failed (need admin?): $_"
}

# ── Step 7: Smoke test ───────────────────────────────────────
Write-Step "Smoke test..."
$result = & $venvPython -c @"
import sys
ok = True
try:
    from main import TraiderMainLoop
    print('  main: OK')
except Exception as e:
    print(f'  main: FAIL {e}'); ok = False
try:
    import api_server
    print('  api_server: OK')
except Exception as e:
    print(f'  api_server: FAIL {e}'); ok = False
try:
    from agents.mt5_live_broker import MT5LiveBroker
    print('  mt5_live_broker: OK')
except Exception as e:
    print(f'  mt5_live_broker: FAIL {e}'); ok = False
try:
    from strategies.mountain import find_signal as _m
    from strategies.mai_ruay import find_signal as _r
    print('  strategies: OK')
except Exception as e:
    print(f'  strategies: FAIL {e}'); ok = False
sys.exit(0 if ok else 1)
"@
Write-Host $result
if ($LASTEXITCODE -ne 0) { Write-Err "Smoke test failed — fix imports before continuing"; exit 1 }
Write-Ok "Imports clean"

# ── Done ─────────────────────────────────────────────────────
Write-Host "`n===== Setup complete =====" -ForegroundColor Green
Write-Host @"

Next steps (manual):
  1. Open MT5 EXNESS, login, and enable Algo Trading (toolbar button → green)
  2. Verify XAUUSDc is visible in Market Watch
  3. (Optional) Auto-start at login:
       .\scripts\install_task_scheduler.ps1
  4. Test launcher:
       .\TraiderLauncher.exe

Documentation: docs\SERVER_DEPLOY.md
"@ -ForegroundColor White
