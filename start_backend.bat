@echo off
REM ============================================
REM Traider Backend Launcher
REM Starts FastAPI server
REM ============================================

title Traider - Backend API

echo.
echo ============================================
echo   Traider Backend API Server
echo ============================================
echo.

REM Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found!
    echo Please run setup first: python -m venv venv
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
echo [1/3] Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if dependencies installed
echo [2/3] Checking dependencies...
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo.
    echo WARNING: Dependencies not installed!
    echo Installing now...
    pip install -r requirements.txt
    echo.
)

REM Start backend
echo [3/3] Starting API server...
echo.
echo API Server: http://127.0.0.1:8080
echo API Docs:   http://127.0.0.1:8080/docs
echo WebSocket:  ws://127.0.0.1:8080/ws
echo.
echo Press Ctrl+C to stop
echo ============================================
echo.

python api_server.py

pause
