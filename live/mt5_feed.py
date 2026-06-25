"""
Build panel_live.parquet straight from the running MT5 terminal (no feed files).

Pulls M1 close bars for the live universe via copy_rates and writes a wide panel
(ts index + one column per symbol) that live_runner.py reads directly. Run it on a
short schedule (e.g. every minute) on the machine where MT5 is open + logged in.

  python live/mt5_feed.py --out panel_live.parquet --lookback-days 5
  python live/mt5_feed.py --out panel_live.parquet --include-crypto   # FX + crypto sleeve
"""
from __future__ import annotations
import argparse, os, sys
import pandas as pd

UNIV = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD",
        "EURGBP", "EURCHF", "XAUUSD", "XAGUSD"]
CRYPTO = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BARUSD"]


def main():
    ap = argparse.ArgumentParser(description="Build panel_live.parquet from MT5 copy_rates")
    ap.add_argument("--out", default="panel_live.parquet")
    ap.add_argument("--lookback-days", type=float, default=5.0)
    ap.add_argument("--include-crypto", action="store_true", help="also pull the crypto sleeve")
    ap.add_argument("--login", type=int); ap.add_argument("--password"); ap.add_argument("--server")
    args = ap.parse_args()

    try:
        import MetaTrader5 as mt5
    except Exception:
        sys.exit("MetaTrader5 package not found. On the trading machine: pip install MetaTrader5")

    ok = mt5.initialize(login=args.login, password=args.password, server=args.server) if args.login else mt5.initialize()
    if not ok:
        sys.exit(f"MT5 initialize failed: {mt5.last_error()}  (open the terminal + log in first)")

    syms = UNIV + (CRYPTO if args.include_crypto else [])
    count = int(args.lookback_days * 24 * 60) + 600     # M1 bars (+buffer for weekend gaps)
    cols = {}
    for s in syms:
        if mt5.symbol_info(s) is None:
            print(f"  ! {s} not on broker, skipping"); continue
        mt5.symbol_select(s, True)
        rates = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_M1, 0, count)
        if rates is None or len(rates) == 0:
            print(f"  ! {s} no rates"); continue
        df = pd.DataFrame(rates)
        ts = pd.to_datetime(df["time"], unit="s")
        cols[s] = pd.Series(df["close"].to_numpy(), index=ts, name=s)

    if not cols:
        mt5.shutdown()
        sys.exit("no rates pulled -- is the terminal logged in with Market Watch populated?")

    panel = pd.concat(cols, axis=1, sort=False).sort_index().ffill().dropna(how="all")
    cutoff = panel.index.max() - pd.Timedelta(days=args.lookback_days)
    panel = panel[panel.index >= cutoff]
    panel.index.name = "ts"
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    panel.reset_index().to_parquet(args.out)
    print(f"wrote {args.out}: {panel.shape[0]} bars x {panel.shape[1]} instruments "
          f"({panel.index[0]} -> {panel.index[-1]})")
    mt5.shutdown()


if __name__ == "__main__":
    main()
