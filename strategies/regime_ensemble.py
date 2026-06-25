"""
Direction #3: multi-horizon momentum ensemble + a self-calibrating volatility
regime gate (scales exposure down when realized vol runs above its own median).
Kept deliberately parameter-light to limit overfitting. Judge it by whether it
smooths the block-to-block lumpiness, not by its headline Sharpe.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .base import Strategy


class RegimeEnsembleMomentum(Strategy):
    name = "regime_ensemble"

    def __init__(self, windows=(240, 480, 960), vol_window=480, smooth=48,
                 target_gross=4.0, regime_window=960, gate_lo=0.4, gate_hi=1.3, eps=1e-8):
        self.windows = tuple(windows); self.vol_window = vol_window; self.smooth = smooth
        self.target_gross = target_gross; self.regime_window = regime_window
        self.gate_lo = gate_lo; self.gate_hi = gate_hi; self.eps = eps; self.W = None

    def precompute(self, panel: pd.DataFrame) -> None:
        self.panel = panel
        ret = np.log(panel).diff()
        # ensemble: average of cross-sectionally z-scored momentum across horizons
        alpha = None
        for w in self.windows:
            mom = panel.pct_change(w)
            z = mom.sub(mom.mean(axis=1), axis=0).div(mom.std(axis=1) + self.eps, axis=0)
            alpha = z if alpha is None else alpha + z
        alpha = (alpha / len(self.windows)).ewm(halflife=self.smooth, min_periods=1).mean()
        # inverse-vol sizing, gross-normalized
        vol = ret.rolling(self.vol_window).std()
        w = alpha / (vol + self.eps)
        w = w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).mul(self.target_gross)
        # self-calibrating vol-regime gate (causal): risk-off when vol > its median
        port_ret = (w.shift(1) * ret).sum(axis=1)
        realized = port_ret.rolling(self.regime_window).std()
        med = realized.rolling(self.regime_window).median()
        gate = (med / (realized + self.eps)).clip(self.gate_lo, self.gate_hi).shift(1).fillna(1.0)
        self.W = w.mul(gate, axis=0).fillna(0.0)

    def target_weights(self, t, history):
        if t in self.W.index:
            return self.W.loc[t]
        return pd.Series(0.0, index=self.panel.columns)
