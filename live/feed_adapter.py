"""
Build / refresh `panel_live.parquet` from the platform's live quote feed.

Format-agnostic: it reuses data_loader.detect_columns, so it adapts to whatever
columns the feed exposes (timestamp / symbol / bid / ask or price). Point --source
at the directory (or glob) the platform writes quote files to, run it on a short
schedule, and the live runner always has a fresh ~lookback-days 1-min panel.
"""
from __future__ import annotations
import argparse, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import polars as pl
import data_loader as dl

# Live universe = the 10 names the broker actually offers (verified via mt5_probe).
UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD",
        "EURGBP","EURCHF","XAUUSD","XAGUSD"]

def main():
    ap = argparse.ArgumentParser(description="Build panel_live.parquet from the live feed")
    ap.add_argument("--source", required=True, help="dir or glob of quote files (parquet/csv) from the feed")
    ap.add_argument("--out", default="/data/panel_live.parquet")
    ap.add_argument("--freq", default="1m")
    ap.add_argument("--lookback-days", type=float, default=5.0)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.source, "*")) if os.path.isdir(args.source) else glob.glob(args.source))
    if not files:
        sys.exit(f"no feed files at {args.source}")
    frames = []
    for f in files:
        try:
            frames.append(dl.to_bars(dl.load_quotes(f), args.freq))
        except Exception as e:
            print(f"skip {f}: {e}")
    if not frames:
        sys.exit("no parseable feed files")
    panel = dl.build_price_panel(pl.concat(frames), "close")
    panel = panel[[c for c in UNIV if c in panel.columns]]
    cutoff = panel.index.max() - pd.Timedelta(days=args.lookback_days)
    panel = panel[panel.index >= cutoff]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    panel.reset_index().to_parquet(args.out)
    print(f"wrote {args.out}: {panel.shape[0]} bars x {panel.shape[1]} instruments "
          f"({panel.index[0]} -> {panel.index[-1]})")

if __name__ == "__main__":
    import pandas as pd
    main()
