"""
Unified AI model router for the sponsor stack (advisory layer — never trades).

Routes calls to Claude (Anthropic), NVIDIA Nemotron, and Doubleword. Preferred path
is the **Pydantic AI Gateway** (one place for spend limits + Logfire tracing); if the
gateway isn't configured it falls back to the provider's direct API. Structured outputs
are validated with **Pydantic**. If nothing is configured, calls return None and callers
use a safe deterministic default.

Env (set what you have):
  PYDANTIC_GATEWAY_URL, PYDANTIC_GATEWAY_KEY     # Pydantic AI Gateway (OpenAI-compatible)
  ANTHROPIC_API_KEY                              # Claude (direct)
  NVIDIA_API_KEY                                 # Nemotron via build.nvidia.com (OpenAI-compatible)
  LOGFIRE_TOKEN                                  # tracing (optional)
Model ids: e.g. "claude-sonnet-4-6", "nvidia/nemotron-3-nano-30b-a3b", "doubleword/<model>".
"""
from __future__ import annotations
import json, os, re
from typing import Optional, Type

NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"


def _logfire_span(name, **kw):
    try:
        import logfire
        if os.environ.get("LOGFIRE_TOKEN"):
            logfire.configure()
            return logfire.span(name, **kw)
    except Exception:
        pass
    class _Null:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return _Null()


def _openai_call(base_url, api_key, model, prompt, system, max_tokens):
    try:
        from openai import OpenAI
    except Exception:
        return None
    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        r = client.chat.completions.create(model=model, messages=msgs, max_tokens=max_tokens, temperature=0)
        msg = r.choices[0].message
        # Reasoning models may leave .content empty and put text in .reasoning_content,
        # or wrap it in <think>...</think>. Capture whichever has the answer.
        content = msg.content or getattr(msg, "reasoning_content", "") or ""
        if "</think>" in content:
            content = content.split("</think>")[-1]
        return content.strip() or None
    except Exception as e:
        print(f"[ai_gateway openai call failed: {e}]")
        return None


def chat(model: str, prompt: str, provider: str = "auto", system: str = "", max_tokens: int = 500) -> Optional[str]:
    """Return model text, or None if no backend is configured/available."""
    with _logfire_span("ai_gateway.chat", model=model, provider=provider):
        gw_url, gw_key = os.environ.get("PYDANTIC_GATEWAY_URL"), os.environ.get("PYDANTIC_GATEWAY_KEY")
        # 1) Pydantic AI Gateway (preferred — ties Anthropic/Nemotron/Doubleword + Logfire together)
        if gw_url and gw_key and provider in ("auto", "gateway"):
            out = _openai_call(gw_url, gw_key, model, prompt, system, max_tokens)
            if out is not None:
                return out
        # 1b) Doubleword private inference (opt-in: provider='doubleword' or model 'doubleword/...')
        if (provider == "doubleword" or model.startswith("doubleword/")) and \
           os.environ.get("DOUBLEWORD_URL") and os.environ.get("DOUBLEWORD_KEY"):
            out = _openai_call(os.environ["DOUBLEWORD_URL"], os.environ["DOUBLEWORD_KEY"],
                               model.split("/", 1)[-1], prompt, system, max_tokens)
            if out is not None:
                return out
        # 2) Direct provider fallbacks. (Don't route claude-* models to NVIDIA in auto mode.)
        if (provider in ("auto", "nvidia") or model.startswith("nvidia/")) \
           and not model.lower().startswith("claude") and os.environ.get("NVIDIA_API_KEY"):
            out = _openai_call(NVIDIA_BASE, os.environ["NVIDIA_API_KEY"], model, prompt, system, max_tokens)
            if out is not None:
                return out
        if (provider in ("auto", "anthropic") or model.startswith("claude")) and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                c = anthropic.Anthropic()
                m = c.messages.create(model=model, max_tokens=max_tokens,
                                      system=system or "You are a precise trading-ops assistant.",
                                      messages=[{"role": "user", "content": prompt}])
                return m.content[0].text
            except Exception as e:
                print(f"[ai_gateway anthropic failed: {e}]")
        return None


def structured(model: str, prompt: str, schema: Type, provider: str = "auto",
               system: str = "", max_tokens: int = 500):
    """Call a model and validate the JSON reply against a Pydantic model. None on failure."""
    txt = chat(model, prompt + "\n\nReply with ONLY a JSON object.", provider=provider,
               system=system, max_tokens=max_tokens)
    if not txt:
        return None
    try:
        s = txt[txt.find("{"): txt.rfind("}") + 1]
        return schema(**json.loads(s))
    except Exception as e:
        print(f"[ai_gateway structured parse failed: {e}]")
        return None


def list_models(provider: str = "nvidia") -> list:
    """Available model ids for a provider's OpenAI-compatible endpoint ([] on failure)."""
    if provider == "nvidia":
        base, key = NVIDIA_BASE, os.environ.get("NVIDIA_API_KEY")
    elif provider == "gateway":
        base, key = os.environ.get("PYDANTIC_GATEWAY_URL"), os.environ.get("PYDANTIC_GATEWAY_KEY")
    else:
        return []
    if not (base and key):
        return []
    try:
        from openai import OpenAI
        return [m.id for m in OpenAI(base_url=base, api_key=key).models.list().data]
    except Exception as e:
        print(f"[ai_gateway list_models failed: {e}]")
        return []


_NEMOTRON_CACHE = None


def resolve_nemotron_model(default: str = "nvidia/llama-3.1-nemotron-70b-instruct") -> str:
    """Find a valid TEXT INSTRUCT Nemotron id from the live NVIDIA catalog; fall back to `default`.
    Makes the news gate immune to model-name drift -- it asks your key what it can call.
    Prefers a plain *instruct* model (replies directly) over reasoning/vision/safety/embed
    variants, and prefers the smaller one, since the gate's job is cheap text->JSON tagging."""
    global _NEMOTRON_CACHE
    if _NEMOTRON_CACHE:
        return _NEMOTRON_CACHE
    ids = [m for m in list_models("nvidia") if "nemotron" in m.lower()]

    def _size(m):
        n = re.findall(r"(\d+)b", m.lower())
        return int(n[0]) if n else 9999

    def _rank(m):
        ml = m.lower()
        skip = any(t in ml for t in ("vl", "vision", "omni", "video", "speech", "audio",
                                     "embed", "reward", "safety", "guard"))
        instruct = "instruct" in ml          # instruct models answer directly (no thinking channel)
        reasoning = "reasoning" in ml or "thinking" in ml
        return (skip, not instruct, reasoning, _size(m), len(m))   # clean small instruct first

    ids.sort(key=_rank)
    _NEMOTRON_CACHE = ids[0] if ids else default
    return _NEMOTRON_CACHE


def configured() -> bool:
    return bool(os.environ.get("PYDANTIC_GATEWAY_KEY") or os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("NVIDIA_API_KEY") or os.environ.get("DOUBLEWORD_KEY"))
