"""
strat_compare.py -- consistency-first strategy comparison (dynamic, not rigid).

Runs each candidate ONCE on the full window (fully warmed up), then slices the equity
curve into 3 equal sub-periods and reports return / 15-min Sharpe (competition-style) /
maxDD for each. Goal: find what works CONSISTENTLY -- especially in the RECENT slice --
not what merely fits the whole window. Sharpe is gross-invariant; gross only scales
return% and maxDD, so we compare MODES at one gross.

  python live/mt5_feed.py --out panel_live.parquet --lookback-days 5
  python live/strat_compare.py --days 5 --gross 1.5
"""
from __future__ import annotations
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget
from strategies.cov_aware import CovAwareMomentum

LIVE10 = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","EURGBP","EURCHF","XAUUSD","XAGUSD"]
RC = {"EURUSD":0.08,"GBPUSD":0.08,"USDCAD":0.08,"AUDUSD":0.08,"USDJPY":0.16,"USDCHF":0.19,
      "EURGBP":0.15,"EURCHF":0.15,"XAUUSD":0.80,"XAGUSD":1.20}

def seg_metrics(eq):
    eq = eq.dropna()
    if len(eq) < 5:
        return float('nan'), float('nan'), float('nan')
    ret = float(eq.iloc[-1]/eq.iloc[0] - 1.0)
    e15 = eq.resample("15min").last().dropna()
    r15 = e15.pct_change().dropna()
    sh = float(r15.mean()/r15.std()) if (len(r15) > 1 and r15.std() > 0) else float('nan')
    dd = float((eq/eq.cummax() - 1.0).min())
    return ret, sh, dd

def build(mode, g):
    if mode in ("mv","hrp"):
        return CovAwareMomentum(mom_window=480, ema=48, cov_window=480, cov_step=60, target_gross=g, mode=mode)
    return DiversifiedVolTarget(mode=mode, mom_window=480, vol_window=480, smooth_halflife=48, target_gross=g)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel_live.parquet"))
    ap.add_argument("--days", type=float, default=5.0)
    ap.add_argument("--gross", type=float, default=1.5)
    args = ap.parse_args()

    p = pd.read_parquet(args.panel).set_index("ts").sort_index()
    p = p[[c for c in LIVE10 if c in p.columns]].astype(float)
    p = p[p.index >= p.index.max() - pd.Timedelta(days=args.days)]
    print(f"window: {p.shape[0]} bars x {p.shape[1]}  ({p.index[0]} -> {p.index[-1]})")
    print(f"comparing MODES at gross {args.gross}, every-4h cadence, net of real costs")
    print("(Sharpe = 15-min non-annualized, like the competition; gross only scales ret%/maxDD)")

    t0, t1 = p.index[0], p.index[-1]
    span = (t1 - t0)
    edges = [t0 + span * k / 3 for k in range(4)]

    print("\n  mode       segment    ret%     Sh(15m)   maxDD%")
    print("  " + "-"*48)
    summary = {}
    for mode in ["mv","momentum","reversion","hrp"]:
        try:
            st = build(mode, args.gross)
            r = run_backtest(p, st, risk=RiskEngine(), rebalance_every=240, cost_bps=RC)
            eq = r.equity
        except Exception as e:
            print(f"  {mode:<10} ERROR: {type(e).__name__}: {e}")
            continue
        fr, fs, fd = seg_metrics(eq)
        print(f"  {mode:<10} FULL     {fr*100:+6.2f}   {fs:+.3f}   {fd*100:+6.2f}")
        seg_rets = []
        for k, lab in enumerate(["early","mid","recent"]):
            seg = eq[(eq.index >= edges[k]) & (eq.index <= edges[k+1])]
            sr, ss, sd = seg_metrics(seg)
            seg_rets.append(sr)
            print(f"  {'':<10}  {lab:<7} {sr*100:+6.2f}   {ss:+.3f}   {sd*100:+6.2f}")
        summary[mode] = (fr, fs, fd, seg_rets)
        print()

    print("=== READ ===")
    print("Best = positive & smooth in the RECENT segment AND not wildly negative in any.")
    print("Flat baseline = 0.00% ret, 0 Sharpe, 0% maxDD -- the bar to beat in a no-edge chop.")
    if summary:
        rec_best = max(summary, key=lambda mm: (summary[mm][3][2] if (summary[mm][3] and summary[mm][3][2]==summary[mm][3][2]) else -9))
        sh_best = max(summary, key=lambda mm: (summary[mm][1] if summary[mm][1]==summary[mm][1] else -9))
        print(f"highest RECENT-segment return: {rec_best}   |   highest full-window Sharpe: {sh_best}")

if __name__ == "__main__":
    main()
