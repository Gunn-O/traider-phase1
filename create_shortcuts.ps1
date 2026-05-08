# ============================================
# Traider Desktop Shortcuts Creator
# Creates shortcuts on Windows Desktop
# ============================================

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Creating Traider Desktop Shortcuts" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Get current directory
$projectPath = Get-Location

# Get Desktop path
$desktopPath = [Environment]::GetFolderPath("Desktop")

# Create WScript Shell object
$WScriptShell = New-Object -ComObject WScript.Shell

# Function to create shortcut
function Create-Shortcut {
    param(
        [string]$ShortcutName,
        [string]$TargetPath,
        [string]$IconPath,
        [string]$Description
    )

    $shortcutPath = Join-Path $desktopPath "$ShortcutName.lnk"
    $shortcut = $WScriptShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $projectPath
    $shortcut.Description = $Description

    if ($IconPath -and (Test-Path $IconPath)) {
        $shortcut.IconLocation = $IconPath
    }

    $shortcut.Save()

    Write-Host "  [OK] Created: $ShortcutName" -ForegroundColor Green
}

# 1. Dashboard Shortcut (Main launcher)
Write-Host "[1/4] Creating Dashboard shortcut..."
Create-Shortcut `
    -ShortcutName "Traider Dashboard" `
    -TargetPath (Join-Path $projectPath "start_dashboard.bat") `
    -Description "Start Traider Dashboard (Backend + Frontend + Browser)"

# 2. Bot Launcher Shortcut
Write-Host "[2/4] Creating Bot Launcher shortcut..."
Create-Shortcut `
    -ShortcutName "Traider Bot" `
    -TargetPath (Join-Path $projectPath "start_bot.bat") `
    -Description "Traider Trading Bot - Select Mode (Backtest/Simulate/Live)"

# 3. Backend Only Shortcut
Write-Host "[3/4] Creating Backend shortcut..."
Create-Shortcut `
    -ShortcutName "Traider Backend" `
    -TargetPath (Join-Path $projectPath "start_backend.bat") `
    -Description "Start Traider Backend API Server Only"

# 4. Frontend Only Shortcut
Write-Host "[4/4] Creating Frontend shortcut..."
Create-Shortcut `
    -ShortcutName "Traider Frontend" `
    -TargetPath (Join-Path $projectPath "start_frontend.bat") `
    -Description "Start Traider Frontend Dashboard Only"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Shortcuts created successfully!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Desktop shortcuts created:" -ForegroundColor Yellow
Write-Host "  - Traider Dashboard  (Recommended - Starts everything)" -ForegroundColor White
Write-Host "  - Traider Bot        (Choose mode: Backtest/Sim/Live)" -ForegroundColor White
Write-Host "  - Traider Backend    (API server only)" -ForegroundColor White
Write-Host "  - Traider Frontend   (Dashboard only)" -ForegroundColor White
Write-Host ""
Write-Host "You can now double-click these shortcuts to start!" -ForegroundColor Green
Write-Host ""

Read-Host "Press Enter to exit"
