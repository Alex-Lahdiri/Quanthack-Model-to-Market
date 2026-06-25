"""
Walk-forward evaluation: tune on the first part of the sample, then report
OUT-OF-SAMPLE results on the held-out tail. Selection uses train data only, so
the OOS number is an honest estimate of what the config would have done live.
"""
from __future__ import annotations

import argparse
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

import pandas as pd

import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies.diversified_vol_target import DiversifiedVolTarget


def run(panel, mode, mw, gross, rb):
    s = DiversifiedVolTarget(mode=mode, mom_window=mw, vol_window=mw, target_gross=gross)
    r = run_backtest(panel, s, risk=RiskEngine(), rebalance_every=rb)
    return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--split", type=float, default=0.6)
    args = ap.parse_args()

    panel = pd.read_parquet(args.panel).set_index("ts").sort_index()
    k = int(len(panel) * args.split)
    train, test = panel.iloc[:k], panel.iloc[k:]
    print(f"panel {panel.shape} | train {train.shape[0]} bars -> test {test.shape[0]} bars")
    print(f"train {train.index[0]}..{train.index[-1]} | test {test.index[0]}..{test.index[-1]}\n")

    grid = [(mode, mw, g, 15)
            for mode in ("momentum", "reversion")
            for mw in (60, 120, 240, 480)
            for g in (6,)]

    print(f"{'mode':<10}{'win':>5}{'gross':>6} | {'TRAIN ret%':>11}{'dd%':>8}{'Sharpe':>8}{'trades':>8}")
    rows = []
    for mode, mw, g, rb in grid:
        m = run(train, mode, mw, g, rb)
        rows.append((mode, mw, g, rb, m))
        print(f"{mode:<10}{mw:>5}{g:>6} | {m['total_return']*100:>11.2f}{m['max_drawdown']*100:>8.2f}"
              f"{m['sharpe']:>8.2f}{m['trade_count']:>8}")

    # select best by TRAIN Sharpe among eligible (>=30 trades, no liquidation)
    elig = [r for r in rows if r[4]["trade_count"] >= 30 and not r[4]["liquidated"]]
    best = max(elig, key=lambda r: r[4]["sharpe"])
    mode, mw, g, rb, mtr = best
    print(f"\n>> selected on TRAIN: mode={mode} window={mw} gross={g} rebalance={rb} "
          f"(train Sharpe {mtr['sharpe']:.2f})")

    mte = run(test, mode, mw, g, rb)
    peers = M.make_synthetic_peers(300, seed=1)
    print("\n--- OUT-OF-SAMPLE (held-out tail) ---")
    M.tearsheet(mte, M.simulate_final_score(mte, peers))


if __name__ == "__main__":
    main()
