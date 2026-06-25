"""Alpha research: stats, correlation/PCA, signal IC, intraday seasonality.
Usage: python research.py [--panel PATH] [--out DIR] [--min-vol PCT]"""
import os, sys, argparse, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

ap = argparse.ArgumentParser()
ap.add_argument("--panel", default="results/panel_majors_2wk.parquet")
ap.add_argument("--out", default="results/research")
ap.add_argument("--min-vol", type=float, default=1.0, help="drop cols below this ann vol %% (pegs)")
args = ap.parse_args()
OUT = args.out; os.makedirs(OUT, exist_ok=True)
ppy = 4*24*365

panel = pd.read_parquet(args.panel).set_index("ts").sort_index()
c15 = panel.resample("15min").last().dropna(how="all").ffill()
# drop degenerate / pegged instruments (inverse-vol sizing footgun + distorts PCA)
annv0 = (np.log(c15).diff().std()*np.sqrt(ppy)*100)
drop = annv0[annv0 < args.min_vol].index.tolist()
if drop: print(f"dropping low-vol/pegged (< {args.min_vol}% ann vol): {drop}")
c15 = c15.drop(columns=drop)
r15 = np.log(c15).diff(); cols = list(c15.columns)
print(f"panel: {panel.shape} -> analysis on {len(cols)} instruments, {c15.shape[0]} 15-min bars")

# 1) stats
acf = lambda k: r15.apply(lambda s: s.autocorr(k))
stats = pd.DataFrame({"ann_vol%": (r15.std()*np.sqrt(ppy)*100).round(1), "skew": r15.skew().round(2),
                      "exkurt": r15.kurt().round(1), "acf_15m": acf(1).round(3), "acf_60m": acf(4).round(3)})
print("\n=== per-instrument stats (15-min returns) ===")
print(stats.sort_values("ann_vol%", ascending=False).to_string())
print(f"\nmean ACF(15m) = {acf(1).mean():.3f} (neg => short-horizon mean reversion)")

# 2) corr + PCA
R = r15[cols].dropna(); corr = R.corr()
ev, V = np.linalg.eigh(np.corrcoef(((R-R.mean())/R.std()).values.T))
o = np.argsort(ev)[::-1]; ev, V = ev[o], V[:, o]; var_exp = ev/ev.sum()
pc1 = pd.Series(V[:, 0], index=cols)
if pc1.mean() < 0: pc1 = -pc1
print(f"\n=== PCA variance explained (top5): {np.round(var_exp[:5]*100,1)} % ===")
print("PC1 loadings:"); print(pc1.round(2).sort_values().to_string())

# 3) IC
Ls = [1, 2, 4, 8, 16, 32]; Hs = [1, 4, 16, 32]
def row_ic(sig, fwd):
    m = sig.notna().all(axis=1) & fwd.notna().all(axis=1)
    s = sig[m].rank(axis=1).values; f = fwd[m].rank(axis=1).values
    if len(s) < 10: return np.nan, np.nan
    s = s - s.mean(1, keepdims=True); f = f - f.mean(1, keepdims=True)
    ic = (s*f).sum(1)/np.sqrt((s*s).sum(1)*(f*f).sum(1)+1e-18)
    return ic.mean(), ic.mean()/(ic.std()+1e-12)*np.sqrt(len(ic))
icm = pd.DataFrame(index=[f"{L*15}m" for L in Ls], columns=[f"{H*15}m" for H in Hs], dtype=float)
tm = icm.copy()
for L in Ls:
    sig = c15.pct_change(L)
    for H in Hs:
        fwd = c15.shift(-H)/c15 - 1; idx = np.arange(0, len(c15), max(H, 1))
        ic, t = row_ic(sig.iloc[idx], fwd.iloc[idx]); icm.iloc[Ls.index(L), Hs.index(H)] = ic; tm.iloc[Ls.index(L), Hs.index(H)] = t
print("\n=== cross-sectional IC (rows=lookback, cols=forward; +momentum / -reversion) ===")
print(icm.round(3).to_string())
print("\n=== approx t-stats ===")
print(tm.round(1).to_string())

# 4) intraday
vol_by_hour = (r15.abs().mean(axis=1)*100).groupby(r15.index.hour).mean()
print("\n=== mean |15m ret| %% by UTC hour ==="); print(vol_by_hour.round(3).to_string())

# charts
fig, ax = plt.subplots(figsize=(8, 7)); im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
ax.set_xticks(range(len(cols))); ax.set_xticklabels(cols, rotation=90, fontsize=7)
ax.set_yticks(range(len(cols))); ax.set_yticklabels(cols, fontsize=7)
plt.colorbar(im, fraction=0.046); ax.set_title("15-min return correlation"); fig.tight_layout()
fig.savefig(f"{OUT}/corr_heatmap.png", dpi=120); plt.close(fig)

fig, axs = plt.subplots(1, 2, figsize=(12, 5))
axs[0].bar(range(1, len(var_exp)+1), var_exp*100); axs[0].set_title("PCA variance explained (%)"); axs[0].set_xlabel("PC")
p = pc1.sort_values(); axs[1].barh(range(len(p)), p.values); axs[1].set_yticks(range(len(p)))
axs[1].set_yticklabels(p.index, fontsize=7); axs[1].set_title(f"PC1 loadings ({var_exp[0]*100:.0f}% var)")
fig.tight_layout(); fig.savefig(f"{OUT}/pca.png", dpi=120); plt.close(fig)

fig, ax = plt.subplots(figsize=(6.5, 5)); im = ax.imshow(icm.values.astype(float), cmap="RdBu_r", vmin=-0.12, vmax=0.12)
ax.set_xticks(range(len(Hs))); ax.set_xticklabels(icm.columns); ax.set_yticks(range(len(Ls))); ax.set_yticklabels(icm.index)
for i in range(len(Ls)):
    for j in range(len(Hs)): ax.text(j, i, f"{icm.values[i,j]:.3f}", ha="center", va="center", fontsize=8)
ax.set_xlabel("forward horizon"); ax.set_ylabel("signal lookback"); ax.set_title("Cross-sectional IC (+mom/-rev)")
plt.colorbar(im, fraction=0.046); fig.tight_layout(); fig.savefig(f"{OUT}/ic_heatmap.png", dpi=120); plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 4)); ax.bar(vol_by_hour.index, vol_by_hour.values)
ax.set_xlabel("UTC hour"); ax.set_ylabel("mean |15m return| %"); ax.set_title("Intraday volatility by hour (UTC)")
fig.tight_layout(); fig.savefig(f"{OUT}/intraday_vol.png", dpi=120); plt.close(fig)

stats.to_csv(f"{OUT}/instrument_stats.csv"); icm.to_csv(f"{OUT}/ic_matrix.csv")
print("\nsaved charts + csvs to", OUT)
