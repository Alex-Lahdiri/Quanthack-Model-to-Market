# Demo - see it work in ~5 minutes

Everything is **dry-run / advisory by default** (paper/contest account only). You can run the
whole pipeline without sending a single order.

## Prereqs
- Python 3.12+, then `pip install -r requirements.txt`
- For live data: MetaTrader 5 open + logged into the contest account.
- Optional (lights up the AI): `setx NVIDIA_API_KEY ...`, `setx ANTHROPIC_API_KEY ...`, `setx LOGFIRE_TOKEN ...`

## 1. Prove the safety claims - no data or keys needed
```
python tests/test_safety.py
```
→ **6/6 pass**: the governor clamps a reckless AI proposal (gross 9 → 3.0), forces defensive in a
no-edge regime, the drawdown + profit-lock tiers fire, and the risk engine enforces the per-name cap.

## 2. Pull a live panel + read the regime
```
python live/mt5_feed.py --out panel_live.parquet --lookback-days 5
python live/edge_scan.py --days 5
```
→ a momentum **IC surface with t-stats**, an autocorrelation read, a cadence×gross backtest net of
real costs, and a plain verdict.

## 3. Watch the autonomous AI desk decide - SHADOW, safe
```
python live/autopilot.py --logfire
```
→ **Nemotron** classifies the live regime, **Claude** proposes strategy/gross/cadence (Pydantic-validated),
the deterministic **Governor** clamps it to safe bounds, and the whole chain is **traced in Logfire**.
Shadow mode only writes `autopilot_decision.json` - it changes nothing.

## 4. Run a full cycle - dry-run
```
$env:QH_DRY=1; powershell -ExecutionPolicy Bypass -File live/run_cycle.ps1
```
→ feed → target book → AI desk → preflight → bridge. Dry-run prints intended orders and sends nothing.

## 5. Observability
- **Logfire:** every cycle and agent call is a traced span (feed → signal → risk → AI → execute).
  > _Add a Logfire trace screenshot here (e.g. `docs/logfire.png`) - strong visual evidence of the tracing._
- **Dashboard:** open `dashboard.html` (or the Northflank service) for the live book + risk view.

## Where to look in the code
- `live/autopilot.py` - the governed autonomous AI desk (the headline).
- `risk_engine.py` + `tests/test_safety.py` - the caps, and the tests that prove them.
- `live/edge_scan.py` / `live/micro_scan.py` - the live research that overturned my own momentum thesis.
- `RESEARCH_LOG.md` - the full, honest research journey (including every negative result).
