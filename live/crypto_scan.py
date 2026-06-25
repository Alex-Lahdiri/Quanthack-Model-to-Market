"""
crypto_scan.py -- UNBIASED read including crypto, for both objectives:
  PROFIT-MAX lens (raw return only) vs COMPOSITE lens (70/15/10/5).
Reports per-instrument moves/vol, momentum IC (FX vs crypto vs all), and
backtests FX-only / FX+crypto / crypto-only at higher gross, net of real costs.

  python live/mt5_feed.py --include-crypto --out panel_all.parquet --lookback-days 5
  python live/crypto_scan.py --days 5
"""
from __future__ import annotations
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

FX10 = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","EURGBP","EURCHF","XAUUSD","XAGUSD"]
CRYPTO = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","BARUSD"]
RC = {"EURUSD":0.08,"GBPUSD":0.08,"USDCAD":0.08,"AUDUSD":0.08,"USDJPY":0.16,"USDCHF":0.19,
      "EURGBP":0.15,"EURCHF":0.15,"XAUUSD":0.80,"XAGUSD":1.20,
      "BTCUSD":3.0,"ETHUSD":3.0,"SOLUSD":5.0,"XRPUSD":5.0,"BARUSD":5.0}

def seg(eq):
    eq = eq.dropna()
    if len(eq) < 5: return float('nan'),float('nan'),float('nan')
    ret = float(eq.iloc[-1]/eq.iloc[0]-1.0)
    e15 = eq.resample("15min").last().dropna(); r15 = e15.pct_change().dropna()
    sh = float(r15.mean()/r15.std()) if (len(r15)>1 and r15.std()>0) else float('nan')
    dd = float((eq/eq.cummax()-1.0).min())
    return ret, sh, dd

def ic(p, cols):
    if len(cols) < 2: return float('nan')
    sub = p[cols]; mom = sub.pct_change(480); momd = mom.sub(mom.mean(axis=1),axis=0)
    fwd = sub.pct_change(60).shift(-60)
    return float(momd.corrwith(fwd,axis=1).mean())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel_all.parquet"))
    ap.add_argument("--days", type=float, default=5.0)
    args = ap.parse_args()
    p = pd.read_parquet(args.panel).set_index("ts").sort_index().astype(float)
    p = p[p.index >= p.index.max() - pd.Timedelta(days=args.days)]
    fx = [c for c in FX10 if c in p.columns]; cr = [c for c in CRYPTO if c in p.columns]
    print(f"window {p.shape[0]} bars  ({p.index[0]} -> {p.index[-1]})")
    print(f"FX/metals ({len(fx)}): {fx}")
    print(f"crypto ({len(cr)}): {cr}")

    print("\n=== PER-INSTRUMENT (this window): total move %, 1-min vol bps ===")
    for c in fx + cr:
        mv = (p[c].iloc[-1]/p[c].iloc[0]-1.0)*100; vol = p[c].pct_change().std()*1e4
        tag = "  <crypto>" if c in cr else ""
        print(f"  {c:<8} move {mv:+8.2f}%   vol {vol:7.1f} bps{tag}")
    print(f"\nmomentum IC (8h->1h):  FX {ic(p,fx):+.4f}   crypto {ic(p,cr):+.4f}   all {ic(p,fx+cr):+.4f}")

    def bt(cols, g):
        if len(cols) < 2: return (float('nan'),)*3
        st = DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480, smooth_halflife=48, target_gross=g)
        r = run_backtest(p[cols], st, risk=RiskEngine(), rebalance_every=240, cost_bps={k:RC[k] for k in cols})
        return seg(r.equity)
    print("\n=== UNIVERSE x GROSS (iv momentum, every-4h, net of real costs) ===")
    print("  universe      gross   ret%     Sh(15m)   maxDD%")
    for label, cols in [("FX-only", fx), ("FX+crypto", fx+cr), ("crypto-only", cr)]:
        for g in [2.0, 3.0]:
            ret,sh,dd = bt(cols, g)
            print(f"  {label:<12} {g:>4}   {ret*100:+6.2f}   {sh:+.3f}   {dd*100:+6.2f}")
    print("\n=== READ ===")
    print("PROFIT-MAX (if only return counts): pick highest ret% -- but maxDD is the risk (account wipeout = instant DQ).")
    print("COMPOSITE (official 70/15/10/5): ret AND smoothness matter; high-vol/crypto usually hurts Sh+DD ranks.")

if __name__ == "__main__":
    main()
