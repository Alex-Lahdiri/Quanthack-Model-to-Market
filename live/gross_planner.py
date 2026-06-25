"""
Per-round gross-leverage planner -- tournament tactics for Model-to-Market.

Backtest fact (live 10 names, full month, real venue costs): Sharpe is ~gross-invariant
(~0.024 at every level) and risk-discipline stays 100 with NO liquidation up to gross 8
(margin <30%). So GROSS is a near-pure RETURN-RANK dial that also scales drawdown ~linearly:

    gross   ~return   ~maxDD     (with the per-name risk caps applied)
    1.5      +6%       -3.5%
    2        +9%       -4.6%
    3       +12%       -6.9%
    4       +12.5%     -7.9%
    5       +13%       -8.2%
    6       +14%       -8.3%

Note the curve FLATTENS above ~gross 3-4: the caps remove the concentration that used
to inflate high-gross returns, so pushing past 4 mostly just adds drawdown. The useful
range is ~2-4. Return is 70% of the score, so more gross still raises expected score, but
it raises the variance of your round result too -- and one bad round ends you in a knockout.
So: survive cheaply early (let high-variance players blow themselves up), lean up only if
you're alive and need rank, and don't bother past ~4. Heuristic -- you make the call.
"""
from __future__ import annotations
import argparse

# measured frontier (gross -> (~return %, ~maxDD %))
FRONTIER = {1.5: (6.4, -3.5), 2: (8.6, -4.6), 3: (11.9, -6.9),
            4: (12.5, -7.9), 5: (13.0, -8.2), 6: (13.9, -8.3)}


def _nearest(g):
    return min(FRONTIER, key=lambda k: abs(k - g))


def recommend(round_no, rounds_total, standing, goal, intra_dd):
    rounds_left = max(0, rounds_total - round_no)
    notes = []
    if rounds_left <= 0:
        if goal == "win":
            g = 4.0; notes.append("final round + going for the win -> gross 4 (efficient max; past 4 adds drawdown for ~1pp return)")
        else:
            g = 3.0; notes.append("final round, protecting a placing -> moderate gross")
    elif rounds_left == 1:
        g = 3.0; notes.append("late stage (one round left) -> lean up")
    else:
        g = 2.0; notes.append("early round -> survive the cut; let high-variance players self-eliminate")

    if standing == "at-risk":
        g += 1.0; notes.append("near the elimination cut -> add some gross to climb the 70%-weighted return rank")
    elif standing == "safe":
        g = min(g, 2.0); notes.append("comfortably advancing -> don't take risk you don't need")

    if intra_dd is not None and intra_dd <= -8:
        g = min(g, 2.0); notes.append(f"down {intra_dd:.0f}% this round -> ease off, let the dd-guard ladder work")

    g = max(1.5, min(5.0, float(round(g))))
    return g, notes


def main():
    ap = argparse.ArgumentParser(description="Per-round gross planner (tournament tactics)")
    ap.add_argument("--round", type=int, required=True, help="current round number (1-based)")
    ap.add_argument("--rounds-total", type=int, default=4, help="total rounds in the competition")
    ap.add_argument("--standing", choices=["safe", "middle", "at-risk", "unknown"], default="unknown",
                    help="your position vs the elimination cut")
    ap.add_argument("--goal", choices=["survive", "win"], default=None,
                    help="default: survive in early rounds, win in the final")
    ap.add_argument("--equity", type=float, default=None, help="current equity (optional)")
    ap.add_argument("--round-start-equity", type=float, default=None, help="equity at the start of this round (optional)")
    args = ap.parse_args()

    goal = args.goal or ("win" if args.round >= args.rounds_total else "survive")
    intra_dd = None
    if args.equity and args.round_start_equity:
        intra_dd = (args.equity / args.round_start_equity - 1) * 100

    g, notes = recommend(args.round, args.rounds_total, args.standing, goal, intra_dd)
    ret, dd = FRONTIER[_nearest(g)]
    print(f"\n=== GROSS PLAN -- round {args.round}/{args.rounds_total}  (goal: {goal}, standing: {args.standing}) ===")
    if intra_dd is not None:
        print(f"  this round: equity {args.equity:,.0f}  ({intra_dd:+.1f}% vs round start)")
    print(f"\n  >>> recommended gross: {g:g}x")
    print(f"      backtest expectation ~{g:g}x:  return ~{ret:+.0f}%   maxDD ~{dd:.0f}%   "
          f"Sharpe ~0.024 (flat)   discipline 100")
    print("  reasoning:")
    for n in notes:
        print(f"    - {n}")
    print(f"\n  run it:\n    python live\\live_runner.py --panel panel_live.parquet --strategy mv --gross {g:g} "
          "--emit book.json \\\n           --dd-guard --peak-state peak.json --risk-gate "
          "--headlines live\\headlines.txt --logfire")
    print()


if __name__ == "__main__":
    main()
