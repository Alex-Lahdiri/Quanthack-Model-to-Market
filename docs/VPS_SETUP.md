# Quanthack on a VPS - 24/7, never sleeps, survives travel

**Why:** last night's outage was your laptop *sleeping*. A Windows VPS runs MT5 + your cycle
around the clock, stays connected, and is independent of your laptop - it would have prevented
that entirely. This is what makes the finals bulletproof (and it ignores your drive to Bristol).

## 1. Get a Windows VPS
- You need a **full Windows VPS with RDP** (Remote Desktop) - *not* a broker "MT5 VPS" (those
  only host EAs, not Python).
- Spec: **2 vCPU, 4 GB RAM, Windows Server 2022**, ~$10–30/mo (hourly/trial options exist).
- Pick a region with **low latency to the broker** (server `3.11.134.149`) - a UK/EU datacenter.
- Any mainstream cloud Windows VPS works (search "Windows VPS RDP hourly").

## 2. Log in (RDP)
- Connect with Remote Desktop using the VPS IP + credentials. Set a **strong password** - your
  contest account will live here.

## 3. Install essentials
- **MetaTrader 5**: install, log into the contest account (login `10009`, server
  `3.11.134.149:443`). Confirm "connected" + balance.
- **Python 3.12+**: from python.org - **tick "Add Python to PATH"**.

## 4. Copy the project over
- Zip `quanthack_backtester` on your laptop → transfer via RDP copy-paste (or OneDrive in the
  VPS browser). Put it somewhere simple, e.g. `C:\quanthack\quanthack_backtester`.

## 5. One-shot setup
Open **PowerShell as Administrator** in the project folder:
```powershell
powershell -ExecutionPolicy Bypass -File setup_vps.ps1
```
This installs every Python dependency, disables sleep, and registers the cycle + fast-monitor
scheduled tasks **using the VPS's own path** (so the hardcoded laptop paths don't matter).

## 6. Set your API keys (then reopen PowerShell)
```powershell
setx NVIDIA_API_KEY "your-key"
setx ANTHROPIC_API_KEY "your-key"
setx LOGFIRE_TOKEN "your-token"
```

## 7. Enable AutoTrading + test
- In MT5, click **Algo Trading** so it's **green**.
- Dry-run a cycle first, then go live:
```powershell
$env:QH_DRY=1; powershell -ExecutionPolicy Bypass -File live\run_cycle.ps1   # preview
# then set live\runtime.json (gross/strategy/live=true) and let the tasks drive
```
- For the `rev` strategy, re-register the cycle faster: `live\register_task.ps1 -IntervalMinutes 15`.

## 8. Disconnect freely
**Closing the RDP window does NOT stop the VPS** - it runs 24/7. Reconnect anytime to check.

## Daily check (30 sec)
- RDP in → MT5 connected + Algo green → skim `live\logs\cycle_*.log`.
- `python live\autopilot.py --logfire` to see the AI desk's current read.
- Log into the competition console once per session (8h inactivity = DQ).
