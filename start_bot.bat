@echo off
REM ============================================
REM Traider Bot Launcher
REM Quick launcher for different trading modes
REM ============================================

title Traider - Bot Launcher

:MENU
cls
echo.
echo ============================================
echo   Traider Trading Bot
echo   Version: V4.26 (V65 Verified)
echo ============================================
echo.
echo Select Mode:
echo.
echo   1. Backtest (Historical Data, No API)
echo   2. Simulation (Paper Trading, With API)
echo   3. Live Trading (Real Money - CAREFUL!)
echo   4. Winrate Test (0.01 lot, No API)
echo   5. Dashboard Only (Web UI)
echo   6. Exit
echo.
echo ============================================
echo.

set /p choice="Enter your choice (1-6): "

if "%choice%"=="1" goto BACKTEST
if "%choice%"=="2" goto SIMULATE
if "%choice%"=="3" goto LIVE
if "%choice%"=="4" goto WINRATE
if "%choice%"=="5" goto DASHBOARD
if "%choice%"=="6" goto EXIT

echo Invalid choice! Please try again.
timeout /t 2 /nobreak >nul
goto MENU

:BACKTEST
cls
echo.
echo ============================================
echo   Backtest Mode
echo ============================================
echo.
set /p startdate="Enter start date (YYYY-MM-DD): "
set /p enddate="Enter end date (YYYY-MM-DD): "
echo.
echo Running backtest from %startdate% to %enddate%...
echo.
call venv\Scripts\activate.bat
python main.py --backtest --start %startdate% --end %enddate% --no-ai
echo.
echo Backtest complete!
echo.
pause
goto MENU

:SIMULATE
cls
echo.
echo ============================================
echo   Simulation Mode (Paper Trading)
echo ============================================
echo.
echo This will connect to MT5 and simulate trading
echo using Claude API for signal review.
echo.
set /p confirm="Continue? (Y/N): "
if /i not "%confirm%"=="Y" goto MENU
echo.
call venv\Scripts\activate.bat
python main.py --simulate
pause
goto MENU

:LIVE
cls
echo.
echo ============================================
echo   LIVE TRADING MODE
echo   WARNING: REAL MONEY!
echo ============================================
echo.
echo This will place REAL orders with REAL money!
echo.
set /p confirm1="Are you ABSOLUTELY SURE? (Y/N): "
if /i not "%confirm1%"=="Y" goto MENU
echo.
set /p confirm2="Final confirmation - Type 'LIVE' to continue: "
if /i not "%confirm2%"=="LIVE" (
    echo.
    echo Live trading cancelled.
    timeout /t 2 /nobreak >nul
    goto MENU
)
echo.
echo Starting live trading...
echo.
call venv\Scripts\activate.bat
python main.py --live
pause
goto MENU

:WINRATE
cls
echo.
echo ============================================
echo   Winrate Test Mode
echo ============================================
echo.
echo This will run backtest with 0.01 lot for all trades
echo (no API calls)
echo.
call venv\Scripts\activate.bat
python main.py --winrate-test --no-ai
echo.
echo Winrate test complete!
echo.
pause
goto MENU

:DASHBOARD
cls
echo.
echo ============================================
echo   Starting Dashboard...
echo ============================================
echo.
call start_dashboard.bat
goto EXIT

:EXIT
echo.
echo Goodbye!
timeout /t 1 /nobreak >nul
exit
