"""
scalp.py -- EXPERIMENTAL fast mean-reversion scalper + ZERO-RISK edge probe.

The winners here scalp microstructure: NO commission + short-horizon returns mean-revert
(lag-1 autocorr ~ -0.2). This fades small fast deviations on ONE instrument: every `interval`
seconds it reads the tick; if mid has pushed >= ENTER_Z std from a short rolling mean it takes
a small position AGAINST the move, then exits on reversion (|z|<=EXIT_Z), a time stop, or a loss stop.

THE POINT: run it DRY first. Dry mode paper-trades on LIVE ticks and reports would-be P&L
**net of the real spread** (entries fill at ask/bid). If that P&L is positive over 20-30 min,
the edge is real and capturable -> then go --live tiny. If it's negative, the spread eats it and
we DON'T bother. This tests the edge with zero risk -- the honest way to find out.

  python live/scalp.py --symbol EURUSD --minutes 20                 # DRY probe on live ticks
  python live/scalp.py --symbol EURUSD --live --i-confirm-paper --size 0.05 --minutes 10
"""
from __future__ import annotations
import argparse, sys, time, collections, statistics as st

ENTER_Z = 2.0      # std from short mean to fade
EXIT_Z  = 0.3      # revert-to-mean exit band
WINDOW  = 60       # rolling samples (~WINDOW * interval seconds)
MAX_HOLD = 45      # seconds
STOP_BPS = 6.0     # hard loss stop per position (bps of price)

def decide(prices, side):
    """Pure signal. prices oldest..newest; side 0 flat/+1 long/-1 short. -> action, z."""
    if len(prices) < 12:
        return "HOLD", 0.0
    hist = prices[:-1]; mid = prices[-1]
    mean = st.fmean(hist); sd = st.pstdev(hist)
    if sd <= 0:
        return "HOLD", 0.0
    z = (mid - mean) / sd
    if side == 0:
        if z >= ENTER_Z:  return "SELL", z
        if z <= -ENTER_Z: return "BUY", z
        return "HOLD", z
    return ("EXIT", z) if abs(z) <= EXIT_Z else ("HOLD", z)

def main():
    ap = argparse.ArgumentParser(description="Fast mean-reversion scalper / edge probe (dry by default)")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--size", type=float, default=0.05)
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--i-confirm-paper", action="store_true")
    ap.add_argument("--max-loss-bps", type=float, default=25.0,
                    help="session circuit-breaker: stop if cumulative P&L falls below -this")
    ap.add_argument("--momentum", action="store_true",
                    help="CHASE moves instead of fading them (demo: momentum is the wrong sign here)")
    args = ap.parse_args()
    if args.live and not args.i_confirm_paper:
        sys.exit("Refusing to trade without --i-confirm-paper (paper/contest account only).")
    try:
        import MetaTrader5 as mt5
    except Exception:
        sys.exit("MetaTrader5 not found (run on the Windows box).")
    if not mt5.initialize():
        sys.exit(f"MT5 init failed: {mt5.last_error()}")
    acct = mt5.account_info()
    if acct is None: mt5.shutdown(); sys.exit("no account info")
    if getattr(acct, "trade_mode", None) == 0 and args.live:
        mt5.shutdown(); sys.exit("Account looks REAL (trade_mode=0). Aborting -- paper only.")
    info = mt5.symbol_info(args.symbol)
    if info is None: mt5.shutdown(); sys.exit(f"{args.symbol} not found")
    if not info.visible: mt5.symbol_select(args.symbol, True)

    def order(side_):  # market order; returns fill price (live) or None
        tick = mt5.symbol_info_tick(args.symbol)
        px = tick.ask if side_ == 1 else tick.bid
        if not args.live:
            return px
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": args.symbol, "volume": round(args.size, 2),
               "type": mt5.ORDER_TYPE_BUY if side_ == 1 else mt5.ORDER_TYPE_SELL,
               "price": px, "deviation": 20, "comment": "quanthack-scalp",
               "type_filling": mt5.ORDER_FILLING_IOC}
        r = mt5.order_send(req); print(f"      order retcode {getattr(r,'retcode',None)}")
        return px

    prices = collections.deque(maxlen=WINDOW)
    side = 0; entry = 0.0; entry_t = 0.0; total_bps = 0.0; trades = 0
    end = time.time() + args.minutes * 60
    print(f"scalp {args.symbol} ({'LIVE' if args.live else 'DRY PROBE'}) size {args.size} enterZ {ENTER_Z} exitZ {EXIT_Z} interval {args.interval}s")
    while time.time() < end:
        t = mt5.symbol_info_tick(args.symbol)
        if not t: time.sleep(args.interval); continue
        bid, ask = t.bid, t.ask; mid = (bid + ask) / 2.0
        prices.append(mid)
        action, z = decide(list(prices), side)
        if args.momentum and action in ("BUY", "SELL"):
            action = "SELL" if action == "BUY" else "BUY"   # chase, not fade
        now = time.time()
        if side == 0 and action in ("BUY", "SELL"):
            side = 1 if action == "BUY" else -1
            entry = order(side); entry_t = now
            print(f"  {action:<4} @ {entry:.5f}  z {z:+.2f}  spread {(ask-bid)/mid*1e4:.2f}bps")
        elif side != 0:
            exit_px = bid if side == 1 else ask          # close long@bid / short@ask (pay spread again)
            pnl_bps = (exit_px - entry) * side / entry * 1e4
            if action == "EXIT" or (now - entry_t) > MAX_HOLD or pnl_bps <= -STOP_BPS:
                if args.live: order(-side)
                total_bps += pnl_bps; trades += 1
                why = "revert" if action == "EXIT" else ("time" if (now-entry_t) > MAX_HOLD else "stop")
                print(f"  EXIT @ {exit_px:.5f}  pnl {pnl_bps:+.2f}bps ({why}, {now-entry_t:.0f}s)  cum {total_bps:+.1f}bps over {trades}")
                side = 0
                if total_bps <= -args.max_loss_bps:
                    print(f"  *** session loss-limit -{args.max_loss_bps:.0f}bps hit -> stopping ***"); break
        time.sleep(args.interval)
    mt5.shutdown()
    avg = total_bps / trades if trades else 0.0
    print(f"\n=== {trades} round-trips | net {total_bps:+.1f} bps | avg {avg:+.2f} bps/trade (NET OF SPREAD) ===")
    print("  > 0  => edge beats the spread -> worth a live-small test.   <= 0 => spread eats it, skip.")

if __name__ == "__main__":
    main()
