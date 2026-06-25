"""Walk-forward tune of turnover (rebalance x smoothing) at low gross. Costs are
the binding constraint on a thin slow-momentum edge, so cutting churn is the lever."""
import sys, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
        "EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel = pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]
k = int(len(panel)*0.6); train, test = panel.iloc[:k], panel.iloc[k:]
peers = M.make_synthetic_peers(300, seed=1)

def ev(pn, rb, sm, g=2, cost=1.0):
    s = DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480,
                             target_gross=g, smooth_halflife=sm)
    r = run_backtest(pn, s, risk=RiskEngine(), rebalance_every=rb, cost_bps=cost)
    return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)

grid = [(rb, sm) for rb in (30, 60, 120) for sm in (24, 48)]
print(f"{'rebal':>6}{'smooth':>7} | {'TR ret%':>8}{'TR Sh':>7}{'TR tr':>7} | {'OOS ret%':>9}{'OOS Sh':>7}{'OOS dd%':>8}{'OOS tr':>7}")
res=[]
for rb, sm in grid:
    tr=ev(train,rb,sm); oo=ev(test,rb,sm); res.append((rb,sm,tr,oo))
    print(f"{rb:>6}{sm:>7} | {tr['total_return']*100:>8.2f}{tr['sharpe']:>7.2f}{tr['trade_count']:>7} | "
          f"{oo['total_return']*100:>9.2f}{oo['sharpe']:>7.2f}{oo['max_drawdown']*100:>8.2f}{oo['trade_count']:>7}")

best=max([r for r in res if r[2]['trade_count']>=30], key=lambda r:r[2]['sharpe'])
rb,sm,tr,oo=best
print(f"\nbest on TRAIN: rebalance {rb}, smooth {sm} (train Sharpe {tr['sharpe']:.2f})")
# cost sensitivity at the chosen config, full month
print("\ncost sensitivity (full month, chosen config, gross 2):")
for c in (0.5, 1.0, 1.5):
    m=ev(panel,rb,sm,g=2,cost=c)
    print(f"  cost {c}bp:  ret {m['total_return']*100:>6.2f}%  Sharpe {m['sharpe']:>5.2f}  trades {m['trade_count']}")
