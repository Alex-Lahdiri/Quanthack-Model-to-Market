# Sponsor-tech plan (Technology Prize)

## Principle: AI is the co-pilot, not the trader
The deterministic quant core makes every trade decision (validated, overfit-checked). The AI
layer only does **research, ops/risk briefings, observability, and a risk-REDUCE-only news gate**.
It can never size up or override the risk engine. This wins the tech prize *and* keeps the trading
edge clean (no overfitting from AI signals).

## How each sponsor is used (already built - in `live/`)
| Sponsor | Use in our system | Code |
|---|---|---|
| **Anthropic / Claude** | (1) the whole system was built agentically with Claude; (2) live ops/risk briefings + round summaries; (3) synthesis step of the news risk-gate; (4) auto-draft submission text | `ops_agent.py`, `news_risk_gate.py`, `ai_gateway.py` |
| **NVIDIA Nemotron** | cheap, fast **bulk headline impact-tagging** (Nano model via build.nvidia.com, OpenAI-compatible) feeding the risk gate; optional offline fine-tune on the Northflank GPU | `ai_gateway.py` (nvidia route), `news_risk_gate.py` |
| **Pydantic** | (1) **AI Gateway** routes ALL model calls (Claude/Nemotron/Doubleword) through one endpoint with spend limits; (2) **Logfire** traces every agent/gate call; (3) **Pydantic models** validate the LLM JSON outputs | `ai_gateway.py`, `news_risk_gate.py` (`RiskGate` model) |
| **Northflank** | 24/7 host for the AI co-pilot layer (ops agent + risk gate + Logfire) and non-MT5 compute; optional GPU for the Nemotron fine-tune. (MT5 execution stays on a Windows host.) | `Dockerfile`, `northflank.json` |
| **Doubleword** | cheap **batch/offline** inference (e.g. label a month of news to backtest the event overlay) via the Pydantic gateway - their own framing: batch, not real-time | `ai_gateway.py` (gateway route) |

## Architecture
```
Windows host  : MT5 terminal -> feed_adapter -> live_runner -> mt5_bridge   (DETERMINISTIC TRADING)
Northflank/Lx : ai_gateway -> [Claude | Nemotron | Doubleword] via Pydantic Gateway
                -> ops_agent briefings  +  news risk-gate (multiplier <=1.0)  -> Logfire traces
live_runner reads the gate multiplier to OPTIONALLY trim gross. Humans approve via decision cards.
```

## What YOU need to do (claim + configure)
1. **Anthropic** - confirm credits; set `ANTHROPIC_API_KEY`. Test: `python live/ops_agent.py --status live/example_status.json --use-claude`.
2. **NVIDIA** - claim Nemotron at build.nvidia.com; set `NVIDIA_API_KEY`; pick a model id (e.g. `nvidia/nemotron-3-nano`) into `NEMOTRON_MODEL`. Test: `python live/news_risk_gate.py --headlines headlines.txt`.
3. **Pydantic** - create a Logfire project -> `LOGFIRE_TOKEN`; set up the AI Gateway -> `PYDANTIC_GATEWAY_URL` + `PYDANTIC_GATEWAY_KEY` (then all model calls route through it with spend caps + tracing).
4. **Northflank** - deploy the `live/` image; set the env vars above + a `/data` volume; (optional) GPU for a Nemotron fine-tune.
5. **Doubleword** - get access via the Pydantic gateway; use for batch NLP only.
6. On the host: `pip install anthropic openai pydantic logfire`.

## Maps to the §9 submission (due after Round 3, Jun 24)
- **GitHub repo** - push the package (`.gitignore` already excludes keys/big files).
- **Partner-tech overview** - this file + `SUBMISSION.md` (each sponsor + where it's used).
- **Data usage** - 20GB tick archive -> ingestion -> bars -> real-spread costs (`data_loader.py`, `batch_ingest.py`, `PLATFORM_NOTES.md`).
- **Demo** - `demo.sh` end-to-end + a Logfire trace + an `ops_agent`/`news_risk_gate` run. **Lead with the overfitting analysis (`overfit.py`)** - it's the differentiator.

## Honesty guardrails
- The AI layer can only **reduce** exposure or document - never increase risk, never bypass the risk engine.
- The news gate's trading value is **unproven** (no news backtest) - it's a prudent risk overlay + a genuine sponsor demo, **optional** to enable. Validate offline (Doubleword batch) before trusting it live.
