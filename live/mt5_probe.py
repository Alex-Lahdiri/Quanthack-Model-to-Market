"""
MT5 PROBE — run on your Windows host after the MT5 terminal is installed + logged in.

It connects to the competition account, dumps the full tradable symbol list + contract
specs to `mt5_symbols.json`, matches our 12-name universe to the broker's exact symbol
names, and confirms the live data feed works. Send the JSON to Claude (it has NO secrets)
to finalize SYMBOL_MAP, lot conversion, and the feed.

Credentials come from ENV VARS — never hardcode/share them:
  set MT5_LOGIN=10009  &  set MT5_PASSWORD=...  &  set MT5_SERVER=3.11.134.149:443
"""
from __future__ import annotations
import os, sys, json

try:
    import MetaTrader5 as mt5
except Exception:
    sys.exit("Install the MT5 python package on your Windows host:  pip install MetaTrader5")

OUR = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
       "EURJPY","EURGBP","EURCHF","XAUUSD","XAGUSD"]

login = int(os.environ.get("MT5_LOGIN", "0")) or None
pw = os.environ.get("MT5_PASSWORD")
server = os.environ.get("MT5_SERVER")
ok = mt5.initialize(login=login, password=pw, server=server) if login else mt5.initialize()
if not ok:
    sys.exit(f"MT5 initialize failed: {mt5.last_error()}  (open the terminal + log in first)")

acct = mt5.account_info()
print(f"connected: login {getattr(acct,'login',None)} | balance {getattr(acct,'balance',None):,} "
      f"{getattr(acct,'currency','')} | leverage 1:{getattr(acct,'leverage',None)} | trade_mode {getattr(acct,'trade_mode',None)} (0=real,1=demo,2=contest)")

ti = mt5.terminal_info()
if getattr(ti, "trade_allowed", False):
    print("Algo Trading: ENABLED  (orders can be sent)")
else:
    print("Algo Trading: *** OFF *** -> click the 'Algo Trading' button in the MT5 toolbar (turns green).")
    print("              Until it's on, every live order returns retcode 10027 and nothing executes.")

syms = mt5.symbols_get() or []
rows = []
for s in syms:
    rows.append({
        "name": s.name, "description": getattr(s, "description", ""), "path": getattr(s, "path", ""),
        "digits": s.digits, "contract_size": getattr(s, "trade_contract_size", None),
        "volume_min": s.volume_min, "volume_step": s.volume_step, "volume_max": s.volume_max,
        "trade_mode": s.trade_mode, "spread": s.spread,
    })
json.dump({"account": {"balance": getattr(acct, "balance", None), "currency": getattr(acct, "currency", ""),
                       "leverage": getattr(acct, "leverage", None), "trade_mode": getattr(acct, "trade_mode", None)},
           "symbols": rows}, open("mt5_symbols.json", "w"), indent=2)
print(f"\nwrote mt5_symbols.json  ({len(rows)} symbols)  -> send this file to Claude")

# match our universe to broker symbol names
names = [r["name"] for r in rows]
print("\nuniverse match (our name -> broker symbol):")
matched = {}
for u in OUR:
    hit = next((n for n in names if n.upper() == u), None) \
        or next((n for n in names if u in n.upper()), None)
    matched[u] = hit
    print(f"  {u:<8} -> {hit or 'NOT FOUND'}")

# confirm the live data feed works on one matched symbol
probe = next((v for v in matched.values() if v), None)
if probe:
    mt5.symbol_select(probe, True)
    rates = mt5.copy_rates_from_pos(probe, mt5.TIMEFRAME_M1, 0, 5)
    tick = mt5.symbol_info_tick(probe)
    print(f"\nfeed check on {probe}: last bar {rates[-1] if rates is not None and len(rates) else 'none'}")
    print(f"  live tick bid/ask: {getattr(tick,'bid',None)} / {getattr(tick,'ask',None)}")
mt5.shutdown()
