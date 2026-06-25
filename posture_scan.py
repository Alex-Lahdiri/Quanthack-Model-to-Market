"""Is ANY simple posture positive over the full month? Low gross, 12-name univ."""
import sys, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
        "EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel = pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]

def ev(strat, rb=15):
    r = run_backtest(panel, strat, risk=RiskEngine(), rebalance_every=rb)
    return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)

configs = {
 "momentum w480 rb15":   (DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480, target_gross=2), 15),
 "momentum w120 rb15":   (DiversifiedVolTarget(mode="momentum", mom_window=120, vol_window=120, target_gross=2), 15),
 "momentum w960 rb15":   (DiversifiedVolTarget(mode="momentum", mom_window=960, vol_window=960, target_gross=2), 15),
 "reversion w480 rb15":  (DiversifiedVolTarget(mode="reversion", mom_window=480, vol_window=480, target_gross=2), 15),
 "reversion w120 rb15":  (DiversifiedVolTarget(mode="reversion", mom_window=120, vol_window=120, target_gross=2), 15),
 "reversion w30 rb15":   (DiversifiedVolTarget(mode="reversion", mom_window=30, vol_window=30, target_gross=2), 15),
 "momentum w480 rb60":   (DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480, target_gross=2), 60),
 "momentum w480 smooth48":(DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480, target_gross=2, smooth_halflife=48), 15),
}
print(f"{'config':<26}{'ret%':>8}{'maxDD%':>9}{'Sharpe':>8}{'trades':>8}")
for tag,(s,rb) in configs.items():
    m = ev(s, rb)
    print(f"{tag:<26}{m['total_return']*100:>8.2f}{m['max_drawdown']*100:>9.2f}{m['sharpe']:>8.2f}{m['trade_count']:>8}")
