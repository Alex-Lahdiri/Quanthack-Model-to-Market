"""
eval_autopilot.py -- evaluate the AI desk's REGIME CALLS against what the market actually did.
Pydantic-validated cases; scores whether each block's regime classification persisted into the
next block. Shows the desk's reads are measured, not assumed. (Pydantic Evals-style.)

  python live/eval_autopilot.py --panel ../panel_live.parquet --days 5 --blocks 8
"""
from __future__ import annotations
import argparse, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from pydantic import BaseModel, Field

FX10 = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","EURGBP","EURCHF","XAUUSD","XAGUSD"]

class EvalCase(BaseModel):
    block: int
    ic: float = Field(description="momentum IC measured this block")
    predicted: str
    next_ic: float
    correct: bool

def classify(ic):
    return "trending" if ic > 0.01 else ("reverting" if ic < -0.005 else "choppy")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=os.path.join(ROOT, "panel_live.parquet"))
    ap.add_argument("--days", type=float, default=5.0); ap.add_argument("--blocks", type=int, default=8)
    a = ap.parse_args()
    p = pd.read_parquet(a.panel).set_index("ts").sort_index()
    p = p[[c for c in FX10 if c in p.columns]].astype(float)
    p = p[p.index >= p.index.max() - pd.Timedelta(days=a.days)]
    mom = p.pct_change(480); momd = mom.sub(mom.mean(axis=1), axis=0)
    fwd = p.pct_change(60).shift(-60)
    ic = momd.corrwith(fwd, axis=1).dropna()
    chunks = np.array_split(ic.values, a.blocks)
    blk_ic = [float(np.nanmean(c)) for c in chunks if len(c)]
    cases = []
    for k in range(len(blk_ic) - 1):
        pred = classify(blk_ic[k]); nxt = blk_ic[k+1]
        correct = ((pred == "trending" and nxt > 0.005) or (pred == "reverting" and nxt < -0.005) or (pred == "choppy" and abs(nxt) <= 0.01))
        cases.append(EvalCase(block=k, ic=round(blk_ic[k], 4), predicted=pred, next_ic=round(nxt, 4), correct=correct))
    acc = float(np.mean([c.correct for c in cases])) if cases else float("nan")
    print(f"=== AUTOPILOT REGIME-CALL EVAL ({len(cases)} cases over {a.days}d) ===")
    for c in cases:
        print(f"  block {c.block}: IC {c.ic:+.4f} -> '{c.predicted}'  | next IC {c.next_ic:+.4f}  | {'HIT' if c.correct else 'miss'}")
    print(f"\n  regime-persistence accuracy: {acc*100:.0f}%   (validates whether the desk's reads hold up)")

if __name__ == "__main__":
    main()
