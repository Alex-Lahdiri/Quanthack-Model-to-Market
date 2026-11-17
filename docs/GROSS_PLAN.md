# Per-round gross game-plan (tournament tactics)

The single biggest lever you control on **placement** is gross leverage. Here's how my book
actually behaves - measured on shrinkage-MV, the live 10 names, the full month, with real venue
costs **and the per-name risk caps applied** (name ≤ 30% of the book, ≤ 75% of equity).

## The gross frontier (with risk caps)

| Gross | ~Return | ~Max DD | Sharpe (15m) | Discipline | Margin use | Peak 1-name |
|------:|--------:|--------:|:------------:|:----------:|:----------:|:-----------:|
| 1.5 | +6% | −3.5% | 0.024 | 100 | 5% | 46% |
| 2 | +9% | −4.6% | 0.024 | 100 | 7% | 61% |
| 3 | +12% | −6.9% | 0.024 | 100 | 10% | 78% |
| 4 | +12.5% | −7.9% | 0.022 | 100 | 14% | 79% |
| 5 | +13% | −8.2% | 0.022 | 100 | 17% | 79% |
| 6 | +14% | −8.3% | 0.022 | 100 | 19% | 79% |

Three things to notice:

- **Sharpe is flat** (~0.024) at every level - gross does **not** affect your Sharpe-prize standing. Run whatever the tournament needs.
- **Returns flatten above ~gross 3–4.** Earlier (before the caps) gross 6 showed +27%, but that came from letting one name balloon to 100%+ of equity. With the caps, the realistic ceiling is ~+14%, and **gross 4 captures nearly all of it.** Pushing past 4 just adds drawdown.
- **No blow-up risk anywhere** - margin only 19% at gross 6, discipline 100, no liquidation. The danger from gross is drawdown, not DQ.

## The tournament logic

Score = **70% return rank** + 15% drawdown + 10% Sharpe + 5% discipline. It's a **knockout**: equity carries between rounds, and one catastrophically bad round ends you. So the trade is *expected rank* vs *variance of rank*.

- **Early rounds (big field, just avoid the bottom cut):** you only need "not last." Low gross = low variance = low chance of a freak bad round, while the reckless players (30×, all-in) blow themselves up and fill the elimination zone for you. **Run gross 2.** Survival is the whole game.
- **Middle rounds:** advancing comfortably → stay 2–3. Near the cut → 3–4 to climb the return rank.
- **Final round / going for the win:** push to **gross 4** - that's the efficient max now; 5–6 add drawdown for ~1pp. Only stretch toward 5 if you're behind and *must* win.

The `--dd-guard` ladder runs underneath everything and auto-cuts size if a round turns against you (3% DD → ×1.0, 5% → ×0.7, 8% → ×0.4, 12% → ×0.2), so the downside of a higher gross is capped in practice.

## Default plan

| Round | Situation | Gross |
|------:|-----------|:-----:|
| 1 | Survive the first cut | **2** |
| 2 | Comfortable → 2–3; near the cut → 3–4 | **2–4** |
| 3+ | Final / must win → 4; protecting a place → 3 | **3–4** |

The takeaway from the caps: the "useful" range is **2–4**, and survival-first is even more clearly the right default - there's little return to be bought by over-levering.

## Use the planner

It turns your live standing into a recommended gross + the exact command:

```powershell
# early, position unknown:
python live\gross_planner.py --round 1 --rounds-total 4

# near the cut in round 2:
python live\gross_planner.py --round 2 --rounds-total 4 --standing at-risk

# final round, going for the win, feed it your equity:
python live\gross_planner.py --round 4 --rounds-total 4 --goal win --equity 1080000 --round-start-equity 1000000
```

Whatever number it gives, put it in `live\runtime.json` → `"gross"` and the next automated cycle uses it. **Start Round 1 at gross 2.**

> Caveat: one month of in-sample data, thin and partly-overfit edge. Treat these as the *shape* of the trade-off (Sharpe-flat, concave in gross, no blow-up), not a promise of +14%. Live will be smaller and noisier - which is exactly why I survive first and only lean up when the tournament math demands it.
