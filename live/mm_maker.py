"""
EXPERIMENTAL market-making prototype (advisory / dry-run by default).

Posts two-sided LIMIT quotes around mid on a few tight-spread majors -- a BUY limit just below
mid and a SELL limit just above -- to capture the spread regardless of direction. Keeps an
inventory cap (only quotes the side that doesn't push inventory past the cap). Run it on a short
schedule (e.g. every minute): each run cancels its stale quotes and re-posts fresh ones.

WHY this might suit a chop: you earn the bid/ask spread from participants who cross it, with no
directional view -- exactly what a sideways market offers.

HONEST LIMITS -- read before using:
  * It cannot be backtested here (we have no fill/queue data for the venue's internal matching).
  * Adverse selection is real: you tend to get filled on the side about to move against you.
  * It is a SEPARATE engine from the momentum book -- don't run both on the same instruments.
  * So: test it LIVE-SMALL between rounds (tiny size, watch inventory + P&L), do NOT integrate
    it into the live book during defensive survival mode.

  python live/mm_maker.py                                  # DRY-RUN (prints intended quotes)
  python live/mm_maker.py --live --i-confirm-paper --size 0.1
  python live/mm_maker.py --cancel-only --live --i-confirm-paper   # pull all MM quotes
"""
from __future__ import annotations
import argparse, sys, time

DEFAULT_INSTRUMENTS = ["EURUSD", "GBPUSD", "USDCAD", "AUDUSD"]   # tightest spreads on this venue
TAG = "quanthack-mm"
SLEEP_BETWEEN = 0.25


def _cancel_mm(mt5):
    n = 0
    for o in (mt5.orders_get() or []):
        if getattr(o, "comment", "") == TAG:
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket}); n += 1
    if n:
        print(f"  cancelled {n} stale MM quote(s)")


def _inventory(mt5, sym):
    inv = 0.0
    for p in (mt5.positions_get(symbol=sym) or []):
        inv += p.volume if p.type == 0 else -p.volume
    return inv


def main():
    ap = argparse.ArgumentParser(description="Experimental market-making prototype (dry-run default)")
    ap.add_argument("--instruments", default=",".join(DEFAULT_INSTRUMENTS))
    ap.add_argument("--size", type=float, default=0.1, help="lots per quote (keep tiny while testing)")
    ap.add_argument("--edge-bps", type=float, default=1.5, help="distance from mid to post, in bps")
    ap.add_argument("--max-inventory", type=float, default=1.0, help="max abs lots per instrument")
    ap.add_argument("--cancel-only", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--i-confirm-paper", action="store_true")
    args = ap.parse_args()
    if args.live and not args.i_confirm_paper:
        sys.exit("Refusing to send without --i-confirm-paper (paper/contest account only).")

    try:
        import MetaTrader5 as mt5
    except Exception:
        sys.exit("MetaTrader5 not found (run on the Windows box).")
    if not mt5.initialize():
        sys.exit(f"MT5 init failed: {mt5.last_error()} (open + log in first)")
    acct = mt5.account_info()
    if acct is None:
        mt5.shutdown(); sys.exit("no account info")
    if getattr(acct, "trade_mode", None) == 0 and args.live:
        mt5.shutdown(); sys.exit("Account looks REAL (trade_mode=0). Aborting -- paper only.")

    if args.live:
        _cancel_mm(mt5)
    if args.cancel_only:
        print("cancel-only: done."); mt5.shutdown(); return

    print(f"market-maker ({'LIVE' if args.live else 'DRY-RUN'})  size {args.size}  edge {args.edge_bps}bps  invcap {args.max_inventory}")
    for sym in [s.strip().upper() for s in args.instruments.split(",") if s.strip()]:
        info = mt5.symbol_info(sym)
        if info is None:
            print(f"  ! {sym} not on broker"); continue
        if not info.visible:
            mt5.symbol_select(sym, True); info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if not tick:
            print(f"  ! {sym} no tick"); continue
        mid = (tick.ask + tick.bid) / 2.0
        edge = args.edge_bps / 1e4 * mid
        digits = getattr(info, "digits", 5)
        buy_px = round(mid - edge, digits); sell_px = round(mid + edge, digits)
        inv = _inventory(mt5, sym)
        post_buy = inv < args.max_inventory          # don't add longs past the cap
        post_sell = inv > -args.max_inventory         # don't add shorts past the cap
        print(f"  {sym:<8} mid {mid:.5f}  inv {inv:+.2f}  "
              f"{'BUY@'+format(buy_px,'.5f') if post_buy else 'buy-skip'}  "
              f"{'SELL@'+format(sell_px,'.5f') if post_sell else 'sell-skip'}")
        if not args.live:
            continue
        for side, px, go in ((mt5.ORDER_TYPE_BUY_LIMIT, buy_px, post_buy),
                             (mt5.ORDER_TYPE_SELL_LIMIT, sell_px, post_sell)):
            if not go:
                continue
            req = {"action": mt5.TRADE_ACTION_PENDING, "symbol": sym, "volume": round(args.size, 2),
                   "type": side, "price": px, "type_time": mt5.ORDER_TIME_GTC, "comment": TAG}
            res = mt5.order_send(req)
            print(f"      -> {('BUY_LIMIT' if side==mt5.ORDER_TYPE_BUY_LIMIT else 'SELL_LIMIT')} retcode {getattr(res,'retcode',None)}")
            time.sleep(SLEEP_BETWEEN)
    if args.live:
        print("  posted. Watch inventory + P&L; re-run each minute to refresh quotes.")
    mt5.shutdown()


if __name__ == "__main__":
    main()
