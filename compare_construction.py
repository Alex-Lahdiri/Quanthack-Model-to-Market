import sys, glob, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import numpy as np, pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget
from strategies.cov_aware import CovAwareMomentum

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD","EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel = pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]
parts = pd.concat([pd.read_parquet(p) for p in glob.glob("/tmp/ingest_state/parts/*.parquet")])
parts = parts[(parts.close>0) & parts.mean_spread.notna()]; parts["hs"]=(parts.mean_spread/parts.close)/2*1e4
realcost = parts.groupby("symbol")["hs"].mean().to_dict()
peers = M.make_synthetic_peers(300, seed=1)
ksplit = int(len(panel)*0.6)

def evalstrat(tag, strat):
    r = run_backtest(panel, strat, risk=RiskEngine(), rebalance_every=60, cost_bps=realcost)
    mf = M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)
    eo = r.equity.iloc[ksplit:]
    oos_ret = eo.iloc[-1]/eo.iloc[0]-1; oos_sh = M.sharpe(M.resample_equity(eo)); oos_dd = M.max_drawdown(eo)
    sc = M.simulate_final_score(mf, peers)["final_score"]
    print(f"{tag:<22}{mf['total_return']*100:>8.2f}{mf['max_drawdown']*100:>8.2f}{mf['sharpe']:>7.2f}"
          f"{mf['discipline']:>6.0f}{mf['trade_count']:>7}{sc:>7.1f} | {oos_ret*100:>8.2f}{oos_dd*100:>8.2f}{oos_sh:>7.2f}")

print(f"{'construction':<22}{'ret%':>8}{'maxDD%':>8}{'Sh':>7}{'disc':>6}{'trd':>7}{'score':>7} | {'OOSret%':>8}{'OOSdd%':>8}{'OOSSh':>7}")
evalstrat("inverse-vol (champ)", DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480, smooth_halflife=48, target_gross=4.0))
evalstrat("shrinkage MV", CovAwareMomentum(mom_window=480, ema=48, cov_window=480, cov_step=60, target_gross=4.0, mode="mv"))
evalstrat("HRP risk-parity", CovAwareMomentum(mom_window=480, ema=48, cov_window=480, cov_step=60, target_gross=4.0, mode="hrp"))
