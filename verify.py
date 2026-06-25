"""Independent sanity checks on the scoring math, risk caps, and liquidation."""
import numpy as np
import pandas as pd

import config as C
import metrics as M
from risk_engine import RiskEngine
from engine import run_backtest
from strategies.base import Strategy

results = []
def check(name, ok, detail=""):
    results.append((name, ok, detail))

idx = lambda k: pd.date_range("2026-01-01", periods=k, freq="15min")

# 1) total return: 100 -> 110 = +10%
check("total_return", abs(M.total_return(pd.Series([100, 110], index=idx(2))) - 0.10) < 1e-12)

# 2) max drawdown: 100 -> 120 -> 90 -> 100  => -25%
check("max_drawdown", abs(M.max_drawdown(pd.Series([100,120,90,100], index=idx(4))) - (-0.25)) < 1e-12)

# 3) Sharpe (periods_per_year=1) == mean/std(ddof=1) of the sampled returns
r = np.array([0.01, -0.005, 0.01, -0.005, 0.02, -0.01])
eq = pd.Series(100*np.cumprod(np.concatenate([[1.0], 1+r])), index=idx(len(r)+1))
man = r.mean()/r.std(ddof=1)
check("sharpe_matches_manual", abs(M.sharpe(eq, periods_per_year=1) - man) < 1e-9, f"{man:.4f}")

# 4) percentile rank: top / bottom / tie-handling
check("pct_rank_top", M.percentile_rank(5, [1,2,3,4], True) == 100.0)
check("pct_rank_bottom", M.percentile_rank(0, [1,2,3,4], True) == 0.0)
check("pct_rank_tie", abs(M.percentile_rank(3, [1,2,3,4,3], True) - 60.0) < 1e-9)
# drawdown ranks on signed values: -0.05 beats -0.20
check("pct_rank_drawdown", M.percentile_rank(-0.05, [-0.20,-0.10,-0.30], True) == 100.0)

# 5) risk engine: concentration cap (one dominant name in a multi-name book)
re = RiskEngine()
wc = re.apply(pd.Series({"A": 50.0, "B": 0.1, "C": -0.1}))
t = RiskEngine.telemetry(wc, 1_000_000)
check("concentration_cap", t["max_name_share"] <= C.SAFE_MAX_CONCENTRATION + 1e-6,
      f"name_share={t['max_name_share']:.4f}")
check("gross_cap", t["gross_leverage"] <= C.EFFECTIVE_GROSS_CAP + 1e-6,
      f"gross={t['gross_leverage']:.4f} (cap {C.EFFECTIVE_GROSS_CAP})")

# 6) net-directional cap does not make a one-sided tilt worse, and reduces a binding one
before = pd.Series({"A": 10.0, "B": 10.0, "C": -1.0})
nb = abs(before.sum())/before.abs().sum()
wa = re.apply(before)
na = abs(wa.sum())/wa.abs().sum()
check("net_directional_not_worse", na <= nb + 1e-9, f"{nb:.3f} -> {na:.3f}")

# 7) forced liquidation flag fires on a wipeout move
panel = pd.DataFrame({"X": [100.0, 100.0, 1.0]}, index=idx(3))
class AllIn(Strategy):
    name = "allin"
    def target_weights(self, t, history): return pd.Series({"X": 25.0})
res = run_backtest(panel, AllIn(), rebalance_every=1, cost_bps=0.0, band_frac=0.0)
check("liquidation_flag", res.liquidated is True)

# 8) no-trade band lowers trade count vs no band (uses synthetic data if present)
import os
if os.path.exists("data/synthetic_quotes.parquet"):
    import data_loader as dl
    from strategies import DiversifiedVolTarget
    panel2 = dl.build_price_panel(dl.to_bars(dl.load_quotes("data/synthetic_quotes.parquet"), "5m"))
    a = run_backtest(panel2, DiversifiedVolTarget(), band_frac=0.0)
    b = run_backtest(panel2, DiversifiedVolTarget(), band_frac=0.05)
    check("band_cuts_trades", b.trade_count < a.trade_count, f"{a.trade_count} -> {b.trade_count}")

print("\n================= VERIFICATION =================")
allok = True
for name, ok, detail in results:
    allok &= ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {name:<28} {detail}")
print("================================================")
print("ALL PASS" if allok else "SOME FAILED")
