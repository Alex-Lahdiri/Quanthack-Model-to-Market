"""
Multi-agent AI trading desk (advisory, reduce-only) -- the AI-native control layer.

Coordinates the sponsor models into the four desk roles from the Syphonix demo, layered
on top of the deterministic strategy + risk engine:

  Market Analyst   (NVIDIA Nemotron)  -> event-risk read of headlines -> exposure multiplier
  Risk Guardian    (rules + drawdown) -> telemetry vs penalty tiers + de-risk ladder
  Strategy Advisor (Anthropic Claude) -> plain-English rationale for the current book
  Executor         (deterministic)    -> applies the MOST CONSERVATIVE overlay, writes orders

SAFETY: every agent can only REDUCE exposure or explain it -- none can size up or override
the risk engine. The final overlay is min(1.0, analyst, guardian), so the AI layer is
strictly risk-reducing. With no API keys set, the desk runs entirely on deterministic
fallbacks (multiplier 1.0, rule-based narrative) so it always works. It never executes
trades; it emits an advisory decision record for the MT5 bridge.

Every step is wrapped in a Pydantic Logfire span (--logfire) for full observability.

  python live/desk.py --book book.json --headlines live/headlines.txt \
         --peak-state peak.json --emit desk_decision.json --logfire
"""
from __future__ import annotations
import argparse, json, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def _span(use, name):
    """Logfire span if enabled+configured, else a no-op context manager."""
    if use:
        try:
            import logfire
            if os.environ.get("LOGFIRE_TOKEN"):
                logfire.configure()
            return logfire.span(name)
        except Exception:
            pass
    class _N:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return _N()


def analyst(headlines_path, use_lf):
    with _span(use_lf, "desk.analyst.nemotron"):
        mult, reason, high = 1.0, "no headlines -> no event-risk change", []
        if headlines_path and os.path.exists(headlines_path):
            try:
                from news_risk_gate import assess
                g = assess(open(headlines_path).read().splitlines())
                mult, reason, high = float(g.multiplier), g.reason, list(getattr(g, "high_impact", []))
            except Exception as e:
                reason = f"analyst unavailable ({e}) -> no change"
        return {"role": "Market Analyst", "model": "NVIDIA Nemotron",
                "multiplier": round(mult, 3), "reason": reason, "high_impact": high[:8]}


def guardian(positions, equity, peak_state, use_lf):
    with _span(use_lf, "desk.guardian.rules"):
        from risk_monitor import assess
        peak = equity
        try:
            from derisk import update_peak
            peak = update_peak(peak_state, equity) if peak_state else equity
        except Exception:
            if peak_state and os.path.exists(peak_state):
                try: peak = float(json.load(open(peak_state)).get("peak", equity))
                except Exception: peak = equity
        rep = assess(positions, equity, peak)
        return {"role": "Risk Guardian", "model": "rules + drawdown ladder",
                "multiplier": round(float(rep.get("derisk_mult", 1.0)), 3),
                "telemetry": {k: rep[k] for k in ("gross_leverage", "net_leverage", "margin_usage",
                              "max_name_share", "margin_level") if k in rep},
                "drawdown": rep.get("drawdown", 0.0), "derisk_level": rep.get("derisk_level", "normal"),
                "warnings": rep.get("warnings", [])}


def advisor(book, an, gd, use_lf):
    with _span(use_lf, "desk.advisor.claude"):
        tgt = book.get("targets", {})
        top = sorted(tgt.items(), key=lambda kv: -abs(kv[1].get("notional", 0)))[:4]
        topdesc = ", ".join(f"{s} {'long' if t.get('notional', 0) > 0 else 'short'} "
                            f"${abs(t.get('notional', 0)):,.0f}" for s, t in top)
        ctx = (f"Book: gross {book.get('gross_leverage','?')}x across {len(tgt)} names, net "
               f"{gd['telemetry'].get('net_leverage','?')}x. Largest: {topdesc}. "
               f"Analyst event-risk x{an['multiplier']} ({an['reason']}). "
               f"Guardian drawdown {gd.get('drawdown',0)*100:.1f}% level '{gd.get('derisk_level')}'.")
        prompt = ("You are the strategy advisor on a market-neutral FX/metals desk in a trading "
                  "competition. In 80 words or fewer, explain in plain English what this book is "
                  "positioned for and the single most important risk. Be concrete and grounded in the "
                  "numbers; do not invent figures and never recommend increasing exposure.\n\n" + ctx)
        text = None
        try:
            import ai_gateway
            if ai_gateway.configured():
                text = ai_gateway.chat(CLAUDE_MODEL, prompt, provider="auto", max_tokens=220)
        except Exception:
            text = None
        if not text:
            text = (f"Market-neutral momentum book at {book.get('gross_leverage','?')}x gross across "
                    f"{len(tgt)} names; largest exposures: {topdesc}. Event-risk overlay "
                    f"x{an['multiplier']}; drawdown {gd.get('drawdown',0)*100:.1f}%. Key risk: "
                    f"concentration in the top name plus any high-impact event the analyst is watching.")
        return {"role": "Strategy Advisor", "model": "Anthropic Claude", "narrative": text.strip()}


def main():
    ap = argparse.ArgumentParser(description="Multi-agent AI trading desk (advisory, reduce-only)")
    ap.add_argument("--book", required=True, help="book.json from live_runner.py")
    ap.add_argument("--headlines", default="")
    ap.add_argument("--peak-state", default="")
    ap.add_argument("--emit", default="")
    ap.add_argument("--logfire", action="store_true")
    args = ap.parse_args()

    book = json.load(open(args.book)); tgt = book.get("targets", {})
    equity = float(book.get("equity", 1_000_000))
    positions = {s: float(t.get("notional", 0)) for s, t in tgt.items()}

    with _span(args.logfire, "desk.cycle"):
        an = analyst(args.headlines, args.logfire)
        gd = guardian(positions, equity, args.peak_state, args.logfire)
        ad = advisor(book, an, gd, args.logfire)
        final = round(min(1.0, an["multiplier"], gd["multiplier"]), 3)
        adj_gross = round(float(book.get("gross_leverage", 0)) * final, 2)
        decision = {"ts": book.get("ts"), "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "agents": {"analyst": an, "guardian": gd, "advisor": ad},
                    "final_overlay": final, "base_gross": book.get("gross_leverage"),
                    "adjusted_gross": adj_gross, "action": "REDUCE" if final < 1.0 else "HOLD"}

    t = gd["telemetry"]
    print("\n=============== QUANTHACK AI TRADING DESK ===============")
    print(f"  {decision['ts']}     base gross {decision['base_gross']}x")
    print(f"  [Market Analyst   | {an['model']:<15}] risk x{an['multiplier']:.2f}  {an['reason']}")
    if an["high_impact"]:
        print(f"       watch: {'; '.join(an['high_impact'][:4])}")
    print(f"  [Risk Guardian    | rules + ladder ] gross {t.get('gross_leverage')}x  net {t.get('net_leverage')}x  "
          f"margin {t.get('margin_usage',0)*100:.0f}%  top {t.get('max_name_share',0)*100:.0f}%  "
          f"dd {gd.get('drawdown',0)*100:.1f}% -> x{gd['multiplier']:.2f}")
    for w in gd["warnings"]:
        print(f"       ! {w}")
    print(f"  [Strategy Advisor | {ad['model']:<15}] {ad['narrative']}")
    print(f"  [Executor         | deterministic  ] final overlay x{final:.2f} -> adjusted gross "
          f"{adj_gross}x   ({decision['action']})")
    print("=========================================================\n")
    if args.emit:
        json.dump(decision, open(args.emit, "w"), indent=2); print(f"wrote {args.emit}")


if __name__ == "__main__":
    main()
