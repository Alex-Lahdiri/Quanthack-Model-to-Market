"""
autopilot.py -- AUTONOMOUS AI quant desk ("Autopilot"), the AI-native control layer.

Each run it RE-TUNES the system from live data:
  1. reads the live regime (momentum IC + t-stat + a net-of-cost lever backtest),
  2. NVIDIA Nemotron (Analyst) classifies the regime  -> Pydantic AnalystView,
  3. Anthropic Claude (Strategist) proposes strategy/gross/cadence -> Pydantic PlanProposal,
  4. a deterministic GOVERNOR clamps the proposal to competition-safe bounds (it can never
     size up in a no-edge regime or breach the gross band / drawdown ladder),
  5. every step is Logfire-traced and routed through the multi-provider AI gateway.

SAFETY: it NEVER trades. In SHADOW (default) it only writes an advisory decision file. With
--arm it writes the *governed* plan to runtime.json, which the normal risk-engine pipeline
then applies. With no API keys it runs on deterministic fallbacks, so it always works.

  python live/autopilot.py                 # SHADOW: propose only
  python live/autopilot.py --arm --logfire # ARMED: write governed plan to runtime.json, traced
"""
from __future__ import annotations
import argparse, json, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from pydantic import BaseModel, Field
import ai_gateway
from engine import run_backtest
from risk_engine import RiskEngine
from strategies import DiversifiedVolTarget
from strategies.cov_aware import CovAwareMomentum

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX10 = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","EURGBP","EURCHF","XAUUSD","XAGUSD"]
RC = {"EURUSD":0.08,"GBPUSD":0.08,"USDCAD":0.08,"AUDUSD":0.08,"USDJPY":0.16,"USDCHF":0.19,
      "EURGBP":0.15,"EURCHF":0.15,"XAUUSD":0.80,"XAGUSD":1.20}
GROSS_FLOOR, GROSS_CEIL = 1.0, 3.0
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

def _dump(m): return m.model_dump() if hasattr(m, "model_dump") else m.dict()

class AnalystView(BaseModel):
    regime: str = Field(description="trending | choppy | reverting")
    confidence: float = Field(ge=0, le=1)
    note: str = ""

class PlanProposal(BaseModel):
    strategy: str = Field(description="iv or mv")
    gross: float = Field(ge=0, le=10)
    cadence_hours: int = Field(ge=1, le=8)
    rationale: str = ""
    confidence: float = Field(ge=0, le=1)

def _span(use, name):
    if use:
        try:
            import logfire
            if os.environ.get("LOGFIRE_TOKEN"): logfire.configure()
            return logfire.span(name)
        except Exception: pass
    class _N:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return _N()

def regime_read(panel_path, days, use_lf):
    with _span(use_lf, "autopilot.regime"):
        p = pd.read_parquet(panel_path).set_index("ts").sort_index()
        p = p[[c for c in FX10 if c in p.columns]].astype(float)
        p = p[p.index >= p.index.max() - pd.Timedelta(days=days)]
        def ic(lb, fwd):
            mom = p.pct_change(lb); momd = mom.sub(mom.mean(axis=1), axis=0)
            f = p.pct_change(fwd).shift(-fwd)
            return momd.corrwith(f, axis=1).dropna()
        s1, s4 = ic(480, 60), ic(480, 240)
        ic1 = float(s1.mean()) if len(s1) else 0.0
        ic4 = float(s4.mean()) if len(s4) else 0.0
        sub = s4.iloc[::240]
        t4 = float(sub.mean() / (sub.std() / np.sqrt(len(sub)))) if (len(sub) > 4 and sub.std() > 0) else 0.0
        def bt(mode, g, rb):
            st = (CovAwareMomentum(mom_window=480, ema=48, target_gross=g, mode="mv") if mode == "mv"
                  else DiversifiedVolTarget(mode="momentum", mom_window=480, vol_window=480, smooth_halflife=48, target_gross=g))
            r = run_backtest(p, st, risk=RiskEngine(), rebalance_every=rb, cost_bps={k: RC[k] for k in p.columns})
            eq = r.equity; r15 = eq.resample("15min").last().dropna().pct_change().dropna()
            ret = float(eq.iloc[-1] / eq.iloc[0] - 1)
            sh = float(r15.mean() / r15.std()) if (len(r15) > 1 and r15.std() > 0) else 0.0
            dd = float((eq / eq.cummax() - 1).min())
            return ret, sh, dd
        iv, mv = bt("iv", 2.0, 240), bt("mv", 2.0, 240)
        return {"bars": int(p.shape[0]), "last": str(p.index[-1]),
                "ic_8h_1h": round(ic1, 4), "ic_8h_4h": round(ic4, 4), "t_8h_4h": round(t4, 2),
                "iv_ret": round(iv[0]*100,2), "iv_sharpe": round(iv[1],3), "iv_maxdd": round(iv[2]*100,2),
                "mv_ret": round(mv[0]*100,2), "mv_sharpe": round(mv[1],3), "mv_maxdd": round(mv[2]*100,2)}

def _det_proposal(reg):
    ic4, t4 = reg["ic_8h_4h"], reg["t_8h_4h"]
    if ic4 > 0.01 and t4 >= 2.0: g = 2.5
    elif ic4 > 0.005: g = 2.0
    elif ic4 > 0: g = 1.5
    else: g = 1.0
    return PlanProposal(strategy="iv", gross=g, cadence_hours=4, confidence=0.5,
                        rationale=f"IC4h {ic4} t{t4}: size to the confirmed edge; smoother iv engine.")

def run_analyst(reg, use_lf):
    with _span(use_lf, "autopilot.analyst.nemotron"):
        lab = "trending" if reg["ic_8h_4h"] > 0.01 else ("reverting" if reg["ic_8h_4h"] < -0.005 else "choppy")
        if not ai_gateway.configured():
            return AnalystView(regime=lab, confidence=0.4, note="deterministic (no AI key)"), "deterministic"
        model = ai_gateway.resolve_nemotron_model()
        prompt = (f"Live FX/metals regime: momentum IC 8h->1h={reg['ic_8h_1h']}, 8h->4h={reg['ic_8h_4h']} "
                  f"(t={reg['t_8h_4h']}). iv backtest ret {reg['iv_ret']}% Sharpe {reg['iv_sharpe']} maxDD {reg['iv_maxdd']}%. "
                  f"Classify regime as trending, choppy, or reverting; give confidence 0-1 and a one-line note.")
        v = ai_gateway.structured(model, prompt, AnalystView, provider="nvidia", max_tokens=200)
        return (v or AnalystView(regime=lab, confidence=0.4, note="fallback (parse failed)")), model

def run_strategist(reg, view, use_lf):
    with _span(use_lf, "autopilot.strategist.claude"):
        if not ai_gateway.configured():
            return _det_proposal(reg), "deterministic"
        prompt = (f"You set the next config for a market-neutral FX/metals desk in a knockout competition scored "
                  f"70% return / 15% drawdown / 10% Sharpe / 5% discipline.\nRegime: {view.regime} (conf {view.confidence}). "
                  f"Momentum IC 8h->4h={reg['ic_8h_4h']} t={reg['t_8h_4h']}. Backtests (every-4h, net of cost): "
                  f"iv ret {reg['iv_ret']}% Sharpe {reg['iv_sharpe']} maxDD {reg['iv_maxdd']}%; "
                  f"mv ret {reg['mv_ret']}% Sharpe {reg['mv_sharpe']} maxDD {reg['mv_maxdd']}%.\n"
                  f"Choose strategy (iv or mv), gross (1.0-3.0), cadence_hours (1, 2 or 4). Prefer the smoother engine; "
                  f"only raise gross when the edge is significant (t>=2). <=40-word rationale, confidence 0-1.")
        p = ai_gateway.structured(CLAUDE_MODEL, prompt, PlanProposal, provider="anthropic", max_tokens=300)
        return (p or _det_proposal(reg)), CLAUDE_MODEL

def govern(prop, reg, dd, use_lf):
    with _span(use_lf, "autopilot.governor"):
        strat = prop.strategy if prop.strategy in ("iv", "mv") else "iv"
        g = float(prop.gross)
        if reg["ic_8h_4h"] <= 0: g = min(g, 1.0)        # no edge -> defensive
        elif reg["t_8h_4h"] < 2.0: g = min(g, 1.5)       # weak/unproven edge
        if dd <= -0.08: g = min(g, 1.0)                  # drawdown ladder
        elif dd <= -0.05: g = min(g, 1.5)
        g = max(GROSS_FLOOR, min(GROSS_CEIL, g))          # hard safe band
        cad = prop.cadence_hours if prop.cadence_hours in (1, 2, 4) else 4
        clamped = (round(g, 2) != round(float(prop.gross), 2)) or (strat != prop.strategy) or (cad != prop.cadence_hours)
        return {"strategy": strat, "gross": round(g, 2), "cadence_hours": cad, "clamped": clamped}

def main():
    ap = argparse.ArgumentParser(description="Autonomous AI quant desk (advisory/shadow by default)")
    ap.add_argument("--panel", default=os.path.join(ROOT, "panel_live.parquet"))
    ap.add_argument("--days", type=float, default=5.0)
    ap.add_argument("--runtime", default=os.path.join(ROOT, "live", "runtime.json"))
    ap.add_argument("--dd", type=float, default=0.0, help="current drawdown fraction, e.g. -0.03")
    ap.add_argument("--emit", default=os.path.join(ROOT, "autopilot_decision.json"))
    ap.add_argument("--arm", action="store_true", help="write the governed plan to runtime.json")
    ap.add_argument("--logfire", action="store_true")
    args = ap.parse_args()

    with _span(args.logfire, "autopilot.cycle"):
        reg = regime_read(args.panel, args.days, args.logfire)
        view, an_model = run_analyst(reg, args.logfire)
        prop, st_model = run_strategist(reg, view, args.logfire)
        gov = govern(prop, reg, args.dd, args.logfire)
        cur = {}
        if os.path.exists(args.runtime):
            try: cur = json.load(open(args.runtime))
            except Exception: cur = {}
        change = (gov["strategy"] != cur.get("strategy")) or (round(float(cur.get("gross", -1)), 2) != gov["gross"])
        decision = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "regime": reg,
                    "analyst": {"model": an_model, **_dump(view)},
                    "strategist": {"model": st_model, **_dump(prop)},
                    "governed_plan": gov, "current_runtime": cur,
                    "mode": "ARMED" if args.arm else "SHADOW",
                    "action": ("APPLIED" if (args.arm and change) else ("WOULD-CHANGE" if change else "HOLD"))}
        json.dump(decision, open(args.emit, "w"), indent=2)
        if args.arm:
            newrt = dict(cur); newrt.update({"gross": gov["gross"], "strategy": gov["strategy"], "live": cur.get("live", True)})
            json.dump(newrt, open(args.runtime, "w"))

    print("\n=============== QUANTHACK AUTOPILOT (AI-native, self-adapting) ===============")
    print(f"  regime: {reg['bars']} bars to {reg['last']}")
    print(f"    IC 8h->4h {reg['ic_8h_4h']:+.4f} (t {reg['t_8h_4h']:+.2f}) | iv {reg['iv_ret']:+.2f}% Sh{reg['iv_sharpe']:+.3f} dd{reg['iv_maxdd']:+.2f}% | mv {reg['mv_ret']:+.2f}% Sh{reg['mv_sharpe']:+.3f}")
    print(f"  [Analyst    NVIDIA {an_model[:20]:<20}] {view.regime} (conf {view.confidence:.2f}) {view.note}")
    print(f"  [Strategist {st_model[:20]:<20}] propose: {prop.strategy} gross {prop.gross} cad {prop.cadence_hours}h (conf {prop.confidence:.2f})")
    print(f"       rationale: {prop.rationale}")
    print(f"  [Governor   deterministic safety    ] final: {gov['strategy']} gross {gov['gross']} cad {gov['cadence_hours']}h" + ("   <-- CLAMPED to safe bounds" if gov["clamped"] else ""))
    print(f"  current runtime: strategy={cur.get('strategy')} gross={cur.get('gross')}   MODE={decision['mode']}  ACTION={decision['action']}")
    print("==============================================================================\n")
    print(f"wrote {args.emit}" + ("  + updated runtime.json (gross+strategy; cadence is advisory)" if args.arm else "   (SHADOW: runtime.json untouched)"))

if __name__ == "__main__":
    main()
