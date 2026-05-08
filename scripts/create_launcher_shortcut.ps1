# Create Desktop shortcut to TraiderLauncher.exe (or launcher.py)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\create_launcher_shortcut.ps1

$ErrorActionPreference = 'Stop'

$root = Resolve-Path "$PSScriptRoot\.."
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Tra(i)der.lnk'

# Prefer compiled .exe, fall back to launcher.py via python
$exePath = Join-Path $root 'TraiderLauncher.exe'
$pyPath  = Join-Path $root 'launcher.py'
$venvPy  = Join-Path $root 'venv\Scripts\pythonw.exe'

if (Test-Path $exePath) {
    $target    = $exePath
    $arguments = ''
    Write-Host "Using compiled exe: $exePath"
} elseif ((Test-Path $pyPath) -and (Test-Path $venvPy)) {
    $target    = $venvPy
    $arguments = "`"$pyPath`""
    Write-Host "Using python launcher: $venvPy $pyPath"
} else {
    Write-Error "Neither TraiderLauncher.exe nor launcher.py found. Build with scripts\build_launcher_exe.bat first."
    exit 1
}

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath       = $target
$shortcut.Arguments        = $arguments
$shortcut.WorkingDirectory = $root.Path
$shortcut.Description      = 'Tra(i)der Trading Bot Launcher'
$shortcut.IconLocation     = "$env:SystemRoot\System32\shell32.dll,167"  # generic chart icon
$shortcut.Save()

Write-Host ""
Write-Host "Shortcut created: $shortcutPath"
Write-Host "Double-click to start MT5 + Backend + Frontend + Open Dashboard"
