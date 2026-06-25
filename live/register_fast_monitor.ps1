# Register the FAST risk monitor as a Windows task (every 3 minutes, reduce-only).
# Run this ONCE when you want it live (recommended: at the Round 1 break, after a dry-run test).
$root   = "C:\Users\alex\OneDrive\Desktop\Backtest\quanthack_backtester"
$script = Join-Path $root "live\fast_monitor.py"

$action  = New-ScheduledTaskAction -Execute "python" `
           -Argument ("`"{0}`" --live --i-confirm-paper" -f $script) -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date)
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
                       -RepetitionInterval (New-TimeSpan -Minutes 3) `
                       -RepetitionDuration (New-TimeSpan -Days 7)).Repetition
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "QuanthackFastMonitor" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Quanthack fast intra-hour risk monitor (reduce-only)" -Force

Write-Host ""
Write-Host "Registered 'QuanthackFastMonitor' -- runs every 3 minutes, trims positions on drawdown (reduce-only)."
Write-Host "It shares the de-risk ladder with the hourly loop, so they agree."
Write-Host "Stop it:  Unregister-ScheduledTask -TaskName QuanthackFastMonitor -Confirm:`$false"
