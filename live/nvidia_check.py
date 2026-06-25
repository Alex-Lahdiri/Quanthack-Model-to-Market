"""
NVIDIA Nemotron connectivity check -- finds a model that actually works on YOUR account.

The catalog /models list includes models with no live endpoint for a given account
(they 404 on inference), and some Nemotron models are "reasoning" models that need a big
token budget. So this probes candidate Nemotron models in a sensible order (plain instruct
first, then small nano), with a generous token budget, and stops at the first that returns
real text. It then tells you exactly which id to pin. Nothing here trades.

Setup (PowerShell):
  $env:NVIDIA_API_KEY="nvapi-...your real key..."   # from build.nvidia.com
  pip install openai pydantic
  python live\nvidia_check.py
"""
from __future__ import annotations
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_gateway

DEMO = ('Tag each headline\'s near-term FX/metals market impact as high/med/low. '
        'Return ONLY JSON {"high": [headlines...]}:\n'
        "- US CPI prints hotter than expected, dollar jumps\n"
        "- ECB holds rates, dovish tone\n"
        "- Gold steady in a quiet Asian session")


def _candidates(ids):
    nemo = [m for m in ids if "nemotron" in m.lower()]

    def _size(m):
        n = re.findall(r"(\d+)b", m.lower())
        return int(n[0]) if n else 9999

    def _rank(m):
        ml = m.lower()
        skip = any(t in ml for t in ("vl", "vision", "omni", "video", "speech", "audio",
                                     "embed", "reward", "safety", "guard"))
        instruct = "instruct" in ml
        reasoning = "reasoning" in ml or "thinking" in ml
        return (skip, not instruct, reasoning, _size(m), len(m))

    nemo.sort(key=_rank)
    return nemo


def main():
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        sys.exit("NVIDIA_API_KEY not set. Get one (nvapi-...) at build.nvidia.com, set it, retry.")
    print(f"NVIDIA_API_KEY detected (...{key[-4:]})  endpoint: {ai_gateway.NVIDIA_BASE}")

    ids = ai_gateway.list_models("nvidia")
    if not ids:
        sys.exit("Could not list models -- check the key is valid (nvapi-...) and you have network access.")

    pinned = os.environ.get("NEMOTRON_MODEL")
    order, seen = [], set()
    for m in ([pinned] if pinned else []) + _candidates(ids):
        if m and m not in seen:
            order.append(m); seen.add(m)

    print("\nprobing for a Nemotron model with a live endpoint on your account "
          "(stops at the first that replies)...")
    working = None
    for m in order[:8]:
        out = ai_gateway.chat(m, DEMO, provider="nvidia", max_tokens=2048)
        ok = bool(out and out.strip())
        print(f"  {'OK  ' if ok else 'no  '} {m}")
        if ok:
            working = (m, out)
            break

    if not working:
        print("\nNone of the candidates returned text. Paste this output to Claude and we'll pick another.")
        return
    m, out = working
    print(f"\n>>> WORKING MODEL:  {m}")
    print("--- Nemotron reply ---")
    print(out.strip()[:600])
    print(f'\nPin it so every run + Task Scheduler uses it:\n  setx NEMOTRON_MODEL "{m}"')
    print("\nReal NVIDIA Nemotron inference is live in your stack. Add --logfire on the gate to trace it.")


if __name__ == "__main__":
    main()
