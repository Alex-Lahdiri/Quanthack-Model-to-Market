"""
Stream the real per-instrument-day Parquet files out of the competition archive
(zip) or a directory, resample to bars, cache a price panel, and backtest.

The archive is one Parquet per SYMBOL_YYYY_MM_DD with columns:
  time (microsecond string), sym, bid, ask, + L2 depth ladders (ignored here).
We extract ONE file at a time and delete it after resampling, so peak disk use
stays at a single ~40MB file regardless of the 20GB archive size.

Examples
--------
python ingest_real.py --zip /path/archive.zip --list
python ingest_real.py --zip /path/archive.zip --instruments EURUSD,GBPUSD,XAUUSD \
                      --start 2026-06-04 --end 2026-06-10 --freq 1m
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import zipfile
from collections import defaultdict

import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_loader as dl
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

PAT = re.compile(r"(?:^|/)([A-Za-z0-9]+)_(\d{4})_(\d{2})_(\d{2})\.parquet$")


def list_members(zip_path: str):
    z = zipfile.ZipFile(zip_path)
    out = []
    for n in z.namelist():
        m = PAT.search(n)
        if m:
            out.append((n, m.group(1), f"{m.group(2)}-{m.group(3)}-{m.group(4)}"))
    return z, out


def build_panel(zip_path, instruments, start, end, freq, workdir,
                max_files=None, verbose=True):
    z, members = list_members(zip_path)
    sel = [(n, s, d) for (n, s, d) in members
           if (not instruments or s in instruments)
           and (not start or d >= start) and (not end or d <= end)]
    sel.sort(key=lambda x: (x[1], x[2]))
    if max_files:
        sel = sel[:max_files]
    if not sel:
        raise SystemExit("No files matched the filters.")
    if verbose:
        syms = sorted({s for _, s, _ in sel})
        print(f"selected {len(sel)} files | {len(syms)} instruments | {sel[0][2]}..{sel[-1][2]}")
    os.makedirs(workdir, exist_ok=True)
    frames, t0 = [], time.time()
    for i, (n, sym, date) in enumerate(sel, 1):
        z.extract(n, workdir)
        path = os.path.join(workdir, n)
        frames.append(dl.to_bars(dl.load_quotes(path), freq))
        os.remove(path)
        if verbose and (i % 20 == 0 or i == len(sel)):
            print(f"  {i}/{len(sel)} resampled ({time.time()-t0:.1f}s)")
    panel = dl.build_price_panel(pl.concat(frames), "close")
    return panel


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Ingest the real competition archive")
    ap.add_argument("--zip", required=True)
    ap.add_argument("--instruments", default="", help="comma list; blank = all")
    ap.add_argument("--start", default="", help="YYYY-MM-DD inclusive")
    ap.add_argument("--end", default="", help="YYYY-MM-DD inclusive")
    ap.add_argument("--freq", default="1m")
    ap.add_argument("--rebalance", type=int, default=15)
    ap.add_argument("--target-gross", type=float, default=6.0)
    ap.add_argument("--max-files", type=int, default=0)
    ap.add_argument("--workdir", default="/tmp/_ingest")
    ap.add_argument("--cache", default=os.path.join(here, "results", "panel.parquet"))
    ap.add_argument("--out", default=os.path.join(here, "results"))
    ap.add_argument("--list", action="store_true", help="list instruments + dates and exit")
    args = ap.parse_args()

    if args.list:
        _, members = list_members(args.zip)
        d = defaultdict(list)
        for _, s, dt in members:
            d[s].append(dt)
        for s in sorted(d):
            print(f"{s:<10} {len(d[s])} days  {min(d[s])}..{max(d[s])}")
        return

    instruments = [x.strip() for x in args.instruments.split(",") if x.strip()] or None
    panel = build_panel(args.zip, instruments, args.start or None, args.end or None,
                        args.freq, args.workdir, args.max_files or None)
    print(f"panel: {panel.shape[0]} bars x {panel.shape[1]} instruments "
          f"({panel.index[0]} -> {panel.index[-1]})")
    os.makedirs(os.path.dirname(args.cache), exist_ok=True)
    panel.reset_index().to_parquet(args.cache)
    print(f"cached panel -> {args.cache}  (re-run strategies off this instantly)")

    strat = DiversifiedVolTarget(target_gross=args.target_gross)
    res = run_backtest(panel, strat, risk=RiskEngine(), rebalance_every=args.rebalance)
    m = M.compute_metrics(res.equity, res.telemetry, res.trade_count, res.liquidated)
    M.tearsheet(m, M.simulate_final_score(m, M.make_synthetic_peers(300, seed=1)))
    os.makedirs(args.out, exist_ok=True)
    res.equity.to_csv(os.path.join(args.out, "real_equity_curve.csv"))
    json.dump({"metrics": m, "params": res.params},
              open(os.path.join(args.out, "real_metrics.json"), "w"), indent=2)
    print(f"saved real_equity_curve.csv + real_metrics.json to {args.out}")


if __name__ == "__main__":
    main()
