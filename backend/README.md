# Harbor backend

Python + FastAPI. The design is in [../docs/DESIGN.md](../docs/DESIGN.md) and the API contract is in
[../docs/API.md](../docs/API.md).

## First-time setup (Windows PowerShell)

Run these from the `backend` folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Then open `.env` and fill in your keys. Git ignores `.env`, so your keys stay on your computer.

## Run the server

```powershell
uvicorn harbor.main:app --reload --workers 1
```

- Health check: http://localhost:8000/health
- Clickable API docs: http://localhost:8000/docs

Harbor uses one worker on purpose. The demo clock and the scheduler live inside the process.

No Nessie key yet? Set `NESSIE_MODE=fake` in `.env` and Harbor uses FakeNessie, an in-memory bank
with the same interface. It forgets everything on restart; `POST /api/v1/demo/persona` rebuilds Maria.

The database is `backend/harbor.db` (SQLite, git-ignored). After a model change, stop the server and
delete it; it's rebuilt on the next start.

## Seed the demo persona

```powershell
python -m harbor.seed
```

Creates (or repairs) Maria Lopez, ZIP 33602: a fictional Nessie customer, Checking $420, Savings $500,
"Brokerage Settlement (Harbor)" $0 and a sample T. Rowe Price ETF portfolio. Safe to run again.
`POST /api/v1/demo/persona` does the same thing over HTTP.

## Rebuild the Milton replay (demo data)

The demo replays Hurricane Milton from real NOAA archives committed in `data/replays/milton-2024/`
(about 1.2 MB: cones and tracks as GeoJSON, wind probabilities clipped to Florida, arrival times and
archived NWS alerts for the demo ZIPs). You only need this to rebuild them:

```powershell
pip install -e ".[dev,tools]"
python tools/fetch_replay.py
```

It downloads about 140 files from NHC and the Iowa Environmental Mesonet (one request a second),
keeps the raw downloads in `data/replays/.cache/` (git-ignored) and rewrites only its own files in
the replay folder. Every advisory time comes from the archive, never from the code.

## Regenerate the API schema for the frontend

```powershell
python tools/export_openapi.py
```

Writes `docs/openapi.json`. Run it after any endpoint or field change, and update `docs/API.md` too.

## Run the tests

```powershell
pytest
```

## Check Nessie (hour 1)

With `NESSIE_API_KEY` set in `.env`:

```powershell
python tools/probe_nessie.py
```

The probe creates a fictional customer and accounts and tests how Nessie really behaves: what a
POST returns, transfer timing, overdrafts, withdrawals, deposits, purchases and rate limits. It
then prints findings to copy into DESIGN.md §1.8 and deletes the accounts it made.

## Deploy for judging

Harbor runs as **one process with one worker**: the demo clock and the scheduler live inside it.
All demo data (Milton replay, sensors, prices, evacuation data) is in `data/`, so a deploy needs
no internet access to NOAA, USGS or OpenStreetMap.

**Railway or Render (no Docker):** point the service at the `backend` folder. It installs from
`pyproject.toml` and starts with the `Procfile` command. Set these environment variables:

- `HARBOR_MODE=demo`
- `NESSIE_MODE=live` with `NESSIE_API_KEY=...`, or `NESSIE_MODE=fake` for the offline bank
- `ANTHROPIC_API_KEY=...` (optional; without it the plan review uses template text)
- `CORS_ORIGINS=["https://your-frontend.vercel.app"]` (a JSON list)

Use an always-on plan: a service that sleeps also stops the scheduler.

**Docker:** with Docker Desktop running, from `backend/`:

```powershell
docker build -t harbor-backend .
docker run -p 8000:8000 --env-file .env harbor-backend
```

The SQLite database lives inside the container and starts empty on each deploy;
`POST /api/v1/demo/persona` rebuilds Maria (or `{"persona": "ruth"}` for the second persona).

**Fallback on demo day:** run everything locally on the laptop (see "Run the server" above) with
`NESSIE_MODE=fake`. That needs no network at all.
