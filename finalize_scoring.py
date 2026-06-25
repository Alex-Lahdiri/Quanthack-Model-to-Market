import sys, warnings, base64; warnings.filterwarnings("ignore"); sys.path.insert(0,".")
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import metrics as M
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget

UNIV=["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD","EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]
panel=pd.read_parquet("results/panel_full_month.parquet").set_index("ts").sort_index()[UNIV]
k=int(len(panel)*0.6); train,test=panel.iloc[:k],panel.iloc[k:]
peers=M.make_synthetic_peers(300,seed=1)
CFG=dict(mode="momentum",mom_window=480,vol_window=480,smooth_halflife=48,target_gross=4.0)
RB,COST=60,0.7

def run(pn):
    r=run_backtest(pn,DiversifiedVolTarget(**CFG),risk=RiskEngine(),rebalance_every=RB,cost_bps=COST)
    return r, M.compute_metrics(r.equity,r.telemetry,r.trade_count,r.liquidated)

rf,mf=run(panel); _,mtr=run(train); rt,mo=run(test)
scf=M.simulate_final_score(mf,peers); sco=M.simulate_final_score(mo,peers)
print("RECOMMENDED: 8h momentum | rebalance 60 | smooth 48 | gross 4 | cost 0.7bp | 12-name universe")
def show(tag,m,s):
    print(f"  {tag:<11} ret {m['total_return']*100:>6.2f}%  maxDD {m['max_drawdown']*100:>6.2f}%  "
          f"Sharpe {m['sharpe']:>5.2f}  disc {m['discipline']:>3.0f}  trades {m['trade_count']:>5}  score {s['final_score']:.1f}")
show("FULL MONTH",mf,scf); show("OOS (last40%)",mo,sco)

fig,ax=plt.subplots(figsize=(9,4)); ax.plot(rf.equity.index, rf.equity.values, lw=1.2)
ax.axvline(test.index[0],color="firebrick",ls="--",lw=1,label="train/test split")
ax.set_title("Recommended config — equity (full month, gross 4)"); ax.set_ylabel("Equity $"); ax.grid(alpha=.3); ax.legend()
fig.tight_layout(); fig.savefig("results/research/recommended_equity.png",dpi=120); plt.close(fig)

def img(n): return "data:image/png;base64,"+base64.b64encode(open(f"results/research/{n}","rb").read()).decode()
html=f"""<!doctype html><html><head><meta charset="utf-8"><title>Scoring-tuned config</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 18px;color:#1a1a1a;line-height:1.55}}
h1{{font-size:24px}} h2{{margin-top:30px;border-bottom:2px solid #eee;padding-bottom:6px}}
.key{{background:#f6ffed;border:1px solid #b7eb8f;border-radius:8px;padding:10px 14px;margin:12px 0}}
.box{{background:#e6f4ff;border:1px solid #91caff;border-radius:8px;padding:10px 14px;margin:12px 0}}
img{{max-width:100%;border:1px solid #eee;border-radius:8px;margin:8px 0}} table{{border-collapse:collapse;font-size:13px}} th,td{{border:1px solid #e3e3e3;padding:5px 9px;text-align:right}} thead th{{background:#fafafa}}</style></head><body>
<h1>Scoring-tuned operating point</h1>
<div class="box"><b>The lever was turnover, not leverage.</b> The thin 8h-momentum edge was being eaten by
transaction costs at 15-min rebalancing. Slowing to hourly rebalancing + heavy smoothing (and using
realistic ~0.7bp FX-major spreads) flips the full month to <b>positive with Sharpe ~1.9</b>. Leverage is
then only a return-vs-drawdown dial — and the simulated score is nearly flat in gross, because the
gross-invariant Sharpe/discipline ranks dominate.</div>

<h2>Recommended configuration</h2>
<div class="key">8-hour cross-sectional momentum · market-neutral (demeaned) · inverse-vol sizing ·
<b>rebalance hourly</b> · <b>smoothing half-life 48</b> · <b>gross 4×</b> · 12-name liquid universe
(one gold, no pegs/redundant crosses) · sized up in the 12–15 UTC session via the risk engine.</div>
<table><thead><tr><th>window</th><th>return</th><th>max DD</th><th>Sharpe</th><th>discipline</th><th>trades</th><th>sim score</th></tr></thead><tbody>
<tr><th>full month</th><td>{mf['total_return']*100:.2f}%</td><td>{mf['max_drawdown']*100:.2f}%</td><td>{mf['sharpe']:.2f}</td><td>{mf['discipline']:.0f}/100</td><td>{mf['trade_count']}</td><td>{scf['final_score']:.1f}</td></tr>
<tr><th>out-of-sample</th><td>{mo['total_return']*100:.2f}%</td><td>{mo['max_drawdown']*100:.2f}%</td><td>{mo['sharpe']:.2f}</td><td>{mo['discipline']:.0f}/100</td><td>{mo['trade_count']}</td><td>{sco['final_score']:.1f}</td></tr>
</tbody></table>
<img src="{img('recommended_equity.png')}">

<h2>Leverage frontier</h2>
<img src="{img('scoring_frontier.png')}">
<div class="key">Sharpe is ~constant in gross; return and drawdown scale together; worst-half stress drawdown
stays modest (≈−7% at 4×, no liquidation). Sim score barely moves (≈58–60), so there's no scoring reason to
over-lever — and the elimination/liquidation rules make tail safety paramount. 4× balances return-rank upside
with a safe drawdown; push to 5–6× only if you deliberately want more return-rank variance.</div>

<h2>How this maps to the 70/15/10/5 score</h2>
<ul>
<li><b>Sharpe (10%) + discipline (5%):</b> strong — Sharpe ~1.9, discipline 100/100, ≥30 trades → also targets the $10k Sharpe prize.</li>
<li><b>Drawdown (15%):</b> strong — single-digit drawdown, no blow-ups across the month incl. the hostile half.</li>
<li><b>Return (70%):</b> modest-positive. The edge is thin, so you rank on consistency + others' mistakes, not a big number.</li>
</ul>
<h2>Caveats</h2>
<ul><li>One month, one split; Sharpe ~1.9 is encouraging but not high-confidence. Costs are the swing factor (breakeven ~1.3bp) — confirm real spreads per instrument on the platform.</li>
<li>Sim score uses a synthetic competitor field; treat as directional. Re-rank against the real 5-min-delayed leaderboard once rounds start.</li></ul>
</body></html>"""
open("/tmp/scoring_tuning_report.html","w").write(html)
print("\nwrote /tmp/scoring_tuning_report.html", f"({len(html)//1024} KB)")
