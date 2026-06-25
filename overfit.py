"""Overfitting controls: Deflated Sharpe Ratio (Bailey & Lopez de Prado) and
Probability of Backtest Overfitting via Combinatorially Symmetric CV (CSCV)."""
import sys, glob, itertools, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import numpy as np, pandas as pd
from scipy.stats import norm
import config as C, metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget
from strategies.cov_aware import CovAwareMomentum

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD","EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel = pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]
parts = pd.concat([pd.read_parquet(p) for p in glob.glob("/tmp/ingest_state/parts/*.parquet")])
parts = parts[(parts.close>0)&parts.mean_spread.notna()]; parts["hs"]=(parts.mean_spread/parts.close)/2*1e4
rc = parts.groupby("symbol")["hs"].mean().to_dict()

# the grid of configs we've effectively explored this session
configs = {}
for w in (120,240,480):
    for sm in (12,48):
        for g in (2,4):
            configs[f"iv_w{w}_s{sm}_g{g}"] = DiversifiedVolTarget(mom_window=w, vol_window=w, smooth_halflife=sm, target_gross=g)
for w in (240,480):
    for g in (2,4):
        configs[f"mv_w{w}_g{g}"] = CovAwareMomentum(mom_window=w, ema=48, target_gross=g, mode="mv")

R = {}
for tag, s in configs.items():
    eq = run_backtest(panel, s, risk=RiskEngine(), rebalance_every=60, cost_bps=rc).equity
    R[tag] = M.resample_equity(eq).pct_change()
R = pd.DataFrame(R).dropna()
N = R.shape[1]; T = R.shape[0]
SR = R.mean()/R.std()                      # per-period Sharpe
ann = np.sqrt(C.PERIODS_PER_YEAR)
print(f"{N} configs, {T} 15-min obs. Annualized Sharpe by config:")
for tag in SR.sort_values(ascending=False).index:
    print(f"  {tag:<16}{SR[tag]*ann:>7.2f}")
best = SR.idxmax(); sr = SR[best]

# --- Deflated Sharpe Ratio ---
g3 = R[best].skew(); g4 = R[best].kurt()+3; V = SR.var(ddof=1); gamma = 0.5772156649
def sr0(n): return np.sqrt(V)*((1-gamma)*norm.ppf(1-1/n)+gamma*norm.ppf(1-1/(n*np.e)))
def dsr(n):
    s0 = sr0(n)
    return norm.cdf((sr - s0)*np.sqrt(T-1)/np.sqrt(1 - g3*sr + (g4-1)/4*sr**2))
print(f"\nbest config: {best}  (annualized Sharpe {sr*ann:.2f}, per-period {sr:.3f})")
print(f"returns skew {g3:.2f}, excess-kurt {g4-3:.1f}, Var(SR across configs) {V:.4f}")
for n in (N, 50, 200):
    print(f"  trials N={n:<4} expected-max SR0(ann) {sr0(n)*ann:5.2f} -> Deflated Sharpe (P[true SR>0]) = {dsr(n):.3f}")

# --- PBO via CSCV ---
S = 10
blocks = np.array_split(np.arange(T), S)
Mb = np.array([[R[c].iloc[b].mean()/(R[c].iloc[b].std()+1e-12) for c in R.columns] for b in blocks])  # S x N
lam = []
for combo in itertools.combinations(range(S), S//2):
    isb = list(combo); oob = [i for i in range(S) if i not in combo]
    nstar = np.argmax(Mb[isb].mean(0))
    oos = Mb[oob].mean(0)
    rank = (oos.argsort().argsort()[nstar]+1)/(N+1)        # ascending rank, 1=worst
    rank = min(max(rank, 1e-6), 1-1e-6); lam.append(np.log(rank/(1-rank)))
lam = np.array(lam); pbo = float(np.mean(lam < 0))
print(f"\nPBO (CSCV, S={S}, {len(lam)} splits): {pbo:.1%}  -> probability the in-sample-best config is below-median out-of-sample")
