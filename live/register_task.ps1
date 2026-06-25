# Register the hourly Quanthack cycle in Windows Task Scheduler.
# Run this ONCE in a normal PowerShell window (it runs "only when you're logged on",
# which is what we want -- it needs your MT5 terminal + your user environment).

param([int]$IntervalMinutes = 60)   # cadence dial: 60 = hourly (trending), 240 = every 4h (choppy)

$root   = "C:\Users\alex\OneDrive\Desktop\Backtest\quanthack_backtester"
$script = Join-Path $root "live\run_cycle.ps1"

$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
           -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $script)

# fire now, then repeat every 60 min for 7 days (covers the competition)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date)
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
                       -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
                       -RepetitionDuration (New-TimeSpan -Days 7)).Repetition

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "QuanthackCycle" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Quanthack hourly feed->book->execute" -Force

Write-Host ""
Write-Host "Registered 'QuanthackCycle' -- runs every $IntervalMinutes min for 7 days."
Write-Host "It reads gross + the live toggle from live\runtime.json each run."
Write-Host "Manage/stop it in Task Scheduler (search 'Task Scheduler' in Start), or run:"
Write-Host "  Unregister-ScheduledTask -TaskName QuanthackCycle -Confirm:`$false"
