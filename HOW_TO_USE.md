# How to use everything — one control panel

You don't need to remember any commands. There's a single menu.

## Open it
**Double-click `Quanthack.bat`** (in the `quanthack_backtester` folder).
Or, in PowerShell: `powershell -ExecutionPolicy Bypass -File quanthack.ps1`

You'll see a control panel with your current mode at the top (DRY-RUN in green = safe, or LIVE in red = orders will send).

## Before you start (one-time)
1. **MetaTrader 5 open and logged in** to account 10009 (prices ticking).
2. **Keys set once** (so the AI layer works). In PowerShell:
   ```powershell
   setx NVIDIA_API_KEY "nvapi-...your key..."
   setx NEMOTRON_MODEL "nvidia/nemotron-mini-4b-instruct"
   ```
   Optional for the full AI desk demo: `setx ANTHROPIC_API_KEY "..."` and `setx LOGFIRE_TOKEN "..."`.
   Close and reopen PowerShell after `setx` so they take effect.

## The menu
| # | What it does |
|---|--------------|
| **1** | **Check setup** — connects to MT5, lists your symbols, shows which keys are set. Run this first. |
| **2** | **Refresh + preview** — pulls live prices, builds the target book, runs the AI desk. **DRY-RUN: shows planned orders, sends nothing.** Your everyday "what would it do right now?" |
| **3** | **Plan this round** — asks your round + standing, recommends a gross level. |
| **4** | **Settings** — change the gross number and flip live ON/OFF. |
| **5** | **GO LIVE: one cycle** — actually sends orders on the paper account (asks you to type GO first; only works if live is ON). |
| **6** | **Automate (hourly)** — registers the scheduled task so the loop runs itself every hour. |
| **7** | **Stop automation** — unregisters it. |
| **8** | **Open dashboard** — opens your live dashboard in the browser. |
| **9** | **View today's log** — last 40 lines of what happened. |
| **0** | Exit. |

## Typical flows

**Now / any time (safe):** `1` to check, then `2` to preview. Look at the planned orders and the AI desk read-out. Nothing is sent.

**Go-live night (Sun 21, 22:00):**
1. `1` — confirm MT5 connected.
2. `3` — plan the round (start: gross 2).
3. `4` — set gross to 2 and live to **on**.
4. `5` — type GO to send the first cycle.
5. `6` — turn on hourly automation so it runs while you sleep.
6. `8` — open the dashboard to watch.

**Each new round:** `3` to get the gross, `4` to set it. The next automated cycle uses it.

**To pause trading:** `4` → set live **off** (the loop keeps running but only previews), or `7` to stop automation entirely.

## Safety
- Starts in **DRY-RUN**; it never sends an order until you turn live on **and** type GO (or enable automation).
- The bridge refuses to trade anything that isn't the paper/contest account.
- The AI desk and risk gate can only **reduce** exposure, never increase it.
- The drawdown ladder auto-cuts size if a round goes against you.
- Laptop must stay **on and awake** with MT5 open for live/automation to run.
