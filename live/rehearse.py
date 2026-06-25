"""
Closed-loop LIVE REHEARSAL. Replays the cached panel hour-by-hour through the ACTUAL
live decision path -- live weight selection (W at time t) -> risk engine -> order/fill
diff (as the MT5 bridge would) -> per-instrument costs -> risk monitor -- to catch
integration bugs (units, signs, symbol map, stale data) before launch. Cross-checks
the resulting equity against the vectorized backtester.
"""
from __future__ import annotations
import sys, os, glob, warnings; warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import numpy as np, pandas as pd
import metrics as M
from engine import run_backtest, _cost_vector
from risk_engine import RiskEngine
from strategies.cov_aware import CovAwareMomentum
from risk_monitor import assess

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
        "EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
GROSS, REBAL, MIN_NOTION = 4.0, 60, 5000.0
panel = pd.read_parquet(os.path.join(os.path.dirname(HERE), "results/panel_full_month.parquet")).set_index("ts").sort_index()[UNIV]
parts = pd.concat([pd.read_parquet(p) for p in glob.glob("/tmp/ingest_state/parts/*.parquet")])
parts = parts[(parts.close>0)&parts.mean_spread.notna()]; parts["hs"]=(parts.mean_spread/parts.close)/2*1e4
rc = parts.groupby("symbol")["hs"].mean().to_dict()

strat = CovAwareMomentum(mom_window=480, ema=48, target_gross=GROSS, mode="mv")
strat.precompute(panel)
risk = RiskEngine(); cost_vec = _cost_vector(rc, list(panel.columns))
P = panel.ffill().bfill().to_numpy(); times = panel.index; n, m = P.shape
equity = 1_000_000.0; units = np.zeros(m); eq = np.empty(n); eq[0] = equity
warn_steps = 0; orders = 0
for i in range(1, n):
    price = P[i]
    equity += float(units @ (price - P[i-1]))            # mark to market
    if i % REBAL == 0:
        w = risk.apply(strat.W.loc[times[i]]).reindex(panel.columns).fillna(0.0).to_numpy()
        target_units = np.where(price > 0, w*equity/price, 0.0)   # runner+bridge: notional->units
        delta = target_units - units
        traded = np.abs(delta) * price
        mask = traded > MIN_NOTION
        if mask.any():
            equity -= float((traded[mask]*cost_vec[mask]).sum())/1e4
            units[mask] = target_units[mask]; orders += int(mask.sum())
        rep = assess({s: float(units[j]*price[j]) for j,s in enumerate(panel.columns)}, equity)  # real monitor
        if rep["warnings"]: warn_steps += 1
    eq[i] = equity
live = pd.Series(eq, index=times)
lm = M.compute_metrics(live, pd.DataFrame(index=times), orders, equity<=0)

# cross-check vs vectorized backtester (same config/costs)
bt = run_backtest(panel, CovAwareMomentum(mom_window=480, ema=48, target_gross=GROSS, mode="mv"),
                  risk=RiskEngine(), rebalance_every=REBAL, cost_bps=rc).equity
diff = float((live/live.iloc[0] - bt/bt.iloc[0]).abs().max())
print("=== LIVE REHEARSAL (actual decision/order/fill path) ===")
print(f"  final equity {lm['final_equity']:,.0f} | return {lm['total_return']*100:.2f}% | "
      f"Sharpe {lm['sharpe']:.2f} | maxDD {lm['max_drawdown']*100:.2f}% | fills {orders}")
print(f"  risk-monitor warning steps: {warn_steps} (0 = never breached a penalty tier)")
print(f"  max normalized equity diff vs vectorized backtest: {diff:.4%}  ({'OK, paths agree' if diff<0.01 else 'INVESTIGATE'})")
print("  live loop ran end-to-end with no errors.")
