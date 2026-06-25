# Model to Market — Technology Submission

## Summary
A scoring-aware, market-neutral FX/metals trading system built end-to-end for the Quanthack
competition: a tick-data ingestion pipeline, a backtester whose risk engine makes the competition's
penalty tiers and the liquidation red line *structurally* unreachable, a rigorously validated
strategy, and an advisory live runtime for 24/7 paper trading. Our differentiator is **methodological
honesty**: we treated every promising backtest as guilty until proven robust, and used Deflated Sharpe
and Probability of Backtest Overfitting to separate real signal from luck.

## What we built
- **Ingestion** (`data_loader.py`, `batch_ingest.py`): streams the 20 GB / 531-file tick archive
  (22 instruments, one Parquet per instrument-day), resamples to bars via a fast minute-bucket method,
  and caches a price panel. Checkpointed so it survives any runtime limit.
- **Backtester** (`engine.py`): event-driven loop with mark-to-market, forced-liquidation detection,
  a no-trade band, and **per-instrument transaction costs** derived from the data's own spreads.
- **Risk engine** (`risk_engine.py`): converts desired weights into compliant ones — closed-form
  per-instrument concentration cap, net-directional cap, gross-leverage/margin cap — so the book never
  touches a penalty tier or the wipeout red line. Discipline stayed 100/100 across the entire month.
- **Strategies** (`strategies/`): cross-sectional momentum (inverse-vol) and a covariance-aware
  variant (shrinkage mean-variance, `Sigma^{-1} alpha`).
- **Scoring + validation** (`metrics.py`, `walkforward.py`, `validation_rolling.py`, `overfit.py`):
  return / drawdown / Sharpe / discipline, a 70/15/10/5 score simulator, rolling walk-forward, and the
  overfitting controls.
- **Live runtime** (`live/`): advisory target-book generator + risk monitor, Dockerised, with a
  Northflank cron spec, optional Logfire tracing, and an MT5 paper-execution bridge.

## Research methodology (the honest journey)
1. **Validate a simple baseline first.** A 2-week backtest of 8h cross-sectional momentum looked great
   (+4.4% / Sharpe 5.4 OOS).
2. **Full-month walk-forward killed the illusion.** Over the full month the same strategy was weak and
   regime-dependent (first half negative); the 2-week result was a favourable sub-window.
3. **Costs, not leverage, were the lever.** Recovering real per-instrument spreads (FX majors
   0.1–0.35 bps) and cutting turnover (hourly rebalance + smoothing) flipped it to genuinely positive.
4. **Four advanced directions, judged ruthlessly:**
   - *Order-book microstructure* → dead end (21/22 instruments ship synthetic symmetric depth; gold's
     real book isn't predictive, |IC| ≤ 0.05).
   - *Shrinkage mean-variance construction* → the one genuine win: higher Sharpe **and** best
     block-consistency (5/6 positive). Accounting for the ~50% USD factor in sizing matters.
   - *Regime gate + signal ensemble* → no improvement.
   - *Overfitting controls* → the reality check.
5. **Overfitting analysis (the centrepiece).** Across the configs we tried: **Deflated Sharpe = 0.26**
   (the best backtest Sharpe ~4.9 sits *below* the ~7.4 expected-max-under-null), and **PBO = 21%**.
   Conclusion: trust the *direction* (MV > inverse-vol, slow > fast, low turnover), not the *magnitude*.

## Headline results (full month, real per-instrument costs, gross 4)
| construction | return | max DD | Sharpe | discipline | OOS Sharpe |
|---|---|---|---|---|---|
| inverse-vol (baseline) | +7.0% | −5.9% | 3.28 | 100/100 | 3.63 |
| shrinkage MV (leading) | +17.8% | −9.2% | 4.77 | 100/100 | 4.32 |

**Caveat we put front-and-centre:** Deflated Sharpe 0.26 means these magnitudes are very likely
inflated by selection. Live, we expect materially less. We therefore deploy at **conservative gross**
and compete on survival + the risk-adjusted ranks (and the $10k Sharpe prize), not on a backtested
return number.

## Risk & compliance
Market-neutral by construction; single-digit drawdowns; **zero forced liquidations** across the month;
never inside a margin (90%) / leverage (28x) / concentration (90%) penalty tier. One account; the MT5
bridge is rate-limited well under 500 req/s and is paper-only with dry-run default.

## Sponsor technology
- **Anthropic / Claude** — the entire research-and-engineering loop was driven agentically with Claude:
  data pipeline, backtester, strategy iteration, and (critically) the decision to *stop adding complexity*
  once the overfitting metrics said so. Optional Claude-powered ops agent for round summaries.
- **Pydantic Logfire** — wired into the live runtime (`--logfire`) to trace every target-book generation
  and risk check; the audit trail doubles as our observability story.
- **Northflank** — Dockerised deployment with two cron jobs (London region) for the hourly runner and
  5-minute risk monitor.
- **Doubleword / NVIDIA Nemotron** — evaluated for an LLM/event signal and a microstructure model; our
  own overfitting analysis argued against adding ML on a single month of data, so we deliberately did not.
  (Honest negative usage is itself a finding.)

## Data usage
20 GB L2 tick archive (2026-05-11→06-10, 22 instruments). We use top-of-book mid for bars, the depth
ladders to confirm microstructure was synthetic, and `mean_spread` to set realistic per-instrument costs.

## Reproducible demo
```
pip install -r requirements.txt
./demo.sh          # recommended config tearsheet -> live target book -> risk monitor (uses shipped cached panel)
python overfit.py  # Deflated Sharpe + PBO (after re-ingesting the archive via batch_ingest.py)
```

## Limitations & future work
One month / one market regime; no crypto in the backtest set; signal edge is thin and the absolute
backtest is overfit. Future: more history for real statistical power, a rolling multi-split CV harness,
and an orthogonal signal (carry / event-driven) validated through the same overfitting gate before trust.
