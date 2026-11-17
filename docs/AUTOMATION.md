# Hands-off automation (Windows Task Scheduler)

Runs the full loop every hour while you sleep: **pull prices from MT5 → build the target book
(with drawdown guard + Nemotron news gate) → execute the deltas on the paper account.** Everything
is logged, and it's **dry-run until you flip one switch**.

## What runs each hour
`live\run_cycle.ps1` does, in order:
1. `mt5_feed.py` → refreshes `panel_live.parquet` from the running MT5 terminal.
2. `live_runner.py` → writes `book.json` at the gross from `runtime.json`, with `--dd-guard`, the `--risk-gate`, and Logfire tracing.
3. `mt5_bridge.py` → trades the delta vs your current positions (dry-run, or live if you enabled it).

Logs land in `live\logs\cycle_YYYYMMDD.log` - open it any time to see exactly what happened.

## The one config file: `live\runtime.json`
```json
{ "gross": 2.0, "strategy": "mv", "live": false }
```
- **gross** - change this per round (use `gross_planner.py` to decide). No need to touch Task Scheduler.
- **live** - `false` = dry-run (plans orders, sends nothing). `true` = actually execute on the paper account.

## Prerequisites (must be true while it runs)
- **MT5 terminal open and logged in** to account 10009 (the scripts attach to it).
- **Env vars set permanently:** `setx NVIDIA_API_KEY "nvapi-..."` and `setx NEMOTRON_MODEL "nvidia/nemotron-mini-4b-instruct"`.
- **Laptop on and not asleep.** Task Scheduler + MT5 only run while Windows is awake - so plug in and disable sleep:
  `powercfg /change standby-timeout-ac 0` (or Settings → Power → Screen & sleep → "Never" on power).
  If the laptop sleeps or shuts, trading pauses until it's back; the loop just resumes next hour.

## Setup (do this Saturday, ~5 min)
1. **Test one cycle by hand (dry-run, sends nothing):**
   ```powershell
   cd C:\Users\alex\OneDrive\Desktop\Backtest\quanthack_backtester
   powershell -ExecutionPolicy Bypass -File live\run_cycle.ps1
   ```
   Then open `live\logs\cycle_<today>.log` and confirm feed → runner → bridge all ran and the bridge printed a DRY-RUN plan.
2. **Register the hourly task:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File live\register_task.ps1
   ```
   Open **Task Scheduler** (Start → search it) and confirm **QuanthackCycle** is listed. Right-click → **Run** to fire it once and re-check the log.

## Go-live (Sunday 22:00)
Edit `live\runtime.json` and set `"live": true`. That's the only change - the task is already running hourly, and now it executes instead of dry-running. To set the round's gross, also set `"gross"` to whatever `gross_planner.py` recommends (start at **2**).

## Each round
1. Run `python live\gross_planner.py --round N --rounds-total 4 --standing <safe|middle|at-risk>`.
2. Put the recommended number in `runtime.json` → `"gross"`. The next cycle picks it up automatically.

## Stop / pause it
- Pause trading but keep the task: set `"live": false` in `runtime.json`.
- Stop entirely: Task Scheduler → QuanthackCycle → Disable (or `Unregister-ScheduledTask -TaskName QuanthackCycle -Confirm:$false`).

## Safety recap
Dry-run by default; the bridge refuses to send unless `live=true` **and** still aborts if the account ever looks real (trade_mode 0); the dd-guard auto-cuts size on drawdowns; rate-limited well under 500 req/s. It only ever trades the simulated contest account.
