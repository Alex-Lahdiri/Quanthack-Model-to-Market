# Deployment checklist — go live for the Jun 21 launch

## 0. Sponsor signups (you do these; ~30 min)
- [ ] **Anthropic** API credits ($50) — for any Claude-powered ops agent.
- [ ] **Pydantic Logfire** — create project, copy `LOGFIRE_TOKEN`.
- [ ] **Northflank** — create account, claim $100 credit, new project "quanthack" (London region).
- [ ] Confirm the platform's **live per-instrument spreads** (should be ≥ as tight as the backtest data).

## 1. Rolling data panel
Stand up a small job that turns the live quote feed into `/data/panel_live.parquet` — a `ts` column +
one close column per instrument (12-name liquid universe), ~5 days of 1-min bars (warm lookback). Reuse
`data_loader` / `batch_ingest` logic.

## 2. Deploy on Northflank (see `live/northflank.json`, `live/Dockerfile`)
- [ ] Build the image from `live/Dockerfile`.
- [ ] Cron job **live-runner** `0 * * * *`: `python live/live_runner.py --panel /data/panel_live.parquet --strategy mv --gross 3 --equity <eq> --emit /data/book.json --logfire`
- [ ] Cron job **risk-monitor** `*/5 * * * *`: `python live/risk_monitor.py --status /data/status.json --logfire`
- [ ] Persistent `/data` volume; set `LOGFIRE_TOKEN` env var.

## 3. Wire MT5 execution (paper account, YOUR machine)
- [ ] `pip install MetaTrader5`; open the MT5 terminal logged into the **paper** Quanthack account.
- [ ] Edit `SYMBOL_MAP` in `live/mt5_bridge.py` to your broker's symbol names.
- [ ] Dry-run first: `python live/mt5_bridge.py --book /data/book.json`
- [ ] Go live (paper): `python live/mt5_bridge.py --book /data/book.json --live --i-confirm-paper`
- [ ] Write `/data/status.json` `{equity, positions}` from MT5 each cycle for the monitor.

## 4. Go-live discipline
- [ ] **Start at gross 2–3**, not 4–6 (the backtest is overfit; size up only if live tracks it).
- [ ] Keep one account; bridge is rate-limited (<500 req/s) — leave it that way.
- [ ] Watch Logfire for any risk-monitor warning; the risk engine already caps weights, but verify.
- [ ] After each round's 22:00–23:00 audit, confirm no red-line flags.

## 5. Technology prize
Push the repo to GitHub, attach `SUBMISSION.md`, and record a short demo of `./demo.sh` + a Logfire trace.
The overfitting analysis (`overfit.py`, Deflated Sharpe + PBO) is the standout — lead with it.

## Per-round runbook (do this each round)
- **At round inception (22:00 cutover):** reset the drawdown peak — `python -c "import sys;sys.path.insert(0,'live');import derisk;derisk.reset_peak('/data/peak.json', <equity>)"`. Risk Discipline + drawdown reset per round.
- **Run the loop with guards on:** `live_runner.py --strategy mv --gross 3 --dd-guard --peak-state /data/peak.json [--risk-gate --headlines news.txt]`.
- **Every 5 min:** `risk_monitor.py --status /data/status.json` (status should include `peak_equity`). Heed any WARN.
- **Watch:** never let margin/leverage/concentration warnings persist; the de-risk ladder auto-trims, but verify. Keep >=30 trades cumulatively for the Sharpe prize.
- **After the 22:00-23:00 audit:** confirm no red-line flags; check the public leaderboard for your qualification.
