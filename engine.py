"""
Event-driven-ish portfolio backtester.

Bar loop:
  1. mark-to-market PnL from positions held over the last bar -> update equity
  2. forced-liquidation check (margin level / equity) -> DQ flag if breached
  3. on rebalance bars: ask strategy for weights, clip via the risk engine,
     trade into the new target (subject to a no-trade band), charge costs,
     count trades
  4. record equity + risk telemetry

`cost_bps` may be a scalar (uniform) OR a dict/Series of {symbol: per-side bps}
so realistic per-instrument spreads can be charged.

Positions are tracked in signed UNITS so PnL is just units * price change.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import config as C
from risk_engine import RiskEngine
from strategies.base import Strategy


@dataclass
class BacktestResult:
    equity: pd.Series
    telemetry: pd.DataFrame
    trade_count: int
    liquidated: bool
    params: dict


def _cost_vector(cost_bps, symbols):
    """Return a per-symbol array of per-side costs in bps."""
    if isinstance(cost_bps, (int, float)):
        return np.full(len(symbols), float(cost_bps))
    cs = pd.Series(cost_bps, dtype=float)
    default = float(cs.median()) if len(cs) else C.DEFAULT_COST_BPS
    return np.array([float(cs.get(s, default)) for s in symbols])


def run_backtest(
    panel: pd.DataFrame,
    strategy: Strategy,
    risk: RiskEngine | None = None,
    rebalance_every: int = 15,
    cost_bps=C.DEFAULT_COST_BPS,        # scalar OR {symbol: per-side bps}
    start_equity: float = C.ACCOUNT_START,
    band_frac: float = 0.02,
) -> BacktestResult:
    risk = risk or RiskEngine()
    strategy.precompute(panel)

    symbols = list(panel.columns)
    times = panel.index
    cost_vec = _cost_vector(cost_bps, symbols)
    P = panel.ffill().bfill().to_numpy(dtype=float)
    n, m = P.shape

    equity = float(start_equity)
    units = np.zeros(m)
    trade_count = 0
    liquidated = False

    eq_curve = np.empty(n)
    eq_curve[0] = equity
    tele_rows: list[dict] = [_telemetry_row(units, P[0], equity)]

    for i in range(1, n):
        price = P[i]
        dprice = price - P[i - 1]
        equity += float(np.dot(units, dprice))

        gross_notional = float(np.dot(np.abs(units), price))
        used_margin = gross_notional / C.MAX_LEVERAGE
        margin_level = equity / used_margin if used_margin > 0 else np.inf
        if not liquidated and (equity <= 0 or margin_level < C.MAINTENANCE_MARGIN_LEVEL):
            liquidated = True
            units = np.zeros(m)
            equity = max(equity, 0.0)

        if (not liquidated) and (i % rebalance_every == 0):
            w = strategy.target_weights(times[i], panel.iloc[: i + 1])
            w = w.reindex(symbols).fillna(0.0)
            w_c = risk.apply(w)
            target_notional = w_c.to_numpy() * equity
            current_notional = units * price
            delta_notional = target_notional - current_notional
            trade_mask = np.abs(delta_notional) > band_frac * equity
            if trade_mask.any():
                new_units = units.copy()
                with np.errstate(divide="ignore", invalid="ignore"):
                    new_units[trade_mask] = np.where(
                        price[trade_mask] > 0,
                        target_notional[trade_mask] / price[trade_mask], 0.0)
                traded_notional = np.abs(new_units - units) * price
                equity -= float((traded_notional * cost_vec).sum()) / 1e4
                trade_count += int(trade_mask.sum())
                units = new_units

        eq_curve[i] = equity
        tele_rows.append(_telemetry_row(units, price, equity))

    return BacktestResult(
        equity=pd.Series(eq_curve, index=times, name="equity"),
        telemetry=pd.DataFrame(tele_rows, index=times),
        trade_count=trade_count,
        liquidated=liquidated,
        params={"strategy": strategy.name, "rebalance_every": rebalance_every,
                "cost_bps": "per-instrument" if not isinstance(cost_bps, (int, float)) else cost_bps,
                "band_frac": band_frac, "start_equity": start_equity},
    )


def _telemetry_row(units: np.ndarray, price: np.ndarray, equity: float) -> dict:
    notional = units * price
    gross = float(np.abs(notional).sum())
    net = float(notional.sum())
    eq = equity if equity > 0 else np.nan
    return {
        "gross_leverage": gross / eq if eq else 0.0,
        "net_leverage": abs(net) / eq if eq else 0.0,
        "margin_usage": (gross / C.MAX_LEVERAGE) / eq if eq else 0.0,
        "max_name_share": float(np.abs(notional).max() / gross) if gross > 0 else 0.0,
        "net_share": abs(net) / gross if gross > 0 else 0.0,
    }
