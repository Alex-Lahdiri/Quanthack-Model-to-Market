"""
Daily market-regime briefing (NVIDIA Nemotron reasoning model, advisory).

Computes simple regime features from panel_live.parquet (cross-sectional momentum dispersion,
recent realized vol, recent average move) and asks a LARGER Nemotron reasoning model whether
the regime looks favorable / neutral / unfavorable for the 8-hour cross-sectional momentum
strategy, with a short rationale. ADVISORY ONLY -- it never sizes trades. Falls back to a
deterministic read if no NVIDIA key. Run once a day.

  python live/regime_brief.py --panel panel_live.parquet --emit regime.json
"""
from __future__ import annotations
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd

# a bigger Nemotron reasoning model (in the contest catalog) for the daily read
NEMOTRON_REASONING = os.environ.get("NEMOTRON_REASONING", "nvidia/llama-3.3-nemotron-super-49b-v1.5")


def features(panel):
    p = panel.dropna(how="all")
    logret = np.log(p).diff()
    mom = p.pct_change(480).iloc[-1] if len(p) > 480 else p.pct_change().iloc[-1]
    disp = float(mom.std())
    vol = float(logret.iloc[-1440:].std().mean()) if len(logret) > 200 else float(logret.std().mean())
    move = float(p.iloc[-1].div(p.iloc[max(0, len(p) - 1440)]).sub(1).abs().mean()) if len(p) > 200 else 0.0
    return {"momentum_dispersion": round(disp, 5), "avg_realized_vol_1m": round(vol, 6),
            "avg_abs_1d_move": round(move, 4), "bars": int(len(p))}


def main():
    ap = argparse.ArgumentParser(description="Daily Nemotron regime briefing (advisory)")
    ap.add_argument("--panel", required=True)
    ap.add_argument("--emit", default="")
    args = ap.parse_args()
    panel = pd.read_parquet(args.panel).set_index("ts").sort_index()
    f = features(panel)
    prompt = ("You are a quant strategist. Given these summary stats for a 10-instrument FX+metals "
              "universe over the recent window, assess whether the regime looks FAVORABLE, NEUTRAL, or "
              "UNFAVORABLE for an 8-hour CROSS-SECTIONAL MOMENTUM strategy, in 70 words or fewer with one "
              "reason. Do not suggest position sizes.\n\n" + json.dumps(f))

    out = None
    try:
        import ai_gateway
        if os.environ.get("NVIDIA_API_KEY"):
            out = ai_gateway.chat(NEMOTRON_REASONING, prompt, provider="nvidia", max_tokens=600)
    except Exception:
        out = None
    if not out:
        label = "UNFAVORABLE" if f["momentum_dispersion"] < 0.004 else "NEUTRAL"
        out = (f"[deterministic] regime looks {label}: momentum dispersion {f['momentum_dispersion']} and "
               f"avg 1m vol {f['avg_realized_vol_1m']}. Thin dispersion = weak cross-sectional signal -> keep gross conservative.")

    print("\n===== NVIDIA NEMOTRON -- DAILY REGIME BRIEFING =====")
    print("  features:", f)
    print("  " + out.strip().replace("\n", "\n  "))
    print("====================================================\n")
    if args.emit:
        json.dump({"features": f, "briefing": out}, open(args.emit, "w"), indent=2)


if __name__ == "__main__":
    main()
