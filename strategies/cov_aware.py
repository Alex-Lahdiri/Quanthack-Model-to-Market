"""
Covariance-aware portfolio construction (advanced sizing).

Same momentum *signal* as the champion, but sizing accounts for the full
covariance instead of just per-name vol:

  mode="mv"  : w propto Sigma_shrunk^{-1} . alpha   (mean-variance / characteristic
               portfolio with Ledoit-Wolf shrinkage -> robust inverse, downweights
               correlated/USD-factor-redundant names)
  mode="hrp" : Hierarchical Risk Parity risk weights (Lopez de Prado) times signal
               sign -> cluster-aware risk budgeting, no matrix inversion

Weights are recomputed on a rolling window every `cov_step` bars (causal) and held
between, matching the engine's rebalance cadence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

from .base import Strategy


def _quasi_diag(link, n):
    link = link.astype(int)
    items = [link[-1, 0], link[-1, 1]]
    while max(items) >= n:
        out = []
        for it in items:
            if it >= n:
                out += [link[it - n, 0], link[it - n, 1]]
            else:
                out.append(it)
        items = out
    return items


def _hrp_weights(window: pd.DataFrame) -> pd.Series:
    cols = list(window.columns)
    cov = window.cov().values
    corr = window.corr().fillna(0).values
    dist = np.sqrt(np.clip(0.5 * (1 - corr), 0, None))
    np.fill_diagonal(dist, 0.0)
    link = linkage(squareform(dist, checks=False), method="single")
    order = _quasi_diag(link, len(cols))
    w = np.ones(len(cols))
    clusters = [order]
    while clusters:
        nxt = []
        for c in clusters:
            if len(c) <= 1:
                continue
            s = len(c) // 2
            left, right = c[:s], c[s:]
            vl = _cluster_var(cov, left)
            vr = _cluster_var(cov, right)
            a = 1 - vl / (vl + vr + 1e-18)
            for i in left:
                w[i] *= a
            for i in right:
                w[i] *= (1 - a)
            nxt += [left, right]
        clusters = nxt
    return pd.Series(w, index=cols)


def _cluster_var(cov, idx):
    sub = cov[np.ix_(idx, idx)]
    iv = 1.0 / (np.diag(sub) + 1e-18)
    w = iv / iv.sum()
    return float(w @ sub @ w)


class CovAwareMomentum(Strategy):
    name = "cov_aware_momentum"

    def __init__(self, mom_window=480, ema=48, cov_window=480, cov_step=60,
                 target_gross=4.0, mode="mv", eps=1e-6):
        self.mom_window = mom_window; self.ema = ema
        self.cov_window = cov_window; self.cov_step = cov_step
        self.target_gross = target_gross; self.mode = mode; self.eps = eps
        self.W = None

    def precompute(self, panel: pd.DataFrame) -> None:
        self.panel = panel
        ret = np.log(panel).diff()
        mom = panel.pct_change(self.mom_window)
        alpha = mom.sub(mom.mean(axis=1), axis=0)            # cross-sectional demean
        alpha = alpha.ewm(halflife=self.ema, min_periods=1).mean()

        cols = list(panel.columns)
        W = pd.DataFrame(np.nan, index=panel.index, columns=cols)
        for i in range(self.cov_window, len(panel), self.cov_step):
            win = ret.iloc[i - self.cov_window:i].dropna(axis=1, how="any")
            a = alpha.iloc[i].reindex(win.columns).fillna(0.0)
            if win.shape[1] < 2 or win.shape[0] < 30 or a.abs().sum() == 0:
                continue
            if self.mode == "mv":
                Sig = LedoitWolf().fit(win.values).covariance_
                raw = np.linalg.solve(Sig + self.eps * np.eye(Sig.shape[0]), a.values)
                w = pd.Series(raw, index=win.columns)
            else:  # hrp
                rw = _hrp_weights(win)
                w = rw * np.sign(a)
            g = w.abs().sum()
            if g > 0:
                W.loc[panel.index[i], win.columns] = (w / g * self.target_gross).values
        self.W = W.ffill().fillna(0.0)

    def target_weights(self, t, history):
        if t in self.W.index:
            return self.W.loc[t]
        return pd.Series(0.0, index=self.panel.columns)
