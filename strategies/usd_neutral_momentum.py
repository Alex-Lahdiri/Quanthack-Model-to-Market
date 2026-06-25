"""
v2 strategy — built directly from the alpha-research findings:

  * Multi-horizon momentum (blend ~2h and ~8h lookbacks): the IC map showed the
    edge lives in hours-of-lookback predicting hours-forward, not minutes.
  * USD / common-factor neutralization: PC1 was 52% of variance, so we estimate
    each instrument's rolling beta to the equal-weight factor and project it out
    of the weights -> the book carries ~zero net factor (USD) exposure.
  * Inverse-vol sizing + per-name cap: silver/gold dominate vol and USDJPY is
    fat-tailed, so size by 1/vol and hard-cap any single name's share of gross.
  * Time-of-day gating: scale gross up in the 11-16 UTC London/NY window and
    down in the 20-21 UTC lull, where there is little vol or edge.

Signal is pure direction (cross-sectional z-scored momentum); sizing is separate
(1/vol), so volatility is only counted once.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _tod_multipliers() -> dict[int, float]:
    m = {h: 0.5 for h in range(24)}
    for h in (11, 12, 13, 14, 15, 16):   # London/NY overlap — most vol & edge
        m[h] = 1.0
    for h in (7, 8, 9, 10, 17, 18, 19):  # active but secondary
        m[h] = 0.7
    for h in (20, 21):                   # dead zone
        m[h] = 0.3
    return m


class UsdNeutralMomentum(Strategy):
    name = "usd_neutral_momentum"

    def __init__(self, windows=(120, 480), vol_window: int = 480,
                 beta_window: int = 960, target_gross: float = 6.0,
                 name_cap: float = 0.25, smooth_halflife: float = 12.0,
                 time_of_day: bool = True, neutralize: bool = True, eps: float = 1e-8):
        self.windows = tuple(windows)
        self.vol_window = vol_window
        self.beta_window = beta_window
        self.target_gross = target_gross
        self.name_cap = name_cap
        self.smooth_halflife = smooth_halflife
        self.time_of_day = time_of_day
        self.neutralize = neutralize
        self.eps = eps
        self.W: pd.DataFrame | None = None

    def precompute(self, panel: pd.DataFrame) -> None:
        self.panel = panel
        lr = np.log(panel).diff()
        eps = self.eps

        # 1) blended, cross-sectionally z-scored momentum (pure direction)
        alpha = None
        for L in self.windows:
            mom = panel.pct_change(L)
            z = mom.sub(mom.mean(axis=1), axis=0).div(mom.std(axis=1) + eps, axis=0)
            alpha = z if alpha is None else alpha + z
        alpha = alpha / len(self.windows)

        # 2) inverse-vol sizing
        vol = lr.rolling(self.vol_window).std()
        w = alpha / (vol + eps)

        # 3) neutralize the portfolio's loading on the common (USD) factor
        if self.neutralize:
            factor = lr.mean(axis=1)
            var = factor.rolling(self.beta_window).var()
            beta = lr.rolling(self.beta_window).cov(factor).div(var + eps, axis=0)
            num = (w * beta).sum(axis=1)
            den = (beta ** 2).sum(axis=1) + eps
            w = w.sub(beta.mul(num / den, axis=0))        # now sum_i w_i*beta_i ~ 0

        # 4) gross-normalize, per-name cap, renormalize
        w = self._normalize(w, self.target_gross)
        cap = self.name_cap * self.target_gross
        w = w.clip(lower=-cap, upper=cap)
        w = self._normalize(w, self.target_gross)

        # 5) time-of-day gross gating
        if self.time_of_day:
            mult = pd.Series(w.index.hour, index=w.index).map(_tod_multipliers()).astype(float)
            w = w.mul(mult, axis=0)

        # 6) smooth to cut turnover
        if self.smooth_halflife and self.smooth_halflife > 0:
            w = w.ewm(halflife=self.smooth_halflife, min_periods=1).mean()

        self.W = w.fillna(0.0)

    @staticmethod
    def _normalize(w: pd.DataFrame, gross: float) -> pd.DataFrame:
        g = w.abs().sum(axis=1).replace(0, np.nan)
        return w.div(g, axis=0).mul(gross)

    def target_weights(self, t, history: pd.DataFrame) -> pd.Series:
        if self.W is None:
            raise RuntimeError("Call precompute(panel) before backtesting.")
        if t not in self.W.index:
            return pd.Series(0.0, index=self.panel.columns)
        return self.W.loc[t]
