"""
Crypto validation gate. We have no historical archive for crypto, so this pulls REAL
price history for the FX core + crypto sleeve straight from the running MT5 terminal,
backtests the mv strategy on FX-only vs FX+crypto, and writes crypto_validated.json
ONLY if adding crypto is safe (no liquidation, discipline intact, Sharpe retained, and
enough history). live_runner includes crypto only if this flag is ok AND runtime.json
opts in -- so crypto can never trade un-validated.

Run on the Windows box with MT5 open:
  python live/validate_crypto.py --lookback-days 10
"""
from __future__ import annotations
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import config as C
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies.cov_aware import CovAwareMomentum

FX = list(C.LIVE_UNIVERSE)
CRYPTO = list(C.CRYPTO_UNIVERSE)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pull(mt5, syms, days):
    count = int(days * 24 * 60) + 600
    cols = {}
    for s in syms:
        if mt5.symbol_info(s) is None:
            print(f"  ! {s} not on broker"); continue
        mt5.symbol_select(s, True)
        r = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_M1, 0, count)
        if r is None or len(r) == 0:
            print(f"  ! {s} no rates"); continue
        df = pd.DataFrame(r)
        cols[s] = pd.Series(df["close"].to_numpy(), index=pd.to_datetime(df["time"], unit="s"), name=s)
    return pd.concat(cols, axis=1, sort=False).sort_index().ffill().dropna(how="all") if cols else pd.DataFrame()


def bt(panel, names):
    cost = {s: C.VENUE_COST_BPS.get(s, 1.0) for s in names}
    strat = CovAwareMomentum(mom_window=480, ema=48, target_gross=2.0, mode="mv")
    r = run_backtest(panel[names].dropna(how="all"), strat, risk=RiskEngine(),
                     rebalance_every=60, cost_bps=cost)
    return M.compute_metrics(r.equity, r.telemetry, r.trade_count, r.liquidated)


def main():
    ap = argparse.ArgumentParser(description="Validate the crypto sleeve on real MT5 history")
    ap.add_argument("--lookback-days", type=float, default=10.0)
    ap.add_argument("--login", type=int); ap.add_argument("--password"); ap.add_argument("--server")
    args = ap.parse_args()

    try:
        import MetaTrader5 as mt5
    except Exception:
        sys.exit("MetaTrader5 not found (run on the Windows box).")
    ok = mt5.initialize(login=args.login, password=args.password, server=args.server) if args.login else mt5.initialize()
    if not ok:
        sys.exit(f"MT5 init failed: {mt5.last_error()} (open + log in first)")

    print(f"pulling {args.lookback_days}d of M1 history for {len(FX)} FX + {len(CRYPTO)} crypto ...")
    panel = pull(mt5, FX + CRYPTO, args.lookback_days)
    mt5.shutdown()

    have_fx = [s for s in FX if s in panel.columns]
    have_cr = [s for s in CRYPTO if s in panel.columns]
    if not have_cr:
        sys.exit("no crypto history pulled -- cannot validate.")
    n = len(panel)
    fx = bt(panel, have_fx)
    comb = bt(panel, have_fx + have_cr)

    def show(tag, m):
        print(f"  {tag:<13} return {m['total_return']*100:6.2f}%  Sharpe {m['sharpe']:.4f}  "
              f"maxDD {m['max_drawdown']*100:6.2f}%  disc {m['discipline']:.0f}  liq={m['liquidated']}")
    print(f"\nbars: {n}   crypto available: {have_cr}")
    show("FX only", fx); show("FX + crypto", comb)

    enough = n >= 480 * 3
    passed = (not comb["liquidated"]) and comb["discipline"] >= 95 and \
             comb["sharpe"] >= 0.8 * fx["sharpe"] and enough
    reasons = []
    if comb["liquidated"]: reasons.append("liquidation in combined book")
    if comb["discipline"] < 95: reasons.append("discipline < 95")
    if comb["sharpe"] < 0.8 * fx["sharpe"]: reasons.append("Sharpe dropped >20% vs FX-only")
    if not enough: reasons.append("insufficient history (need >=3 days)")
    reason = "passes gate: no liquidation, discipline intact, Sharpe retained" if passed else \
             "FAILS gate: " + "; ".join(reasons)

    out = {"ok": bool(passed), "reason": reason, "crypto": have_cr, "bars": int(n),
           "fx": {k: fx[k] for k in ("total_return", "sharpe", "max_drawdown", "discipline", "liquidated")},
           "combined": {k: comb[k] for k in ("total_return", "sharpe", "max_drawdown", "discipline", "liquidated")}}
    path = os.path.join(ROOT, "crypto_validated.json")
    json.dump(out, open(path, "w"), indent=2)
    print(f"\n>>> crypto {'ENABLED (validated)' if passed else 'NOT enabled'} -- {reason}")
    print(f"    wrote {path}")
    print('    To actually trade it, also set  "include_crypto": true  in live/runtime.json')


if __name__ == "__main__":
    main()
