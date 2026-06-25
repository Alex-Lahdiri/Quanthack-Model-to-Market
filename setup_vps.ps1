# setup_vps.ps1 -- one-shot Quanthack setup on a fresh Windows VPS.
# Run as Administrator in the PROJECT ROOT, after: Python installed (on PATH) + project copied + MT5 installed.
# Path-agnostic: it uses THIS folder's location, so the laptop's hardcoded paths don't matter.

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Write-Host "Quanthack VPS setup | project root: $root" -ForegroundColor Cyan

# 1) Python dependencies
Write-Host "`n[1/4] installing Python packages (this takes a few minutes)..."
python -m pip install --upgrade pip
python -m pip install pandas numpy scipy scikit-learn pyarrow polars MetaTrader5 openai anthropic pydantic pydantic-ai logfire

# 2) never sleep / hibernate (screen may still turn off; the machine stays awake)
Write-Host "`n[2/4] disabling sleep + hibernate..."
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0

$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew

# 3) main cycle task (every 60 min; change the interval for rev: register_task.ps1 -IntervalMinutes 15)
Write-Host "`n[3/4] registering QuanthackCycle (every 60 min)..."
$cycle  = Join-Path $root "live\run_cycle.ps1"
$aCycle = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $cycle)
$tCycle = New-ScheduledTaskTrigger -Once -At (Get-Date)
$tCycle.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 60) -RepetitionDuration (New-TimeSpan -Days 3)).Repetition
Register-ScheduledTask -TaskName "QuanthackCycle" -Action $aCycle -Trigger $tCycle -Settings $set -Force | Out-Null

# 4) fast monitor task (every 3 min, live reduce-only -- harmless until positions exist)
Write-Host "[4/4] registering QuanthackFastMonitor (every 3 min)..."
$aFast = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -Command `"Set-Location '{0}'; python live\fast_monitor.py --live --i-confirm-paper`"" -f $root)
$tFast = New-ScheduledTaskTrigger -Once -At (Get-Date)
$tFast.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 3) -RepetitionDuration (New-TimeSpan -Days 3)).Repetition
Register-ScheduledTask -TaskName "QuanthackFastMonitor" -Action $aFast -Trigger $tFast -Settings $set -Force | Out-Null

Write-Host "`nDONE. Remaining manual steps:" -ForegroundColor Green
Write-Host "  1. setx NVIDIA_API_KEY / ANTHROPIC_API_KEY / LOGFIRE_TOKEN, then reopen PowerShell"
Write-Host "  2. MT5: log into account 10009, click Algo Trading GREEN"
Write-Host "  3. set live\runtime.json, dry-run:  `$env:QH_DRY=1; powershell -ExecutionPolicy Bypass -File live\run_cycle.ps1"
Write-Host "  4. tasks then run 24/7. Closing the RDP window does NOT stop them."
