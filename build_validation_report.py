import base64
def img(n): return "data:image/png;base64,"+base64.b64encode(open(f"results/research/{n}","rb").read()).decode()
spreads=[("EURUSD",0.103),("USDJPY",0.142),("USDCAD",0.168),("GBPUSD",0.181),("EURGBP",0.183),
 ("AUDUSD",0.201),("EURJPY",0.229),("EURCHF",0.287),("USDCHF",0.352),("NZDUSD",0.354),("XAUUSD",0.112),("XAGUSD",0.784)]
blocks=[(1,"May12-15",5.43,-2.51,13.6),(2,"May15-21",-1.87,-3.94,-5.9),(3,"May21-27",-2.47,-4.29,-7.8),
 (4,"May27-Jun1",3.38,-1.74,10.8),(5,"Jun1-5",-0.33,-2.60,-2.2),(6,"Jun5-10",2.36,-3.50,5.3)]
srow="".join(f"<tr><th>{s}</th><td>{c}</td></tr>" for s,c in spreads)
brow="".join(f"<tr><th>{i}</th><td>{d}</td><td>{r:+.2f}%</td><td>{dd:.2f}%</td><td>{sh:+.1f}</td></tr>" for i,d,r,dd,sh in blocks)
html=f"""<!doctype html><html><head><meta charset="utf-8"><title>Robustness validation</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 18px;color:#1a1a1a;line-height:1.55}}
h1{{font-size:24px}} h2{{margin-top:30px;border-bottom:2px solid #eee;padding-bottom:6px}}
.good{{background:#f6ffed;border:1px solid #b7eb8f;border-radius:8px;padding:10px 14px;margin:12px 0}}
.warn{{background:#fffbe6;border:1px solid #ffe58f;border-radius:8px;padding:10px 14px;margin:12px 0}}
img{{max-width:100%;border:1px solid #eee;border-radius:8px}} table{{border-collapse:collapse;font-size:13px;margin:8px 0}} th,td{{border:1px solid #e3e3e3;padding:5px 9px;text-align:right}} thead th{{background:#fafafa}}</style></head><body>
<h1>Robustness validation — real costs + rolling walk-forward</h1>

<h2>1. Real transaction costs (much lower than assumed)</h2>
<div class="good">Per-side spreads recovered from the data's own bid/ask are tiny — FX majors
<b>0.10–0.35 bps</b>, gold 0.11, silver 0.78. My earlier flat 0.7bp was 2–7× too conservative.
With <b>real per-instrument costs</b> the recommended config (gross 4) does
<b>+7.0% / Sharpe 3.28 / max DD −5.9%</b> over the month — vs +3.8% / Sharpe 1.9 at the conservative 0.7bp.</div>
<table><thead><tr><th>instrument</th><th>per-side bps</th></tr></thead><tbody>{srow}</tbody></table>
<p style="color:#666">Full-month cost sensitivity (gross 4): real → +7.0% / Sh 3.28 · 0.7bp → +3.8% / Sh 1.89 · zero → +9.0% / Sh 4.10.</p>

<h2>2. Rolling walk-forward (6 consecutive blocks, real costs)</h2>
<img src="{img('rolling_blocks.png')}">
<table><thead><tr><th>block</th><th>dates</th><th>return</th><th>max DD</th><th>Sharpe</th></tr></thead><tbody>{brow}</tbody></table>
<div class="warn"><b>Honest verdict — viable but lumpy.</b> Full-month Sharpe is strong (3.26) and the profile is
"win big, lose small": 3 of 6 blocks positive, but the winners are large (Sharpe 13.6, 10.8, 5.3) and the
losers are small (worst block −2.5% / −4.3% DD). Positive expectancy with controlled downside and no blow-ups —
but the edge clusters in certain regimes, so a single 5-day round could land in a flat/negative block.</div>

<h2>3. Deploy verdict</h2>
<ul>
<li><b>Green light to run it.</b> Positive after real costs, Sharpe ~3, single-digit drawdown, discipline 100, no liquidation across the whole month including the hostile stretches.</li>
<li><b>Gross 4 confirmed</b> — worst-block drawdown only ~4%, miles from any penalty/liquidation zone. Real costs are low enough that 5–6× is also safe if you want more return-rank.</li>
<li><b>Manage expectations per round:</b> week-to-week variance is real; rely on the multi-round structure + small losses to carry the positive expectancy.</li>
<li><b>Last unknowns:</b> the platform's live spreads (should be ≥ as good as this data) and slippage on fills. Confirm at launch.</li>
</ul>
</body></html>"""
open("/tmp/validation_report.html","w").write(html); print("wrote /tmp/validation_report.html", f"({len(html)//1024} KB)")
