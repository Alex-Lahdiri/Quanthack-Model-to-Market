# Live deployment (advisory) — Quanthack

**Safety first.** `live_runner.py` computes a target book; `risk_monitor.py` watches risk. Neither
sends orders. Execution is `mt5_bridge.py`, which is **dry-run by default** and refuses to send
without `--live --i-confirm-paper`, against the **paper/contest** account (trade_mode 2). It aborts
if the account looks real (trade_mode 0). Keep yourself in the loop. Never wire this to real money.

## Verified venue facts (mt5_probe.py, contest server)
- Account **10009**, $1,000,000, leverage 1:30, **trade_mode 2 (contest)**.
- **10 tradeable + validated names:** EURUSD GBPUSD USDJPY USDCHF USDCAD AUDUSD EURGBP EURCHF XAUUSD XAGUSD.
- Broker does **not** offer NZDUSD / EURJPY. Crypto (BTC/ETH/SOL/XRP/BAR) is live but **unvalidated** → excluded.
- Contract sizes: FX = 100,000; **XAUUSD = 100 oz**; **XAGUSD = 5,000 oz**. Min lot 0.01, step 0.01.

## Architecture (MT5-native — one terminal, three scripts)
```
MT5 terminal (open + logged in to 10009)
   -> mt5_feed.py     (every 1 min)   panel_live.parquet   (10 names, ~5 days of 1-min closes)
   -> live_runner.py  (every hour)    book.json            (target USD notionals per name)
   -> mt5_bridge.py   (after runner)  notional -> LOTS -> paper orders (deltas vs current)
   -> risk_monitor.py (every 5 min)   reads status.json -> warnings / Logfire
```
All scripts attach to the already-logged-in terminal: leave creds unset and just call them.

## 1. Build the rolling panel from MT5
```
python live/mt5_feed.py --out panel_live.parquet --lookback-days 5
```
Pulls M1 closes via `copy_rates` for the 10 names. Run on a 1-min schedule so the 480-bar (8h)
lookback stays warm.

## 2. Generate the target book (hourly)
```
python live/live_runner.py --panel panel_live.parquet --strategy mv --gross 2 \
       --equity <current_equity> --emit book.json --dd-guard --peak-state peak.json --logfire
```
`--strategy mv` (shrinkage covariance) or `iv` (inverse-vol). Per the overfit analysis,
**start at gross 2** and only size toward 3–4 if live tracks the backtest. `--dd-guard` applies the
drawdown de-risk ladder; `--risk-gate --headlines headlines.txt` adds the news multiplier.

## 3. Execute on the paper account (dry-run first!)
```
# DRY RUN — prints planned orders in lots, sends nothing:
python live/mt5_bridge.py --book book.json
# When the plan looks right, actually send on the contest account:
python live/mt5_bridge.py --book book.json --live --i-confirm-paper
```
The bridge converts each target's **USD notional → lots** using the real contract size, live price,
and base/quote currency (USD-quote, USD-base, and EUR-cross handled separately), rounds to the 0.01
step, clamps to broker min/max, skips dust, and picks a supported fill mode. It only trades the
**delta** vs your current positions, so re-running it just nudges you toward target.

## 4. Monitor (every 5 min)
Write `status.json` = `{equity, positions:{SYM:notional}}` from MT5, then:
```
python live/risk_monitor.py --status status.json --logfire
```
Flags proximity to the margin (90%), leverage (28x), and concentration (90%) penalty tiers and the
liquidation red line.

## 5. Deploy on Northflank (optional — only if you want it running unattended)
- Region **London** (latency). Cron jobs (see `northflank.json`): feed `* * * * *`, runner `0 * * * *`,
  monitor `*/5 * * * *`. Persistent volume for the panel/book/status.
- **Note:** MetaTrader5's Python package is Windows-only, so the *bridge/feed* run on your Windows box.
  Northflank can host the runner/monitor (no MT5 needed) if you ship it the panel; for the contest it's
  simplest to run all three on the Windows machine with Task Scheduler.

## 6. Logfire (optional, sponsor)
`pip install logfire`, set `LOGFIRE_TOKEN`, pass `--logfire`. Traces every run + risk alert — useful
for the tech-prize demo.

## Go-live sequence (Jun 21, 22:00)
1. MT5 open + logged into 10009, Market Watch showing the 10 names, prices ticking.
2. `mt5_feed.py` → confirm `panel_live.parquet` has ~5 days × 10 cols.
3. `live_runner.py --gross 2` → eyeball the book (gross ~2x, no single name > ~30%).
4. `mt5_bridge.py --book book.json` (DRY RUN) → confirm lots look sane.
5. `mt5_bridge.py --book book.json --live --i-confirm-paper` → you're live.
6. Loop feed+runner+bridge hourly; monitor every 5 min; let `--dd-guard` cut risk on drawdowns.
