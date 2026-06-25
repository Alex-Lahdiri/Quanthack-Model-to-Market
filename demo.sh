#!/usr/bin/env bash
# Portable working demo — runs end-to-end on the shipped cached panel (no 20GB archive needed).
set -e
cd "$(dirname "$0")"
echo "### 1. Recommended scoring-tuned config (full-month cached panel)"
python run_recommended.py
echo; echo "### 2. Generate a live target book from the latest bars"
python live/live_runner.py --panel results/panel_full_month.parquet --strategy mv --gross 4 --emit /tmp/book.json
echo; echo "### 3. Risk monitor on that book"
python - <<PY
import json; b=json.load(open('/tmp/book.json'))
json.dump({'equity':b['equity'],'positions':{s:v['notional'] for s,v in b['targets'].items()}}, open('/tmp/status.json','w'))
PY
python live/risk_monitor.py --status /tmp/status.json
echo; echo "### (full research repro: overfit.py / compare_construction.py — need the 20GB archive re-ingested via batch_ingest.py)"
