"""
CLI entrypoint: load data -> run strategy -> score it -> save a tearsheet.

Examples
--------
# 0) validate everything on synthetic data (auto-generated if missing)
python run_backtest.py

# 1) inspect the real file's schema FIRST
python run_backtest.py --data /path/to/week1.parquet --inspect

# 2) backtest on the real file
python run_backtest.py --data /path/to/week1.parquet --freq 5m --rebalance 3 --target-gross 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C
import data_loader as dl
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget


def _ensure_synthetic(path: str) -> str:
    if not os.path.exists(path):
        print("synthetic data not found -- generating it...")
        import make_synthetic_data as msd
        msd.main()
    return path


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_data = os.path.join(here, "data", "synthetic_quotes.parquet")

    ap = argparse.ArgumentParser(description="Quanthack scoring-aware backtester")
    ap.add_argument("--data", default=default_data, help="path to quote/bar Parquet")
    ap.add_argument("--inspect", action="store_true", help="print schema + exit")
    ap.add_argument("--freq", default="1m", help="bar size, e.g. 1m 5m 15m 1h")
    ap.add_argument("--rebalance", type=int, default=15, help="rebalance every N bars")
    ap.add_argument("--target-gross", type=float, default=8.0, help="target gross leverage")
    ap.add_argument("--mom-window", type=int, default=480)
    ap.add_argument("--vol-window", type=int, default=480)
    ap.add_argument("--cost-bps", type=float, default=C.DEFAULT_COST_BPS)
    ap.add_argument("--out", default=os.path.join(here, "results"))
    args = ap.parse_args()

    if args.data == default_data:
        _ensure_synthetic(default_data)

    if args.inspect:
        dl.inspect_parquet(args.data)
        return

    print(f"loading {args.data} ...")
    quotes = dl.load_quotes(args.data)
    bars = dl.to_bars(quotes, freq=args.freq)
    panel = dl.build_price_panel(bars, field="close")
    print(f"panel: {panel.shape[0]} bars x {panel.shape[1]} instruments "
          f"({panel.index[0]} -> {panel.index[-1]})")

    strat = DiversifiedVolTarget(
        mom_window=args.mom_window,
        vol_window=args.vol_window,
        target_gross=args.target_gross,
    )
    result = run_backtest(
        panel, strat, risk=RiskEngine(),
        rebalance_every=args.rebalance, cost_bps=args.cost_bps,
    )

    m = M.compute_metrics(result.equity, result.telemetry,
                          result.trade_count, result.liquidated)
    peers = M.make_synthetic_peers(n=300, seed=1)
    score = M.simulate_final_score(m, peers)
    M.tearsheet(m, score)

    os.makedirs(args.out, exist_ok=True)
    result.equity.to_csv(os.path.join(args.out, "equity_curve.csv"))
    result.telemetry.to_csv(os.path.join(args.out, "telemetry.csv"))
    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump({"metrics": m, "score": score, "params": result.params}, f, indent=2)
    _save_plot(result.equity, args.out)
    print(f"saved equity_curve.csv, telemetry.csv, metrics.json to {args.out}")


def _save_plot(equity: pd.Series, out: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity.index, equity.values, lw=1.2)
    ax.set_title("Equity curve")
    ax.set_ylabel("Equity ($)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "equity_curve.png"), dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
