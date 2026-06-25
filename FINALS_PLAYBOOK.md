# Quanthack - Finals Playbook

**Status:** Round 3 done, system paused. One reference to execute the finals fast.
**Honest aim:** win the **Tech prize** + a **strong composite placement** (smooth book + layered
protection), with **upside optionality** - Autopilot presses if the finals trend and the scalpers
get purged in the audit. We do *not* try to out-scalp the BTC HFT bot for the raw-return crown.

---

## 0. Before the finals open
- [ ] **Confirm you qualified** - check the roster when the leaderboard's back (top 100 advances).
- [ ] **Log into the console** within any 8-hour window (8h inactivity = DQ).
- [ ] **Infra decision:** VPS (best - never sleeps; see `VPS_SETUP.md`) *or* laptop kept awake
      (plugged in, lid open, `powercfg` sleep disabled). The overnight outage was *sleep* - don't repeat it.
- [ ] **Re-anchor the profit-lock:** delete `profit_peak.json` so the ratchet tracks gains from the finals-start equity.

## 1. At finals start - validate, don't assume (≈5 min)
```powershell
python live\mt5_feed.py --out panel_live.parquet --lookback-days 5
python live\micro_scan.py --panel panel_live.parquet --days 5
python live\edge_scan.py --days 5
```
Pick the strategy from the data, not a hunch:
- **Reversion structure holds** (60-min autocorr negative; rev positive across sub-periods) → `rev`, 15-min cadence.
- **Flipped to trending** (momentum IC positive *and* t ≥ 2) → `iv`, 4-hour cadence.
- **Choppy / no clear edge** → `rev` at the low end, or near-flat. Don't force a bet.

## 2. Lock the config (`live\runtime.json`)
```json
{ "gross": 1.5, "live": true, "strategy": "rev" }
```
- **Gross band 1.0–2.0.** Default low (1.0–1.5). Press toward 2.0+ *only* if **live P&L confirms** the edge is paying - never on a backtest alone.
- Cadence: `rev` → `register_task.ps1 -IntervalMinutes 15`; `iv` → 4h.

## 3. Protections (all on - verify)
- Risk-engine caps: per-name 30%, metals sector, net-directional, gross/margin - always.
- Drawdown ladder: 3 / 5 / 8 / 12% → ×0.7 / 0.4 / 0.2 / lockdown.
- **Profit-lock ratchet:** once up ≥0.5%, de-risks at 25 / 50 / 75% give-back of peak gain → ×0.7 / 0.4 / 0.2.
- **Fast monitor** every 3 min (now includes profit-lock), reduce-only; emergency flatten if margin < 200%.
- Preflight: halts a cycle on stale feed / insane book.

## 4. Let Autopilot drive
- `python live\autopilot.py --logfire` (shadow) → see Nemotron + Claude's read each session.
- `--arm` lets it set the governed config - it **cannot** breach the gross band or press in a no-edge regime.

## 5. Operating rules
- **Judge by LIVE P&L, not the backtest.** Bleeding despite a green scan → cut gross.
- **Press only when the edge pays live AND you're watching** (or Autopilot confirms). Default smooth.
- **Any unattended stretch / overnight / travel → gross 1.0** (or let the VPS run it).
- Re-scan at every natural break.

## 6. Prize plan
- **Tech prize (highest EV):** repo + Autopilot demo + the honest momentum→tested→reversion story. Pitch **June 27**.
- **Composite placement:** smooth + disciplined beats the bleeding field; protections defend it.
- **Upside:** Autopilot captures return rank *if* the finals trend and scalpers get purged.
