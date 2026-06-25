"""Walk-forward: baseline (DiversifiedVolTarget) vs v2 (UsdNeutralMomentum).
Each tunes ONE knob on train only; we report out-of-sample head-to-head."""
import sys, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget, UsdNeutralMomentum

panel = pd.read_parquet("results/panel_majors_2wk.parquet").set_index("ts").sort_index()
k = int(len(panel) * 0.6)
train, test = panel.iloc[:k], panel.iloc[k:]
peers = M.make_synthetic_peers(300, seed=1)
print(f"train {train.shape[0]} bars ({train.index[0]}..{train.index[-1]})")
print(f"test  {test.shape[0]} bars ({test.index[0]}..{test.index[-1]})\n")

def ev(panel_, strat, rb=15):
    r = run_backtest(panel_, strat, risk=RiskEngine(), rebalance_every=rb)
    return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)

def line(tag, m):
    return (f"{tag:<26}{m['total_return']*100:>8.2f}{m['max_drawdown']*100:>9.2f}"
            f"{m['sharpe']:>8.2f}{m['discipline']:>7.0f}{m['trade_count']:>8}")

# ---- baseline: tune lookback window on train ----
base_grid = [DiversifiedVolTarget(mode="momentum", mom_window=w, vol_window=w, target_gross=6.0)
             for w in (120, 240, 480)]
base_tr = [(s, ev(train, s)) for s in base_grid]
base_best = max([x for x in base_tr if x[1]["trade_count"] >= 30 and not x[1]["liquidated"]],
                key=lambda x: x[1]["sharpe"])
b_strat = base_best[0]
b_oos = ev(test, DiversifiedVolTarget(mode="momentum", mom_window=b_strat.mom_window,
                                      vol_window=b_strat.vol_window, target_gross=6.0))

# ---- v2: tune target_gross on train ----
v2_grid = [UsdNeutralMomentum(target_gross=g) for g in (4, 6, 8)]
v2_tr = [(s, ev(train, s)) for s in v2_grid]
v2_best = max([x for x in v2_tr if x[1]["trade_count"] >= 30 and not x[1]["liquidated"]],
              key=lambda x: x[1]["sharpe"])
v_strat = v2_best[0]
v_oos = ev(test, UsdNeutralMomentum(target_gross=v_strat.target_gross))

print(f"{'':<26}{'ret%':>8}{'maxDD%':>9}{'Sharpe':>8}{'disc':>7}{'trades':>8}")
print("-- TRAIN (selection) --")
print(line(f"baseline mom{b_strat.mom_window}", base_best[1]))
print(line(f"v2 gross{v_strat.target_gross:g}", v2_best[1]))
print("-- OUT-OF-SAMPLE --")
print(line(f"baseline mom{b_strat.mom_window}", b_oos))
print(line(f"v2 gross{v_strat.target_gross:g}", v_oos))

sb = M.simulate_final_score(b_oos, peers)
sv = M.simulate_final_score(v_oos, peers)
print(f"\nOOS simulated score vs field:  baseline {sb['final_score']:.1f}   v2 {sv['final_score']:.1f}")
print(f"  baseline ranks  ret {sb['rank_return']:.0f} | dd {sb['rank_drawdown']:.0f} | "
      f"sharpe {sb['rank_sharpe']:.0f} | disc {sb['rank_discipline']:.0f}")
print(f"  v2 ranks        ret {sv['rank_return']:.0f} | dd {sv['rank_drawdown']:.0f} | "
      f"sharpe {sv['rank_sharpe']:.0f} | disc {sv['rank_discipline']:.0f}")
