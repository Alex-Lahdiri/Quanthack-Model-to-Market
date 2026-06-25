import sys, glob, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import numpy as np, pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget
from strategies.cov_aware import CovAwareMomentum
from strategies.regime_ensemble import RegimeEnsembleMomentum
UNIV=["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD","EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel=pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]
parts=pd.concat([pd.read_parquet(p) for p in glob.glob("/tmp/ingest_state/parts/*.parquet")])
parts=parts[(parts.close>0)&parts.mean_spread.notna()]; parts["hs"]=(parts.mean_spread/parts.close)/2*1e4
rc=parts.groupby("symbol")["hs"].mean().to_dict()
def blocks(eq,K=6):
    e=eq.iloc[1440:]; idx=np.array_split(np.arange(len(e)),K)
    rets=[e.iloc[ii].iloc[-1]/e.iloc[ii].iloc[0]-1 for ii in idx]
    shs=[M.sharpe(M.resample_equity(e.iloc[ii])) for ii in idx]
    return sum(r>0 for r in rets), min(rets), float(np.mean(shs))
def show(tag,s):
    r=run_backtest(panel,s,risk=RiskEngine(),rebalance_every=60,cost_bps=rc)
    m=M.compute_metrics(r.equity,r.telemetry,r.trade_count,r.liquidated)
    pos,worst,msh=blocks(r.equity)
    print(f"{tag:<26}{m['total_return']*100:>7.2f}{m['max_drawdown']*100:>8.2f}{m['sharpe']:>7.2f}{m['discipline']:>6.0f} | pos {pos}/6  worst {worst*100:>6.2f}%  meanblkSh {msh:>5.2f}")
print(f"{'strategy':<26}{'ret%':>7}{'maxDD%':>8}{'Sh':>7}{'disc':>6} | block consistency")
show("inverse-vol champ", DiversifiedVolTarget(mom_window=480,vol_window=480,smooth_halflife=48,target_gross=4.0))
show("shrinkage MV", CovAwareMomentum(mom_window=480,ema=48,target_gross=4.0,mode="mv"))
show("regime+ensemble", RegimeEnsembleMomentum(target_gross=4.0))
