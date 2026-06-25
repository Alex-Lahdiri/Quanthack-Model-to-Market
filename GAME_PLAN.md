# GAME PLAN — Model to Market (Quanthack)

**Strategy in one line:** a market-neutral 8-hour-momentum book, shrinkage-MV sized, run at
*conservative* leverage (2-3x), behind a risk engine + drawdown de-risk that make blow-ups and
penalties near-impossible. We win by **surviving the knockout** + the **$10k Sharpe prize** + the **Tech prize**.

**Timeline (BST):** Jun 17 prep · Jun 18 22:00 API + reg deadline · Jun 19 08:00 pick method ·
Jun 21 22:00 **LAUNCH** · Jun 22/23/24 22:00 round cuts · Jun 24-26 Finals · Jun 27 results.

**Everything lives in:** `Desktop\Backtest\quanthack_backtester\`  (commands below are PowerShell).

---

## ☐ TODAY — Jun 17 (setup, ~2 hrs)
1. ☐ **Set up the Windows host for MT5** (do first — it has lead time). MT5's Python API only runs on
   Windows. Use your PC (left on 24/7) or a cheap Windows VPS. Install: MT5 terminal, Python 3.10+, then
   `pip install MetaTrader5`.
2. ☐ **Smoke-test the code:**
   ```powershell
   cd $HOME\Desktop\Backtest\quanthack_backtester
   python -m venv .venv; .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python run_recommended.py      # should print the tearsheet
   python verify.py               # should say ALL PASS
   ```
3. ☐ **Test your sponsor keys work** (catch dead keys now):
   ```powershell
   $env:ANTHROPIC_API_KEY="..."; pip install anthropic
   python live\ops_agent.py --status live\example_status.json --use-claude
   $env:NVIDIA_API_KEY="...";    python live\news_risk_gate.py --headlines live\example_status.json
   $env:LOGFIRE_TOKEN="...";     pip install logfire
   python live\risk_monitor.py --status live\example_status.json --logfire
   ```
4. ☐ **Push to GitHub** (needed for Northflank + the tech submission):
   `git init; git add .; git commit -m "quanthack system"; git remote add origin <repo>; git push -u origin main`
5. ☐ **Capture from the platform (browse mode) and send to me:** the tradable symbol list, each
   instrument's lot size + leverage, and a screenshot of the order ticket. → I lock the MT5 `SYMBOL_MAP`.
6. ☐ **Download the updated historical data** if it's been released; tell me → I re-validate on it.

## ☐ Jun 18 (API opens, evening) — reg deadline 22:00
7. ☐ Confirm your 2nd registration is done.
8. ☐ Get your **MT5 credentials** (login / password / server) + the **API docs**. Send the feed format +
   symbol specs to me → I finalize `feed_adapter.py`, `SYMBOL_MAP`, and lot conversion.
9. ☐ (Optional) Create the **Northflank** project for the AI co-pilot/Logfire: connect the repo, add env
   vars (`ANTHROPIC_API_KEY`, `NVIDIA_API_KEY`, `LOGFIRE_TOKEN`, gateway URL/key), **leave cron paused**.

## ☐ Jun 19 08:00 — pick trading method
10. ☐ Select **MT5 + custom**.
11. ☐ Build the live panel + run the rehearsal (the key pre-launch check):
    ```powershell
    python live\feed_adapter.py --source <feed_dir> --out data\panel_live.parquet
    python live\rehearse.py
    ```

## ☐ Jun 20 — dress rehearsal (dry-run, no real orders)
12. ☐ On the Windows host, run the full loop in DRY-RUN and fix any wiring:
    ```powershell
    python live\live_runner.py --panel data\panel_live.parquet --strategy mv --gross 3 --dd-guard --emit data\book.json
    python live\mt5_bridge.py --book data\book.json          # dry-run, sends nothing
    python live\risk_monitor.py --status data\status.json
    ```

## ☐ Jun 21 22:00 — LAUNCH
13. ☐ Reset the drawdown peak to your starting equity:
    `python -c "import sys;sys.path.insert(0,'live');import derisk;derisk.reset_peak('data/peak.json',1000000)"`
14. ☐ Start the loop (hourly), guards ON, **gross 2-3**:
    ```powershell
    python live\live_runner.py --panel data\panel_live.parquet --strategy mv --gross 3 --dd-guard --peak-state data\peak.json --emit data\book.json
    python live\mt5_bridge.py --book data\book.json --live --i-confirm-paper
    ```
15. ☐ Run `risk_monitor.py` every ~5 min; run `ops_agent.py` for a briefing each round.

## ☐ Each round cut — Jun 22 / 23 / 24 at 22:00
16. ☐ At the cutover, **reset the drawdown peak** to current equity (discipline + drawdown reset per round).
17. ☐ During the 22:00-23:00 audit: confirm no red-line flags; check the leaderboard for qualification.
18. ☐ Keep cumulative **trades ≥ 30** (Sharpe prize), discipline **100**, gross **modest**.

## ☐ Jun 24 22:00 — Top 100 advance to Finals
19. ☐ Finals leaderboard goes blind — rely on your own monitor + this plan; don't chase others.

## ☐ Jun 24 (after Round 3) — Tech-prize submission
20. ☐ Submit: GitHub link + `submission_onepager.html` / `SUBMISSION.md` + a `demo.sh` recording + a Logfire
    trace screenshot. **Lead with the overfitting analysis** (`overfit.py`) — that's the differentiator.

## ☐ Jun 26 22:00 — Finals close · Jun 27 — results & awards

---

## RED LINES — instant disqualification (never do)
Forced liquidation (wipeout) → eliminated · exploiting quote/latency/matching bugs · API abuse (>500 req/s)
· multiple accounts · collusion. The dd-guard + risk engine are built to keep you far from all of these.

## Ping me (Claude) when:
- You have the symbol specs / feed format (Jun 17-18) → I lock the mapping.
- Anything errors in the smoke test / rehearsal / dry-run → paste it, I debug.
- The updated data is released → I re-validate.
- Mid-competition → paste your status/leaderboard and I'll give you a read + adjust gross.
