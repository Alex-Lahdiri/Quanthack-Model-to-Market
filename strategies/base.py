"""Strategy interface. Subclass this and implement `target_weights`."""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name: str = "base"

    def precompute(self, panel: pd.DataFrame) -> None:
        """
        Optional hook: cache vectorized signals from the full price panel BEFORE
        the backtest loop. Only use data causally (rolling windows look backward),
        never reference future rows -- that would leak look-ahead bias.
        """
        self.panel = panel

    @abstractmethod
    def target_weights(self, t, history: pd.DataFrame) -> pd.Series:
        """
        Desired signed weights at rebalance time `t`, indexed by symbol.
        +0.5 = long 50% of equity notional; -0.5 = short. `history` is the price
        panel up to and including `t` (provided for convenience). The risk engine
        will clip whatever you return to the compliant envelope.
        """
        raise NotImplementedError
