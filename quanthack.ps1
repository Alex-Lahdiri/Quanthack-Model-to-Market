# ============================================================
#   QUANTHACK CONTROL PANEL  -  one menu to run everything
#   Launch by double-clicking Quanthack.bat, or:
#     powershell -ExecutionPolicy Bypass -File quanthack.ps1
# ============================================================
$root = "C:\Users\alex\OneDrive\Desktop\Backtest\quanthack_backtester"
Set-Location $root
$cfg = Join-Path $root "live\runtime.json"

function Get-Cfg {
    if (Test-Path $cfg) { try { return Get-Content $cfg -Raw | ConvertFrom-Json } catch {} }
    return [pscustomobject]@{ gross = 2.0; strategy = "mv"; live = $false }
}
function Pause2 { Read-Host "`n  Press Enter to return to the menu" | Out-Null }
function Header {
    $c = Get-Cfg; Clear-Host
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "    QUANTHACK CONTROL PANEL" -ForegroundColor Cyan
    $state = if ($c.live) { "LIVE (orders WILL send)" } else { "DRY-RUN (safe)" }
    $col = if ($c.live) { "Red" } else { "Green" }
    Write-Host ("    strategy={0}   gross={1}x   mode={2}" -f $c.strategy, $c.gross, $state) -ForegroundColor $col
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  [1] Check setup         MT5 connection + keys + files"
    Write-Host "  [2] Refresh + preview   prices -> book -> AI desk  (DRY, sends nothing)"
    Write-Host "  [3] Plan this round     gross recommendation for your standing"
    Write-Host "  [4] Settings            change gross / turn live ON-OFF"
    Write-Host "  [5] GO LIVE: one cycle  executes on the paper account" -ForegroundColor Yellow
    Write-Host "  [6] Automate (hourly)   register the scheduled task"
    Write-Host "  [7] Stop automation"
    Write-Host "  [8] Open dashboard"
    Write-Host "  [9] View today's log"
    Write-Host "  [0] Exit"
    Write-Host ""
}

while ($true) {
    Header
    switch (Read-Host "  Choose") {
        "1" {
            Write-Host "`n-- MT5 connection --" -ForegroundColor Cyan
            python live\mt5_probe.py
            Write-Host "`n-- keys --" -ForegroundColor Cyan
            Write-Host ("  NVIDIA_API_KEY set : {0}" -f [bool]$env:NVIDIA_API_KEY)
            Write-Host ("  NEMOTRON_MODEL     : {0}" -f $env:NEMOTRON_MODEL)
            Write-Host ("  ANTHROPIC_API_KEY  : {0} (optional)" -f [bool]$env:ANTHROPIC_API_KEY)
            Write-Host ("  LOGFIRE_TOKEN      : {0} (optional)" -f [bool]$env:LOGFIRE_TOKEN)
            Write-Host "`n  REMINDER: before going live, MT5's 'Algo Trading' toolbar button must be ON (green)." -ForegroundColor Yellow
            Write-Host "  (Orders returning retcode 10027 = that button is off.)"
            Pause2
        }
        "2" {
            $env:QH_DRY = "1"
            powershell -ExecutionPolicy Bypass -File live\run_cycle.ps1
            $env:QH_DRY = $null
            Write-Host "`n  DRY RUN complete - nothing was sent. Review the planned orders above." -ForegroundColor Green
            Pause2
        }
        "3" {
            $r = Read-Host "  Round number (1-4)"
            $st = Read-Host "  Standing? safe / middle / at-risk / Enter=unknown"
            if (-not $st) { $st = "unknown" }
            python live\gross_planner.py --round $r --rounds-total 4 --standing $st
            Pause2
        }
        "4" {
            $c = Get-Cfg
            $g = Read-Host ("  Gross (current {0}) - Enter to keep" -f $c.gross)
            if (-not $g) { $g = $c.gross }
            $l = Read-Host ("  Live mode? type on / off (current {0})" -f $c.live)
            $live = if ($l -eq "on") { $true } elseif ($l -eq "off") { $false } else { [bool]$c.live }
            (@{ gross = [double]$g; strategy = $c.strategy; live = $live } | ConvertTo-Json) | Set-Content $cfg
            Write-Host ("`n  Saved: gross={0}x  live={1}" -f $g, $live) -ForegroundColor Green
            Pause2
        }
        "5" {
            $c = Get-Cfg
            if (-not $c.live) {
                Write-Host "`n  Live mode is OFF. Turn it on in [4] first." -ForegroundColor Red
            } else {
                Write-Host ("`n  About to SEND ORDERS on the paper account at gross {0}x." -f $c.gross) -ForegroundColor Yellow
                if ((Read-Host "  Type GO to confirm") -eq "GO") {
                    powershell -ExecutionPolicy Bypass -File live\run_cycle.ps1
                } else { Write-Host "  Cancelled." }
            }
            Pause2
        }
        "6" { powershell -ExecutionPolicy Bypass -File live\register_task.ps1; Pause2 }
        "7" {
            try { Unregister-ScheduledTask -TaskName QuanthackCycle -Confirm:$false; Write-Host "`n  Automation stopped." -ForegroundColor Green }
            catch { Write-Host "`n  No scheduled task found." }
            Pause2
        }
        "8" {
            if (Test-Path "$root\dashboard.html") { Start-Process "$root\dashboard.html" } else { Write-Host "  dashboard.html not found" }
        }
        "9" {
            $lg = Join-Path $root ("live\logs\cycle_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
            if (Test-Path $lg) { Get-Content $lg -Tail 40 } else { Write-Host "`n  No log yet today." }
            Pause2
        }
        "0" { Write-Host "  Bye."; exit }
        default { }
    }
}
