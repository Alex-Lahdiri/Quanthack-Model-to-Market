"""micro_scan.py -- UNBIASED microstructure check. Tests SHORT-TERM MEAN REVERSION (negative
autocorrelation) vs our momentum bias, with sub-period STABILITY checks (anti-overfit).
No-commission venue + tight spreads make fast reversion viable, so we test it honestly."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

FX10 = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","EURGBP","EURCHF","XAUUSD","XAGUSD"]
RC = {"EURUSD":0.08,"GBPUSD":0.08,"USDCAD":0.08,"AUDUSD":0.08,"USDJPY":0.16,"USDCHF":0.19,
      "EURGBP":0.15,"EURCHF":0.15,"XAUUSD":0.80,"XAGUSD":1.20}

def seg(eq):
    eq=eq.dropna()
    if len(eq)<5: return float('nan'),float('nan'),float('nan')
    ret=float(eq.iloc[-1]/eq.iloc[0]-1)
    r15=eq.resample("15min").last().dropna().pct_change().dropna()
    sh=float(r15.mean()/r15.std()) if (len(r15)>1 and r15.std()>0) else float('nan')
    dd=float((eq/eq.cummax()-1).min())
    return ret,sh,dd

def autocorr_at(p,h):
    r=p.resample(f"{h}min").last().pct_change()
    acs=[r[c].dropna().autocorr(1) for c in p.columns if r[c].dropna().shape[0]>10]
    return float(np.nanmean(acs))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--panel", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"panel_all.parquet"))
    ap.add_argument("--days",type=float,default=5.0); args=ap.parse_args()
    p=pd.read_parquet(args.panel).set_index("ts").sort_index()
    p=p[[c for c in FX10 if c in p.columns]].astype(float)
    p=p[p.index>=p.index.max()-pd.Timedelta(days=args.days)]
    print(f"window {p.shape[0]} bars ({p.index[0]} -> {p.index[-1]})")
    t0,t1=p.index[0],p.index[-1]; edges=[t0+(t1-t0)*k/3 for k in range(4)]
    def sub(k): return p[(p.index>=edges[k])&(p.index<=edges[k+1])]

    print("\n=== 1) AUTOCORRELATION (lag-1) by horizon  ( <0 mean-reverting | >0 trending ) ===")
    print("   horizon |   full    early     mid    recent")
    for h in [1,5,15,30,60]:
        print(f"   {h:>3}min  | {autocorr_at(p,h):+.3f}   {autocorr_at(sub(0),h):+.3f}   {autocorr_at(sub(1),h):+.3f}   {autocorr_at(sub(2),h):+.3f}")

    def bt(mode,lb,cad):
        st=DiversifiedVolTarget(mode=mode,mom_window=lb,vol_window=60,smooth_halflife=max(2,lb//3),target_gross=2.0)
        r=run_backtest(p,st,risk=RiskEngine(),rebalance_every=cad,cost_bps=RC)
        return seg(r.equity), r.trade_count

    print("\n=== 2) BACKTEST (gross 2, net of spread, NO commission) ===")
    print("   signal      look cadence   ret%    Sh(15m)  maxDD%   trades")
    rows=[]
    for lb in [15,30,60]:
        for cad in [5,15,30]:
            (rr,ss,dd),tc=bt("reversion",lb,cad)
            print(f"   reversion   {lb:>3}m {cad:>3}m     {rr*100:+6.2f}  {ss:+.3f}  {dd*100:+6.2f}   {tc}")
            rows.append(("reversion",lb,cad,rr,ss,dd))
    for lb in [30,60]:
        (rr,ss,dd),tc=bt("momentum",lb,15)
        print(f"   momentum    {lb:>3}m  15m     {rr*100:+6.2f}  {ss:+.3f}  {dd*100:+6.2f}   {tc}")

    best=max(rows,key=lambda r:(r[4] if r[4]==r[4] else -9))
    print(f"\n=== 3) CONSISTENCY of best reversion ({best[1]}m look / {best[2]}m cadence) ===")
    st=DiversifiedVolTarget(mode="reversion",mom_window=best[1],vol_window=60,smooth_halflife=max(2,best[1]//3),target_gross=2.0)
    eq=run_backtest(p,st,risk=RiskEngine(),rebalance_every=best[2],cost_bps=RC).equity
    for k,lab in enumerate(["early","mid","recent"]):
        rr,ss,dd=seg(eq[(eq.index>=edges[k])&(eq.index<=edges[k+1])])
        print(f"   {lab:<7} ret {rr*100:+6.2f}%  Sh {ss:+.3f}  maxDD {dd*100:+6.2f}%")
    print("\n=== READ ===")
    print("Negative autocorr stable across horizons AND sub-periods => structural mean reversion (not overfit).")
    print("If reversion is positive in ALL sub-periods, it generalizes and is worth switching to.")

if __name__=="__main__": main()
