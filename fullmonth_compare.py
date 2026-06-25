"""Full-month walk-forward: baseline vs v2 (+ ablation) on the liquid 12-name
universe (one gold, no pegs/redundant crosses)."""
import sys, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget, UsdNeutralMomentum

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
        "EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel = pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]
k = int(len(panel)*0.6); train, test = panel.iloc[:k], panel.iloc[k:]
peers = M.make_synthetic_peers(300, seed=1)
print(f"universe {len(UNIV)} | train {train.shape[0]} bars ({train.index[0].date()}..{train.index[-1].date()}) "
      f"| test {test.shape[0]} bars ({test.index[0].date()}..{test.index[-1].date()})\n")

def ev(pn, s): 
    r = run_backtest(pn, s, risk=RiskEngine(), rebalance_every=15)
    return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)
def row(tag, m): 
    return f"{tag:<26}{m['total_return']*100:>8.2f}{m['max_drawdown']*100:>9.2f}{m['sharpe']:>8.2f}{m['discipline']:>7.0f}{m['trade_count']:>8}"

base = {w: DiversifiedVolTarget(mode="momentum", mom_window=w, vol_window=w, target_gross=6.0) for w in (120,240,480)}
v2 = {
 "v2 full":         UsdNeutralMomentum(target_gross=6.0),
 "v2 -neutralize":  UsdNeutralMomentum(target_gross=6.0, neutralize=False),
 "v2 -blend(480)":  UsdNeutralMomentum(target_gross=6.0, windows=(480,)),
 "v2 strip extras": UsdNeutralMomentum(target_gross=6.0, windows=(480,), time_of_day=False, neutralize=False, name_cap=0.85),
}
print(f"{'config (TRAIN)':<26}{'ret%':>8}{'maxDD%':>9}{'Sharpe':>8}{'disc':>7}{'trades':>8}")
btr = {w: ev(train, s) for w, s in base.items()}
for w in base: print(row(f"baseline mom{w}", btr[w]))
vtr = {t: ev(train, s) for t, s in v2.items()}
for t in v2: print(row(t, vtr[t]))

bw = max(btr, key=lambda w: btr[w]["sharpe"] if btr[w]["trade_count"]>=30 else -9)
bv = max(vtr, key=lambda t: vtr[t]["sharpe"] if vtr[t]["trade_count"]>=30 else -9)
print(f"\nselected on TRAIN -> baseline mom{bw} (Sh {btr[bw]['sharpe']:.2f}) | {bv} (Sh {vtr[bv]['sharpe']:.2f})")
print("\n--- OUT-OF-SAMPLE ---")
print(f"{'config':<26}{'ret%':>8}{'maxDD%':>9}{'Sharpe':>8}{'disc':>7}{'trades':>8}")
bo = ev(test, base[bw]); vo = ev(test, v2[bv])
print(row(f"baseline mom{bw}", bo)); print(row(bv, vo))
sb = M.simulate_final_score(bo, peers); sv = M.simulate_final_score(vo, peers)
print(f"\nOOS simulated score:  baseline {sb['final_score']:.1f}   v2 {sv['final_score']:.1f}")
