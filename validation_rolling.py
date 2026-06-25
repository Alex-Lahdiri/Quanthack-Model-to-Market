"""Confirm robustness: real per-instrument spreads + rolling block walk-forward."""
import sys, glob, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
        "EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel = pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]

# real per-instrument per-side cost (bps) = mean half-spread, from ingest parts
parts = pd.concat([pd.read_parquet(p) for p in glob.glob("/tmp/ingest_state/parts/*.parquet")])
parts = parts[(parts.close > 0) & parts.mean_spread.notna()]
parts["hs"] = (parts.mean_spread/parts.close)/2*1e4
realcost = parts.groupby("symbol")["hs"].mean().to_dict()
print("real per-side cost (bps):", {k: round(realcost[k],3) for k in UNIV if k in realcost})

def make(): return DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480,
                                        smooth_halflife=48, target_gross=4.0)
def run(cost): return run_backtest(panel, make(), risk=RiskEngine(), rebalance_every=60, cost_bps=cost)
def met(r): return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)

print("\n=== full-month cost sensitivity (gross 4) ===")
for tag, c in [("real per-instrument", realcost), ("flat 0.7bp", 0.7), ("zero", 0.0)]:
    m = met(run(c)); print(f"  {tag:<20} ret {m['total_return']*100:>6.2f}%  Sharpe {m['sharpe']:>5.2f}  "
                           f"maxDD {m['max_drawdown']*100:>6.2f}%  trades {m['trade_count']}")

# rolling blocks on the real-cost run (drop 1-day warmup, then 6 equal blocks)
res = run(realcost); eq = res.equity.iloc[1440:]
K = 6; idx = np.array_split(np.arange(len(eq)), K)
print(f"\n=== rolling walk-forward: {K} consecutive blocks (real costs, post-warmup) ===")
print(f"{'block':<7}{'dates':<26}{'ret%':>8}{'maxDD%':>9}{'Sharpe':>8}")
blk = []
for i, ii in enumerate(idx, 1):
    e = eq.iloc[ii]
    ret = e.iloc[-1]/e.iloc[0]-1; dd = M.max_drawdown(e); sh = M.sharpe(M.resample_equity(e))
    blk.append((ret, dd, sh))
    print(f"{i:<7}{str(e.index[0].date())+'..'+str(e.index[-1].date()):<26}{ret*100:>8.2f}{dd*100:>9.2f}{sh:>8.2f}")
rets = [b[0] for b in blk]; shs = [b[2] for b in blk]
print(f"\nblocks positive: {sum(r>0 for r in rets)}/{K} | mean block Sharpe {np.mean(shs):.2f} | "
      f"worst block ret {min(rets)*100:.2f}% | full(post-warmup) Sharpe {M.sharpe(M.resample_equity(eq)):.2f}")

fig, ax = plt.subplots(figsize=(9,4))
ax.bar(range(1,K+1), [r*100 for r in rets], color=["#3f8f3f" if r>0 else "#c0392b" for r in rets])
ax.set_xlabel("walk-forward block"); ax.set_ylabel("block return %"); ax.axhline(0,color="k",lw=.6)
ax.set_title("Rolling walk-forward block returns (real costs, gross 4)")
for i,r in enumerate(rets,1): ax.text(i, r*100, f"Sh {shs[i-1]:.1f}", ha="center", va="bottom" if r>0 else "top", fontsize=8)
fig.tight_layout(); fig.savefig("results/research/rolling_blocks.png", dpi=120); plt.close(fig)
print("\nsaved results/research/rolling_blocks.png")
