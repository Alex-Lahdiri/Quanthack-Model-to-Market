"""
orderflow_probe.py -- READ-ONLY order-flow probe. Subscribes to the live MT5 Depth-of-Market
(DOM) for one instrument, computes top-of-book IMBALANCE + the MICROPRICE, and measures whether
imbalance predicts the next mid move (a live information coefficient). Sends NO orders.

Teaches order flow AND verifies whether this venue's book is real/informative or synthetic.
(Our archive research found the depth was mostly synthetic with ~0 IC -- this checks the LIVE feed.)

  python live/orderflow_probe.py --symbol BTCUSD --minutes 5
"""
from __future__ import annotations
import argparse, sys, time
import numpy as np

def main():
    ap = argparse.ArgumentParser(description="Read-only live order-flow probe (DOM imbalance -> predictive IC)")
    ap.add_argument("--symbol", default="BTCUSD")
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--horizon", type=int, default=3, help="samples ahead to measure the next move")
    args = ap.parse_args()

    try:
        import MetaTrader5 as mt5
    except Exception:
        sys.exit("MetaTrader5 not found (run on the Windows box).")
    if not mt5.initialize():
        sys.exit(f"MT5 init failed: {mt5.last_error()}")
    sym = args.symbol
    if mt5.symbol_info(sym) is None:
        mt5.shutdown(); sys.exit(f"{sym} not found")
    mt5.symbol_select(sym, True)
    if not mt5.market_book_add(sym):
        print(f"  market_book_add failed -> this venue provides NO order book (DOM) for {sym}.")
        print("  => order flow isn't possible here; the feed is top-of-book only. (Matches the archive finding.)")
        mt5.shutdown(); return

    print(f"order-flow probe {sym} (READ-ONLY, no orders) for {args.minutes} min ...")
    imb, mids = [], []
    end = time.time() + args.minutes * 60
    while time.time() < end:
        book = mt5.market_book_get(sym)
        tick = mt5.symbol_info_tick(sym)
        if book and tick:
            bids = [b.volume for b in book if b.type == mt5.BOOK_TYPE_BUY]
            asks = [b.volume for b in book if b.type == mt5.BOOK_TYPE_SELL]
            bv, av = sum(bids[:5]), sum(asks[:5])
            if bv + av > 0:
                imb.append((bv - av) / (bv + av))
                mids.append((tick.bid + tick.ask) / 2.0)
        time.sleep(args.interval)
    mt5.market_book_release(sym); mt5.shutdown()

    n = len(imb)
    if n < args.horizon + 6:
        print(f"  only {n} samples -- not enough to judge."); return
    im = np.array(imb); md = np.array(mids)
    fwd = md[args.horizon:] - md[:-args.horizon]
    x = im[:-args.horizon]
    ic = float(np.corrcoef(x, fwd)[0, 1]) if (x.std() > 0 and fwd.std() > 0) else float("nan")
    print(f"\n=== {n} samples ===")
    print(f"  mean |imbalance| = {np.mean(np.abs(im)):.3f}   (~0 => synthetic/symmetric book | >0.1 => real asymmetry)")
    print(f"  imbalance -> next-move IC ({args.horizon}-step) = {ic:+.3f}   (>+0.05 predictive | ~0 noise | <0 contrarian)")
    print("  READ: a real, tradeable order-flow edge needs |imbalance|>0 AND a positive IC.")
    print("        If both are ~0, the book is synthetic and order flow is a dead end here.")

if __name__ == "__main__":
    main()
