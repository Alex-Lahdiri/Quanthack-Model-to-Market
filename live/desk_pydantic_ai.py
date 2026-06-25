"""
Pydantic-AI-native trading desk (typed agents, validated outputs) -- the idiomatic way to
build a validated multi-agent LLM system on the Pydantic stack.

The desk's Market Analyst is expressed as a pydantic-ai Agent whose output is a *typed,
validated* RegimeRead model (the LLM literally cannot return an out-of-range multiplier).
Advisory / reduce-only, like desk.py.

Model choice: prefers Anthropic Claude (handles pydantic-ai's structured tool-calls natively).
NVIDIA's NIM endpoint rejects pydantic-ai's `strict` tool schema, so NVIDIA is only used if
no Anthropic key is set. Requires `pip install pydantic-ai`; falls back to desk.py otherwise.

  python live/desk_pydantic_ai.py --book book.json --headlines live/headlines.txt --emit desk_decision.json
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def _build_model():
    """Prefer Claude (native pydantic-ai tool support); fall back to NVIDIA OpenAI-compatible."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        from pydantic_ai.models.anthropic import AnthropicModel
        try:
            from pydantic_ai.providers.anthropic import AnthropicProvider
            return AnthropicModel(CLAUDE_MODEL, provider=AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"]))
        except Exception:
            return AnthropicModel(CLAUDE_MODEL)   # picks up ANTHROPIC_API_KEY from env
    # OpenAI-compatible (NVIDIA) fallback -- may hit the 'strict' schema limitation
    try:
        from pydantic_ai.models.openai import OpenAIChatModel as _OAModel
    except Exception:
        from pydantic_ai.models.openai import OpenAIModel as _OAModel
    from pydantic_ai.providers.openai import OpenAIProvider
    return _OAModel(os.environ.get("NEMOTRON_MODEL", "nvidia/nemotron-mini-4b-instruct"),
                    provider=OpenAIProvider(base_url=NVIDIA_BASE, api_key=os.environ["NVIDIA_API_KEY"]))


def run_pydantic_ai(book):
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent

    class RegimeRead(BaseModel):
        stance: str = Field(description="favorable | neutral | unfavorable")
        rationale: str = Field(description="one concise sentence, grounded in the book")
        overlay: float = Field(ge=0.3, le=1.0, description="reduce-only exposure multiplier; 1.0 = no change")

    analyst = Agent(_build_model(), output_type=RegimeRead, system_prompt=(
        "You are the market analyst on a market-neutral FX/metals competition desk. Read the book and "
        "return a REDUCE-ONLY exposure multiplier in [0.3, 1.0] (1.0 = no change; never above 1.0), a "
        "stance, and a one-sentence rationale. You can only cut risk, never add."))

    tgt = book.get("targets", {})
    top = sorted(tgt.items(), key=lambda kv: -abs(kv[1].get("notional", 0)))[:5]
    ctx = (f"Book gross {book.get('gross_leverage')}x across {len(tgt)} names. Largest: "
           + ", ".join(f"{s} {round(t.get('notional', 0))}" for s, t in top))
    res = analyst.run_sync(ctx)
    out = getattr(res, "output", None) or getattr(res, "data", None)
    overlay = max(0.3, min(1.0, float(out.overlay)))
    return {"engine": "pydantic-ai", "model": "Claude (typed Agent)" if os.environ.get("ANTHROPIC_API_KEY") else "NVIDIA (typed Agent)",
            "stance": out.stance, "rationale": out.rationale, "overlay": round(overlay, 3)}


def main():
    ap = argparse.ArgumentParser(description="Pydantic-AI typed-agent desk (advisory)")
    ap.add_argument("--book", required=True)
    ap.add_argument("--headlines", default="")
    ap.add_argument("--emit", default="")
    args = ap.parse_args()
    book = json.load(open(args.book))

    out = None
    try:
        import pydantic_ai  # noqa: F401
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("NVIDIA_API_KEY"):
            out = run_pydantic_ai(book)
    except Exception as e:
        print(f"[pydantic-ai unavailable: {e}] -> falling back to the deterministic desk")
        out = None

    if out is None:
        cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "desk.py"), "--book", args.book]
        if args.headlines:
            cmd += ["--headlines", args.headlines]
        if args.emit:
            cmd += ["--emit", args.emit]
        subprocess.run(cmd)
        return

    print("\n===== PYDANTIC-AI DESK (typed agents) =====")
    print(f"  model: {out['model']}")
    print(f"  stance: {out['stance']}    overlay x{out['overlay']:.2f}")
    print("  " + out["rationale"].strip())
    print("===========================================\n")
    if args.emit:
        json.dump(out, open(args.emit, "w"), indent=2)


if __name__ == "__main__":
    main()
