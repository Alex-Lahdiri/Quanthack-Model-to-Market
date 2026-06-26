# Quanthack Backtester - "Model to Market" (Syphonix)

A local, scoring-aware backtesting harness + risk engine for the competition.
MT5 / custom-code track. Built to optimize the actual grading formula, not raw P&L:

```
Final Score = 0.70·Return_rank + 0.15·Drawdown_rank + 0.10·Sharpe_rank + 0.05·Discipline_rank
```
(all percentile ranks vs the field) - plus the hard rule that a **forced liquidation = elimination**.

Everything is parameterized in `config.py` so you can match the console's published
numbers exactly.

---

## Why it's shaped this way

- **Return is 70%**, so exposure matters - but the other 30% (drawdown, Sharpe,
  discipline) is what separates winners from blow-ups, and liquidation ends your run.
- The risk engine makes it **structurally impossible** to breach the penalty tiers
  or red lines: it caps gross leverage, per-instrument concentration, and net-directional
  concentration *before* any order is sized.
- Sharpe is graded on **15-minute equity steps**, so the metrics sample equity exactly
  that way.

## Install

```bash
pip install -r requirements.txt
```

## Quick start (works today, no real data needed)

```bash
python run_backtest.py          # auto-generates synthetic data, runs, prints a tearsheet
python verify.py                # 12 independent checks on the scoring math + risk caps
```

## Onboarding the real 20GB Week-1 Parquet

1. **Inspect the schema first** (I don't know the exact column names yet):
   ```bash
   python run_backtest.py --data /path/to/week1.parquet --inspect
   ```
   This prints columns, row count, and an auto-detected mapping
   (`ts / symbol / bid / ask / price`).

2. If any field shows `NOT FOUND`, add the real name to the alias lists at the top of
   `data_loader.py` (or pass an explicit `mapping=` to `load_quotes`).

3. **Backtest** (the lazy loader streams the file; it is never fully loaded into RAM):
   ```bash
   python run_backtest.py --data /path/to/week1.parquet --freq 5m --rebalance 3 --target-gross 10
   ```

Outputs land in `results/`: `equity_curve.csv`, `telemetry.csv`, `metrics.json`, `equity_curve.png`.

## Files

| File | Role |
|------|------|
| `config.py` | All competition constants: scoring weights, leverage/margin/concentration limits, safe caps. **Edit to match the console.** |
| `data_loader.py` | Lazy Parquet loader (polars). Auto-detects columns, resamples to OHLC bars, builds a wide price panel. |
| `risk_engine.py` | Converts desired weights → compliant weights: concentration, net-directional, and gross/margin caps. |
| `engine.py` | Bar loop: mark-to-market, forced-liquidation check, banded rebalancing, equity + risk telemetry. |
| `metrics.py` | Return, max drawdown, Sharpe/Sortino (15-min), discipline, and the **final-score simulator** (percentile ranks → weighted score). |
| `strategies/diversified_vol_target.py` | Reference strategy (see below). Subclass `strategies/base.Strategy` for your own. |
| `make_synthetic_data.py` | Generates fake multi-asset quotes so the pipeline is testable before the real file lands. |
| `run_backtest.py` | CLI entrypoint that wires it all together. |
| `verify.py` | Independent correctness checks. |

## The reference strategy (a starting point, not a finished edge)

`DiversifiedVolTarget`: cross-sectional, risk-adjusted momentum that is
market-neutral (demeaned), inverse-vol sized, and EMA-smoothed to keep turnover -
and therefore cost - low. This shape protects drawdown/Sharpe/discipline while still
taking exposure. **Tune `target_gross`, the windows, and `smooth_halflife` on the
real data**, and consider adding a mean-reversion sleeve for the crypto names.

## Simulating your final score

`metrics.simulate_final_score(my_metrics, peers_df)` turns raw metrics into the
70/15/10/5 weighted percentile score. Before the rounds start, `make_synthetic_peers()`
gives a plausible field for what-if analysis. **Once Rounds 1–3 open, the leaderboard is
visible on a 5-minute delay - scrape it into a DataFrame with columns
`total_return, max_drawdown, sharpe, discipline` and pass it in for a real ranking.**

## Important caveats (read these)

- **Synthetic data has constant drift**, so the reference strategy looks *too* good on it
  (Sharpe ~10, big returns). That validates the *plumbing*, not an edge. Real markets won't
  hand you persistent drift - expect far lower numbers and re-tune.
- **"Trades executed" counts position adjustments**, so the figure is large; what matters for
  the $10k Sharpe prize is simply clearing the 30-trade floor (I do, easily).
- **The margin/liquidation model is a conservative assumption** (`MAINTENANCE_MARGIN_LEVEL`
  in `config.py`). Confirm the platform's real maintenance margin and update it.
- This is paper trading. No strategy guarantees returns; markets are not predictable.

## Suggested next steps

1. Point `--inspect` at the real Parquet the moment it finishes; fix the column mapping.
2. Re-tune gross / windows / rebalance frequency on real data; watch costs (turnover).
3. Walk-forward test: split Week-1 data, fit early, evaluate late (no peeking).
4. Wire your tuned weights into your MT5 execution layer, keeping the risk engine in front.

---

## Working with the REAL competition archive

The provided archive is a zip of **one Parquet per `SYMBOL_YYYY_MM_DD`** (531 files,
~21.8 GB uncompressed), columns: `time` (microsecond string), `sym`, `bid`, `ask`,
plus full L2 depth ladders (ignored - I use top-of-book `bid`/`ask`).

**Universe (22):** AUDJPY, AUDNZD, AUDUSD, EURCHF, EURGBP, EURJPY, EURUSD, GBPUSD,
NZDUSD, USDCAD, USDCHF, USDCNH, USDHKD, USDJPY, XAGUSD, XAUUSD (+ XAUCNH/XAUGCNH/
XAUHKD/XAUKUSD gold crosses), UKOILUSD, USOILUSD. **Note: no crypto in this backtest
set** (the live event universe may differ - re-check before relying on crypto signals).
Dates span 2026-05-11 → 2026-06-10.

Use `ingest_real.py` - it extracts ONE file at a time and deletes it after resampling,
so disk never balloons:

```bash
# see instruments + date coverage
python ingest_real.py --zip /path/archive.zip --list

# build + cache a 1-min panel for a subset, then auto-backtest
python ingest_real.py --zip /path/archive.zip \
    --instruments EURUSD,GBPUSD,USDJPY,USDCAD,XAUUSD,XAGUSD \
    --start 2026-06-01 --end 2026-06-10 --freq 1m
```

It writes `results/panel.parquet`. Re-run strategy experiments off that cache instantly
(no re-ingest). Throughput is ~1.2 s/file, so the full month (~531 files) takes ~11 min -
ingest in batches if you want the whole thing.

### Early read on real data (small sample - not conclusive)

On 3 days × 4 majors: **longer-window momentum (≈120-min lookback) was positive**
(Sharpe ~4), while short-window momentum and mean-reversion lost. The naive 60-min
default is mediocre. Validate any edge on a **larger panel with walk-forward splits**
before trusting it - 3 days is far too short to conclude anything.

### Walk-forward result (2 weeks, 12 instruments - honest, out-of-sample)

Tuned on the first ~6 days, evaluated on the held-out last ~7 days
(`walkforward.py`). Only **slow momentum (8-hour / 480-min lookback)** was
positive in-sample; every shorter window and all mean-reversion configs lost.
That config then held up **out-of-sample**: +4.4% return, −4.8% max drawdown,
Sharpe ~5.4, discipline 100/100, no liquidation. The default window is now 480.

Caveats: still only 2 weeks and a single split. Before trusting it, run rolling
walk-forward, add more instruments / the full month, and re-test. New helpers:
`batch_ingest.py` (checkpointed full-archive ingestion) and `walkforward.py`.

### v2 experiment - did NOT beat the baseline (documented negative result)

I encoded the research findings into `UsdNeutralMomentum` (2h+8h momentum blend,
rolling-beta USD-factor neutralization, per-name caps, time-of-day gating) and
walk-forwarded it head-to-head (`compare_v2.py`, `ablate.py`).

Result: it **lost** - OOS −2.3% / Sharpe −25 vs the baseline's +4.4% / Sharpe +5.4.
Ablation (selected on train) showed the 2h signal and the beta-neutralization were
the main drags; even the stripped-down v2 reached only ~flat OOS, still below the
plain 8-hour momentum baseline.

**Takeaway:** on two weeks of data, added complexity overfits. The champion remains
simple cross-sectional 8h momentum + inverse-vol + demean (`DiversifiedVolTarget`).
The research signals (longer-horizon momentum, USD factor, session timing) are
real *descriptively* but need the **full month** for the statistical power to turn
into a tradeable improvement - validate there before adding complexity.

### Full-month validation (the verdict flipped)

Ingested all 531 files (22 instruments, full month) via the fast resampler into
`panel_full_month.parquet`, then re-ran research + walk-forward (`research.py --panel ...`,
`fullmonth_compare.py`).

The 2-week result did NOT generalize: over the full month the momentum strategy is weak and
regime-dependent (first half lost on every config; best OOS was 8h momentum at +0.6% / Sharpe 0.73).
v2 still underperformed the baseline. The earlier +4.4% / Sharpe 5.4 was a favorable sub-window.

Robust findings that DO hold: ~50% USD factor (PC1), short-horizon reversion, clean 12–15 UTC session
peak, fat-tailed USDJPY/AUDNZD, and - most importantly - the book's risk discipline (100/100, controlled
drawdowns, no liquidation). Competition takeaway: compete on survival + the drawdown/Sharpe/discipline
ranks (and the $10k Sharpe prize), not on a big return bet. New: `fullmonth_compare.py`, research is
parameterized (`--panel`, `--min-vol`).

### Scoring-tuned operating point (recommended)

Tuning revealed the binding constraint was **turnover/cost, not leverage**: the thin 8h-momentum
edge was being eaten by 15-min churn. Slowing to **hourly rebalancing + smoothing half-life 48**, with
realistic ~0.7bp FX spreads, flips the full month to **positive with Sharpe ~1.9** (OOS +1.6% / Sharpe 2.2).

Leverage is then just a return-vs-drawdown dial - Sharpe is gross-invariant and the simulated score is
nearly flat across gross (≈58–60), so there is no scoring reason to over-lever (and elimination/liquidation
make tail safety paramount).

**Recommended:** `DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480, smooth_halflife=48,
target_gross=4)`, `rebalance_every=60`, 12-name liquid universe. Full month +3.8% / Sharpe 1.89 / DD −6.8% /
discipline 100 / 5396 trades. Reproduce: `python run_recommended.py`. Push gross to 5–6 only for deliberate
return-rank variance. See `results/research/scoring_tuning_report.html`.

### Robustness validation (real costs + rolling walk-forward)

Recovered real per-instrument spreads from the data (`mean_spread`): FX majors 0.10–0.35 bps/side, gold 0.11,
silver 0.78 - far below the conservative 0.7bp. Added per-instrument costs to the engine (`run_backtest(cost_bps={sym:bps})`).

With real costs the recommended config (gross 4) does **+7.0% / Sharpe 3.28 / maxDD −5.9%** over the month.
Rolling 6-block walk-forward: full Sharpe 3.26, but "win big / lose small" - 3/6 blocks positive, winners large
(Sharpe 13.6/10.8/5.3), worst block −2.5% / −4.3% DD. Verdict: viable and safe to deploy, with honest week-to-week
variance. New: `validation_rolling.py`, `results/research/validation_report.html`.

### Advanced direction #1 (order book) - dead end, documented
Only XAUUSD has real L2 depth; the other 21 instruments ship a synthetic symmetric size
template (zero imbalance). Even gold's order-flow imbalance/microprice has negligible,
slightly contrarian predictive power (|IC| <= 0.05 at 60s). No usable microstructure edge here.

### Advanced direction #2 (portfolio construction) - shrinkage MV WINS
Same momentum signal, sized by Ledoit-Wolf shrinkage covariance: `w ~ Sigma^{-1} alpha`
(`strategies/cov_aware.py`, mode="mv"). Accounting for correlations (esp. the 50% USD factor)
beats naive inverse-vol clearly: full month **+17.8% / Sharpe 4.77** vs +7.0% / 3.28, and holds
out-of-sample (+5.4% / Sharpe 4.32). HRP (mode="hrp") failed for a long/short book (−2.3%,
discipline breached). Shrinkage-MV is the new leading construction - pending the overfit checks
in direction #4. See `results/research/construction_compare.png`. Scripts: `compare_construction.py`.

### Advanced direction #4 (overfitting controls) - the reality check
Deflated Sharpe Ratio (Bailey & Lopez de Prado) + Probability of Backtest Overfitting via CSCV
(`overfit.py`), run over the grid of configs explored this session:

- **Deflated Sharpe = 0.26** (N=16 trials), falling to 0.13 (N=50) / 0.05 (N=200). The best backtest
  Sharpe (~4.9) is actually BELOW the expected-max under the null (~7.4) - i.e. given how many configs I
  tried and how variable their Sharpes are, ~4.9 is what you'd get by luck. **The absolute performance does
  not survive deflation.**
- **PBO = 21%** - the in-sample-best config is below-median OOS ~21% of the time, so the *ranking*
  (MV > inverse-vol, long windows > short, low turnover) is moderately persistent / probably real.

**Bottom line:** trust the *direction* of the findings, not the *magnitude*. The +17.8% / Sharpe 4.8 is
overfit; live, expect far less (likely a low-single-digit Sharpe at best, possibly ~0). This argues AGAINST
adding ML/more complexity (it would overfit worse) and FOR the conservative, low-gross, disciplined posture.
See `results/research/overfit_dsr.png`.

### Advanced direction #3 (regime gate + ensemble) - no improvement
Multi-horizon momentum ensemble + self-calibrating vol-regime gate (`strategies/regime_ensemble.py`).
Result: roughly flat (+0.2% / Sharpe 0.28, 2/6 positive blocks) - worse than the simpler strategies.
Another case of added complexity not helping. (Notably, shrinkage-MV had the best block consistency, 5/6.)

### Deployment systems (`live/`)
Advisory, no-execution runtime for the live event:
- `live/live_runner.py` - hourly: latest panel -> strategy weights -> risk engine -> `book.json` target notionals.
- `live/risk_monitor.py` - every 5 min: flags proximity to margin/leverage/concentration penalty tiers + liquidation.
- `live/Dockerfile`, `live/northflank.json` - deploy as two Northflank cron jobs (London); optional Pydantic Logfire tracing.
- `live/LIVE_README.md` - wiring, MT5 execution handoff, safety (paper only, human-in-loop).

### Advanced program - synthesis
Of the four advanced directions: order-book microstructure = dead end (synthetic depth); shrinkage-MV
construction = the one genuine improvement (better Sharpe AND block consistency); regime/ensemble = no help;
overfit controls = the reality check (Deflated Sharpe 0.26, PBO 21% -> trust direction, not magnitude).
Net: a disciplined, market-neutral, shrinkage-MV momentum book at conservative gross, deployed via `live/`,
competing on survival + risk-adjusted ranks rather than a backtested return number.

### Live rehearsal (pre-launch de-risk) - `live/feed_adapter.py`, `live/rehearse.py`
- `feed_adapter.py`: builds `panel_live.parquet` from the platform feed (format-agnostic via `detect_columns`); point `--source` at the feed dir, run on a short schedule.
- `rehearse.py`: replays the month through the ACTUAL live path (weight selection -> risk engine -> order/fill diff as the MT5 bridge does -> per-instrument costs -> risk monitor). Result: live path reproduces the vectorized backtest to **0.05%**, **0 penalty-tier breaches**, no errors. Run it before launch to catch integration bugs. (Return magnitude still subject to the overfit caveat; the rehearsal validates plumbing, not alpha.)

### AI ops/risk agent - `live/ops_agent.py`
Advisory briefing agent (the "AI-native" piece): reads account status + risk assessment, reports headroom
to every penalty tier, and recommends hold/trim/de-risk. Uses Claude (Anthropic) when `ANTHROPIC_API_KEY`
is set, with a deterministic fallback that always works; logs to Logfire. Verified: correctly says HOLD on a
healthy book and "REDUCE GROSS now" (with red-line warning) on a stressed one. Run every ~15 min and per round.
