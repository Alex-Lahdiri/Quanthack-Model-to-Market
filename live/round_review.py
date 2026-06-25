"""
Post-round red-team review (Anthropic Claude, advisory).

Given a round's start/end equity and the latest book, Claude writes a short
"what worked / what to change" memo critiquing the risk posture for the next round.
Advisory only -- it never changes weights. Falls back to a deterministic memo with no key.

  python live/round_review.py --book book.json --round 1 --start-equity 1000000 --end-equity 1012000 --emit review.json
"""
from __future__ import annotations
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def main():
    ap = argparse.ArgumentParser(description="Post-round Claude red-team memo (advisory)")
    ap.add_argument("--book", default="")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--start-equity", type=float, default=1_000_000)
    ap.add_argument("--end-equity", type=float, default=None)
    ap.add_argument("--emit", default="")
    args = ap.parse_args()

    book = json.load(open(args.book)) if args.book and os.path.exists(args.book) else {}
    tgt = book.get("targets", {})
    end_eq = args.end_equity if args.end_equity is not None else float(book.get("equity", args.start_equity))
    ret = (end_eq / args.start_equity - 1) * 100
    top = sorted(tgt.items(), key=lambda kv: -abs(kv[1].get("notional", 0)))[:5]
    summary = {"round": args.round, "round_return_pct": round(ret, 2), "gross": book.get("gross_leverage"),
               "top_positions": {s: round(t.get("notional", 0)) for s, t in top}}
    prompt = ("You are a risk officer red-teaming a market-neutral FX/metals book after a competition round "
              "(scored 70% return, 15% drawdown, 10% Sharpe, 5% discipline; knockout, equity carries). In 110 "
              "words or fewer: what the result implies, the biggest risk in the current posture, and ONE concrete "
              "adjustment for next round (e.g., gross up/down, trim a concentrated name). Be specific and grounded; "
              "never recommend breaching risk limits.\n\n" + json.dumps(summary, indent=2))

    memo = None
    try:
        import ai_gateway
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PYDANTIC_GATEWAY_KEY"):
            memo = ai_gateway.chat(CLAUDE_MODEL, prompt, provider="auto", max_tokens=360)
    except Exception:
        memo = None
    if not memo:
        nxt = "down" if ret < -1 else ("up one notch" if ret > 2 else "hold")
        big = list(summary["top_positions"])[:1]
        memo = (f"[deterministic] Round {args.round}: return {ret:+.2f}% at gross {book.get('gross_leverage','?')}x. "
                f"Biggest risk: concentration in {big}. Next round: take gross {nxt}, keep the dd-guard on, and re-run "
                f"the gross planner with your new standing.")

    print("\n===== CLAUDE -- POST-ROUND RED-TEAM MEMO =====")
    print(f"  round {args.round} | return {ret:+.2f}% | gross {book.get('gross_leverage','?')}x")
    print("  " + memo.strip().replace("\n", "\n  "))
    print("==============================================\n")
    if args.emit:
        json.dump({"summary": summary, "memo": memo}, open(args.emit, "w"), indent=2)


if __name__ == "__main__":
    main()
