"""
Deterministic drawdown DE-RISK ladder (survival control - not alpha).

As intra-round drawdown from the equity peak deepens, scale gross exposure down.
This protects the competition's Drawdown rank (15%), smooths the equity curve (Sharpe),
and - most importantly in a knockout - keeps you alive (away from forced liquidation)
while over-levered competitors eliminate themselves. Peak is tracked in a small state
file so it persists across runner invocations within a round (reset the file each round).
"""
from __future__ import annotations
import json, os

# (max drawdown-from-peak, gross multiplier, label). First row whose threshold
# is >= current drawdown wins. Beyond the last row -> lockdown.
DEFAULT_LADDER = [
    (0.03, 1.00, "normal"),
    (0.05, 0.70, "caution"),
    (0.08, 0.40, "defensive"),
    (0.12, 0.20, "survival"),
]
LOCKDOWN = (0.10, "lockdown")


def derisk(equity: float, peak: float, ladder=DEFAULT_LADDER):
    """Return (multiplier<=1.0, drawdown, level) given current and peak equity."""
    dd = max(0.0, 1.0 - equity / peak) if peak and peak > 0 else 0.0
    for thresh, mult, label in ladder:
        if dd <= thresh:
            return mult, dd, label
    return LOCKDOWN[0], dd, LOCKDOWN[1]


def update_peak(state_path: str, equity: float) -> float:
    """Read prior peak, update with current equity, persist, return the peak."""
    peak = equity
    try:
        peak = max(float(json.load(open(state_path)).get("peak", equity)), equity)
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
        json.dump({"peak": peak}, open(state_path, "w"))
    except Exception:
        pass
    return peak


def reset_peak(state_path: str, equity: float):
    """Call at each round's inception (Risk Discipline + drawdown reset per round)."""
    json.dump({"peak": equity}, open(state_path, "w"))


if __name__ == "__main__":
    # quick self-test of the ladder
    for eq in (1_000_000, 970_000, 950_000, 920_000, 880_000):
        m, dd, lvl = derisk(eq, 1_000_000)
        print(f"equity {eq:>10,} | dd {dd*100:5.1f}% -> gross x{m:.2f} ({lvl})")
