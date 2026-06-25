"""
Reference strategy: diversified, risk-adjusted cross-sectional signal.

`mode`:
  * "momentum"  -> long recent winners / short recent losers (trend).
  * "reversion" -> the opposite (fade recent moves). Short FX horizons often
    mean-revert, so this is worth comparing against momentum on real data.

Why this shape fits the 70/15/10/5 formula:
  * Cross-sectional + demeaned  -> roughly market-neutral, so a single asset
    crash doesn't wipe equity (protects Drawdown rank, avoids liquidation DQ).
  * Inverse-volatility sizing    -> each name contributes similar risk, which
    smooths the 15-min equity steps Sharpe is sampled on (protects Sharpe rank).
  * EMA-smoothed signal           -> positions evolve gradually instead of
    flipping every bar, which collapses turnover (and therefore cost bleed).
  * Gross target is a dial         -> raise `target_gross` to chase the 70%
    Return weight once you've validated it survives on the real data.

A STARTING POINT, not a finished edge. Tune mode / windows / gross / smoothing
on the real Parquet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class DiversifiedVolTarget(Strategy):
    name = "diversified_vol_target"

    def __init__(self, mom_window: int = 480, vol_window: int = 480,
                 target_gross: float = 6.0, smooth_halflife: float = 12.0,
                 market_neutral: bool = True, mode: str = "momentum",
                 eps: float = 1e-8):
        self.mom_window = mom_window
        self.vol_window = vol_window
        self.target_gross = target_gross
        self.smooth_halflife = smooth_halflife
        self.market_neutral = market_neutral
        self.mode = mode
        self.eps = eps
        self.W: pd.DataFrame | None = None

    def precompute(self, panel: pd.DataFrame) -> None:
        self.panel = panel
        logret = np.log(panel).diff()

        momentum = panel.pct_change(self.mom_window)        # causal
        vol = logret.rolling(self.vol_window).std()          # causal

        score = momentum / (vol + self.eps)
        if self.mode == "reversion":
            score = -score
        if self.market_neutral:
            score = score.sub(score.mean(axis=1), axis=0)
        if self.smooth_halflife and self.smooth_halflife > 0:
            score = score.ewm(halflife=self.smooth_halflife, min_periods=1).mean()

        gross = score.abs().sum(axis=1).replace(0, np.nan)
        weights = score.div(gross, axis=0).mul(self.target_gross)
        self.W = weights.fillna(0.0)

    def target_weights(self, t, history: pd.DataFrame) -> pd.Series:
        if self.W is None:
            raise RuntimeError("Call precompute(panel) before backtesting.")
        if t not in self.W.index:
            return pd.Series(0.0, index=self.panel.columns)
        return self.W.loc[t]
