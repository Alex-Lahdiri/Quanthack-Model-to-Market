"""
Competition constants for "Model to Market" (Quanthack by Syphonix).

Every number the scoring formula and the red-line rules care about lives here,
so the rest of the harness reads from one source of truth. Update these if the
console's published rules differ from the kickoff notes.

Final Score = 0.70 * Return_rank + 0.15 * Drawdown_rank
            + 0.10 * Sharpe_rank + 0.05 * RiskDiscipline_rank   (all percentile ranks 0-100)
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------
ACCOUNT_START: float = 1_000_000.0     # $1M paper account
MAX_LEVERAGE: float = 30.0             # platform hard cap (gross notional / equity)

# ---------------------------------------------------------------------------
# Scoring weights (must sum to 1.0)
# ---------------------------------------------------------------------------
SCORE_WEIGHTS: dict[str, float] = {
    "return": 0.70,
    "drawdown": 0.15,
    "sharpe": 0.10,
    "discipline": 0.05,
}

# Sharpe is sampled on the equity curve at this cadence (kickoff notes: 15-min steps).
EQUITY_SAMPLE_MINUTES: int = 15

# Periods/year used only to *annualize* Sharpe for display. The competitor RANK
# is invariant to this constant (it scales every Sharpe equally), so the exact
# value does not change your placement. 24/7 crypto-style default.
PERIODS_PER_YEAR: float = 4 * 24 * 365  # 35,040 fifteen-minute periods

# Best Sharpe Ratio Award ($10k) eligibility.
MIN_TRADES_FOR_SHARPE_PRIZE: int = 30

# ---------------------------------------------------------------------------
# Red lines (instant disqualification) -- model what we can; the rest are conduct.
# ---------------------------------------------------------------------------
# Forced liquidation = account wipeout = elimination. Liquidate when margin level
# (equity / used_margin) drops below this. Conservative default; tune to console.
MAINTENANCE_MARGIN_LEVEL: float = 1.00   # i.e. free margin hits zero

# ---------------------------------------------------------------------------
# Penalty thresholds (point penalties, NOT DQ) -- we keep a buffer below each.
# ---------------------------------------------------------------------------
MARGIN_PENALTY_TIERS: tuple[float, ...] = (0.90, 0.95, 0.98)   # sustained margin usage
LEVERAGE_PENALTY_TIERS: tuple[float, ...] = (28.0, 29.0)        # sustained gross leverage
CONCENTRATION_PENALTY: float = 0.90    # single instrument OR net-directional share...
CONCENTRATION_HOLD_MINUTES: int = 30   # ...held this long triggers the penalty

# ---------------------------------------------------------------------------
# OUR self-imposed safety caps (sit comfortably under every penalty threshold)
# ---------------------------------------------------------------------------
SAFE_MAX_LEVERAGE: float = 27.0        # stay under the 28x penalty tier
SAFE_MAX_MARGIN_USAGE: float = 0.85    # stay under the 90% penalty tier
SAFE_MAX_CONCENTRATION: float = 0.85   # net-directional share of gross (and legacy default)

# Per-name diversification + survival caps. Added after the live book showed one name
# reaching ~100% of equity at gross 2. max_name_share limits a name's share of GROSS
# (scale-invariant diversification); max_name_equity is a hard ceiling on a name's
# exposure as a fraction of EQUITY (caps single-name shock, also implicitly limits gross).
# Tuned on the full month: at gross 2 these trim peak single-name from ~100% -> ~60% of
# equity for ~0.4pp return cost and unchanged Sharpe.
SAFE_MAX_NAME_SHARE: float = 0.30
SAFE_MAX_NAME_EQUITY: float = 0.75

# Sector cap: correlated groups (gold + silver move together) can co-dominate the book even
# when each name is under its per-name cap. Limit a sector's COMBINED share of gross. Surfaced
# by the AI desk -- XAU+XAG shorts reached ~35% of gross as a single risk factor.
SECTORS: dict[str, tuple[str, ...]] = {"metals": ("XAUUSD", "XAGUSD")}
# 0.35 trims only the co-directional spikes the AI flagged (~0.9pp return cost on the month
# when metals were a winner; likely neutral/positive in a soft metals regime). Loosen to 0.40
# (nearly free) for less insurance, or 0.25 for more. One number, easy to change.
SAFE_MAX_SECTOR_SHARE: float = 0.35

# The margin cap usually binds before the leverage cap:
#   margin_usage = gross_leverage / MAX_LEVERAGE
#   => gross_leverage <= SAFE_MAX_MARGIN_USAGE * MAX_LEVERAGE
# Effective gross-leverage ceiling the risk engine will enforce:
EFFECTIVE_GROSS_CAP: float = min(SAFE_MAX_LEVERAGE, SAFE_MAX_MARGIN_USAGE * MAX_LEVERAGE)

# ---------------------------------------------------------------------------
# Execution assumptions for backtesting (tune to observed spreads on real data)
# ---------------------------------------------------------------------------
# Cost charged on traded notional when a position changes (round-trip ~ 2x this).
DEFAULT_COST_BPS: float = 1.0          # 1 basis point per side; override per asset class

# Rough per-asset-class spread guidance (bps of notional, one side) for sizing/costs.
ASSET_CLASS_COST_BPS: dict[str, float] = {
    "fx_major": 0.3,
    "fx_minor": 1.0,
    "metal": 1.5,
    "crypto": 3.0,
}

# ---- CONFIRMED against the official rules (released Jun 15) ----
# Scoring 70/15/10/5 is EXACT. Risk-discipline tiers below match the rules.
NET_DIRECTIONAL_PENALTY: float = 0.95     # net-directional exposure penalty (single-instrument = 0.90)
MIN_SHARPE_OBS: int = 8                    # <8 valid 15-min returns -> Sharpe Rank capped at 50
SHARPE_RANK_CAP_LOW_OBS: float = 50.0
# Sharpe is NON-ANNUALIZED (Mean/Std of 15-min equity returns); PERIODS_PER_YEAR is display-only.

# ---------------------------------------------------------------------------
# LIVE venue facts (from mt5_probe.py on the contest server, Jun 18 2026)
# ---------------------------------------------------------------------------
# The 10 names the broker actually offers that we have validated on. (No NZDUSD/
# EURJPY on this server. Crypto BTC/ETH/SOL/XRP/BAR is live but unvalidated.)
LIVE_UNIVERSE: tuple[str, ...] = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD",
    "EURGBP", "EURCHF", "XAUUSD", "XAGUSD",
)

# MT5 contract sizes (1.0 lot = this many base units). Used for notional->lots.
CONTRACT_SIZE: dict[str, float] = {
    "EURUSD": 100_000, "GBPUSD": 100_000, "USDJPY": 100_000, "USDCHF": 100_000,
    "USDCAD": 100_000, "AUDUSD": 100_000, "EURGBP": 100_000, "EURCHF": 100_000,
    "XAUUSD": 100,      # 1 lot = 100 oz gold
    "XAGUSD": 5_000,    # 1 lot = 5,000 oz silver
}

# Real venue half-spread (bps per side) derived from the MT5 spread field, with
# conservative floors for the names the snapshot showed at 0. Pass as cost_bps.
VENUE_COST_BPS: dict[str, float] = {
    "EURUSD": 0.08, "GBPUSD": 0.08, "USDCAD": 0.08, "AUDUSD": 0.08,
    "USDJPY": 0.16, "USDCHF": 0.19, "EURGBP": 0.15, "EURCHF": 0.15,
    "XAUUSD": 0.80, "XAGUSD": 1.20,
}

# ---------------------------------------------------------------------------
# Crypto sleeve -- live on the venue but GATED behind validation.
# We have no historical archive for crypto, so it never trades until
# live/validate_crypto.py (which pulls real history from MT5) writes a pass flag
# AND runtime.json opts in. Contract sizes are from the MT5 probe; costs are
# conservative placeholders (crypto spreads are wider + more volatile than FX).
# ---------------------------------------------------------------------------
CRYPTO_UNIVERSE: tuple[str, ...] = ("BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BARUSD")
CONTRACT_SIZE.update({"BTCUSD": 1.0, "ETHUSD": 1.0, "SOLUSD": 10.0, "XRPUSD": 100.0, "BARUSD": 100.0})
VENUE_COST_BPS.update({"BTCUSD": 3.0, "ETHUSD": 3.0, "SOLUSD": 5.0, "XRPUSD": 5.0, "BARUSD": 5.0})
