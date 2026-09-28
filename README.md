# Gold Trading — Backend (FastAPI)

Collects the upcoming **MCX GOLD futures** (nearest 3 expiries by default) from
Upstox Market Data Feed V3, backfills history from Upstox Historical V3, and
serves candles for every chart timeframe plus a live WebSocket stream.

## Run locally

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env        # set UPSTOX_ACCESS_TOKEN
uvicorn app.main:app --reload      # API  → http://127.0.0.1:8000/docs
python -m workers.gold_collector   # live collector (second terminal)
```

## Production (Ubuntu VPS, no Docker)

Run two long-lived processes from this folder with the venv active
(systemd or PM2), and restart the collector first:

```bash
python -m workers.gold_collector                              # Upstox feed → MongoDB
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1  # API behind Nginx
```

Keep `--workers 1`: the automatic backfill runs inside the API process.
Nginx must pass WebSocket upgrades for `/api/v1/market/stream`.

## API v1

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health/live`, `/health/ready` | Process / MongoDB health |
| GET | `/market/instruments` | Collected GOLD contracts (expiries), nearest first |
| GET | `/market/instrument` | One contract (default: nearest expiry) |
| GET | `/market/ticks/latest`, `/market/ticks` | Latest / recent ticks |
| GET | `/market/candles?interval=4h&limit=1000` | `1m 5m 15m 30m 1h 4h 1d 1w 1mo` |
| WS | `/market/stream?interval=15m` | Live tick + current candle |
| GET | `/analytics/indicators`, `/backtest/summary` | Signal and backtest |
| POST | `/historical/sync` | Manual backfill (`intervals`, dates, `instrument_key`) |

Every market, analytics, backtest and stream endpoint accepts an optional
`instrument_key` (e.g. `MCX_FO|454818`) to choose the contract.

## How candles are built

Only two series are stored in MongoDB:

| Collection | Source | Used for |
| --- | --- | --- |
| `gold_candles_1m` | live collector + 1-minute backfill | 1m, 5m, 15m, 30m, 1h, 4h |
| `gold_candles_1d` | Upstox daily backfill | 1d, 1w, 1mo (today comes from live 1m data) |

Bucketing rules live in `app/services/candles.py` (IST-aligned; 4h bars start
at 09:00; weeks start Monday). The same rule is used by the MongoDB
aggregation and by the live stream.

## Live stream

`WS /api/v1/market/stream?interval=15m` polls MongoDB once a second and pushes
`{"type": "update", "tick": {...}, "candle": {...}}` whenever a new tick
arrives, plus a heartbeat every 15 s. It works on a standalone MongoDB (no
replica set required).

## Other collections

- `gold_ticks`: decoded live tick updates
- `instruments`: selected MCX Gold contract
- `historical_sync_logs`: backfill audit log
