"""
FAST risk monitor (intra-hour circuit breaker). Runs every few minutes BETWEEN the hourly
rebalances and does exactly one job: if drawdown from the tracked peak crosses the de-risk
ladder, it TRIMS every position (reduce-only) immediately -- so a shock at :05 past the hour
is handled in minutes, not at the top of the next hour. It never opens or increases
positions; the hourly cycle handles re-entry. Deterministic + fast (no LLM in the hot path).

Ladder is shared with the hourly dd-guard (same peak file + same derisk.py), so they agree:
  drawdown small -> full size ; deeper drawdown -> 0.7 / 0.4 / 0.2 of base gross.
Plus a hard emergency flatten if margin level falls dangerously low (should never trigger at
our gross, but it's the last backstop before the 30% stop-out).

  python live/fast_monitor.py                            # DRY-RUN (prints intended trims, sends nothing)
  python live/fast_monitor.py --live --i-confirm-paper   # actually trims on the paper account
"""
from __future__ import annotations
import argparse, json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TOLERANCE = 0.10            # don't trim unless current gross exceeds target by >10% (avoids churn)
HARD_MARGIN_LEVEL = 2.0     # emergency flatten if equity/used_margin < 200% (far above the 30% stop-out)
SLEEP_BETWEEN = 0.25


def _filling(mt5, info):
    fm = getattr(info, "filling_mode", 0)
    if fm & getattr(mt5, "SYMBOL_FILLING_IOC", 2): return mt5.ORDER_FILLING_IOC
    if fm & getattr(mt5, "SYMBOL_FILLING_FOK", 1): return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def _reduce(mt5, pos, frac, live):
    """Close `frac` (0..1) of a position, reduce-only, via an opposite market order on the netting book."""
    info = mt5.symbol_info(pos.symbol); tick = mt5.symbol_info_tick(pos.symbol)
    step = getattr(info, "volume_step", 0.01) or 0.01
    vol = round(round(abs(pos.volume) * frac / step) * step, 2)
    if vol < (getattr(info, "volume_min", 0.01) or 0.01):
        return None
    is_long = (pos.type == 0)
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": pos.symbol, "position": pos.ticket,
           "volume": vol, "type": mt5.ORDER_TYPE_SELL if is_long else mt5.ORDER_TYPE_BUY,
           "price": tick.bid if is_long else tick.ask, "deviation": 30,
           "comment": "quanthack-derisk", "type_filling": _filling(mt5, info)}
    if not live:
        return f"DRY  {pos.symbol:<8} {'SELL' if is_long else 'BUY'} {vol} (reduce)"
    res = mt5.order_send(req)
    return f"{pos.symbol:<8} {'SELL' if is_long else 'BUY'} {vol} -> retcode {getattr(res,'retcode',None)}"


def main():
    ap = argparse.ArgumentParser(description="Fast intra-hour risk monitor (reduce-only)")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--i-confirm-paper", action="store_true")
    ap.add_argument("--peak-state", default=os.path.join(ROOT, "peak.json"))
    ap.add_argument("--base-gross", type=float, default=None, help="default: read live/runtime.json")
    args = ap.parse_args()
    if args.live and not args.i_confirm_paper:
        sys.exit("Refusing to trade without --i-confirm-paper (paper/contest account only).")

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

    equity = float(acct.equity)
    used_margin = float(getattr(acct, "margin", 0) or 0)
    leverage = float(getattr(acct, "leverage", 30) or 30)
    margin_level = (equity / used_margin) if used_margin > 0 else float("inf")
    cur_gross = (used_margin * leverage / equity) if equity else 0.0
    positions = list(mt5.positions_get() or [])

    base_gross = args.base_gross
    if base_gross is None:
        try:
            base_gross = float(json.load(open(os.path.join(ROOT, "live", "runtime.json"))).get("gross", 2))
        except Exception:
            base_gross = 2.0

    from derisk import derisk, update_peak
    peak = update_peak(args.peak_state, equity)
    mult, dd, level = derisk(equity, peak)
    # profit-lock ratchet: protect banked gains -- another reduce-only overlay, combined via min
    try:
        from profit_lock import update_state as _pl_state, ratchet as _pl_ratchet
        _pa, _pp = _pl_state(os.path.join(ROOT, "profit_peak.json"), equity)
        pl_mult, pl_info = _pl_ratchet(equity, _pa, _pp)
    except Exception as e:
        pl_mult, pl_info = 1.0, {"err": str(e)}
    eff_mult = min(mult, pl_mult)
    target_gross = base_gross * eff_mult

    ts = time.strftime("%H:%M:%S")
    print(f"{ts} fast-monitor | equity {equity:,.0f} | dd {dd*100:.2f}% ({level}) | "
          f"gross ~{cur_gross:.2f}x -> target ~{target_gross:.2f}x | margin level "
          f"{('inf' if margin_level==float('inf') else format(margin_level*100,'.0f')+'%')}")
    if pl_info.get("armed"):
        print(f"  profit-lock: peak gain {pl_info['peak_gain_pct']}% | given back "
              f"{pl_info.get('giveback_pct',0)}% -> ratchet x{pl_mult}")

    actions = []
    if margin_level < HARD_MARGIN_LEVEL:
        print("  *** EMERGENCY: margin level critical -> flattening all positions ***")
        for p in positions:
            r = _reduce(mt5, p, 1.0, args.live)
            if r: actions.append(r); time.sleep(SLEEP_BETWEEN)
    elif cur_gross > target_gross * (1 + TOLERANCE) and cur_gross > 0:
        frac = max(0.0, 1.0 - target_gross / cur_gross)
        cause = (f"profit-lock x{pl_mult}" if pl_mult < mult else f"drawdown {dd*100:.1f}% ({level})")
        print(f"  {cause} -> trimming every position by ~{frac*100:.0f}% (reduce-only)")
        for p in positions:
            r = _reduce(mt5, p, frac, args.live)
            if r: actions.append(r); time.sleep(SLEEP_BETWEEN)
    else:
        print("  within tolerance -> no action")

    for a in actions:
        print("   ", a)
    print(f"  ({'LIVE' if args.live else 'DRY-RUN'})")
    mt5.shutdown()


if __name__ == "__main__":
    main()
