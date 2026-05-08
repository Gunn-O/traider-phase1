<#
.SYNOPSIS
    Auto-start TraiderLauncher.exe at user logon via Windows Task Scheduler.
.DESCRIPTION
    Creates / updates a scheduled task `TraiderLauncher` that:
      - Triggers on user logon (any user)
      - Runs TraiderLauncher.exe at HIGHEST privilege level
      - Restarts up to 3 times if launcher exits unexpectedly
      - Survives reboots

    Run as administrator from repo root.

    Uninstall:  .\scripts\install_task_scheduler.ps1 -Uninstall
.PARAMETER Uninstall
    Remove the scheduled task instead of creating it.
.EXAMPLE
    .\scripts\install_task_scheduler.ps1
.EXAMPLE
    .\scripts\install_task_scheduler.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [switch] $Uninstall
)

$ErrorActionPreference = 'Stop'
$taskName = 'TraiderLauncher'

# ── Locate repo + exe ───────────────────────────────────────
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exePath  = Join-Path $repoRoot 'TraiderLauncher.exe'

# ── Uninstall path ──────────────────────────────────────────
if ($Uninstall) {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "[OK] Removed scheduled task '$taskName'" -ForegroundColor Green
    } else {
        Write-Host "[i] Task '$taskName' was not registered" -ForegroundColor Yellow
    }
    return
}

# ── Validate ─────────────────────────────────────────────────
if (-not (Test-Path $exePath)) {
    Write-Host "[X] TraiderLauncher.exe not found at: $exePath" -ForegroundColor Red
    Write-Host "    Build it first: .\scripts\setup_server.ps1" -ForegroundColor Yellow
    exit 1
}

# Require admin (RegisterScheduledTask needs it for HIGHEST RunLevel)
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[X] Must run as Administrator" -ForegroundColor Red
    Write-Host "    Right-click PowerShell → Run as administrator" -ForegroundColor Yellow
    exit 1
}

# ── Build task definition ───────────────────────────────────
$action  = New-ScheduledTaskAction -Execute $exePath -WorkingDirectory $repoRoot

# Trigger: at user logon (any user). Delay 30s to let MT5 finish auto-start
# (MT5 itself launches via launcher; this delay just gives the system breathing room).
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = 'PT30S'

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

# Run as current user with highest privileges
$principal = New-ScheduledTaskPrincipal `
    -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -RunLevel Highest `
    -LogonType Interactive

# ── Register / replace ──────────────────────────────────────
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[i] Removed existing task to update" -ForegroundColor Yellow
}

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Tra(i)der trading bot launcher — auto-starts at logon" `
    | Out-Null

Write-Host "[OK] Scheduled task '$taskName' installed" -ForegroundColor Green
Write-Host @"

Triggers at every logon, 30s delay.
Runs:    $exePath
Restart: up to 3 times on failure (5 min interval)

Verify:
  Get-ScheduledTask -TaskName '$taskName' | Format-List
  Start-ScheduledTask -TaskName '$taskName'   # test now without logoff

Uninstall:
  .\scripts\install_task_scheduler.ps1 -Uninstall
"@ -ForegroundColor White
