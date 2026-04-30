@echo off
REM ============================================
REM Traider Dashboard Launcher (All-in-One)
REM Starts Backend + Frontend + Opens Browser
REM ============================================

title Traider - Dashboard Launcher

echo.
echo ============================================
echo   Starting Traider Dashboard
echo ============================================
echo.

REM Check if required files exist
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found!
    echo Please run: python -m venv venv
    echo Then install: pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "frontend\package.json" (
    echo ERROR: Frontend not found!
    pause
    exit /b 1
)

REM Start backend in new window
echo [1/4] Starting Backend API...
start "Traider Backend" cmd /k "call venv\Scripts\activate.bat && python api_server.py"

REM Wait for backend to start
echo [2/4] Waiting for backend to initialize...
timeout /t 5 /nobreak >nul

REM Start frontend in new window
echo [3/4] Starting Frontend Dashboard...
start "Traider Frontend" cmd /k "cd frontend && npm run dev"

REM Wait for frontend to start
echo [4/4] Waiting for frontend to initialize...
timeout /t 10 /nobreak >nul

REM Open dashboard in default browser
echo.
echo ============================================
echo   Opening Dashboard...
echo ============================================
echo.
echo   Backend:  http://127.0.0.1:8080
echo   Frontend: http://localhost:3001
echo   Docs:     http://127.0.0.1:8080/docs
echo.

start http://localhost:3001

echo.
echo Dashboard opened in browser!
echo.
echo Two windows are running:
echo   - Traider Backend  (API Server)
echo   - Traider Frontend (React App)
echo.
echo To stop: Close both windows or press Ctrl+C in each
echo.
pause
