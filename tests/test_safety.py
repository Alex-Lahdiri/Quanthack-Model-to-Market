"""
Safety tests -- PROVE the risk/governor/profit-lock claims are real, not just asserted.

    python -m pytest tests/ -q          # if pytest is installed
    python tests/test_safety.py         # standalone runner (no pytest needed)
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "live"))
import pandas as pd
import config as C

NAMES = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","EURGBP","EURCHF","XAUUSD","XAGUSD"]

# ---------- Autopilot governor: AI proposals are clamped to safe bounds ----------
def test_governor_clamps_reckless_gross():
    import autopilot as A
    from autopilot import PlanProposal
    strong = {"ic_8h_4h": 0.05, "t_8h_4h": 3.0}
    g = A.govern(PlanProposal(strategy="reckless", gross=9, cadence_hours=3, confidence=1), strong, 0.0, False)
    assert g["gross"] <= 3.0, g
    assert g["strategy"] == "iv", g           # invalid strategy -> safe default
    assert g["cadence_hours"] in (1, 2, 4), g

def test_governor_forces_defensive_in_no_edge():
    import autopilot as A
    from autopilot import PlanProposal
    noedge = {"ic_8h_4h": -0.02, "t_8h_4h": -0.3}
    g = A.govern(PlanProposal(strategy="iv", gross=2.5, cadence_hours=4, confidence=1), noedge, 0.0, False)
    assert g["gross"] <= 1.0, g               # no edge -> forced low regardless of AI ask

def test_governor_drawdown_overrides_strong_edge():
    import autopilot as A
    from autopilot import PlanProposal
    strong = {"ic_8h_4h": 0.05, "t_8h_4h": 3.0}
    g = A.govern(PlanProposal(strategy="iv", gross=3, cadence_hours=4, confidence=1), strong, -0.09, False)
    assert g["gross"] <= 1.0, g               # deep drawdown wins even with a strong edge

# ---------- Profit-lock ratchet ----------
def test_profit_lock_inactive_when_flat():
    import profit_lock as P
    mult, info = P.ratchet(1_000_000, 1_000_000, 1_000_000)
    assert mult == 1.0 and not info["armed"]

def test_profit_lock_tiers_fire():
    import profit_lock as P
    a, pk = 1_000_000, 1_010_000             # +1% peak gain -> armed
    assert P.ratchet(1_009_000, a, pk)[0] == 1.0   # gave back 10% -> no cut
    assert P.ratchet(1_005_000, a, pk)[0] == 0.4   # gave back 50% -> x0.4
    assert P.ratchet(1_002_500, a, pk)[0] == 0.2   # gave back 75% -> x0.2

# ---------- Risk engine: output respects caps regardless of input ----------
def test_risk_engine_enforces_per_name_cap():
    from risk_engine import RiskEngine
    w = pd.Series([5,1,1,1,1,1,1,1,1,1], index=NAMES, dtype=float)  # over-concentrated, all long
    out = RiskEngine().apply(w)
    gross = out.abs().sum()
    assert gross > 0
    top_share = out.abs().max() / gross
    assert top_share <= C.SAFE_MAX_NAME_SHARE + 1e-6, f"top name {top_share:.3f} > cap {C.SAFE_MAX_NAME_SHARE}"

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
