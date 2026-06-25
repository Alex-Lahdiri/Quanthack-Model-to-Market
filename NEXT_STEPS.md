# Next steps (you've done the signups)

Today is Jun 16. The live feed + MT5 open Jun 19 (method selection) / Jun 21 (launch),
so split the work into "now" and "Jun 19+".

## A. NOW (Jun 16-18) — get it running locally + repo + Northflank shell

### 1. Get the code
The project is in `Desktop\Backtest\quanthack_backtester\` on your machine (also in the zip).

### 2. Python env + smoke test (PowerShell)
```powershell
cd $HOME\Desktop\Backtest\quanthack_backtester
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_recommended.py            # should print the tearsheet (Sharpe ~1.9 at 0.7bp)
```

### 3. Verify your new credentials work
```powershell
# Anthropic (ops agent): paste your key into THIS shell, never into a file you commit
$env:ANTHROPIC_API_KEY="sk-ant-..."
pip install anthropic
python live\ops_agent.py --status live\example_status.json --use-claude
#   -> a Claude-written briefing = key works. (Without the flag it prints the deterministic one.)

# Logfire (observability):
$env:LOGFIRE_TOKEN="..."
pip install logfire
python live\risk_monitor.py --status live\example_status.json --logfire
#   -> the run should appear in your Logfire project.
```

### 4. Push to GitHub (needed for Northflank + the tech submission)
```powershell
git init; git add .; git commit -m "Quanthack system"
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/quanthack.git
git branch -M main; git push -u origin main
```
(`.gitignore` already excludes the big parquets / venv. No API keys are in the repo — keep it that way.)

### 5. Stand up the Northflank shell (don't schedule live yet)
- New project **quanthack**, region **London (europe-west)**.
- Connect your GitHub repo; build from `live/Dockerfile`.
- Add env vars `ANTHROPIC_API_KEY`, `LOGFIRE_TOKEN`; add a persistent `/data` volume.
- Create the two cron jobs from `live/northflank.json` but **leave them paused** — there's no live feed yet.

## B. Jun 19 (method selection opens) — wire the live feed

### 6. Pick the trading method: MT5 + custom (your plan).
### 7. Find how the platform exposes the live quote feed + your positions/equity.
   **Send me the feed's format (a sample file or the column names)** and I'll finalize the
   `feed_adapter.py` / `mt5_bridge.py SYMBOL_MAP` mappings in minutes.
### 8. The critical check:
```powershell
python live\feed_adapter.py --source <feed_dir> --out data\panel_live.parquet
python live\rehearse.py      # confirm the live path is sane on real data
```

## C. Jun 21 launch
- Un-pause the Northflank cron jobs.
- MT5 bridge: dry-run first, then `--live --i-confirm-paper` on the PAPER account.
- **Start at gross 2-3** (the backtest is overfit). Watch `ops_agent` / `risk_monitor`.

## D. Jun 24 (after Round 3)
- Submit the GitHub repo + a `demo.sh` recording + a Logfire trace.
- Lead with the overfitting analysis (`overfit.py`, `results/research/overfit_dsr.png`).
