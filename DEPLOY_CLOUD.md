# Cloud deployment — Northflank "mission control"

A live, public cloud service that serves your **dashboard** and runs the **AI trading desk**
(Nemotron + Claude, traced in Logfire). It's the impressive, demonstrable cloud piece for the
judges — without pretending the cloud can do what only the Windows box can.

## Architecture (honest split)

```
  YOUR WINDOWS BOX                          NORTHFLANK (cloud, public URL)
  ----------------                          -----------------------------
  MT5 terminal (login 10009)                mission-control web service
  mt5_feed.py    -> panel_live.parquet      GET /          -> live dashboard.html
  live_runner.py -> book.json   ───────────▶ GET /api/desk  -> runs desk.py on book.json
  desk.py + mt5_bridge.py (execution)       GET /health     -> health check
                                            cron: desk-review every 15 min -> Logfire
```

MetaTrader5's Python package is **Windows-only**, so price feed and order execution stay on
your machine. The cloud runs the advisory/observability layer: the dashboard, the AI desk,
and Logfire tracing. State (the current `book.json`) reaches the cloud either by committing it
to the repo the service builds from, or by syncing it to the service's `/data` volume.

## Endpoints

| Route | What it returns |
|-------|-----------------|
| `/` | the live dashboard page |
| `/health` | `{"status":"ok"}` (Northflank health check) |
| `/api/desk` | runs the AI desk on the latest `book.json`, returns the decision JSON |
| `/api/status` | the most recent `desk_decision.json` |

## Deploy (one service)

1. Push this folder to a Git repo Northflank can read (GitHub/GitLab), or use the Northflank CLI.
2. Create a **Combined Service** → build from **`live/Dockerfile`**, context = repo root.
3. Set port **8080**, public, health check **`/health`**, region **London (eu-west)**.
4. Add secrets: `NVIDIA_API_KEY`, `ANTHROPIC_API_KEY` (optional), `LOGFIRE_TOKEN` (optional),
   and env `NEMOTRON_MODEL=nvidia/nemotron-mini-4b-instruct`.
5. Deploy. Open the public URL → the dashboard loads; `/api/desk` returns a live desk decision.

The included **`live/northflank.json`** captures this spec (service + an optional 15-minute
`desk-review` cron job that writes traces to Logfire).

## Run it locally first (sanity check)

```bash
PORT=8080 python live/server.py
# then: curl localhost:8080/health   and open localhost:8080/ in a browser
```

## Notes
- The container deliberately omits MetaTrader5 (Windows-only) — it never trades; it's advisory.
- For full Nemotron + Claude + Logfire output, set the three secrets; without them the desk
  still runs on deterministic fallbacks.
