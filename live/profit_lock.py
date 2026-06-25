"""
profit_lock.py -- profit-protecting RATCHET (not a stop-loss).

Once the session is up >= ACTIVATE, it tracks high-water equity and de-risks as you give
back a chunk of that peak gain -- locking in profit WITHOUT a hard stop's whipsaw: it only
acts when you're AHEAD, and it scales gross down (never flattens). Built for a competition
where small give-backs cost ranks, and a choppy/mean-reverting tape where tight stops sell
the bottom. Use as another <=1.0 overlay (combine via min with the drawdown ladder).

  anchor, peak = update_state(path, equity)
  mult, info   = ratchet(equity, anchor, peak)   # mult in (0,1], 1.0 = inactive
  reset(path, equity)                            # re-anchor at a round/session start
"""
from __future__ import annotations
import json, os

ACTIVATE = 0.005                                  # arm only once session gain >= 0.5% of anchor
TIERS = [(0.25, 0.7), (0.50, 0.4), (0.75, 0.2)]   # give-back fraction of peak gain -> gross mult

def update_state(path, equity):
    st = {}
    if path and os.path.exists(path):
        try: st = json.load(open(path))
        except Exception: st = {}
    anchor = float(st.get("anchor", equity))
    peak = max(float(st.get("peak", equity)), float(equity))
    if path:
        try: json.dump({"anchor": anchor, "peak": peak}, open(path, "w"))
        except Exception: pass
    return anchor, peak

def ratchet(equity, anchor, peak):
    peak_gain = peak - anchor
    if peak_gain <= ACTIVATE * anchor:
        return 1.0, {"armed": False, "peak_gain_pct": round(peak_gain / anchor * 100, 3)}
    giveback = (peak - equity) / peak_gain
    mult = 1.0
    for thr, m in TIERS:
        if giveback >= thr:
            mult = m
    return mult, {"armed": True, "peak_gain_pct": round(peak_gain / anchor * 100, 3),
                  "giveback_pct": round(giveback * 100, 1), "mult": mult}

def reset(path, equity):
    if path:
        try: json.dump({"anchor": float(equity), "peak": float(equity)}, open(path, "w"))
        except Exception: pass
