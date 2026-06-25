# NVIDIA Nemotron implementation

This project uses **NVIDIA Nemotron** (via the NIM OpenAI-compatible endpoint,
`integrate.api.nvidia.com`) as a first-class decision-making component - not a demo bolt-on.

## Where Nemotron runs
1. **Regime Analyst inside Autopilot** (`live/autopilot.py`) - Nemotron reads the live regime
   (momentum IC, t-stats, a net-of-cost lever backtest) and returns a **Pydantic-validated**
   `AnalystView` (regime label + confidence). Its read feeds the Strategist and the governor.
2. **News / event-risk gate** (`live/news_risk_gate.py`) - Nemotron tags high-impact headlines and
   emits a **reduce-only** exposure multiplier ahead of events. It can only ever cut risk.
3. **Market Analyst in the multi-agent desk** (`live/desk.py`).

## Engineering details an NVIDIA reviewer cares about
- **Structured, validated outputs.** Every Nemotron response is parsed into a Pydantic model with
  hard bounds - a malformed or out-of-range reply is rejected and the system falls back to a safe
  deterministic default. The model advises; it can never breach a risk limit.
- **Catalog auto-resolver** (`resolve_nemotron_model` in `live/ai_gateway.py`) - queries the live
  NVIDIA model catalog and auto-selects a valid *text-instruct* Nemotron, ranking out
  vision/reasoning/embed/safety variants. The system is immune to model-name drift.
- **Multi-provider gateway** - one interface (`live/ai_gateway.py`) routes Nemotron alongside Claude
  and Doubleword, with Logfire tracing on every call.
- **Graceful degradation** - with no key set, every Nemotron-backed component falls back to a
  deterministic rule, so the system always runs.

## Try it
```
python live/nvidia_check.py         # verifies the key, lists + auto-resolves a Nemotron model
python live/autopilot.py --logfire  # Nemotron as the live regime Analyst (shadow mode)
```
