"""
AI ops/risk briefing agent (advisory — never trades).

Reads current account status + the risk-engine assessment (+ optional leaderboard)
and produces a plain-English briefing with recommended actions. Uses Claude
(Anthropic sponsor) when ANTHROPIC_API_KEY is set; otherwise a deterministic
rule-based briefing so it always works. Logs to Pydantic Logfire if configured.

Run on a schedule (e.g., every 15 min, and once per round). It SUGGESTS; humans act.
"""
from __future__ import annotations
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as C
from risk_monitor import assess


def headroom(rep):
    return {
        "margin_headroom_to_penalty": round(C.MARGIN_PENALTY_TIERS[0] - rep["margin_usage"], 3),
        "leverage_headroom_to_penalty": round(C.LEVERAGE_PENALTY_TIERS[0] - rep["gross_leverage"], 2),
        "concentration_headroom": round(C.CONCENTRATION_PENALTY - rep["max_name_share"], 3),
        "margin_level": rep["margin_level"],
    }


def deterministic_brief(status, rep, hr, equity_change_pct):
    action = "HOLD — book is well within all limits."
    flags = []
    if rep["warnings"]:
        action = "REDUCE GROSS now — a penalty tier is breached."; flags = rep["warnings"]
    elif hr["margin_headroom_to_penalty"] < 0.05 or hr["leverage_headroom_to_penalty"] < 1.5:
        action = "TRIM exposure — approaching a penalty tier."
    elif equity_change_pct is not None and equity_change_pct < -4:
        action = "CONSIDER de-risking — drawdown building this round."
    lines = [
        "QUANTHACK OPS BRIEFING",
        f"  equity {status['equity']:,.0f}" + (f"  ({equity_change_pct:+.2f}% since round start)" if equity_change_pct is not None else ""),
        f"  gross {rep['gross_leverage']}x | net {rep['net_leverage']}x | margin {rep['margin_usage']:.0%} | "
        f"top-name {rep['max_name_share']:.0%} | margin-level {rep['margin_level']}",
        f"  headroom: margin {hr['margin_headroom_to_penalty']:.0%} | leverage {hr['leverage_headroom_to_penalty']:.1f}x | "
        f"concentration {hr['concentration_headroom']:.0%}",
        f"  >> {action}",
    ]
    if flags:
        lines += ["  warnings: " + "; ".join(flags)]
    return "\n".join(lines)


def claude_brief(payload, model):
    import anthropic
    client = anthropic.Anthropic()
    prompt = ("You are a risk/ops officer for a simulated trading competition scored 70% return, "
              "15% drawdown, 10% Sharpe, 5% discipline, with instant DQ on forced liquidation and point "
              "penalties for sustained margin>90%, leverage>28x, or single-name/net concentration>90%. "
              "Given this JSON status, write a <=120-word briefing: one-line health summary, the single most "
              "important risk, and a concrete recommended action (hold / trim / de-risk). Be calm and specific.\n\n"
              + json.dumps(payload, indent=2))
    msg = client.messages.create(model=model, max_tokens=400, messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text


def main():
    ap = argparse.ArgumentParser(description="AI ops/risk briefing (advisory)")
    ap.add_argument("--status", required=True, help="JSON {equity, positions:{sym:notional}, round_start_equity?}")
    ap.add_argument("--use-claude", action="store_true")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--logfire", action="store_true")
    args = ap.parse_args()

    s = json.load(open(args.status))
    rep = assess(s["positions"], s["equity"]); hr = headroom(rep)
    chg = None
    if s.get("round_start_equity"):
        chg = (s["equity"]/s["round_start_equity"] - 1) * 100
    payload = {"status": {k: s[k] for k in s if k != "positions"}, "risk": rep, "headroom": hr,
               "round_change_pct": chg, "n_positions": len(s["positions"])}

    brief = None
    if args.use_claude and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            brief = claude_brief(payload, args.model)
        except Exception as e:
            print(f"[claude unavailable: {e}] -> deterministic briefing")
    if brief is None:
        brief = deterministic_brief(s, rep, hr, chg)
    print(brief)

    if args.logfire:
        try:
            import logfire; logfire.configure()
            (logfire.warn if rep["warnings"] else logfire.info)("ops briefing", brief=brief, **rep)
        except Exception as e:
            print(f"[logfire unavailable: {e}]")


if __name__ == "__main__":
    main()
