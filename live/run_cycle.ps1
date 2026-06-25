# Quanthack hourly cycle: refresh feed -> build target book -> AI desk review -> execute deltas.
# DRY-RUN unless live\runtime.json has "live": true. Everything is logged to live\logs\.
# Requires: MT5 terminal open + logged in; NVIDIA_API_KEY / NEMOTRON_MODEL set (setx); python on PATH.

$ErrorActionPreference = "Continue"
$root = "C:\Users\alex\OneDrive\Desktop\Backtest\quanthack_backtester"
Set-Location $root

$logdir = Join-Path $root "live\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$log = Join-Path $logdir ("cycle_" + (Get-Date -Format "yyyyMMdd") + ".log")
function Log($m) { ("{0}  {1}" -f (Get-Date -Format "HH:mm:ss"), $m) | Tee-Object -FilePath $log -Append }

# --- per-round config (gross / strategy / live toggle / crypto opt-in) ---
$gross = 2.0; $strategy = "mv"; $live = $false; $crypto = $false
$cfgPath = Join-Path $root "live\runtime.json"
if (Test-Path $cfgPath) {
    try {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json
        if ($c.gross)          { $gross = [double]$c.gross }
        if ($c.strategy)       { $strategy = [string]$c.strategy }
        if ($c.live)           { $live = $true }
        if ($c.include_crypto) { $crypto = $true }
    } catch { Log "WARN: couldn't parse runtime.json, using defaults (gross 2, mv, dry-run)" }
}
if ($env:QH_DRY) { $live = $false }   # control-panel 'preview' forces dry-run regardless of config
$cryptoArg = $null; if ($crypto) { $cryptoArg = "--include-crypto" }
Log "===== cycle start | gross=$gross strategy=$strategy live=$live crypto=$crypto ====="

# --- 1) refresh the price panel from the running MT5 terminal ---
Log "[1/3] feed: pulling prices from MT5..."
python live\mt5_feed.py --out panel_live.parquet --lookback-days 5 $cryptoArg 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Log "feed FAILED (is MT5 open + logged in?). Skipping this cycle."; exit 1 }

# --- 2) build the target book (drawdown guard + news gate on, traced to Logfire) ---
Log "[2/3] runner: building target book at gross $gross ($strategy)..."
python live\live_runner.py --panel panel_live.parquet --strategy $strategy --gross $gross `
    --emit book.json --dd-guard --profit-lock --peak-state peak.json `
    --risk-gate --headlines live\headlines.txt $cryptoArg --logfire 2>&1 | Tee-Object -FilePath $log -Append
if (-not (Test-Path (Join-Path $root "book.json"))) { Log "no book.json produced. Skipping execution."; exit 1 }

# --- 2b) AI trading desk review (advisory, reduce-only) + Logfire trace + Claude rationale ---
Log "[desk] AI trading desk review..."
python live\desk.py --book book.json --headlines live\headlines.txt --peak-state peak.json --emit desk_decision.json --logfire 2>&1 | Tee-Object -FilePath $log -Append

# --- 2c) PREFLIGHT safety gate: HALT (no orders) if the feed is stale or the book is insane ---
Log "[preflight] safety checks..."
python live\preflight.py --panel panel_live.parquet --book book.json 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Log "PREFLIGHT HALT -> no orders this cycle."; exit 1 }

# --- 3) execute the deltas vs current positions ---
if ($live) {
    Log "[3/3] bridge: LIVE execution on the paper/contest account..."
    python live\mt5_bridge.py --book book.json --live --i-confirm-paper 2>&1 | Tee-Object -FilePath $log -Append
} else {
    Log "[3/3] bridge: DRY-RUN (flip live=true in runtime.json to send orders)..."
    python live\mt5_bridge.py --book book.json 2>&1 | Tee-Object -FilePath $log -Append
}
Log "===== cycle done ====="
