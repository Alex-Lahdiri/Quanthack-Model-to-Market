"""
MT5 execution bridge for the PAPER competition account (Quanthack / Model-to-Market).

Reads a target book (from live_runner.py), compares it to current MetaTrader 5
positions, converts each target's USD notional into broker LOTS using the real
contract specs, and places the delta orders.

SAFETY:
  * dry-run by default -- prints planned orders in lots, sends nothing. Add --live.
  * paper/contest/demo account only. Refuses to send unless --i-confirm-paper.
    Aborts if the account looks REAL (trade_mode == 0).
  * rate-limited; well under the competition's <500 req/s rule.
  * never moves real money.

Sizing (the important bit):
  live_runner emits a signed target USD notional per symbol. USD-per-lot depends
  on the pair, so we compute it from MT5's own contract_size + live price + the
  base/quote currencies:
    * USD is the QUOTE  (EURUSD, XAUUSD, ...):  usd_per_lot = contract_size * price
    * USD is the BASE   (USDJPY, USDCHF, ...):  usd_per_lot = contract_size
    * cross (EURGBP, EURCHF):                   usd_per_lot = contract_size * (base->USD)
  lots = notional_usd / usd_per_lot, rounded to volume_step, clamped to [min, max].
  (We size from NOTIONAL, not the book's `units`, because units = notional/price is
   only the correct base-unit count for USD-quoted pairs.)

Run on the machine where the MT5 terminal is open + logged into the contest account.
Simplest auth: leave creds unset and just keep the terminal logged in -> initialize()
attaches to that running session (no password is handled by this script).
"""
from __future__ import annotations
import argparse, json, time, sys

# Our names == broker names on this contest server (verified via mt5_probe.py).
# Broker does NOT offer NZDUSD / EURJPY. Crypto exists but is unvalidated -> excluded.
SYMBOL_MAP = {
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY", "USDCHF": "USDCHF",
    "USDCAD": "USDCAD", "AUDUSD": "AUDUSD", "EURGBP": "EURGBP", "EURCHF": "EURCHF",
    "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD",
    # crypto sleeve (only reaches the bridge if validated + opted-in upstream)
    "BTCUSD": "BTCUSD", "ETHUSD": "ETHUSD", "SOLUSD": "SOLUSD", "XRPUSD": "XRPUSD", "BARUSD": "BARUSD",
}
MIN_TRADE_LOTS = 0.02      # ignore dust deltas smaller than this (after step-rounding)
SLEEP_BETWEEN = 0.25       # seconds between orders (rate-limit safety)


def _mid(tick):
    if not tick:
        return 0.0
    if tick.ask and tick.bid:
        return (tick.ask + tick.bid) / 2.0
    return float(tick.ask or tick.bid or 0.0)


def _round_step(vol, step):
    if step and step > 0:
        return round(round(vol / step) * step, 8)
    return round(vol, 2)


def usd_per_lot(mt5, info, tick):
    """USD value of 1.0 lot for `info`, from contracts + live price + currencies."""
    cs = float(info.trade_contract_size)
    base = (getattr(info, "currency_base", "") or "").upper()
    quote = (getattr(info, "currency_profit", "") or "").upper()   # profit ccy == quote
    price = _mid(tick)
    if quote == "USD":                       # xxxUSD -> 1 lot = cs base, worth cs*price USD
        return cs * price
    if base == "USD":                        # USDxxx -> 1 lot = cs USD
        return cs
    conv = mt5.symbol_info_tick(base + "USD")          # cross: convert base -> USD
    if conv and _mid(conv):
        return cs * _mid(conv)
    inv = mt5.symbol_info_tick("USD" + base)
    if inv and _mid(inv):
        return cs / _mid(inv)
    return cs * price                        # graceful fallback


def _filling(mt5, info):
    fm = getattr(info, "filling_mode", 0)
    if fm & getattr(mt5, "SYMBOL_FILLING_IOC", 2):
        return mt5.ORDER_FILLING_IOC
    if fm & getattr(mt5, "SYMBOL_FILLING_FOK", 1):
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def _cancel_pending(mt5, tag="quanthack-passive"):
    """Remove our own stale passive limit orders so cycles don't stack them."""
    n = 0
    for o in (mt5.orders_get() or []):
        if getattr(o, "comment", "") == tag:
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket}); n += 1
    if n:
        print(f"  cancelled {n} stale passive order(s)")


def main():
    ap = argparse.ArgumentParser(description="MT5 paper execution bridge (notional -> lots)")
    ap.add_argument("--book", required=True, help="book.json from live_runner.py")
    ap.add_argument("--live", action="store_true", help="actually send orders (else dry-run)")
    ap.add_argument("--i-confirm-paper", action="store_true", help="affirm this is the PAPER/contest account")
    ap.add_argument("--passive", action="store_true",
                    help="post LIMIT orders at the touch (provide liquidity, save the spread) instead of market")
    ap.add_argument("--login", type=int); ap.add_argument("--password"); ap.add_argument("--server")
    args = ap.parse_args()

    book = json.load(open(args.book))
    targets = book["targets"]
    if args.live and not args.i_confirm_paper:
        sys.exit("Refusing to send live orders without --i-confirm-paper (paper/contest account only).")

    try:
        import MetaTrader5 as mt5
    except Exception:
        sys.exit("MetaTrader5 package not found. On the trading machine: pip install MetaTrader5")

    ok = mt5.initialize(login=args.login, password=args.password, server=args.server) if args.login else mt5.initialize()
    if not ok:
        sys.exit(f"MT5 initialize failed: {mt5.last_error()}  (open the terminal + log in first)")
    acct = mt5.account_info()
    if acct is None:
        mt5.shutdown(); sys.exit("No MT5 account info.")
    if getattr(acct, "trade_mode", None) == 0 and args.live:   # 0 == real
        mt5.shutdown(); sys.exit("Account looks REAL (trade_mode=0). Aborting -- paper only.")
    print(f"connected: login {acct.login} | equity {acct.equity:,.0f} {acct.currency} "
          f"| trade_mode {acct.trade_mode} (2=contest)")

    # Build the plan: target lots from USD notional, minus current position lots.
    plan = []
    for sym, t in targets.items():
        mt5sym = SYMBOL_MAP.get(sym, sym)
        info = mt5.symbol_info(mt5sym)
        if info is None:
            print(f"  ! {mt5sym}: not on broker, skipping"); continue
        if not info.visible:
            mt5.symbol_select(mt5sym, True); info = mt5.symbol_info(mt5sym)
        tick = mt5.symbol_info_tick(mt5sym)
        upl = usd_per_lot(mt5, info, tick)
        target_lots = (t["notional"] / upl) if upl else 0.0      # signed
        cur_lots = 0.0
        for p in (mt5.positions_get(symbol=mt5sym) or []):
            cur_lots += p.volume if p.type == 0 else -p.volume   # 0=BUY, 1=SELL
        delta = _round_step(target_lots - cur_lots, info.volume_step)
        if abs(delta) < max(MIN_TRADE_LOTS, info.volume_min):
            continue
        if abs(delta) > info.volume_max:                         # clamp per-order size
            delta = info.volume_max if delta > 0 else -info.volume_max
        plan.append((mt5sym, delta, target_lots, cur_lots, t["notional"], info))

    print(f"\nplanned orders ({'LIVE' if args.live else 'DRY-RUN'}):")
    if not plan:
        print("  (nothing to do -- already within a dust band of target)")
    for mt5sym, delta, tgt, cur, notion, info in plan:
        print(f"  {mt5sym:<8} {'BUY ' if delta>0 else 'SELL'} {abs(delta):>7.2f} lots"
              f"   (cur {cur:+.2f} -> tgt {tgt:+.2f} | USD notional {notion:>14,.0f})")
    if not args.live:
        print("\ndry-run: no orders sent. Re-run with --live --i-confirm-paper to execute on the paper account.")
        mt5.shutdown(); return

    if args.passive:
        _cancel_pending(mt5)          # clear our stale limit orders so we don't stack across cycles
    sent = 0
    for mt5sym, delta, tgt, cur, notion, info in plan:
        tick = mt5.symbol_info_tick(mt5sym)
        if args.passive:
            # provide liquidity at the touch: BUY at bid, SELL at ask -> save (or earn) the spread
            req = {"action": mt5.TRADE_ACTION_PENDING, "symbol": mt5sym,
                   "volume": round(abs(delta), 2),
                   "type": mt5.ORDER_TYPE_BUY_LIMIT if delta > 0 else mt5.ORDER_TYPE_SELL_LIMIT,
                   "price": tick.bid if delta > 0 else tick.ask,
                   "type_time": mt5.ORDER_TIME_GTC, "comment": "quanthack-passive"}
        else:
            req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": mt5sym,
                   "volume": round(abs(delta), 2),
                   "type": mt5.ORDER_TYPE_BUY if delta > 0 else mt5.ORDER_TYPE_SELL,
                   "price": tick.ask if delta > 0 else tick.bid,
                   "deviation": 30, "comment": "quanthack", "type_filling": _filling(mt5, info)}
        res = mt5.order_send(req)
        rc = getattr(res, "retcode", None)
        kind = "LIMIT" if args.passive else "MKT "
        flag = "" if rc == getattr(mt5, "TRADE_RETCODE_DONE", 10009) else "  (check Market Watch / filling)"
        print(f"  {mt5sym:<8} {kind} {'BUY ' if delta > 0 else 'SELL'} {abs(delta):.2f} -> retcode {rc}{flag}")
        sent += 1
        time.sleep(SLEEP_BETWEEN)
    print(f"\nsent {sent} {'passive limit' if args.passive else 'market'} orders.")
    if args.passive:
        print("note: passive = liquidity provision; fills aren't guaranteed. Unfilled deltas are re-posted next cycle.")
    mt5.shutdown()


if __name__ == "__main__":
    main()
