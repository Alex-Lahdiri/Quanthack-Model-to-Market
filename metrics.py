"""
Scoring metrics — aligned to the OFFICIAL competition rules.

Final Score = 70% Return Rank + 15% Drawdown Rank + 10% Sharpe Rank + 5% Risk Discipline.
Rank_i = 100 * (N - Rank_i) / (N - 1), Rank=1 best (so best->100, worst->0).
Sharpe is NON-ANNUALIZED: Mean/Std of 15-minute equity returns. If <8 valid 15-min
observations, Sharpe Rank is capped at 50. If Std=0, Sharpe=0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config as C


def resample_equity(equity: pd.Series, minutes: int = C.EQUITY_SAMPLE_MINUTES) -> pd.Series:
    s = equity.sort_index()
    return s.resample(f"{minutes}min").last().dropna()


def total_return(equity: pd.Series) -> float:
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def max_drawdown(equity: pd.Series) -> float:
    s = equity.sort_index()
    dd = s / s.cummax() - 1.0
    return float(dd.min())


def sharpe(equity_sampled: pd.Series, periods_per_year: float = 1.0) -> float:
    """Competition Sharpe = Mean/Std of 15-min returns, NON-annualized (default).
    Pass periods_per_year only if you want an annualized figure for intuition."""
    rets = equity_sampled.pct_change().dropna()
    if len(rets) < 2 or rets.std(ddof=1) == 0:
        return 0.0
    return float(rets.mean() / rets.std(ddof=1) * np.sqrt(periods_per_year))


def sortino(equity_sampled: pd.Series, periods_per_year: float = 1.0) -> float:
    rets = equity_sampled.pct_change().dropna()
    downside = rets[rets < 0]
    dd = downside.std(ddof=1)
    if len(rets) < 2 or dd == 0 or np.isnan(dd):
        return 0.0
    return float(rets.mean() / dd * np.sqrt(periods_per_year))


def discipline_score(telemetry: pd.DataFrame) -> float:
    if telemetry.empty:
        return 100.0
    within = (
        (telemetry["margin_usage"] < C.MARGIN_PENALTY_TIERS[0])
        & (telemetry["gross_leverage"] < C.LEVERAGE_PENALTY_TIERS[0])
        & (telemetry["max_name_share"] < C.CONCENTRATION_PENALTY)
        & (telemetry["net_share"] < C.NET_DIRECTIONAL_PENALTY)
    )
    return float(within.mean() * 100.0)


def compute_metrics(equity: pd.Series, telemetry: pd.DataFrame,
                    trade_count: int, liquidated: bool) -> dict:
    sampled = resample_equity(equity)
    n = int(len(sampled))
    return {
        "total_return": total_return(equity),
        "max_drawdown": max_drawdown(equity),
        "sharpe": sharpe(sampled),                       # non-annualized (competition)
        "sharpe_annualized": sharpe(sampled, C.PERIODS_PER_YEAR),  # intuition only
        "sortino": sortino(sampled),
        "discipline": discipline_score(telemetry),
        "trade_count": int(trade_count),
        "liquidated": bool(liquidated),
        "final_equity": float(equity.iloc[-1]),
        "n_equity_samples": n,
        "sharpe_prize_eligible": (trade_count >= C.MIN_TRADES_FOR_SHARPE_PRIZE
                                  and not liquidated),
    }


# ---------------------------------------------------------------------------
# Ranking -> final score (official formula)
# ---------------------------------------------------------------------------
def percentile_rank(value: float, peers: np.ndarray, higher_is_better: bool = True) -> float:
    """Percent of the field you beat (0-100). Kept for quick what-ifs/tests."""
    peers = np.asarray(peers, dtype=float)
    if peers.size == 0:
        return 50.0
    if higher_is_better:
        wins = np.sum(value > peers) + 0.5 * np.sum(value == peers)
    else:
        wins = np.sum(value < peers) + 0.5 * np.sum(value == peers)
    return float(100.0 * wins / peers.size)


def competition_rank(value: float, peers: np.ndarray, higher_is_better: bool = True) -> float:
    """Official: Rank=1 best; score = 100*(N-Rank)/(N-1). N includes `value`."""
    allv = np.append(np.asarray(peers, dtype=float), value)
    N = len(allv)
    if N <= 1:
        return 100.0
    order = np.argsort(-allv if higher_is_better else allv, kind="mergesort")
    ranks = np.empty(N); ranks[order] = np.arange(1, N + 1)
    rank_value = ranks[-1]                       # value was appended last
    return float(100.0 * (N - rank_value) / (N - 1))


def simulate_final_score(my: dict, peers: pd.DataFrame) -> dict:
    """`peers` columns: total_return, max_drawdown, sharpe, discipline."""
    r_return = competition_rank(my["total_return"], peers["total_return"].values, True)
    r_draw = competition_rank(my["max_drawdown"], peers["max_drawdown"].values, True)  # closer to 0 better
    r_sharpe = competition_rank(my["sharpe"], peers["sharpe"].values, True)
    if my.get("n_equity_samples", 99) < C.MIN_SHARPE_OBS:
        r_sharpe = min(r_sharpe, C.SHARPE_RANK_CAP_LOW_OBS)
    r_disc = competition_rank(my["discipline"], peers["discipline"].values, True)
    final = (C.SCORE_WEIGHTS["return"] * r_return + C.SCORE_WEIGHTS["drawdown"] * r_draw
             + C.SCORE_WEIGHTS["sharpe"] * r_sharpe + C.SCORE_WEIGHTS["discipline"] * r_disc)
    return {"rank_return": r_return, "rank_drawdown": r_draw, "rank_sharpe": r_sharpe,
            "rank_discipline": r_disc, "final_score": final}


def make_synthetic_peers(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = rng.normal(0.04, 0.12, n)
    gambler = rng.random(n) < 0.25
    base[gambler] += rng.normal(0.10, 0.25, gambler.sum())
    drawdown = -np.abs(rng.normal(0.06, 0.05, n)) - np.clip(base, 0, None) * 0.3
    sharpe_ = base / (np.abs(drawdown) + 0.02) * rng.normal(1.0, 0.2, n)
    disc = np.clip(rng.normal(85, 12, n), 0, 100); disc[gambler] -= 25
    return pd.DataFrame({"total_return": base, "max_drawdown": drawdown,
                         "sharpe": sharpe_, "discipline": np.clip(disc, 0, 100)})


def tearsheet(m: dict, score: dict | None = None) -> str:
    lines = [
        "",
        "============== QUANTHACK BACKTEST TEARSHEET ==============",
        f"  Total return         {m['total_return']*100:>8.2f} %",
        f"  Final equity         {m['final_equity']:>12,.0f}",
        f"  Max drawdown         {m['max_drawdown']*100:>8.2f} %",
        f"  Sharpe (15m, comp)   {m['sharpe']:>8.4f}   [annualized ~{m.get('sharpe_annualized',0):.2f}]",
        f"  Risk discipline      {m['discipline']:>8.1f} / 100",
        f"  Trades executed      {m['trade_count']:>8d}   (>= {C.MIN_TRADES_FOR_SHARPE_PRIZE} for Sharpe prize)",
        f"  Forced liquidation   {'YES -- DQ!' if m['liquidated'] else 'no':>8}",
    ]
    if score:
        lines += [
            "  ----------------------------------------------------",
            "  Simulated rank vs field (official 100*(N-Rank)/(N-1)):",
            f"    Return     {score['rank_return']:>6.1f}   x70%",
            f"    Drawdown   {score['rank_drawdown']:>6.1f}   x15%",
            f"    Sharpe     {score['rank_sharpe']:>6.1f}   x10%",
            f"    Discipline {score['rank_discipline']:>6.1f}   x 5%",
            f"  >> FINAL SCORE  {score['final_score']:>6.1f} / 100",
        ]
    lines += ["==========================================================", ""]
    out = "\n".join(lines); print(out); return out
