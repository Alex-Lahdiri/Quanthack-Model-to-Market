"""
News/event RISK GATE (advisory, risk-REDUCING only).

Reads recent headlines (one per line) and, via NVIDIA Nemotron (cheap bulk impact
tagging) + Claude (synthesis) through the Pydantic gateway, returns a gross-exposure
multiplier in [0.3, 1.0]. It can ONLY cut exposure ahead of high-impact events; it can
never increase it and never overrides the deterministic risk engine. With no AI
configured it returns 1.0 (no change) — so the system is safe by default.

  python news_risk_gate.py --headlines headlines.txt
"""
from __future__ import annotations
import argparse, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_gateway

try:
    from pydantic import BaseModel, Field, field_validator
    class RiskGate(BaseModel):
        multiplier: float = Field(ge=0.3, le=1.0)
        reason: str = ""
        high_impact: list[str] = []
        @field_validator("multiplier")
        @classmethod
        def _clamp(cls, v): return max(0.3, min(1.0, float(v)))
    HAVE_PYDANTIC = True
except Exception:
    HAVE_PYDANTIC = False
    class RiskGate:                      # minimal fallback
        def __init__(self, multiplier=1.0, reason="", high_impact=None):
            self.multiplier = max(0.3, min(1.0, float(multiplier)))
            self.reason = reason; self.high_impact = high_impact or []


SAFE = lambda why: RiskGate(multiplier=1.0, reason=why, high_impact=[])
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def _nemotron_model() -> str:
    # explicit override wins; otherwise discover a valid id from the live catalog
    return os.environ.get("NEMOTRON_MODEL") or ai_gateway.resolve_nemotron_model()


def assess(headlines: list[str]) -> "RiskGate":
    headlines = [h.strip() for h in headlines if h.strip()]
    if not headlines or not ai_gateway.configured():
        return SAFE("AI gate disabled (no headlines or no API config) -> no change")
    # 1) Nemotron: cheap bulk impact tagging (high/med/low) for each headline
    tag_prompt = ("Tag each headline's near-term FX/metals market impact as high/med/low. "
                  "Return JSON {\"high\": [headlines...]}:\n" + "\n".join(f"- {h}" for h in headlines[:50]))
    high = []
    if HAVE_PYDANTIC:
        class _High(BaseModel):
            high: list[str] = []
        # provider="nvidia" forces the Nemotron call onto NVIDIA's endpoint (for the reward)
        tagged = ai_gateway.structured(_nemotron_model(), tag_prompt, _High, provider="nvidia", max_tokens=1024)
        high = tagged.high if tagged else []
    # 2) Claude (if configured): refine into a nuanced multiplier from the high-impact set
    syn = ("You are a risk officer for a market-neutral FX/metals book. Given these "
           "high-impact headlines, choose a gross-exposure multiplier in [0.3,1.0] "
           "(1.0 = normal, lower = trim risk ahead of events). Be conservative but not "
           "trigger-happy. JSON {\"multiplier\": float, \"reason\": str, \"high_impact\": [str]}:\n"
           + "\n".join(f"- {h}" for h in (high or headlines)[:20]))
    if HAVE_PYDANTIC and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PYDANTIC_GATEWAY_KEY")):
        gate = ai_gateway.structured(CLAUDE_MODEL, syn, RiskGate, provider="auto", max_tokens=300)
        if gate:
            return gate
    # 3) Nemotron-only fallback: deterministic risk-off scaled by the count of high-impact items.
    #    Makes the gate fully functional on NVIDIA alone (no Claude required), still reduce-only.
    if high:
        n = len(high)
        mult = max(0.5, 1.0 - 0.15 * n)        # 1 -> 0.85, 2 -> 0.70, 3+ -> floor 0.50
        return RiskGate(multiplier=mult,
                        reason=f"Nemotron flagged {n} high-impact headline(s); trimming gross",
                        high_impact=high[:10])
    return SAFE("Nemotron found no high-impact events -> no change")


def main():
    ap = argparse.ArgumentParser(description="News/event risk gate (risk-reduce only)")
    ap.add_argument("--headlines", required=True, help="text file, one headline per line")
    args = ap.parse_args()
    g = assess(open(args.headlines).read().splitlines())
    print(f"multiplier {g.multiplier:.2f} | {g.reason}")
    if g.high_impact:
        print("high-impact:", "; ".join(g.high_impact))


if __name__ == "__main__":
    main()
