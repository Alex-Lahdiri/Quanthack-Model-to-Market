"""
Risk monitor (read-only): flags proximity to the competition penalty tiers + red lines,
and reports drawdown + the de-risk level. Run every few minutes. Optional Logfire alert.
status JSON: {equity, positions:{sym:notional}, peak_equity?: float, round_start_equity?: float}
"""
from __future__ import annotations
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

def assess(positions: dict, equity: float, peak_equity: float = None) -> dict:
    gross = sum(abs(v) for v in positions.values())
    net = sum(positions.values())
    gl = gross / equity if equity else 0.0
    nl = abs(net) / equity if equity else 0.0
    margin_usage = gl / C.MAX_LEVERAGE
    name_share = (max(abs(v) for v in positions.values()) / gross) if gross else 0.0
    margin_level = equity / (gross / C.MAX_LEVERAGE) if gross else float("inf")
    warns = []
    if margin_usage >= C.MARGIN_PENALTY_TIERS[0]: warns.append(f"MARGIN {margin_usage:.0%} >= {C.MARGIN_PENALTY_TIERS[0]:.0%} penalty tier")
    elif margin_usage >= C.SAFE_MAX_MARGIN_USAGE: warns.append(f"margin {margin_usage:.0%} approaching penalty tier")
    if gl >= C.LEVERAGE_PENALTY_TIERS[0]: warns.append(f"LEVERAGE {gl:.1f}x >= {C.LEVERAGE_PENALTY_TIERS[0]}x penalty tier")
    if name_share >= C.CONCENTRATION_PENALTY: warns.append(f"CONCENTRATION {name_share:.0%} single-name >= {C.CONCENTRATION_PENALTY:.0%}")
    if margin_level < 1.5: warns.append(f"MARGIN LEVEL {margin_level:.2f} -- liquidation risk (red line)")
    out = {"gross_leverage": round(gl,2), "net_leverage": round(nl,2), "margin_usage": round(margin_usage,3),
           "max_name_share": round(name_share,3), "margin_level": round(margin_level,2)}
    if peak_equity:
        try:
            from derisk import derisk
            m, dd, lvl = derisk(equity, peak_equity)
            out.update({"drawdown": round(dd,4), "derisk_level": lvl, "derisk_mult": m})
            if lvl != "normal": warns.append(f"DRAWDOWN {dd:.1%} -> de-risk '{lvl}' (gross x{m:.2f})")
        except Exception:
            pass
    out["warnings"] = warns
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", required=True)
    ap.add_argument("--logfire", action="store_true")
    args = ap.parse_args()
    s = json.load(open(args.status))
    r = assess(s["positions"], s["equity"], s.get("peak_equity"))
    print(json.dumps(r, indent=2))
    if r["warnings"]:
        print("\n".join("WARN " + w for w in r["warnings"]))
    if args.logfire:
        try:
            import logfire; logfire.configure()
            (logfire.warn if r["warnings"] else logfire.info)("risk check", **{k:v for k,v in r.items() if k!='warnings'}, warnings=r["warnings"])
        except Exception as e:
            print(f"[logfire unavailable: {e}]")

if __name__ == "__main__":
    main()
