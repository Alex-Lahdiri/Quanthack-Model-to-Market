"""
scalp_of.py -- ORDER-FLOW-ENHANCED scalper. Same fast mean-reversion as scalp.py, but it only
ENTERS when the price z-score AND the live order-book imbalance AGREE (contrarian confirmation:
a bid-heavy book precedes a drop, so we fade up-spikes only when the book confirms). Lets you test
whether combining price + order flow sharpens the scalp. Dry-run by default; tiny size + loss-limit.

  python live/scalp_of.py --symbol BTCUSD --minutes 20                                   # DRY probe
  python live/scalp_of.py --symbol BTCUSD --live --i-confirm-paper --size 0.05 --minutes 20 --max-loss-bps 25
"""
from __future__ import annotations
import argparse, os, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scalp import decide, WINDOW, MAX_HOLD, STOP_BPS

def main():
    ap = argparse.ArgumentParser(description="Order-flow-enhanced mean-reversion scalper (dry default)")
    ap.add_argument("--symbol", default="BTCUSD")
    ap.add_argument("--size", type=float, default=0.05)
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--imb-thresh", type=float, default=0.10, help="book imbalance needed to confirm the fade")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--i-confirm-paper", action="store_true")
    ap.add_argument("--max-loss-bps", type=float, default=25.0, help="session circuit-breaker")
    args = ap.parse_args()
    if args.live and not args.i_confirm_paper:
        sys.exit("Refusing to trade without --i-confirm-paper (paper/contest account only).")
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
    acct = mt5.account_info()
    if acct and getattr(acct, "trade_mode", None) == 0 and args.live:
        mt5.shutdown(); sys.exit("Account looks REAL (trade_mode=0). Aborting -- paper only.")
    has_book = bool(mt5.market_book_add(sym))
    if not has_book:
        print("  no DOM for this symbol -> order-flow filter disabled (price-only).")

    def imbalance():
        if not has_book:
            return 0.0
        book = mt5.market_book_get(sym)
        if not book:
            return 0.0
        bv = sum(b.volume for b in book if b.type == mt5.BOOK_TYPE_BUY)
        av = sum(b.volume for b in book if b.type == mt5.BOOK_TYPE_SELL)
        return (bv - av) / (bv + av) if (bv + av) > 0 else 0.0

    def order(side_):
        t = mt5.symbol_info_tick(sym); px = t.ask if side_ == 1 else t.bid
        if not args.live:
            return px
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": round(args.size, 2),
               "type": mt5.ORDER_TYPE_BUY if side_ == 1 else mt5.ORDER_TYPE_SELL, "price": px,
               "deviation": 20, "comment": "quanthack-scalp-of", "type_filling": mt5.ORDER_FILLING_IOC}
        r = mt5.order_send(req); print(f"      order retcode {getattr(r,'retcode',None)}")
        return px

    prices = collections.deque(maxlen=WINDOW)
    side = 0; entry = 0.0; entry_t = 0.0; total = 0.0; trades = 0; skipped = 0
    end = time.time() + args.minutes * 60
    print(f"scalp_of {sym} ({'LIVE' if args.live else 'DRY'}) size {args.size} imb_thresh {args.imb_thresh} maxLoss {args.max_loss_bps}bps")
    while time.time() < end:
        t = mt5.symbol_info_tick(sym)
        if not t:
            time.sleep(args.interval); continue
        bid, ask = t.bid, t.ask; mid = (bid + ask) / 2.0
        prices.append(mid); imb = imbalance()
        pz, z = decide(list(prices), side)
        now = time.time()
        if side == 0 and pz in ("BUY", "SELL"):
            of = "SELL" if imb >= args.imb_thresh else ("BUY" if imb <= -args.imb_thresh else "HOLD")
            if (of == pz) or (not has_book):            # price + flow agree (or no book -> price-only)
                side = 1 if pz == "BUY" else -1
                entry = order(side); entry_t = now
                print(f"  {pz:<4} @ {entry:.2f}  z {z:+.2f}  imb {imb:+.2f}  -> price+flow AGREE")
            else:
                skipped += 1                              # the lesson: flow didn't confirm -> skip
        elif side != 0:
            exit_px = bid if side == 1 else ask
            pnl = (exit_px - entry) * side / entry * 1e4
            if pz == "EXIT" or (now - entry_t) > MAX_HOLD or pnl <= -STOP_BPS:
                if args.live:
                    order(-side)
                total += pnl; trades += 1
                print(f"  EXIT @ {exit_px:.2f}  pnl {pnl:+.2f}bps  cum {total:+.1f}bps / {trades}")
                side = 0
                if total <= -args.max_loss_bps:
                    print(f"  *** session loss-limit -{args.max_loss_bps:.0f}bps hit -> stopping ***"); break
        time.sleep(args.interval)
    if has_book:
        mt5.market_book_release(sym)
    mt5.shutdown()
    print(f"\n=== {trades} round-trips | net {total:+.1f}bps (NET OF SPREAD) | {skipped} entries SKIPPED by the order-flow filter ===")

if __name__ == "__main__":
    main()
