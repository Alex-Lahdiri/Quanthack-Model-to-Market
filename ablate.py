import sys, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0,".")
import pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget, UsdNeutralMomentum

panel = pd.read_parquet("results/panel_majors_2wk.parquet").set_index("ts").sort_index()
k=int(len(panel)*0.6); train,test=panel.iloc[:k],panel.iloc[k:]
def ev(pn,s): 
    r=run_backtest(pn,s,risk=RiskEngine(),rebalance_every=15)
    return M.compute_metrics(r.equity,r.telemetry,r.trade_count,r.liquidated)
def row(tag,m): return f"{tag:<30}{m['total_return']*100:>8.2f}{m['max_drawdown']*100:>9.2f}{m['sharpe']:>8.2f}{m['discipline']:>7.0f}{m['trade_count']:>8}"

variants={
 "baseline mom480":              DiversifiedVolTarget(mom_window=480,vol_window=480,target_gross=6.0),
 "v2 full":                      UsdNeutralMomentum(target_gross=6.0),
 "v2  -timeofday":               UsdNeutralMomentum(target_gross=6.0,time_of_day=False),
 "v2  -neutralize":              UsdNeutralMomentum(target_gross=6.0,neutralize=False),
 "v2  -blend (480 only)":        UsdNeutralMomentum(target_gross=6.0,windows=(480,)),
 "v2  -namecap (0.85)":          UsdNeutralMomentum(target_gross=6.0,name_cap=0.85),
 "v2  strip all extras":         UsdNeutralMomentum(target_gross=6.0,windows=(480,),time_of_day=False,neutralize=False,name_cap=0.85),
}
print(f"{'variant':<30}{'ret%':>8}{'maxDD%':>9}{'Sharpe':>8}{'disc':>7}{'trades':>8}   (TRAIN)")
tr={}
for tag,s in variants.items():
    m=ev(train,s); tr[tag]=m; print(row(tag,m))

v2tags=[t for t in variants if t.startswith("v2")]
best=max([t for t in v2tags if tr[t]["trade_count"]>=30 and not tr[t]["liquidated"]], key=lambda t:tr[t]["sharpe"])
print(f"\nbest v2 variant on TRAIN: {best} (Sharpe {tr[best]['sharpe']:.2f})")
print("\n--- OUT-OF-SAMPLE ---")
print(f"{'variant':<30}{'ret%':>8}{'maxDD%':>9}{'Sharpe':>8}{'disc':>7}{'trades':>8}")
print(row("baseline mom480", ev(test, variants["baseline mom480"])))
print(row(best, ev(test, variants[best])))
