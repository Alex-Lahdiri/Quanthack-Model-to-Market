# Platform notes (from Discord Q&A, pre-official-rules) - confirmed facts + plan changes

## The two interfaces (decides my integration)
- **MT5 (with API for automation)** and the **Syphonix AI Agent** (chat UI, "decision cards" you approve).
- **There is NO standalone Syphonix API** (they *may* add one later). The AI agents are chat-only - you
  cannot drive my quant book through them programmatically.
- => **My custom shrinkage-MV book runs via the MT5 API.** (This matches the original "MT5 + custom" choice.)

## ⚠ Deployment architecture change (important)
- The MT5 Python integration **requires a local Windows MT5 terminal - not supported on Linux**, so it
  **cannot run on Northflank** (Linux).
- **New plan: run the live loop on a Windows host** - your own Windows PC (kept on) or a **Windows VPS** for 24/7.
  One host runs: MT5 terminal → pull quotes (feed) → `live_runner` (target book) → `mt5_bridge` (orders) → `risk_monitor`/`ops_agent`.
- Northflank's role shrinks to optional: hosting Logfire dashboards / the ops agent, or a Syphonix-API path
  if one appears. Don't put MT5 on it.

## Market model
- Real market data is the input; orders are simulated (no live-market impact). BUT there's **internal
  order-book matching - you can match against other participants**. Slippage, market impact, partial fills
  simulated. Maker + taker both supported. Everyone sees the same bid/ask. **No Syphonix-side rate limit**
  (limits, if any, come from the MT5 layer - my bridge's pacing is still prudent).

## Universe
- FX + precious metals + **crypto (BTCUSD, ETHUSD, SOLUSD, XRPUSD, HBARUSD)**. No stocks/indices/bonds. 30+ total; full list after login.
- Backtest archive = 1 month, tick-level, 5-level depth - **but NO crypto, and FX depth is synthetic** (my finding).
  They're releasing an **updated data version** (adding L2 to MT5 data). **Grab the update when out** - it may fix the
  synthetic depth and revive the microstructure idea. For crypto, use public data if you choose to trade it (I have none → unvalidated).

## Scoring (CONFIRM against official rules released Jun 15)
- Discord says **"primary ranking metric is PnL"** + risk controls (leverage 30:1, margin, concentration, drawdown,
  rule breaches) to stop gambling. **PnL CARRIES OVER across rounds** (not reset).
- My console-derived **70/15/10/5** weights are in `config.py` - **verify them against the official rules** and I'll
  update the weights/thresholds. If scoring is more PnL-weighted than assumed, I may nudge gross up a touch - but the
  knockout-by-equity structure still rewards survival, so conservative-but-positive stays right.
- External data (news/prediction markets) **is allowed**.

## Timeline (BST)
- **Jun 15:** historical data + sponsor perks (after kickoff ~22:00).
- **Jun 18 (eve):** API access. Jun 15–18 = backtest/setup only.
- **Jun 21 23:00:** live trading starts (Asia open).
- **Jun 24 22:00:** Top-100 cut; leaderboard goes blind after.
- **Jun 26 22:00:** finals close, positions liquidated, final PnL + Sharpe computed.
- **Jun 27:** finalist event.

## Open items to confirm on Jun 15 / 18 (then I finalize the code)
1. **Official scoring formula + exact risk thresholds** -> I set `config.py`.
2. **MT5 credentials/server** + whether quotes come via MT5 API (`copy_rates`) or files -> I finalize the feed puller.
3. **Exact symbol names + contract specs** (lot size, leverage per instrument; "1 Lot = 100 XAUUSD") -> `mt5_bridge.SYMBOL_MAP` + lots conversion.
4. **Real starting balance** ($1M rules vs $100M seen in the demo) -> `--equity`.
5. Whether a **Syphonix API** appears; whether **updated historical data** (with real depth / crypto) is released.

## OFFICIAL RULES (released Jun 15) - reconciled
- **Scoring 70/15/10/5 is EXACT** (§11). My `config.py` already matched. No change needed.
- **Initial funds $1,000,000, max leverage 30x** (§2) - confirmed (the $100M in the demo was a sandbox).
- **Risk-discipline tiers match exactly** (§13): margin >90%/95%/98%, leverage >28x/29x/~30x, single-instrument >90%, net-directional >95%. My safe caps sit below all of them.
- **Red lines** (§14): forced liquidation = elimination; bug/quote/latency exploit, API abuse (safe harbor ≤500/s), multi-account, collusion = DQ. Aligned.
- **FIX APPLIED:** competition **Sharpe is NON-annualized** = Mean/Std of 15-min equity returns (§12.5/§17). Updated `metrics.py` to report it (e.g. recommended config = 0.0101; annualized ~1.89). **Ranks are unchanged**, so every relative conclusion still holds. Also added the <8-obs Sharpe-rank cap and the exact rank formula 100*(N-Rank)/(N-1).
- **Equity carries across rounds** (Return measured vs the fixed $1M); **Risk Discipline resets each round**. Knockout by Final Score at each 22:00 cutoff; Top 100 -> Finals.
- **$10k Best Sharpe** (§17): Finals + Top 50 + no red-line + >=30 trades. I clear the trade count easily.
- **Timeline:** method selection **Jun 19 08:00**; launch **Jun 21 22:00**; Round cuts 22/23/24 Jun 22:00; Finals to 26 Jun 22:00; results 27 Jun.

**Bottom line:** the official rules validate the entire design I built. Only correction was the Sharpe units.
