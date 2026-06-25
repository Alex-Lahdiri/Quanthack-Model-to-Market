"""
ask.py -- "Ask the Desk": plain-English Q&A over the LIVE book + risk, answered by Anthropic
Claude (Nemotron fallback, deterministic fallback). READ-ONLY -- it never trades. Logfire-traced.

  python live/ask.py "what's our risk right now?"
  python live/ask.py "why are we short silver?"
"""
from __future__ import annotations
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

def _span(name):
    try:
        import logfire
        if os.environ.get("LOGFIRE_TOKEN"): logfire.configure()
        return logfire.span(name)
    except Exception:
        class _N:
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _N()

def gather_state():
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            a = mt5.account_info()
            if a:
                eq = float(a.equity); used = float(getattr(a, "margin", 0) or 0); lev = float(getattr(a, "leverage", 30) or 30)
                pos = [{"symbol": p.symbol, "side": "long" if p.type == 0 else "short", "profit": float(p.profit), "lots": float(p.volume)} for p in (mt5.positions_get() or [])]
                mt5.shutdown()
                return {"source": "MT5 (live)", "equity": round(eq), "gross_leverage": round(used*lev/eq, 2) if eq else 0,
                        "margin_level_pct": round(eq/used*100) if used > 0 else None, "positions": pos}
            mt5.shutdown()
    except Exception:
        pass
    bp = os.path.join(ROOT, "book.json")
    if os.path.exists(bp):
        b = json.load(open(bp)); tgt = b.get("targets", {})
        pos = [{"symbol": s, "side": "long" if t.get("notional", 0) > 0 else "short", "notional": t.get("notional")} for s, t in tgt.items()]
        return {"source": "book.json (last cycle)", "equity": b.get("equity"), "gross_leverage": b.get("gross_leverage"), "positions": pos}
    return {"source": "none", "positions": [], "note": "no live MT5 and no book.json - run a cycle first"}

def context_str(st):
    pos = st.get("positions", [])
    key = lambda p: -abs(p.get("notional") or p.get("profit") or 0)
    top = sorted(pos, key=key)[:8]
    lines = [f"  {p['symbol']:<8} {p['side']:<5} " + (f"${abs(p['notional']):,.0f}" if p.get("notional") is not None else f"P/L ${p.get('profit',0):+,.0f}") for p in top]
    return (f"Source: {st.get('source')}\nEquity: {st.get('equity')}\nGross leverage: {st.get('gross_leverage')}x\n"
            f"Margin level: {st.get('margin_level_pct')}%\nPositions ({len(pos)}):\n" + ("\n".join(lines) if lines else "  (flat)")
            + (f"\nNote: {st['note']}" if st.get("note") else ""))

def main():
    ap = argparse.ArgumentParser(description="Ask the Desk -- NL Q&A over the live book (read-only)")
    ap.add_argument("question", nargs="*")
    args = ap.parse_args()
    q = " ".join(args.question) or "Summarise our current risk and positioning."
    with _span("ask_the_desk"):
        ctx = context_str(gather_state())
        prompt = ("You are the risk & strategy desk for a market-neutral FX/metals book in a trading competition "
                  "(scored 70% return / 15% drawdown / 10% Sharpe / 5% discipline). Answer concisely and ONLY from "
                  "the state below; cite the numbers; never advise increasing exposure beyond prudent limits.\n\n"
                  f"LIVE STATE:\n{ctx}\n\nQUESTION: {q}")
        ans = None
        try:
            import ai_gateway
            if ai_gateway.configured():
                ans = ai_gateway.chat(CLAUDE_MODEL, prompt, provider="auto", max_tokens=320)
        except Exception:
            ans = None
        print("\n=== ASK THE DESK ===")
        print(ans or f"(AI not configured -- raw desk state)\n{ctx}")
        print("====================")

if __name__ == "__main__":
    main()
