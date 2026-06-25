"""One-command reproducer for the scoring-tuned recommended config.
Usage: python run_recommended.py [--panel results/panel_full_month.parquet] [--gross 4]"""
import argparse, sys, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
import pandas as pd
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD",
        "EURGBP","EURCHF","XAUUSD","XAGUSD"]  # 10 live names (broker has no NZDUSD/EURJPY)
ap = argparse.ArgumentParser()
ap.add_argument("--panel", default="results/panel_full_month.parquet")
ap.add_argument("--gross", type=float, default=4.0)
ap.add_argument("--cost-bps", type=float, default=0.7)
args = ap.parse_args()

panel = pd.read_parquet(args.panel).set_index("ts").sort_index()
panel = panel[[c for c in UNIV if c in panel.columns]]
strat = DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480,
                             smooth_halflife=48, target_gross=args.gross)
res = run_backtest(panel, strat, risk=RiskEngine(), rebalance_every=60, cost_bps=args.cost_bps)
m = M.compute_metrics(res.equity, res.telemetry, res.trade_count, res.liquidated)
M.tearsheet(m, M.simulate_final_score(m, M.make_synthetic_peers(300, seed=1)))
