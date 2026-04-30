@echo off
REM ============================================
REM Traider Frontend Launcher
REM Starts React development server
REM ============================================

title Traider - Frontend Dashboard

echo.
echo ============================================
echo   Traider Frontend Dashboard
echo ============================================
echo.

REM Check if frontend folder exists
if not exist "frontend" (
    echo ERROR: Frontend folder not found!
    pause
    exit /b 1
)

REM Navigate to frontend
cd frontend

REM Check if node_modules exists
if not exist "node_modules" (
    echo [1/3] Installing dependencies...
    call npm install
    echo.
) else (
    echo [1/3] Dependencies already installed
)

REM Start frontend
echo [2/3] Starting development server...
echo.
echo Frontend: http://localhost:3001
echo.
echo Press Ctrl+C to stop
echo ============================================
echo.

call npm run dev

pause
