"""
Risk engine: turns a strategy's *desired* weights into *compliant* weights.

Weights are signed fractions of equity expressed as notional exposure
(e.g. +0.5 = long 50% of equity in that instrument, -0.5 = short). Aggregate
gross can exceed 1.0 up to the leverage cap.

It enforces, in order:
  1. per-instrument concentration  (no single name dominates the book)
  2. net-directional concentration  (book isn't ~entirely one-sided)
  3. gross leverage / margin usage   (stay under the penalty tiers)

The whole point: by construction we never touch a red line or penalty tier,
which protects the 15% drawdown + 5% discipline slices of the score and, above
all, avoids the forced-liquidation DQ.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import config as C


@dataclass
class RiskEngine:
    max_gross: float = C.EFFECTIVE_GROSS_CAP          # gross leverage ceiling
    max_name_share: float = C.SAFE_MAX_NAME_SHARE     # |w_i| / gross (diversification)
    max_name_equity: float = C.SAFE_MAX_NAME_EQUITY   # |w_i| as fraction of EQUITY (survival cap)
    max_sector_share: float = C.SAFE_MAX_SECTOR_SHARE # combined |w| of a correlated sector / gross
    sectors: dict = field(default_factory=lambda: {k: tuple(v) for k, v in C.SECTORS.items()})
    max_net_share: float = C.SAFE_MAX_CONCENTRATION   # |sum w| / gross
    max_leverage: float = C.MAX_LEVERAGE              # platform hard cap (margin calc)
    _passes: int = field(default=4, repr=False)       # concentration iterations

    def apply(self, target: pd.Series) -> pd.Series:
        """Return compliant signed weights (same index as `target`)."""
        w = target.astype(float).fillna(0.0).copy()
        if w.abs().sum() == 0:
            return w

        # 0) absolute per-name EQUITY cap (survival): no single instrument's notional
        #    exceeds this fraction of equity, regardless of gross. Later steps only
        #    reduce exposure, so this ceiling holds through to the final weights.
        if 0 < self.max_name_equity < 1:
            w = w.clip(lower=-self.max_name_equity, upper=self.max_name_equity)

        # 1) per-instrument concentration. Want |w_i| <= s * gross. Solving the
        #    coupling gives a closed-form per-name cap = s/(1-s) * (gross - |w_i|),
        #    which converges in 1-2 passes (vs many for naive clip-to-s*gross).
        #    Skip when only one name is active -- you can't diversify a 1-name book.
        s = self.max_name_share
        if (w != 0).sum() > 1 and 0 < s < 1:
            for _ in range(self._passes):
                gross = w.abs().sum()
                if gross == 0:
                    break
                cap = (s / (1 - s)) * (gross - w.abs())
                clipped = w.clip(lower=-cap, upper=cap)
                if np.allclose(clipped.values, w.values):
                    w = clipped
                    break
                w = clipped

        # 2) net-directional: if the book is too one-sided, shrink the heavy side.
        gross = w.abs().sum()
        if gross > 0:
            net = w.sum()
            if abs(net) / gross > self.max_net_share:
                longs, shorts = w[w > 0].sum(), -w[w < 0].sum()
                target_net = np.sign(net) * self.max_net_share * gross
                if net > 0 and longs > 0:
                    w[w > 0] *= max(0.0, (shorts + target_net) / longs)
                elif net < 0 and shorts > 0:
                    w[w < 0] *= max(0.0, (longs - target_net) / shorts)

        # 2b) sector concentration: cap a correlated group's COMBINED share of gross, so
        #     gold+silver (or any sector) can't co-dominate even when each name is in-bounds.
        if self.sectors and 0 < self.max_sector_share < 1:
            gross = w.abs().sum()
            for names in self.sectors.values():
                idx = [n for n in names if n in w.index]
                s_gross = float(w[idx].abs().sum()) if idx else 0.0
                if gross > 0 and s_gross > self.max_sector_share * gross:
                    w[idx] *= (self.max_sector_share * gross) / s_gross

        # 3) gross leverage / margin usage cap
        gross = w.abs().sum()
        if gross > self.max_gross:
            w *= self.max_gross / gross

        return w

    @staticmethod
    def telemetry(w: pd.Series, equity: float) -> dict:
        """Current risk ratios + penalty/red-line flags for a weight vector."""
        wv = w.astype(float).fillna(0.0)
        gross = float(wv.abs().sum())
        net = float(wv.sum())
        margin_usage = gross / C.MAX_LEVERAGE
        name_share = float(wv.abs().max() / gross) if gross > 0 else 0.0
        net_share = abs(net) / gross if gross > 0 else 0.0
        return {
            "gross_leverage": gross,
            "net_leverage": abs(net),
            "margin_usage": margin_usage,
            "max_name_share": name_share,
            "net_share": net_share,
            # penalty-tier breaches (point penalties if *sustained*)
            "flag_leverage": gross >= C.LEVERAGE_PENALTY_TIERS[0],
            "flag_margin": margin_usage >= C.MARGIN_PENALTY_TIERS[0],
            "flag_concentration": (name_share >= C.CONCENTRATION_PENALTY
                                   or net_share >= C.CONCENTRATION_PENALTY),
        }
