@echo off
REM Build TraiderLauncher.exe via PyInstaller
REM Usage: scripts\build_launcher_exe.bat
REM Output: dist\TraiderLauncher.exe

cd /d %~dp0\..
echo === Building TraiderLauncher.exe ===
echo.

call venv\Scripts\activate.bat

pyinstaller --noconfirm --onefile --windowed ^
            --name TraiderLauncher ^
            --add-data "config\strategies.json;config" ^
            --hidden-import tkinter ^
            launcher.py

echo.
echo === Build complete ===
echo Output: dist\TraiderLauncher.exe
echo.

REM Optional: copy to project root for easy access
if exist dist\TraiderLauncher.exe (
    copy /Y dist\TraiderLauncher.exe TraiderLauncher.exe
    echo Copied TraiderLauncher.exe to project root
)

pause
