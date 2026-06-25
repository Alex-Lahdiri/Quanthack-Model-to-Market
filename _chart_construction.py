import sys, glob, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget
from strategies.cov_aware import CovAwareMomentum
UNIV=["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD","EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel=pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]
parts=pd.concat([pd.read_parquet(p) for p in glob.glob("/tmp/ingest_state/parts/*.parquet")])
parts=parts[(parts.close>0)&parts.mean_spread.notna()]; parts["hs"]=(parts.mean_spread/parts.close)/2*1e4
rc=parts.groupby("symbol")["hs"].mean().to_dict()
def eq(s): return run_backtest(panel,s,risk=RiskEngine(),rebalance_every=60,cost_bps=rc).equity
e1=eq(DiversifiedVolTarget(mom_window=480,vol_window=480,smooth_halflife=48,target_gross=4.0))
e2=eq(CovAwareMomentum(target_gross=4.0,mode="mv"))
e3=eq(CovAwareMomentum(target_gross=4.0,mode="hrp"))
fig,ax=plt.subplots(figsize=(9,4.5))
ax.plot(e1.index,e1.values/1e6,label="inverse-vol (champ)  Sh 3.3")
ax.plot(e2.index,e2.values/1e6,label="shrinkage MV  Sh 4.8",lw=2,color="#2e7d32")
ax.plot(e3.index,e3.values/1e6,label="HRP  Sh -4.5",color="#c0392b",alpha=.7)
ax.set_ylabel("equity ($M)"); ax.set_title("Advanced portfolio construction (full month, real costs, gross 4)")
ax.grid(alpha=.3); ax.legend(); fig.tight_layout(); fig.savefig("results/research/construction_compare.png",dpi=120)
print("saved construction_compare.png")
