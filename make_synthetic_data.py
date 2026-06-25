"""
Generate a small synthetic quote Parquet so the whole pipeline can be validated
TODAY, before the real 20GB Week-1 file finishes downloading.

Schema mimics a typical quote feed: timestamp, symbol, bid, ask. The data_loader
auto-detects these columns, so swapping in the real file later changes nothing
but the path.

Run:  python make_synthetic_data.py  ->  data/synthetic_quotes.parquet
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

# (symbol, start_price, annual_drift, annual_vol, spread_bps, beta_to_market)
INSTRUMENTS = [
    ("EURUSD", 1.08, 0.00, 0.07, 0.3, 0.2),
    ("GBPUSD", 1.27, 0.00, 0.08, 0.4, 0.2),
    ("USDJPY", 156.0, 0.00, 0.09, 0.4, -0.1),
    ("AUDUSD", 0.66, 0.00, 0.10, 0.5, 0.3),
    ("USDCHF", 0.90, 0.00, 0.07, 0.5, -0.1),
    ("XAUUSD", 2350.0, 0.05, 0.15, 1.5, 0.1),
    ("XAGUSD", 30.0, 0.04, 0.25, 2.0, 0.2),
    ("BTCUSD", 67000.0, 0.20, 0.60, 3.0, 1.0),
    ("ETHUSD", 3500.0, 0.18, 0.70, 3.0, 1.0),
    ("SOLUSD", 150.0, 0.15, 0.95, 4.0, 1.1),
    ("XRPUSD", 0.52, 0.05, 0.85, 4.0, 0.8),
    ("ADAUSD", 0.45, 0.03, 0.90, 4.0, 0.8),
]


def generate(n_days: int = 7, freq_min: int = 1, seed: int = 7,
             start: str = "2026-06-09 00:00:00") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = int(n_days * 24 * 60 / freq_min)
    dt = freq_min / (60 * 24 * 365)            # year fraction per step
    ts = pd.date_range(start=start, periods=steps, freq=f"{freq_min}min")

    market = rng.normal(0, 1, steps)           # common factor (shared shocks)
    frames = []
    for sym, p0, mu, sigma, spread_bps, beta in INSTRUMENTS:
        idio = rng.normal(0, 1, steps)
        shock = (beta * market + idio) / np.sqrt(beta**2 + 1)   # unit-variance mix
        logret = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shock
        mid = p0 * np.exp(np.cumsum(logret))
        half = mid * (spread_bps / 1e4) / 2
        frames.append(pd.DataFrame({
            "timestamp": ts,
            "symbol": sym,
            "bid": mid - half,
            "ask": mid + half,
        }))
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "synthetic_quotes.parquet")
    df = generate()
    df.to_parquet(out_path, index=False)
    print(f"wrote {len(df):,} rows x {df['symbol'].nunique()} instruments -> {out_path}")
    print(df.groupby("symbol")["bid"].agg(["first", "last"]).round(4))


if __name__ == "__main__":
    main()
