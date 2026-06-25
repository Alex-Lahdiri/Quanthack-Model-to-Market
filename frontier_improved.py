import sys, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
        "EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel = pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]
half = panel.iloc[:int(len(panel)*0.5)]   # momentum-hostile first half = stress
peers = M.make_synthetic_peers(300, seed=1)
COST = 0.7   # blended realistic spread (majors ~0.3-0.6bp, metals higher)

def ev(pn, g):
    s = DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480,
                             target_gross=g, smooth_halflife=48)
    r = run_backtest(pn, s, risk=RiskEngine(), rebalance_every=60, cost_bps=COST)
    return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)

G=[1,2,3,4,5,6,8]; rows=[]
print(f"improved config: 8h momentum, rebalance 60, smooth 48, cost {COST}bp\n")
print(f"{'gross':>5}{'ret%':>8}{'maxDD%':>8}{'Sharpe':>7}{'disc':>6}{'score':>7} | {'STRESS dd%':>10}")
for g in G:
    m=ev(panel,g); s=ev(half,g); sc=M.simulate_final_score(m,peers)["final_score"]
    rows.append((g,m,sc,s))
    print(f"{g:>5}{m['total_return']*100:>8.2f}{m['max_drawdown']*100:>8.2f}{m['sharpe']:>7.2f}"
          f"{m['discipline']:>6.0f}{sc:>7.1f} | {s['max_drawdown']*100:>10.2f}")

fig, ax = plt.subplots(figsize=(8,5))
ax.plot(G,[r[1]['total_return']*100 for r in rows],"o-",label="full-month return %")
ax.plot(G,[r[1]['max_drawdown']*100 for r in rows],"s-",label="max drawdown %")
ax.plot(G,[r[3]['max_drawdown']*100 for r in rows],"^--",label="stress (worst-half) DD %",color="firebrick")
ax.set_xlabel("target gross leverage"); ax.set_ylabel("%"); ax.grid(alpha=.3); ax.axhline(0,color="k",lw=.5)
ax2=ax.twinx(); ax2.plot(G,[r[2] for r in rows],"d:",color="green",label="sim score (synthetic field)")
ax2.set_ylabel("sim score",color="green")
ax.set_title("Scoring frontier — improved slow-momentum book"); ax.legend(loc="lower left")
fig.tight_layout(); fig.savefig("results/research/scoring_frontier.png", dpi=120); plt.close(fig)
print("\nsaved results/research/scoring_frontier.png")
