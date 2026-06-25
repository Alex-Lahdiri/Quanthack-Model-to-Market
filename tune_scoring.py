"""Scoring-aware tuning. The edge is thin and ~Sharpe-invariant to leverage, so
gross only trades return-rank vs drawdown-rank + blow-up risk. We map that frontier
on the full month and show the 'stress' (worst-half) drawdown at each gross."""
import sys, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
        "EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel = pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]
half = panel.iloc[:int(len(panel)*0.5)]    # the momentum-hostile first half = stress test
peers = M.make_synthetic_peers(300, seed=1)

def ev(pn, g):
    s = DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480, target_gross=g)
    r = run_backtest(pn, s, risk=RiskEngine(), rebalance_every=15)
    return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)

print(f"full month {panel.shape[0]} bars, {len(UNIV)} instruments\n")
print(f"{'gross':>5}{'ret%':>8}{'maxDD%':>8}{'Sharpe':>8}{'disc':>6}{'liq':>5}{'score':>7} | {'STRESS ret%':>11}{'maxDD%':>8}{'liq':>5}")
rows=[]
for g in (1,2,3,4,6,8,10,12):
    m = ev(panel, g); s = ev(half, g)
    sc = M.simulate_final_score(m, peers)["final_score"]
    rows.append((g, m, sc, s))
    print(f"{g:>5}{m['total_return']*100:>8.2f}{m['max_drawdown']*100:>8.2f}{m['sharpe']:>8.2f}"
          f"{m['discipline']:>6.0f}{('Y' if m['liquidated'] else '-'):>5}{sc:>7.1f} | "
          f"{s['total_return']*100:>11.2f}{s['max_drawdown']*100:>8.2f}{('Y' if s['liquidated'] else '-'):>5}")
print("\nnote: Sharpe ~constant in gross (return & vol scale together) -> leverage only")
print("trades return-rank vs drawdown-rank + liquidation risk. Score uses a SYNTHETIC field.")
