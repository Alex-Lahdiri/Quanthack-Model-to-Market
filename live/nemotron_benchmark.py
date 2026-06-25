"""
nemotron_benchmark.py -- benchmark NVIDIA Nemotron via the NIM API vs Doubleword private/self-host
inference: same regime-classification task to both, measuring latency + answer agreement.
Targets the NVIDIA "self-host Nemotron" criterion. Needs NVIDIA_API_KEY (+ DOUBLEWORD_URL/KEY).

  python live/nemotron_benchmark.py --n 5
"""
from __future__ import annotations
import argparse, os, sys, time, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_gateway

PROMPT = ("Classify this FX/metals regime as exactly one word -- trending, choppy, or reverting. "
          "Momentum IC (8h->4h) = +0.09 with t-stat 2.3; backtest Sharpe +0.11. One word only.")

def bench(provider, model, n):
    lat, ans = [], []
    for _ in range(n):
        t0 = time.time()
        out = ai_gateway.chat(model, PROMPT, provider=provider, max_tokens=12)
        lat.append(time.time() - t0); ans.append((out or "").strip().lower()[:16])
    return lat, ans

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=5); a = ap.parse_args()
    print("=== NEMOTRON: NIM API vs DOUBLEWORD (self-host) ===")
    results = {}
    legs = [("nvidia", ai_gateway.resolve_nemotron_model()),
            ("doubleword", "doubleword/" + os.environ.get("DOUBLEWORD_MODEL", "nemotron-mini-4b-instruct"))]
    for provider, model in legs:
        if provider == "nvidia" and not os.environ.get("NVIDIA_API_KEY"):
            print(f"  {provider}: skipped (no NVIDIA_API_KEY)"); continue
        if provider == "doubleword" and not (os.environ.get("DOUBLEWORD_URL") and os.environ.get("DOUBLEWORD_KEY")):
            print(f"  {provider}: skipped (no DOUBLEWORD_URL/KEY)"); continue
        lat, ans = bench(provider, model, a.n)
        results[provider] = ans
        print(f"  {provider:<11} model={model}")
        print(f"     median latency {st.median(lat)*1000:.0f} ms over {a.n} calls   answers={ans}")
    if len(results) == 2:
        agree = sum(1 for x, y in zip(*results.values()) if x.split()[0:1] == y.split()[0:1])
        print(f"\n  answer agreement: {agree}/{a.n}  (high agreement => self-host is a faithful drop-in)")

if __name__ == "__main__":
    main()
