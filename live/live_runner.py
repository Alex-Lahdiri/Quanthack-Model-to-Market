"""
ADVISORY live runner (NOT an executor). Computes the current target book from the
latest data and writes target notionals for your MT5 / AI-agent bridge to act on.
It never sends orders or moves money itself.

Risk overlays (both <=1.0, risk-reduce only, combined by taking the min):
  --risk-gate   news/event multiplier (Nemotron+Claude)
  --dd-guard    drawdown de-risk ladder (peak tracked in --peak-state)
"""
from __future__ import annotations
import argparse, json, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget
from strategies.cov_aware import CovAwareMomentum

# Live universe = the 10 names the broker actually offers (verified via mt5_probe).
UNIV = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD",
        "EURGBP","EURCHF","XAUUSD","XAGUSD"]
CRYPTO = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","BARUSD"]  # added ONLY if validated + opted-in

def build(name, gross):
    if name == "mv":
        return CovAwareMomentum(mom_window=480, ema=48, target_gross=gross, mode="mv")
    if name == "rev":
        # Hourly cross-sectional MEAN REVERSION: fade the ~1h move. Matches the persistent
        # negative autocorrelation in this regime (momentum was the wrong sign). Market-neutral
        # + inverse-vol sized so it stays smooth for the drawdown/Sharpe ranks. Deploy LOW gross.
        return DiversifiedVolTarget(mode="reversion", mom_window=60, vol_window=60,
                                    smooth_halflife=20, target_gross=gross)
    return DiversifiedVolTarget(mom_window=480, vol_window=480, smooth_halflife=48, target_gross=gross)

def main():
    ap = argparse.ArgumentParser(description="Advisory target-book generator (no execution)")
    ap.add_argument("--panel", required=True)
    ap.add_argument("--equity", type=float, default=1_000_000.0)
    ap.add_argument("--strategy", choices=["iv", "mv", "rev"], default="mv")
    ap.add_argument("--gross", type=float, default=4.0)
    ap.add_argument("--emit", default="")
    ap.add_argument("--logfire", action="store_true")
    ap.add_argument("--risk-gate", action="store_true", help="apply news/event multiplier")
    ap.add_argument("--headlines", default="")
    ap.add_argument("--dd-guard", action="store_true", help="apply drawdown de-risk ladder")
    ap.add_argument("--profit-lock", action="store_true", help="apply profit-lock ratchet (protect banked gains)")
    ap.add_argument("--peak-state", default="/data/peak.json")
    ap.add_argument("--include-crypto", action="store_true",
                    help="add crypto IF validated (crypto_validated.json ok); else FX only")
    args = ap.parse_args()

    if args.logfire:
        try:
            import logfire; logfire.configure(); logfire.info("live_runner start", strategy=args.strategy, gross=args.gross)
        except Exception as e:
            print(f"[logfire unavailable: {e}]")

    panel = pd.read_parquet(args.panel).set_index("ts").sort_index()
    univ = list(UNIV)
    if args.include_crypto:
        vp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "crypto_validated.json")
        try:
            if json.load(open(vp)).get("ok"):
                univ += CRYPTO
                print("[crypto enabled: crypto_validated.json ok]")
            else:
                print("[crypto requested but validation flag not ok -> FX only]")
        except Exception:
            print("[crypto requested but no crypto_validated.json -> FX only]")
    panel = panel[[c for c in univ if c in panel.columns]]
    strat = build(args.strategy, args.gross); strat.precompute(panel)
    w = RiskEngine().apply(strat.W.iloc[-1])

    overlays = {}
    if args.risk_gate and args.headlines and os.path.exists(args.headlines):
        try:
            from news_risk_gate import assess
            g = assess(open(args.headlines).read().splitlines())
            overlays["news"] = (g.multiplier, g.reason)
        except Exception as e:
            print(f"[risk gate skipped: {e}]")
    if args.dd_guard:
        try:
            from derisk import derisk, update_peak
            peak = update_peak(args.peak_state, args.equity)
            m, dd, lvl = derisk(args.equity, peak)
            overlays["drawdown"] = (m, f"dd {dd*100:.1f}% -> {lvl}")
        except Exception as e:
            print(f"[dd-guard skipped: {e}]")
    if args.profit_lock:
        try:
            from profit_lock import update_state, ratchet
            _plp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profit_peak.json")
            _a, _pk = update_state(_plp, args.equity)
            _plm, _pli = ratchet(args.equity, _a, _pk)
            if _plm < 1.0:
                overlays["profit_lock"] = (_plm, f"gave back {_pli.get('giveback_pct',0)}% of {_pli.get('peak_gain_pct',0)}% peak")
        except Exception as e:
            print(f"[profit-lock skipped: {e}]")

    mult = min([1.0] + [v[0] for v in overlays.values()])
    w = w * mult

    last = panel.iloc[-1]; book = {}
    for s in w.index:
        notion = float(w[s] * args.equity)
        book[s] = {"weight": round(float(w[s]), 4), "notional": round(notion, 2),
                   "units": round(notion / last[s], 2) if last[s] else 0.0}
    gross = sum(abs(v["notional"]) for v in book.values())
    out = {"ts": str(panel.index[-1]), "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
           "strategy": args.strategy, "equity": args.equity,
           "gross_leverage": round(gross/args.equity, 2),
           "overlay_multiplier": round(mult, 3),
           "overlays": {k: {"mult": v[0], "reason": v[1]} for k, v in overlays.items()},
           "targets": book}
    print(f"target book @ {out['ts']} | gross {out['gross_leverage']}x | strategy {args.strategy}"
          f" | overlay x{mult:.2f}" + (f"  ({'; '.join(f'{k}:{v[1]}' for k,v in overlays.items())})" if overlays else ""))
    for s, v in sorted(book.items(), key=lambda kv: -abs(kv[1]['notional'])):
        print(f"  {s:<8} w {v['weight']:+.3f}  notional {v['notional']:>14,.0f}")
    if args.emit:
        json.dump(out, open(args.emit, "w"), indent=2); print(f"wrote {args.emit}")
    if args.logfire:
        try:
            import logfire; logfire.info("target book", gross=out["gross_leverage"], overlay=mult)
        except Exception:
            pass

if __name__ == "__main__":
    main()
