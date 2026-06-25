import base64, os
import pandas as pd
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "research")
def img(n):
    with open(os.path.join(OUT, n), "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()
os.makedirs(OUT, exist_ok=True)
stats = pd.read_csv(os.path.join(OUT, "instrument_stats.csv"), index_col=0)
icm = pd.read_csv(os.path.join(OUT, "ic_matrix.csv"), index_col=0)
def table(df, fmt="{:.3f}"):
    th = "".join(f"<th>{c}</th>" for c in df.columns)
    rows = "".join("<tr><th>"+str(i)+"</th>"+"".join(f"<td>{v if isinstance(v,str) else fmt.format(v)}</td>" for v in r)+"</tr>" for i,r in df.iterrows())
    return f"<table><thead><tr><th></th>{th}</tr></thead><tbody>{rows}</tbody></table>"

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Quanthack - Alpha Research (full month)</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:980px;margin:24px auto;padding:0 18px;color:#1a1a1a;line-height:1.55}}
h1{{font-size:26px;margin-bottom:2px}} h2{{margin-top:34px;border-bottom:2px solid #eee;padding-bottom:6px}}
.sub{{color:#666}} .verdict{{background:#fff1f0;border:1px solid #ffa39e;border-radius:8px;padding:12px 16px;margin:16px 0}}
.key{{background:#f6ffed;border:1px solid #b7eb8f;border-radius:8px;padding:10px 14px;margin:12px 0}}
img{{max-width:100%;border:1px solid #eee;border-radius:8px;margin:10px 0}}
table{{border-collapse:collapse;font-size:13px;margin:10px 0}} th,td{{border:1px solid #e3e3e3;padding:4px 8px;text-align:right}} thead th{{background:#fafafa}}
li{{margin:5px 0}}
</style></head><body>
<h1>Quanthack - Alpha Research (full month)</h1>
<div class="sub">21 instruments (USDHKD dropped as pegged) · 1-min → 15-min · 2026-05-11 → 2026-06-10 (33,124 bars)</div>

<div class="verdict"><b>Headline verdict:</b> the strong 2-week backtest was a <b>favorable sub-window, not a durable edge.</b>
Over the full month the momentum strategy is weak and regime-dependent - the first half (May 11–28) lost on every
config, and the best out-of-sample result was only <b>+0.6% / Sharpe 0.73</b> (8-hour momentum). The research-built v2
still underperformed. What <i>is</i> robust: <b>risk discipline (100/100), controlled drawdowns, and no blow-ups</b>.
Translation for the competition: compete on survival + risk-adjusted ranks, not on a big return bet.</div>

<h2>1. Factor structure - a persistent USD factor (~50%)</h2>
<img src="{img('pca.png')}">
<div class="key">PC1 explains <b>50.4%</b> of variance - same clean USD factor as the 2-week cut, so this is robust:
USD-quote pairs and gold/silver load positive, USD-base pairs negative. The five gold instruments
(XAUUSD/XAUCNH/XAUGCNH/XAUHKD/XAUKUSD) load near-identically - they're <b>redundant</b>, so trade one gold, not five.</div>
<img src="{img('corr_heatmap.png')}">

<h2>2. Where the edge lives - slow momentum, but weak</h2>
<img src="{img('ic_heatmap.png')}">
{table(icm)}
<div class="key">Short lookbacks remain noise/reversion (mean 15-min autocorrelation −0.037). Long lookbacks
(≈8h) are the most <i>consistently</i> positive, but <b>nothing is statistically significant</b> (max t ≈ 1.1).
With more data the signal got <i>weaker</i>, not stronger - the 2-week t≈1.8 was partly luck. A real but thin edge.</div>

<h2>3. Risk & fat tails</h2>
{table(stats, fmt="{:.2f}")}
<div class="key">Silver (65%) and oil (65% / 57%) are the vol monsters; gold ~27%; FX 4–10%. <b>USDJPY</b> (excess
kurtosis 18, skew −1.4) and <b>AUDNZD</b> (kurtosis 18) are the tail-risk names - cap them. Inverse-vol sizing is
mandatory, and a vol floor is needed to keep pegged pairs (USDHKD) from soaking up leverage.</div>

<h2>4. Intraday timing - robust session effect</h2>
<img src="{img('intraday_vol.png')}">
<div class="key">Volatility peaks <b>12–15 UTC</b> (London/NY overlap, ~0.08–0.10% per 15-min) and dies <b>20–21 UTC</b>
(~0.02%). Even cleaner with more data - a dependable timing signal for when to take vs. avoid risk.</div>

<h2>5. Strategy verdict (full-month walk-forward, 12-name liquid universe)</h2>
<table><thead><tr><th>config</th><th>TRAIN ret%</th><th>TRAIN Sharpe</th><th>OOS ret%</th><th>OOS Sharpe</th><th>OOS disc</th></tr></thead>
<tbody>
<tr><th>baseline mom480 (8h)</th><td>-10.65</td><td>-5.17</td><td>+0.63</td><td>0.73</td><td>100</td></tr>
<tr><th>v2 (research-built)</th><td>-7.16</td><td>-6.71</td><td>-4.00</td><td>-5.92</td><td>100</td></tr>
</tbody></table>
<div class="key">Both lost on the first-half train; out-of-sample the simple 8h momentum was barely positive and v2 was
negative. <b>v2 still does not beat the baseline with a full month of data</b> - the verdict from the 2-week test holds.
The durable value is risk control (discipline 100, drawdowns 8–20%, no liquidation), not return.</div>

<h2>6. So what should the competition strategy be?</h2>
<ul>
<li><b>Lower expectations on return alpha.</b> A month of FX/metals gives only a thin, regime-dependent momentum edge.</li>
<li><b>Compete on the 30% (drawdown + Sharpe + discipline) and survival.</b> The book never blows up and stays inside every penalty tier - that alone is a strong, low-variance position, and it targets the $10k Sharpe prize.</li>
<li><b>Run 8h momentum at moderate gross</b>, market-neutral, inverse-vol, one gold, vol-floor on pegs, USDJPY/AUDNZD capped, sized up in the 12–15 UTC window.</li>
<li><b>Keep hunting</b> for orthogonal signals (carry, oil/metal-specific, event-driven) - but validate every one with this walk-forward before trusting it.</li>
</ul>

<h2>Caveats</h2>
<ul>
<li>One month, one split. t-stats are modest; treat signals as weak priors.</li>
<li>Descriptive analysis is in-sample; the walk-forward is the honest P&L test.</li>
<li>No crypto here; live universe may differ.</li>
</ul>
</body></html>"""
open("/tmp/research_report.html", "w").write(html)
print("wrote full-month report", f"({len(html)//1024} KB)")
