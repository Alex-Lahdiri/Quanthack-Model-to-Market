"""
Regime report -- run anytime (especially at a round break) to see what the CURRENT market is
doing and which lever to pull. Reads the live panel your feed saves (panel_live.parquet),
measures whether momentum is working, and backtests the cadence/gross levers on the recent
window. Prints a plain verdict + recommendation. Paste the output to your co-pilot to decide.

  python live/regime_report.py                       # uses ../panel_live.parquet
  python live/regime_report.py --panel panel_live.parquet --days 5
"""
from __future__ import annotations
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

LIVE10 = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","EURGBP","EURCHF","XAUUSD","XAGUSD"]
RC = {"EURUSD":0.08,"GBPUSD":0.08,"USDCAD":0.08,"AUDUSD":0.08,"USDJPY":0.16,"USDCHF":0.19,
      "EURGBP":0.15,"EURCHF":0.15,"XAUUSD":0.80,"XAGUSD":1.20}


def main():
    ap = argparse.ArgumentParser(description="Live regime report")
    ap.add_argument("--panel", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel_live.parquet"))
    ap.add_argument("--days", type=float, default=5.0)
    args = ap.parse_args()

    p = pd.read_parquet(args.panel).set_index("ts").sort_index()
    p = p[[c for c in LIVE10 if c in p.columns]]
    p = p[p.index >= p.index.max() - pd.Timedelta(days=args.days)]
    print(f"window: {p.shape[0]} bars x {p.shape[1]}  ({p.index[0]} -> {p.index[-1]})")

    # momentum IC: 8h cross-sectional momentum vs next-1h return
    mom = p.pct_change(480); momd = mom.sub(mom.mean(axis=1), axis=0)
    fwd = p.pct_change(60).shift(-60)
    ic = float(momd.corrwith(fwd, axis=1).mean())
    # proper trend read: NON-overlapping hourly returns, mean lag-1 autocorr
    hr = p.resample("60min").last().pct_change().dropna(how="all")
    ac = float(np.nanmean([hr[c].dropna().autocorr(1) for c in hr.columns if hr[c].dropna().shape[0] > 5]))
    print("\n=== REGIME ===")
    print(f"  momentum IC (8h -> next 1h): {ic:+.4f}   (>+0.005 trending, ~0 choppy, <-0.005 reverting)")
    print(f"  hourly-return autocorr:      {ac:+.4f}   (>0 trending, <0 mean-reverting)")

    def bt(mode, g, rb):
        s = DiversifiedVolTarget(mode=mode, mom_window=480, vol_window=480, smooth_halflife=48, target_gross=g)
        r = run_backtest(p, s, risk=RiskEngine(), rebalance_every=rb, cost_bps=RC)
        return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)

    print("\n=== LEVERS (recent window) ===")
    rows = [("momentum g2  hourly", "momentum", 2.0, 60),
            ("momentum g2  every 2h", "momentum", 2.0, 120),
            ("momentum g2  every 4h", "momentum", 2.0, 240),
            ("momentum g1.5 every 2h", "momentum", 1.5, 120),
            ("reversion g2  hourly", "reversion", 2.0, 60)]
    best = None
    for tag, mode, g, rb in rows:
        m = bt(mode, g, rb)
        print(f"  {tag:<24} ret {m['total_return']*100:>6.2f}%  Sh {m['sharpe']:+.4f}  maxDD {m['max_drawdown']*100:>6.2f}%")
        if best is None or m['sharpe'] > best[1]:
            best = (tag, m['sharpe'])

    print("\n=== VERDICT ===")
    if ic > 0.005:
        print("  TRENDING -> momentum is working. Keep hourly cadence, gross 2. Speed is fine.")
    elif ic < -0.005:
        print("  REVERTING -> momentum is fighting the tape. Slow cadence hard (every 4h) and lower gross;")
        print("  a small reversion tilt *may* help but is overfit-risky on a short window.")
    else:
        print("  CHOPPY (IC ~ 0) -> momentum is noise. SLOW the cadence (every 2-4h) to cut whipsaw, keep")
        print("  gross modest. Don't expect gains -- bleed less and survive until trends return.")
    print(f"  best lever on this window: {best[0]} (Sharpe {best[1]:+.4f})  [short window -- trust direction, not exact value]")


if __name__ == "__main__":
    main()
