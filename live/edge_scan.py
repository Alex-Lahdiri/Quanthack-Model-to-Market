"""
edge_scan.py -- ADVANCED live-edge scanner.

Run at a round break (or any time) to decide three things from the CURRENT market:
  1. Do we genuinely have an edge?      -> IC surface + t-stats + persistence
  2. Should we trade faster or slower?  -> which forward-horizon the edge lives at + cadence backtest
  3. How hard should we press (gross)?  -> cadence x gross backtest, net of real venue costs

Refresh the feed first, then run this:
  python live/mt5_feed.py --out panel_live.parquet --lookback-days 5
  python live/edge_scan.py --days 5

Honest note: this is a SHORT window. Trust the DIRECTION and the t-stat, not the exact decimals.
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

LIVE10 = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "EURGBP", "EURCHF", "XAUUSD", "XAGUSD"]
RC = {"EURUSD": 0.08, "GBPUSD": 0.08, "USDCAD": 0.08, "AUDUSD": 0.08, "USDJPY": 0.16, "USDCHF": 0.19,
      "EURGBP": 0.15, "EURCHF": 0.15, "XAUUSD": 0.80, "XAGUSD": 1.20}


def ic_series(p, lb, fwd):
    """Per-bar cross-sectional IC: demeaned lb-momentum vs next fwd-return."""
    mom = p.pct_change(lb)
    momd = mom.sub(mom.mean(axis=1), axis=0)
    f = p.pct_change(fwd).shift(-fwd)
    return momd.corrwith(f, axis=1)


def tstat(s, step):
    """t-stat of mean IC, thinned by `step` bars to approximate non-overlapping samples."""
    s = s.dropna()
    if len(s) < 10:
        return float("nan"), 0
    sub = s.iloc[::max(1, step)]
    n = len(sub)
    if n < 5 or sub.std() == 0:
        return float("nan"), n
    return float(sub.mean() / (sub.std() / np.sqrt(n))), n


def main():
    ap = argparse.ArgumentParser(description="Advanced live-edge scanner")
    ap.add_argument("--panel", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel_live.parquet"))
    ap.add_argument("--days", type=float, default=5.0)
    args = ap.parse_args()

    p = pd.read_parquet(args.panel).set_index("ts").sort_index()
    p = p[[c for c in LIVE10 if c in p.columns]].astype(float)
    p = p[p.index >= p.index.max() - pd.Timedelta(days=args.days)]
    print(f"window: {p.shape[0]} bars x {p.shape[1]} cols   ({p.index[0]} -> {p.index[-1]})")
    print(f"last bar: {p.index[-1]}  <- if this is not within ~an hour of now, refresh the feed and re-run")

    # ---------- 1) IC SURFACE ----------
    lbs = [120, 240, 480, 720, 1440]   # 2h, 4h, 8h, 12h, 24h lookback
    fwds = [15, 30, 60, 120, 240]      # 15m, 30m, 1h, 2h, 4h forward
    surf = {}
    print("\n=== 1) IC SURFACE (cross-sectional momentum) ===")
    print("   rows = lookback, cols = forward horizon.   >+0.01 tradeable | ~0 noise | <0 reverting")
    print("   lookback |   15m     30m      1h      2h      4h")
    fwd_ic = {f: [] for f in fwds}
    for lb in lbs:
        cells = []
        for fwd in fwds:
            s = ic_series(p, lb, fwd)
            surf[(lb, fwd)] = s
            ic = float(s.dropna().mean()) if s.dropna().size else float("nan")
            fwd_ic[fwd].append(ic)
            cells.append(f"{ic:+.3f}".rjust(7))
        print(f"   {str(lb//60)+'h':>6}   | " + " ".join(cells))

    # ---------- 2) SIGNIFICANCE ----------
    print("\n=== 2) SIGNIFICANCE (thinned to ~non-overlapping; |t|>=2 real, 1-2 weak, <1 noise) ===")
    flat = {(lb, fwd): float(surf[(lb, fwd)].dropna().mean()) for lb in lbs for fwd in fwds if surf[(lb, fwd)].dropna().size > 20}
    best = max(flat, key=lambda k: abs(flat[k])) if flat else (480, 60)
    for (lb, fwd, label) in [(480, 60, "headline 8h->1h"), (best[0], best[1], f"strongest {best[0]//60}h->{best[1]}m")]:
        t, n = tstat(surf[(lb, fwd)], fwd)
        ic = float(surf[(lb, fwd)].dropna().mean())
        tag = "REAL-ish" if abs(t) >= 2 else ("weak" if abs(t) >= 1 else "noise")
        print(f"   {label:<20} IC {ic:+.4f}   t={t:+.2f} (n~{n})  -> {tag}")

    # ---------- 3) PERSISTENCE ----------
    s = surf[(480, 60)].dropna()
    if len(s) > 40:
        h = len(s) // 2
        ic1, ic2 = float(s.iloc[:h].mean()), float(s.iloc[h:].mean())
        hold = "HOLDING" if (np.sign(ic1) == np.sign(ic2) and ic2 > 0) else "fading/flipping"
        print("\n=== 3) PERSISTENCE (headline 8h->1h, first vs second half of window) ===")
        print(f"   first-half IC {ic1:+.4f}    second-half IC {ic2:+.4f}   -> {hold}")

    # ---------- 4) PER-INSTRUMENT ----------
    print("\n=== 4) PER-INSTRUMENT (recent 8h momentum & hourly autocorr) ===")
    mom8 = p.pct_change(480).iloc[-1]
    hr = p.resample("60min").last().pct_change().dropna(how="all")
    for c in p.columns:
        ser = hr[c].dropna()
        ac = ser.autocorr(1) if ser.shape[0] > 5 else float("nan")
        print(f"   {c:<8} 8h-mom {mom8[c]*100:+6.2f}%    hourly-AC {ac:+.2f}")

    # ---------- 5) CADENCE x GROSS BACKTEST ----------
    def bt(mode, g, rb):
        st = DiversifiedVolTarget(mode=mode, mom_window=480, vol_window=480, smooth_halflife=48, target_gross=g)
        r = run_backtest(p, st, risk=RiskEngine(), rebalance_every=rb, cost_bps=RC)
        return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)

    print("\n=== 5) CADENCE x GROSS (recent window, net of real venue costs) ===")
    for rb, lab in [(60, "hourly"), (120, "every2h"), (240, "every4h")]:
        parts = []
        for g in [2.0, 2.5, 3.0]:
            m = bt("momentum", g, rb)
            parts.append(f"g{g}: {m['total_return']*100:+5.2f}% Sh{m['sharpe']:+.3f} dd{m['max_drawdown']*100:+5.2f}%")
        print(f"   {lab:<8} " + "  |  ".join(parts))
    mrev = bt("reversion", 2.0, 60)
    print(f"   reversion g2 hourly (sanity) -> {mrev['total_return']*100:+.2f}%  Sh{mrev['sharpe']:+.3f}")

    # ---------- 6) VERDICT ----------
    ic_head = float(surf[(480, 60)].dropna().mean())
    best_fwd = max(fwd_ic, key=lambda f: np.nanmean(fwd_ic[f]))
    print("\n=== VERDICT ===")
    if ic_head > 0.01:
        print(f"   TRENDING (headline IC {ic_head:+.3f}). Momentum is working -> pressing (gross 2.5-3) is justified.")
    elif ic_head < -0.005:
        print(f"   REVERTING (headline IC {ic_head:+.3f}). Cut gross + slow cadence; do NOT press.")
    else:
        print(f"   CHOPPY (headline IC {ic_head:+.3f}). Keep gross modest (1.5-2), slow cadence; press only if it firms up.")
    print(f"   edge is strongest at the ~{best_fwd}m forward horizon -> trade no faster than that.")
    print("   Pick the best cell in section 5 (highest Sharpe at acceptable drawdown) for cadence + gross.")
    print("   [short window: trust direction + t-stat, not exact decimals]")


if __name__ == "__main__":
    main()
