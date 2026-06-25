"""
Pre-trade safety gate (circuit breaker). Run AFTER the runner builds book.json and BEFORE
the bridge sends. Verifies the price feed is fresh and the book is sane; exits non-zero to
HALT the cycle (no orders) if anything looks wrong -- so a stale feed, a crashed loop, or a
garbage book can never reach the market on an unattended overnight run.

  python live/preflight.py --panel panel_live.parquet --book book.json
exit 0 = cleared to trade ; exit 1 = HALT (reasons printed).
"""
from __future__ import annotations
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as C


def _finite(x):
    try:
        v = float(x)
        return v == v and abs(v) != float("inf")
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="Pre-trade safety gate (circuit breaker)")
    ap.add_argument("--panel", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--max-staleness-min", type=float, default=15.0)
    ap.add_argument("--min-names", type=int, default=5)
    ap.add_argument("--min-bars", type=int, default=480)
    args = ap.parse_args()
    fails = []

    # 1) FEED FRESHNESS -- the panel file must have been refreshed recently + be warm enough
    if not os.path.exists(args.panel):
        fails.append(f"panel missing: {args.panel}")
    else:
        age_min = (time.time() - os.path.getmtime(args.panel)) / 60.0
        if age_min > args.max_staleness_min:
            fails.append(f"stale feed: panel_live is {age_min:.0f} min old (> {args.max_staleness_min:.0f}) -- did mt5_feed run?")
        try:
            import pandas as pd
            n = len(pd.read_parquet(args.panel))
            if n < args.min_bars:
                fails.append(f"thin panel: {n} bars (< {args.min_bars}); momentum lookback not warm")
        except Exception as e:
            fails.append(f"panel unreadable: {e}")

    # 2) BOOK SANITY -- the things the bridge doesn't already check
    try:
        book = json.load(open(args.book))
        tgt = book.get("targets", {})
        eq = float(book.get("equity", C.ACCOUNT_START))
        gross = float(book.get("gross_leverage", 0))
        if len(tgt) < args.min_names:
            fails.append(f"too few names: {len(tgt)} (< {args.min_names})")
        if not (0.3 <= gross <= C.EFFECTIVE_GROSS_CAP * 1.25):
            fails.append(f"gross out of range: {gross}x (expect 0.3..{C.EFFECTIVE_GROSS_CAP * 1.25:.1f})")
        bad = [s for s, t in tgt.items() if not _finite(t.get("notional")) or not _finite(t.get("units"))]
        if bad:
            fails.append(f"non-finite notionals: {bad[:5]}")
        mx = max((abs(float(t.get("notional", 0))) for t in tgt.values()), default=0.0)
        if mx > eq * 1.0 + 1:   # no single name should exceed ~100% of equity (per-name cap is 75%)
            fails.append(f"single-name notional too large: {mx:,.0f} (> equity {eq:,.0f})")
    except Exception as e:
        fails.append(f"book unreadable: {e}")

    if fails:
        print("PREFLIGHT: *** HALT *** -- not trading this cycle:")
        for f in fails:
            print(f"   - {f}")
        sys.exit(1)
    print("PREFLIGHT: OK -- feed fresh, book sane. Cleared to trade.")
    sys.exit(0)


if __name__ == "__main__":
    main()
