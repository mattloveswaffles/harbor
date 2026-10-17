# Harbor system design

How the Harbor backend works, which data and APIs it uses, and why. The build schedule is in
[ROADMAP.md](ROADMAP.md) and the frontend contract is in [API.md](API.md).

**How to read this file.** Part 1 holds the decisions: the parts to build from. Part 2 holds the
detailed research notes for each subsystem: exact URLs, field names, quirks and sources, all checked
on 2026-10-16. Where a research note disagrees with Part 1, **Part 1 wins**; the conflicts are listed
in §1.7. Anything marked **UNVERIFIED** gets tested in hour 1 of the build.

---

# Part 1: Decisions

## 1.1 What Harbor is

Harbor watches hurricane forecasts and real sensors for a user's ZIP code. With the user's approval,
it gets evacuation money ready in time: savings to checking, a sale of only the ETF shares needed,
early enough to settle, and cash via Capital One's Nessie API. It plans a safe route and a place to
stay that suits the household and its budget, and puts the money back once the storm has really
passed. **Rules decide, the user approves, AI explains, and sensors gate safety.**

## 1.2 Whole-system picture

```
             DATA IN                                 (demo: committed replay files; live: same interfaces)
 NHC cone/track/wind-prob · NWS/IEM alerts · CO-OPS tide · USGS/NWPS river · NDBC buoy · ETF closes
 OSM hotels/ATMs · FEMA shelters · GSA per-diem · ORS/OSRM routing · Hillsborough evac zones
                                   │
 ┌──────────────── FastAPI (1 worker) ──────────────────────────────────────────────────────┐
 │ Clock (Real | Demo)  ←  /demo/start|advance|pause|reset                                  │
 │ APScheduler tick (2 s demo / 60 s live)                                                  │
 │   sources/forecast → zip exposure {p34, p64, in_cone, eta}                               │
 │   sources/sensors  → readings + status normal/watch/warning/stale                        │
 │   engine/risk      → level clear→monitor→prepare→act→shelter→recover   (pure function)   │
 │   evac/            → destination picker → route → shelters + lodging → household checklist│
 │   engine/plan      → budget (lodging, fuel, food, pets, buffer) → waterfall              │
 │                      checking → savings → ETF sale (T+1 calendar, tax lots, caps)        │
 │   ai/              → PlanReview (before approval) · Explain · Wrap-up report (after)     │
 │                      Claude text only → number validator → template fallback            │
 │   USER APPROVES (or edits → engine re-runs → new plan version)                           │
 │   executor         → state machine per move, tagged + reconciled                         │
 │        ├─ bank/nessie   transfers · withdrawals · deposits · purchases · bills           │
 │        └─ portfolio     SQLite lots, brokerage_cash T+1 queue                            │
 │   events           → DB row → per-user queue → SSE stream                                │
 │ SQLite (WAL): user, household, account, lot, plan, move, event, advisory, reading, evac  │
 └──────────────────────────────┬───────────────────────────────────────────────────────────┘
                REST (X-User-Id) + SSE (?user_id=) + GeoJSON map layers
                                ▼
        Next.js: dashboard by risk level · map (cone, route, shelters, hotels, ATMs, sensors)
        plan + AI review + approve · evacuation guide · sensors charts · /demo judge panel
```

The whiteboard versions are in [diagrams/](diagrams/).

**Responsibility rules**
- The rules engine (`engine/risk`, `engine/plan`, `evac/destination`) makes every decision. These are pure functions.
- The user approves every plan. Every ETF sale needs its own explicit tap.
- Claude writes text only, using numbers that come from the plan. A validator rejects any other
  number, and a template is used whenever Claude fails or is switched off.
- Sensors can raise risk, freeze money moves and hold recovery. They never move money on their own.
- Nessie is the record for bank balances. SQLite is the record for exact cents, moves, tax lots and the clock.

## 1.3 What the research changed

| Finding | Effect on the design |
|---|---|
| Nessie lives at `https://api.nessieisreal.com` (HTTPS only), with `?key=` auth. **A wrong key returns `200 []`**. Amounts are **whole dollars**. A POST may not return the new ID. The withdrawal path is singular (`/withdrawal/{id}`). Enterprise routes expose everyone's data. | Keep cents in SQLite. Round only inside `bank/nessie.py`: up when moving toward safety, down when restoring. Tag every write `[harbor:{move_id}]` and reconcile with `find_by_tag`. `/health` checks that the seeded customer exists. Use fictional people only. |
| **Nessie ATMs (13) and branches (207) are all in VA/MD/DC.** | Florida ATMs come from a one-time OpenStreetMap snapshot, labelled as such. The Nessie standouts become the **bill shield**, the **spend log** and the **restore**. |
| In the Milton replay the **forecast escalates before the sensors do**. | The sensor beats are the **recovery hold** (Alafia River at 24.36 ft vs a 19 ft major stage after NHC ends its alerts), the **reverse surge** (−2.0 ft at St. Pete) and the **wind freeze** (≥ 39 mph). Don't claim in the demo that sensors escalated early. |
| ETFs: T. Rowe Price's own (TCAF, TSPA, TOUS, TOTR, TBUX), with real Oct 2024 closes. Stooq is dead. T+1 settlement. | Milton's first advisories fell on a weekend, so the sale waits for Monday. Use that on stage. |
| AI: `claude-opus-5-5` (verified), `effort: low`, `messages.parse` with Pydantic. Prefill and `thinking: disabled` return 400. | Text only, behind the validator and template fallback. |
| Amadeus Self-Service **shut down on 2026-07-17**. Booking and Expedia need contracts. | Hotels and motels come from OSM Overpass. Cost is estimated from **GSA per diem**. Free shelters come from FEMA Open Shelters. "Estimated cost, call to confirm." |
| OpenRouteService gives route geometry and steps, but its avoid-polygon is capped at 150 km. | Avoid the cone by **choosing the destination**, then check the overlap with `shapely`. Fallback order: OSRM, then a Maps link. |
| Florida uses Emergency Shoulder Use (I-75 N, I-4 E during Milton). Hillsborough publishes its evacuation zones on ArcGIS. FEMA's pet and ADA fields are often blank. | Unknown stays "unknown". The Milton demo uses curated shelters (11 general, 3 special-needs), including ones that filled up. |
| FastAPI ≥ 0.135 has built-in SSE. | No extra library. `EventSource` authenticates with `?user_id=`. |

**Demo decisions:** replay Hurricane Milton using its **real October 2024 timestamps**. The persona is
**Maria, ZIP 33602 (Tampa)**: 2 adults, 1 child and 1 dog. The UI always says
"Replay of Hurricane Milton, Oct 2024 – real NOAA data".

## 1.4 Backend modules

Layout: `backend/harbor/`, run with `uvicorn harbor.main:app --workers 1`.

| Module | Job | Key details |
|---|---|---|
| `config.py` | Settings | `HARBOR_MODE=demo\|live`, `NESSIE_MODE=live\|fake`, `NESSIE_API_KEY`, `NESSIE_BASE_URL`, `ANTHROPIC_API_KEY`, `HARBOR_MODEL=claude-opus-5-5`, `ORS_API_KEY`, `GSA_API_KEY`, `NOAA_USER_AGENT`, `DEMO_CANCEL_WINDOW_S=20`, `EVAC_LEAD_HOURS=6` |
| `clock.py` | One injectable clock | `RealClock`; `DemoClock` handles speed, pause, advance to the next advisory or to a risk level, and auto-pauses at `awaiting_approval` |
| `db.py`, `models.py` | SQLModel tables | user, household, account, lot (`shares_micro`), plan (versioned), move, event, advisory, zip_exposure, sensor_reading, evac_guide, price_snapshot |
| `sources/forecast.py` | NHC and alerts | Cone and track to GeoJSON; wind probability at a point; ETA from the arrival-time product; NWS (live) or IEM (replay) alerts; `ReplaySource` filters by `clock.now()` |
| `sources/sensors.py` | Sensors | CO-OPS 8726520 (surge = observed − predicted), USGS 02301500 + NWPS LITF1 flood categories, NDBC 42036 (stretch). Thresholds live in one constants file. Stale data is never treated as all-clear |
| `sources/market.py` | ETF prices | A fixture of real closes (demo); Alpaca IEX (live, optional) |
| `engine/risk.py` | Pure state machine | `sensor_flag` = one station at warning, or two station types at watch, while the storm is within 500 mi. Shelter starts when the ETA is under 12 h, a warning is in force, or wind is ≥ 39 mph. Recovery gate: alerts ended, pressure recovered, surge < 1 ft for 3 h, rivers out of major flood and falling for 6 h (or below minor). In the Milton recording this opens Sun 13 Oct ~20:00Z; waiting for action stage would hold money until 19 Oct |
| `engine/calendar.py` | Trading days | NYSE and Fed calendars, T+1, `latest_safe_approval_at` |
| `engine/plan.py` | Pure plan builder | Budget lines, each citing a `source`. Waterfall: checking, then savings, then ETFs (TBUX first, then by tax lot), capped at 25% of the portfolio and `max_etf_sell_cents`. Sales that would arrive late are shown, not hidden. `alternatives_precomputed[]`. `build_restore()` returns unspent cash and offers an opt-in rebuy with a wash-sale warning |
| `evac/destination.py` | Safe destination (pure) | About 40 candidate cities in `fl_destinations.json`. Tier A: local, outside every evacuation zone. Tier B: outside the cone plus 40 km. Score = drive time + cone penalty + heading-toward-track penalty − hotel-hub bonus. Returns the top 2–3 (or the user's own pick). `leave_by = ETA − evacuation drive time − 3 h` |
| `evac/route.py` | Route | ORS, then OSRM, then a link only. Returns a GeoJSON line, miles, normal and evacuation drive times (2.5×, an estimate), steps, cone overlap %, corridor notes, Google/Apple Maps links and attribution. Cached per rounded origin, destination and advisory |
| `evac/shelters.py` | Shelters | FEMA Open Shelters (live) or the curated Milton JSON (demo). Pets and ADA are yes/no/unknown; capacity is what's left. Shelters fill up during the replay |
| `evac/lodging.py` | Hotels and motels | OSM snapshot + GSA rate. Economy, standard and comfort bands. Rooms = ceil(people ÷ 4). A pet fee line. Filtered by household needs. A price-gouging card |
| `evac/household.py` | Household needs | Sourced checklists for everyone, kids, older adults, medical and disability, pets, and people without a car. No car means no route and county transport instead. Dialysis or a ventilator means "leave early, plan with your doctor". The FL §252.358 refill rule |
| `bank/nessie.py`, `bank/fake.py` | Bank | httpx with retries, tags, `find_by_tag`, balance checks before and after, bank-down mode during `shelter` |
| `portfolio.py` | ETF holdings | Tax lots, sells, a `brokerage_cash` T+1 queue. Settlement = Nessie deposit to "Brokerage Settlement (Harbor)", then a transfer to checking |
| `executor.py` | Moves | `proposed → scheduled → executing → pending_settlement → done` or `cancelled`/`failed`. Records intent first, then reconciles. Entering `act` pulls moves forward. `prepare → monitor` cancels pending moves and reverses the ones already done |
| `ai/review.py` | Allocation review | `PlanReview`: summary; "Suggestion only – not financial advice"; per-source reasoning (checking, savings, ETF); pre-computed alternatives; risks; a double-check list; household notes (allowed sources only); lodging comments. Numbers appear only through `cited_refs` |
| `ai/explain.py` | "Why?" chat | Grounded in the plan. Advice requests get a fixed refusal. 500 characters, 10 per minute |
| `ai/wrapup.py` | Post-storm report | What was moved, spent, restored and rebought, plus a tax note |
| `ai/guard.py` | Guardrails | Number validator; regenerate once, then use the template. Prompt caching. 20 s timeout and never blocks: the template text ships first and Claude's text follows as `plan_updated`. "AI offline" toggle |
| `events.py` | Event bus | Writes a DB row, puts it on a per-user queue, streams it over SSE with `Last-Event-ID` replay |
| `api/*.py` | Routers | users/me, storm, sensors, plan, evacuation, map, events, demo, health |

**Offline tools** (`backend/tools/`, run before judging; output committed to `backend/data/replays/milton-2024/`):
- `fetch_replay.py`: NHC cones, wind probabilities, arrival times; IEM alerts.
- `record_storm.py`: CO-OPS, USGS/NWPS and NDBC readings.
- `fetch_prices.py`: ETF closes.
- `snapshot_osm.py`: hotels and ATMs near the destination cities.
- `build_demo_evac.py`: curated shelters (geocoded with the Census geocoder), precomputed routes, GSA rates, `fl_destinations.json`.

## 1.5 Track coverage

**STR "Sensors for Good"**
- **What Harbor uses:** CO-OPS St. Petersburg (tide vs prediction, pressure, wind), the USGS Alafia River at Lithia with NWPS flood categories, and NDBC buoy 42036 (stretch).
- **Three protective rules:**
  - Recovery hold.
  - Reverse-surge warning.
  - Wind freeze.
- **Evacuation guide:** it protects people as well as money (route, `leave_by`, pet-friendly and special-needs shelters, household checklists).
- **What judges see:** every protective action shows the reading behind it (station, distance, last update, a `stale` badge).
- **Stretch:** a community barometer (ESP32 + BME280) via `POST /sensors/ingest`, since browsers expose no barometer.

**Capital One "Best Use of Nessie"**
- **Nessie is the real bank:** a seeded customer; Checking, Savings and "Brokerage Settlement (Harbor)" accounts; transfers; a withdrawal rounded to $20; the settlement deposit; spend-log purchases; the bill shield. The restore returns unspent money = withdrawn − purchases.
- **Robustness:** idempotency tags, reconcile, balance checks, bank-down mode, and the FakeNessie fallback.

**T. Rowe Price "NextGen Finance"**
- **ETF portfolio:** T. Rowe Price ETFs; the TBUX storm sleeve sold first; tax lots; wash-sale warnings; T+1 on real calendars; the `latest_safe_approval_at` countdown; caps.
- **Responsible AI:** "Decided by rules / Explained by AI" badges, the number validator, the advice refusal, explicit taps on every sale, and an AI-offline toggle that leaves the numbers unchanged.
- **Tokenization:** skipped ("and/or"), so it's one future-work line.

## 1.6 Risk levels

| Level | Enter when | Money |
|---|---|---|
| `clear` | No storm threatens the ZIP | Nothing moves |
| `monitor` | Tropical-storm wind probability (p34) at the ZIP ≥ 5% | Nothing moves; the user is alerted |
| `prepare` | p34 ≥ 20%, **or** `level ≥ monitor` and `sensor_flag` | The plan, AI review and evacuation guide are built, and the user approves. Approved moves run at `scheduled_for` |
| `act` | p34 ≥ 50%, or a hurricane watch or warning | Remaining transfers are pulled forward to now |
| `shelter` | A warning and ETA < 12 h, or sustained wind ≥ 39 mph | No Nessie writes; last-known balances are shown |
| `recover` | Alerts have ended, the ZIP is out of the cone **and** the sensor recovery gate has passed (pressure ≥ 1005 mb, surge under 1 ft for 3 h, rivers out of major flood and falling for 6 h or below minor) | Restore unspent cash; optional rebuy |

Going back from `prepare` to `monitor` (the storm turned away) cancels pending moves and reverses the
completed ones. All thresholds live in one constants file and are tuned against the Milton replay.

## 1.7 Contradictions resolved

| # | Conflict between research notes | Resolution |
|---|---|---|
| 1 | Nessie base URL: http vs https | `https://api.nessieisreal.com`, overridable with `NESSIE_BASE_URL` |
| 2 | Nessie amounts: floats vs integers | Whole-dollar integers. Convert only in `nessie.py` and store the rounding on the Move |
| 3 | Withdrawal path | Singular `/withdrawal/{id}`. `POST /accounts/{id}/transfers` is missing from the spec; test it in hour 1 |
| 4 | Replay timestamps: shift to 2026 vs keep 2024 | Keep 2024 everywhere. Nessie `transaction_date` uses the demo-clock date |
| 5 | Demo ZIP | 33602 Tampa (Maria). Fort Myers 33901 is a stretch persona |
| 6 | `cash_needed_by` | ETA − `EVAC_LEAD_HOURS` (6): money must reach checking before banking can go down; the family may already be driving and pays by card. Cash is withdrawn right after the savings transfer. With 18 h, every Milton ETF sale arrived late |
| 7 | Cancel deadline | `scheduled_for ≥ approved_at + window`; deadline = `scheduled_for − 5 min`. The demo window is 20 real seconds and the clock auto-pauses |
| 8 | Sensor thresholds | One constants file; `sensor_flag` as defined in §1.4; the API.md example becomes `watch` |
| 9 | Recovery ignored sensors | Add the sensor recovery gate (§1.6). Tuned on the real recording: the Alafia stays above minor flood until 17 Oct, so the gate uses major flood + falling |
| 10 | When moves run | At `scheduled_for` in `prepare`/`act`; `act` pulls them forward; `shelter` freezes them |
| 11 | Settlement path | `calendar.py` settle date 09:00 ET; Nessie deposit to the settlement account, then a transfer to checking |
| 12 | SSE library | FastAPI's built-in SSE; no `event:` field; the type is in `data.type` |
| 13 | Market data | Fixture closes (demo), Alpaca IEX (live); yfinance only in offline tools |
| 14 | AI timeout and model | `claude-opus-5-5` via `HARBOR_MODEL`, 20 s async timeout, never blocking |
| 15 | Env var names | As listed in §1.4 `config.py` |
| 16 | Repo layout | As in §1.4; replay data in `backend/data/replays/milton-2024/` |
| 17 | Advisory times | Derived from the archived TCMs, never hard-coded |
| 18 | Map: the routing notes assume "no map UI" | **The map is in.** The routing notes still apply; also return the GeoJSON route line for `/me/map` |

## 1.8 UNVERIFIED items to test in hour 1

| Item | Fallback if it fails |
|---|---|
| Nessie: POST response shape, immediate balance update, overdraft rejection, purchase body, rate limits | `NESSIE_MODE=fake` plus a `nessie: degraded` banner |
| Milton risk levels come out in the right order | Run `risk.py` over the manifest (`test_demo_e2e.py`) |
| USGS `ogcapi` v0 vs v1 | Pin whichever works and commit the recorded data |
| `messages.parse` together with `output_config` on `claude-opus-5-5` | Plain JSON prompt plus Pydantic validation |
| T. Rowe ETF launch dates (TBUX, TOUS, TOTR) have closes for Sep–Oct 2024 | Swap in TCHP, TEQI or TDVG |
| Apple Maps link parameters | Google link only |
| Statewide FDEM evacuation-zone service | Hillsborough county layer plus a zone the user picks |
| FL price-gouging citation §501.160 | Generic wording without a citation |

---

# Part 2: Research notes

Detailed research notes for each subsystem, checked against official docs and live APIs on 2026-10-16. Part 1 overrides these where they conflict.


---

## Backend architecture

### 1. Shape: one process, one app

Harbor runs as a single FastAPI process (`uvicorn harbor.main:app`). It holds the HTTP API, the SSE stream, the scheduler and the demo clock. With two people and 48 hours, a separate worker plus Redis or Celery would only add more things that can break. Everything time-based runs as an APScheduler job inside the FastAPI `lifespan`. Every service gets "now" from one injected `Clock`, so the real-time path and the demo path run the same code.

Rule of thumb: **routers are thin, services hold the logic, adapters hold all I/O.** The rules engine (`risk`, `plan`) is pure and deterministic. It never calls the network or the AI, which makes it easy to unit-test.

### 2. Package layout

```
harbor/
  pyproject.toml            # deps, pytest config, ruff
  .env.example              # NAMES only: NESSIE_API_KEY=, ANTHROPIC_API_KEY=, HARBOR_MODE=demo
  data/replays/milton-2024/ # pre-downloaded NHC + sensor files (committed, small)
  harbor/
    main.py                 # create_app(), lifespan: DB init, scheduler start/stop, clock
    config.py               # pydantic-settings Settings
    deps.py                 # FastAPI Depends(): get_session, get_clock, get_current_user, get_nessie
    clock.py                # Clock protocol, RealClock, DemoClock, FrozenClock (tests)
    db.py                   # engine, SQLite WAL pragmas, session factory
    models.py               # SQLModel tables (section 3)
    schemas.py              # API response models matching docs/API.md exactly
    errors.py               # HarborError(code, message, status) -> {"error":{code,message}}
    events.py               # EventBus: persist Event row + fan out to SSE queues
    api/
      users.py              # POST /users, GET/PATCH /me, /me/accounts, /me/portfolio, /me/atms
      storm.py              # /me/storm, /storms/{id}/cone.geojson
      sensors.py            # /me/sensors, /me/sensors/{id}/history
      plan.py               # /me/plan, approve, cancel, moves/{id}/cancel, explain, /me/plans
      events.py             # /me/events, /me/events/stream (SSE)
      demo.py               # /demo/*
      health.py             # /health
    services/
      forecast.py           # NHC adapter: live feed or replay files -> Storm/Advisory rows
      sensors.py            # NDBC / NWS / USGS adapters -> SensorReading rows + status
      risk.py               # PURE: (advisory, sensors, alerts, now) -> RiskLevel + reasons
      plan.py               # PURE: (user, accounts, holdings, lots, storm eta) -> Plan + Moves
      executor.py           # Move state machine, idempotent, reconcile loop
      nessie.py             # NessieClient (httpx) + FakeNessie (tests/offline)
      market.py             # price provider chain + cache
      ai.py                 # Claude: plan summary, per-move "why", /explain
      notifier.py           # turns events into user-facing messages (SSE now, SMS later)
      geo.py                # ZIP -> lat/lon, haversine, point-in-cone (shapely)
      ticker.py             # the single "tick" job that drives everything
  tests/
    conftest.py             # FrozenClock, FakeNessie, in-memory SQLite, fixture replay
    test_risk.py  test_plan.py  test_executor.py  test_demo_e2e.py
```

### 3. Database

**Use SQLite** (a file such as `harbor.db`, WAL mode). It needs no setup, both teammates can delete it and rebuild it, and a demo reset is just a delete. One FastAPI process plus one scheduler running in the same event loop is well within what SQLite handles. On connect, set `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON`. Keep everything behind SQLModel so moving to Postgres later only means changing the connection URL. Skip Alembic. Run `SQLModel.metadata.create_all()` at startup and rebuild the database when the schema changes.

Money columns are `int` cents. Datetimes are stored as UTC and returned as ISO 8601 with `Z`. Use string IDs with a type prefix (`usr_`, `pln_`, `mv_`, `evt_`) to match the contract.

| Table | Key columns |
|---|---|
| `user` | id, name, zip, lat, lon, household_json, evacuation_json, settings_json (auto_approve, max_etf_sell_cents, cancel_window_minutes, rebuy_opt_in), nessie_customer_id, risk_level, risk_reasons_json, risk_changed_at |
| `account` | id, user_id, nessie_id, type (`checking`/`savings`/`brokerage_cash`), nickname, cached_balance_cents, balance_synced_at |
| `holding` | id, user_id, symbol, name, shares (`Decimal` stored as TEXT or integer micro-shares) |
| `tax_lot` | id, holding_id, shares_micro, cost_basis_cents, acquired_at, sold_at nullable, sold_move_id |
| `price` | symbol, as_of, price_cents, source (`stooq`/`yfinance`/`fixture`): a cache |
| `storm` | id (`al142024`), name, basin, year, is_replay |
| `advisory` | id, storm_id, number, issued_at, next_advisory_at, category, max_wind_kt, cone_geojson, track_geojson, wsp_source_ref |
| `zip_exposure` | advisory_id, zip, ts_wind_prob_5day, hu_wind_prob_5day, in_cone, earliest_ts_eta |
| `alert` | id, zip/zone, type (`hurricane_watch`…), headline, issued_at, expires_at |
| `sensor` | id (`ndbc_42036`), source, name, lat, lon |
| `sensor_reading` | id, sensor_id, observed_at, pressure_mb, pressure_change_3h_mb, wind_speed_mph, wave_height_ft, water_level_ft, flood_stage_ft, status; UNIQUE(sensor_id, observed_at) |
| `plan` | id, user_id, storm_id, status, created_at, approved_at, cash_needed_by, budget_json, sources_json, summary, tax_note, warnings_json, rules_version, inputs_hash |
| `move` | id, plan_id, seq, kind, status, from_ref, to_ref, symbol, shares_micro, amount_cents, scheduled_for, expected_available_at, cancel_deadline, why, **idempotency_key UNIQUE**, nessie_object_id, attempts, last_attempt_at, error, depends_on_move_id |
| `event` | id, user_id, at, type, message, data_json |
| `demo_state` | singleton: storm_key, running, speed, anchor_real, anchor_sim, paused_at_sim |

`plan.inputs_hash` holds a hash of the inputs the rules engine saw, so the "why" answer can always point back to an exact snapshot. `move.depends_on_move_id` lets `withdraw_cash` wait until the `sell_etf` settlement has landed.

### 4. Clock: one seam for real and demo time

```python
class Clock(Protocol):
    def now(self) -> datetime: ...          # always tz-aware UTC

class RealClock:   now = lambda self: datetime.now(UTC)
class DemoClock:   # sim_now = anchor_sim + (real_now - anchor_real) * speed, frozen while paused
    def start(storm, speed, sim_start); advance(hours); pause(); resume()
class FrozenClock: # tests: set(t), tick(timedelta)
```

`app.state.clock` holds a `ClockRouter`. It delegates to `DemoClock` while a demo runs and to `RealClock` otherwise. All code calls `clock.now()`. Nothing may call `datetime.now()` directly; a `ruff` banned-API rule or a grep in CI enforces this. The forecast and sensor adapters take `now` as an argument. In replay mode they return "the newest advisory with `issued_at <= now`" from the files on disk. In live mode they fetch from NOAA. That is the only place the two modes differ.

`/demo/advance` moves `anchor_sim` forward and then **runs a tick right away**, so the UI updates without waiting for the next scheduler interval.

### 5. Scheduler

Use **APScheduler 3.11.x** (`AsyncIOScheduler`). The latest stable release is 3.11.3 (2026-06-28). The 4.0 releases are still alphas (4.0.0a6), so avoid them; their API is different. Start it in the lifespan:

```python
@asynccontextmanager
async def lifespan(app):
    init_db(); app.state.clock = ClockRouter(); app.state.bus = EventBus()
    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(ticker.tick, "interval", seconds=settings.tick_seconds,  # 2s demo, 60s live
                  max_instances=1, coalesce=True, args=[app])
    sched.start(); yield; sched.shutdown(wait=False)
```

There is **one job**, `tick()`. Every scheduler trigger runs in real time, so per-move APScheduler jobs would break under a demo clock that jumps forward. Instead, `tick()` reads `clock.now()` and does this:

1. `forecast.refresh(now)`: ingest any new advisory, then compute `zip_exposure` per user ZIP.
2. `sensors.refresh(now)`: ingest readings and set each sensor's status.
3. `risk.evaluate(user, now)` for each user. On a level change, write the event and call the plan hooks.
4. `executor.run_due(now)`: moves with `status=scheduled AND scheduled_for <= now`, plus `pending_settlement` moves whose `expected_available_at <= now`.
5. `executor.reconcile(now)`: moves stuck in `executing`.

`max_instances=1, coalesce=True` stops ticks from overlapping. In live mode, the NOAA fetches inside the tick are throttled with a per-source "last fetched" timestamp (NHC every 10 minutes, NDBC every 10 minutes, USGS every 15 minutes), not on every tick.

### 6. Move executor: state machine, idempotency, crash safety

States follow the contract: `proposed → scheduled → executing → pending_settlement → done`, plus `cancelled` and `failed`. Allowed transitions live in one dict. `transition(move, to)` raises if a jump is illegal and emits `move_*` events.

**Write the intent first, then call Nessie, then reconcile.** Steps for each due move:

1. In one DB transaction: `UPDATE move SET status='executing', attempts=attempts+1, last_attempt_at=now WHERE id=? AND status='scheduled'`. If 0 rows change, another tick already has the move, so skip it. Commit.
2. Call Nessie. Put the move's `idempotency_key` (e.g. `harbor:mv_03:v1`) in the transfer or withdrawal `description`. Nessie has no idempotency-key header (UNVERIFIED), so the description acts as our marker.
3. On success, store `nessie_object_id`. Then set `done` for transfers and withdrawals, or `pending_settlement` for `sell_etf`, with `expected_available_at = next business day 14:00Z`.
4. On a 4xx error: `failed`, store the error message, emit `move_failed`, and **do not retry**. On a 5xx error or timeout, leave the move in `executing`. Reconcile handles it.

**Reconcile** finds moves in `executing` for more than 30 seconds. It lists `GET /accounts/{id}/transfers` (or `/withdrawals`) and looks for the idempotency key in `description`. If it finds a match, it takes that ID and moves forward. If not, it puts the move back to `scheduled` (up to 3 attempts, then `failed`). This makes the system safe if the app crashes between the Nessie call and the DB commit.

**`sell_etf` is simulated inside Harbor.** Close lots first-in-first-out, or pick the lowest-gain lots first and record which rule `plan.py` used. Credit `brokerage_cash` right away as unsettled. When `expected_available_at` passes, run `deposit` into Nessie checking (`POST /accounts/{chk}/deposits`) under its own idempotency key (`harbor:mv_03:settle`), then `done`. **The ETF price is locked when the move executes**, not when the plan is drafted. The difference is stored on the move.

**Guards checked right before execution:** user risk is not `shelter` (the contract says no new moves then, except moves already in flight), the plan is still `running`, `now >= cancel_deadline`, and the source has enough balance (live `GET /accounts/{id}`).

### 7. Event bus and SSE

`EventBus.publish(user_id, type, message, data)` does two things. (a) It inserts an `event` row, the durable source of truth behind `/me/events`. (b) It pushes the event to every `asyncio.Queue` registered for that user (`dict[user_id, set[Queue]]`, unbounded queues, at most 5 connections per user). `/me/events/stream` uses **sse-starlette 3.5.0** `EventSourceResponse` with an async generator. The generator yields `{"id": evt.id, "event": evt.type, "data": json}`, keeps the default 15-second `ping`, and checks `await request.is_disconnected()`. When the browser reconnects it sends `Last-Event-ID`, and the server replays the newer `event` rows from the DB before switching to the live queue. The bus is in-process and the app is a single process, so nothing more is needed.

`notifier.py` subscribes to the bus and decides what the user sees. For example, it collapses three `move_done` events into one "Your evacuation cash is ready" message. That keeps message wording out of the executor. It is also where SMS or email would go later (out of scope for 48h).

### 8. Configuration and logging

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")
    mode: Literal["demo","live"] = "demo"
    nessie_api_key: SecretStr; nessie_base_url: str = "http://api.nessieisreal.com"
    anthropic_api_key: SecretStr | None = None; anthropic_model: str = "claude-..."  # pick per claude-api skill
    database_url: str = "sqlite:///harbor.db"
    tick_seconds: float = 2.0
    nhc_base_url: str = "https://www.nhc.noaa.gov"
    noaa_user_agent: str = "Harbor hackathon (contact: team email)"   # NWS API requires a UA
    cors_origins: list[str] = ["http://localhost:3000"]
    ai_enabled: bool = True; market_source_order: list[str] = ["stooq","yfinance","fixture"]
```

`.env` is in `.gitignore`. `.env.example` lists variable names only. `SecretStr` keeps keys out of reprs and logs. Nessie authenticates with `?key=` in the query string, so **httpx log lines must have the query string removed** (a custom `event_hooks` logger, or set the `httpx` logger to WARNING).

For logging, use `structlog`, or stdlib `logging` with a JSON formatter. Every line carries `user_id`, `plan_id`, `move_id`, `sim_now` and `real_now`. That turns a failed live demo into something you can debug in seconds. Add `CORSMiddleware` for the teammate's Next.js dev origin.

### 9. Testing

- **`FrozenClock`**: tests call `clock.set("2024-10-07T15:00Z")` and `clock.tick(hours=6)`. No sleeping.
- **`FakeNessie`**: an in-memory version of the same interface as `NessieClient` (create customer/account, transfer, withdrawal, deposit, list, get balance, atms). It has fault-injection flags: `fail_next=500`, `timeout_next=True`, `succeed_but_drop_response=True`. The last one is the crash-safety test: the transfer happens but the client never sees the response, and reconcile must take the existing transfer ID rather than sending a second one.
- **Pure-engine tests**: table-driven `risk.evaluate` cases for each threshold (5%, 20%, 50%, watch/warning, a 12h ETA, a sensor pressure drop of 3 mb or more in 3h). For `plan.build`: budget math, choosing between savings and ETF, the T+1 deadline, the wash-sale warning.
- **End-to-end replay test** (`test_demo_e2e.py`): load `data/replays/milton-2024`, step the FrozenClock advisory by advisory, call `tick()`, and check the level sequence `clear→monitor→prepare→act→shelter→recover` and the final balances. The AI is replaced by a stub that returns fixed text.
- One test, skipped unless the env var is set, hits real Nessie (`@pytest.mark.live`). Run it once a day.

### 10. One full demo, step by step

The demo user is Maria, ZIP 33602 (Tampa). The replay is `milton-2024` at speed 3600 (one real second is one storm hour).

1. **Setup.** `POST /users` → `api/users` → `nessie.create_customer`, then two `create_account` calls (checking $420, savings $2,500), and seed holdings and tax lots. `market.price()` fills `price`. `POST /demo/start` → `api/demo` → `DemoClock.start()` and `demo_state` saved. **Event:** none yet, risk `clear`.
2. **Storm appears.** `ticker.tick` → `forecast.refresh(now)` finds the first Milton advisory file with `issued_at <= now`. It writes `storm`, `advisory` and `zip_exposure` (from the 34-kt wind speed probability at the ZIP point, and point-in-cone via `geo` + shapely). `risk.evaluate`: ts prob > 5% → **monitor**. `events.publish(risk_changed, advisory_issued)` → SSE → the website map shows the cone.
3. **Prepare.** Ts prob passes 20%, or `sensors.refresh` sees buoy 42036 report `pressure_change_3h_mb ≤ -3`, which sets status `warning` and emits `sensor_alert` (the Sensors track). `risk` → **prepare**. Its hook calls `plan.build()`. Budget from household × evacuation settings. Sources in order: checking, then savings, then the smallest ETF sale that covers the gap, capped at `max_etf_sell_cents`. Timing: `cash_needed_by = earliest_ts_eta − 24h`, and `sell_etf.scheduled_for` is the last market close that still settles T+1 before that time. Moves are saved as `proposed` and the plan as `draft`. Then `ai.write_summary(plan_snapshot)` fills `summary` and each `why`, under a timeout. If the AI fails, a template string is used, so the plan never waits on it. The plan goes to `awaiting_approval` and `plan_created` is emitted.
4. **User approves.** `POST /me/plan/approve` → `api/plan` → moves change `proposed→scheduled`, each `cancel_deadline = scheduled_for − cancel_window`, and `plan_approved` is emitted. Questions such as "Why VTI and not BND?" go to `POST /me/plan/explain` → `ai.explain(question, plan_snapshot)`. The answer explains the plan but never changes it.
5. **Act.** Ts prob > 50% or a watch → **act**, and the plan is `running`. `executor.run_due` runs the steps in order:
   - (a) `transfer` savings→checking through `nessie` → `done`.
   - (b) `sell_etf`: the lot math and the price come from `market` → `pending_settlement`.
   - (c) the next tick after `expected_available_at` makes a Nessie `deposit` into checking → `done`.
   - (d) `withdraw_cash` (depends on c) through a Nessie withdrawal → `done`.

   Each step emits `move_done`. `/me/atms` (`nessie.atms` + `geo`) lists ATMs outside the cone along the route.
6. **Shelter.** A warning plus ETA < 12h → **shelter**. The executor refuses any new moves, and `notifier` sends "Cash is in hand; Harbor is paused."
7. **Recover.** Alerts expire and the ZIP is no longer in the cone for N advisories → **recover**. `plan.build_restore()` creates a `restore_transfer` of unspent cash (checking above the pre-storm balance) back to savings, plus `rebuy_etf` if `rebuy_opt_in`, with a wash-sale warning if the price is below the lot cost. The plan goes `restoring→restored` and `plan_restored` is emitted. `POST /demo/reset` → `nessie` deletes and rebuilds the accounts and resets the DB.

### 11. Main risks for a 48h build

| Risk | Mitigation |
|---|---|
| **Nessie is slow, down, or blocks the network** (it runs on plain `http://`; the docs page returned 403 to my fetch) | `NESSIE_FAKE=1` switches to FakeNessie so the demo still works. Set an httpx timeout of 8s. Cache balances (`cached_balance_cents`) for reads. Re-seed customers before judging. Confirm the base URL and key on Friday night. |
| **Nessie behaviour quirks** (UNVERIFIED, from community use): amounts are dollar floats, not cents; transfers may come back `pending` and balances may not update straight away; some create calls only return `{"code":201,"objectCreated":{...}}` | Convert cents↔dollars only inside `nessie.py`. After every move, re-read `GET /accounts/{id}`, and reconcile on our own ledger, not on Nessie's status. |
| **Market data blocked** (yfinance rate-limits or gets blocked often; free keys expire) | Use a provider chain in `market.py`: Stooq CSV, then yfinance, then committed `fixtures/prices.csv` with real closes for VTI/BND/VXUS for the replay dates. Demo mode always uses the historical closes for the replay date, which are real prices and fully deterministic. |
| **NHC archive formats** | Cone and track files are zipped shapefiles named `{basin}{nn}{yyyy}_5day_{adv:03d}.zip` (e.g. `al142024_5day_014.zip`), with a `_fcst_` variant for wind radii. Wind speed probabilities come as shapefile/KMZ/GRIB (`wsp_120hr5km`), and watches/warnings only as KMZ (`*_WW.kmz`) (source: https://www.nhc.noaa.gov/gis/). **Convert to GeoJSON offline before the hackathon** with a small `tools/build_replay.py` (pyshp/fiona + shapely), commit the GeoJSON plus a per-advisory `exposure.json`, and the server never has to parse a shapefile during the demo. "latest" files are overwritten with each advisory, so live mode must read an advisory's own file, not "latest". |
| **Historical sensor data** | NDBC historical stdmet files are yearly gzip text and come out after the season. Download the Milton window for 3 to 5 buoys and USGS gauges ahead of time into the replay folder. Live mode reads `realtime2` (UNVERIFIED paths, covered by the sensors section of this document). |
| **AI latency or cost** | Call the AI once per plan plus explain calls, with an 8s timeout, a template fallback, and `ai_enabled=False` for tests. The AI never decides any money move. |
| **SQLite "database is locked"** | WAL mode, `busy_timeout`, short transactions, one process. |
| **Demo clock and scheduler drift** | A single tick job with `coalesce`. `/demo/advance` runs a tick synchronously. |
| **Contract drift with the frontend** | `schemas.py` matches API.md field for field. Serve `/docs`. Add a contract test that checks example payloads against the schemas. |

### 12. Dependencies

| Package | Purpose |
|---|---|
| `fastapi`, `uvicorn[standard]` | API server |
| `sqlmodel` (pulls in SQLAlchemy 2, pydantic 2) | ORM and tables |
| `pydantic-settings` | env-based config, `SecretStr` |
| `httpx` | async client for Nessie and NOAA, also used for test transports |
| `apscheduler>=3.11,<4` | the tick job (4.x is alpha only) |
| `sse-starlette` (3.5.0) | `/me/events/stream` |
| `anthropic` | plan summaries and `/explain` (check the current model ID before choosing one) |
| `shapely` | point-in-cone, distance to the track |
| `pyshp` or `fiona` (offline tools only) | shapefile → GeoJSON for replays |
| `pgeocode` or a committed ZIP→lat/lon CSV | ZIP geocoding without an API key |
| `yfinance` (optional fallback), `pandas` (only if Stooq CSV parsing needs it) | prices |
| `structlog` | structured logs |
| `tenacity` | bounded retries on NOAA fetches only (never on Nessie writes; reconcile covers those) |
| dev: `pytest`, `pytest-asyncio`, `respx`, `time-machine` or our FrozenClock, `ruff` | tests and linting |

### Verified vs UNVERIFIED

- **Verified:**
  - APScheduler 3.11.3 is the latest stable release, and 4.x is still pre-release (https://pypi.org/project/APScheduler/).
  - sse-starlette 3.5.0: `ping` defaults to 15s, and `request.is_disconnected()` is how to detect a closed connection (https://pypi.org/project/sse-starlette/).
  - NHC GIS file names and formats (https://www.nhc.noaa.gov/gis/).
  - Nessie route list: `/customers/{id}/accounts`, `/accounts/{id}/transfers|withdrawals|deposits`, `/transfers/{id}`, `/withdrawals/{id}`, `/deposits/{id}`, `/atms`, `/branches`. Source: https://apievangelist.com/2018/03/06/capital-one-devexchange-provides-an-important-banking-api-blueprint/ (a 2018 secondary source).
- **UNVERIFIED** (the official Nessie docs at http://api.nessieisreal.com/documentation returned 403):
  - Nessie POST body fields (`medium`, `payee_id`, `amount`, `transaction_date`, `description`).
  - Transfer `status` values.
  - The `objectCreated` response shape.
  - `?key=` query auth.
  - A data-delete endpoint for resets.
  - Any rate limits.
  - No idempotency support.

  Check all of these in the first hour, using the live Swagger page or a single curl.


---

## Forecasts: data sources, ingestion and risk engine

### 1. Sources (all verified on 2026-10-16 unless marked UNVERIFIED)

#### 1.1 NHC `CurrentStorms.json` (live index)

- URL: `https://www.nhc.noaa.gov/CurrentStorms.json`. It is about 9.5 KB. It sends `Cache-Control: max-age=300`, plus `ETag` and `Last-Modified`, so poll with `If-None-Match`. The docs sample is at `https://www.nhc.noaa.gov/productexamples/NHC_JSON_Sample.json`.
- The root is `{"activeStorms": [...]}`. Each storm has:
  - `id` (`"al142024"`, lowercase), `binNumber` (`"AT1"`), `name`, `classification` (`TD`, `TS`, `HU`, ...).
  - `intensity` (kt) and `pressure` (mb), both **strings**.
  - `latitudeNumeric`/`longitudeNumeric` (floats; west is negative), `movementDir`, `movementSpeed`, `lastUpdate` (ISO, `Z`).
- Each storm also has product objects `{advNum, issuance, fileUpdateTime, url | zipFile | kmzFile}`:
  - Text products: `publicAdvisory`, `forecastAdvisory`, `windSpeedProbabilities`, `forecastDiscussion`.
  - GIS products: `forecastTrack`, `trackCone`, `windWatchesWarnings`, `initialWindExtent`, `forecastWindRadiiGIS`, `bestTrackGIS`.
  - Arrival times: `earliestArrivalTimeTSWindsGIS` and `mostLikelyTimeTSWindsGIS`, which have `kmzFile` only.
  - `windSpeedProbabilitiesGIS` has `zipFile5km`, `zipFile0p5deg` and `kmzFile34kt`/`50kt`/`64kt`.
- Any product can be `null`. Weak systems often have no GIS products, and East Pacific storms often have no arrival-time product.
- Today the Atlantic is quiet. The GIS RSS feed (`https://www.nhc.noaa.gov/gis-at.xml`) says "There are no tropical cyclones at this time." Only EP21 Trudy is active. **Live mode will show `clear` for any US ZIP, so the demo must run on replay.**

#### 1.2 NHC GIS products (index: `https://www.nhc.noaa.gov/gis/`)

None of these are GeoJSON. Harbor converts them.

| Product | Archive URL (per advisory) | Contents (inspected) |
|---|---|---|
| Cone, track, watches/warnings | `https://www.nhc.noaa.gov/gis/forecast/archive/{id}_5day_{NNN}[A].zip` | Shapefiles: `{id}-{NNN}_5day_pgn` (cone polygon), `_5day_lin` (track line), `_5day_pts` (forecast points), `_ww_wwlin` (coast segments, field `TCWW` ∈ `TWA`/`TWR`/`HWA`/`HWR`). The points layer has `LAT`, `LON`, `MAXWIND`, `GUST`, `MSLP`, `SSNUM` (Saffir-Simpson category), `TAU` (hours), `STORMTYPE`, `ADVDATE` ("400 PM CDT Tue Oct 08 2024", **local time**), `ADVISNUM`. |
| Wind radii | `.../forecast/archive/{id}_fcst_{NNN}.zip` | Initial and forecast 34/50/64 kt radii. Optional. |
| Wind speed probabilities | `.../forecast/archive/{YYYYMMDDHH}_wsp_120hr5km.zip` and `_wsp_120hrhalfDeg.zip`, plus `{YYYYMMDDHH}_wsp{34,50,64}knt120hr_5km.kmz` | **Named by synoptic time, not by storm.** One file covers all active storms combined. `YYYYMMDDHH` = advisory time minus 3 h (advisory 15 at 21Z uses `…18`). There are none for intermediate `A` advisories. See below. |
| Arrival time of 34 kt winds | `https://www.nhc.noaa.gov/storm_graphics/api/{ID}_{NNN}adv_{earliest_reasonable,most_likely}_toa_34.kmz` (**uppercase** `AL142024`) | Archived from 2018. There are none for `A` advisories (a 404 was confirmed for `015A`). Live versions: `…/{ID}_{earliest_reasonable,most_likely}_toa_34_latest.kmz`. GRIB2 is at `https://ftp.nhc.ncep.noaa.gov/toa/`; whether it is archived there is UNVERIFIED. |
| Preliminary best track | `https://www.nhc.noaa.gov/gis/best_track/{id}_best_track.zip` | The observed track, used to show where the storm went. |
| Live "latest" files | `.../forecast/archive/{id}_5day_latest.zip`, `.../forecast/archive/wsp_120hr5km_latest.zip`, `.../forecast/archive/wsp_120hrhalfDeg_latest.zip` | Use the `zipFile` URLs from CurrentStorms instead. Their numbered names make caching easy. |
| ArcGIS REST (live only) | `https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/NHC_tropical_weather/MapServer` | Supports `f=geojson`. Layers per bin are things like "AT1 Forecast Cone" and "AT1 Earliest Reasonable Arrival Time". Handy for a live map, but it has no history. |

**What's inside the wind speed probability files.** I opened `2024100812_*`:

- **The 5 km zip** holds, per threshold, a polygon shapefile with 11 records. Each record has a `PERCENTAGE` string: `<5%`, `5-10%`, `10-20%` … `>90%`. The bands are **disjoint rings with holes**: a point falls in exactly one band, using even-odd point-in-polygon. Tampa fell in `80-90%`.
- **The half-degree zip** holds, per threshold, a point shapefile on a 0.5° grid with one field, `PWIND120`. It is a **string** holding a **percent** (0.1–100). Points are missing where the value rounds to zero.
  - Points near Tampa read 88.5 / 89.1 / 92.5 / 94.4, which matches the band.
  - All values are cumulative for 0–120 h. These files contain **no interval (timing) probabilities**.
- **How Harbor gets the number at a lat/lon:**
  1. Bilinear-interpolate the four surrounding half-degree points (treat a missing point as 0).
  2. Clamp the result into the 5 km band that contains the point.
  3. Store it as 0–1, e.g. `ts_wind_probability_5day: 0.89`.
  - The 5 km band alone gives only a range. The half-degree grid alone (about 55 km) is too coarse near the coast. Together they are accurate enough.

**What's inside the arrival-time KMZ.** I opened `AL142024_015adv_earliest_reasonable_toa_34.kmz` (37 KB):

- It holds one KML file plus `labels/*.png`.
- `Document/ExtendedData` gives `timezone` (`CDT`), `atcfid`, `advisoryNum`, and `pubAdvTime` ("400 PM CDT Tue Oct 08 2024").
- About 10 `Placemark`s are **open `LineString` isochrones**. Their label sits only in the CDATA `<description>` as `<td>Wed 8 am</td>`: a local day and hour, **with no date**.
- One more LineString, labelled "Wind Speed Probability 5% contour", is a closed ring.
- There are **no polygons**.
- Spacing is 6 h on day 1 and 12 h after that, at 8 am/8 pm local, according to `https://www.nhc.noaa.gov/arrivaltimes`.
- "Earliest reasonable" means the time before which there is at most a 10% chance that tropical-storm winds have started. That is the right conservative value for `earliest_ts_winds_eta`.

#### 1.3 NHC text archive (needed for replay metadata and the AI summary)

- `https://www.nhc.noaa.gov/archive/2024/al14/al142024.{fstadv|public|discus|wndprb}.{NNN}.shtml`. All four were confirmed returning 200 for NNN=015.
- Intermediate public advisories use `.public_a.{NNN}.shtml`.
- `fstadv` (TCM) has the UTC issuance line, e.g. "1500 UTC SAT OCT 05 2024". **Use this, not the local-time `ADVDATE`.**
- `wndprb` (PWS) has a per-city table with interval and cumulative probabilities for 34/50/64 kt at 12, 24, 36, 48, 72, 96 and 120 h. Example from advisory 15: `TAMPA FL 34 X 7( 7) 77(84) 8(92) ...`.
  - This is the **only** easy source of timing-resolved probabilities.
  - It is a fallback for estimating the arrival time. If the cumulative 34 kt value at the nearest PWS city first reaches 10% in a window, the start of that window is about the earliest reasonable arrival.

#### 1.4 NWS API alerts (live)

- Base URL: `https://api.weather.gov`.
- A `User-Agent` header is **required**. Use something like `(harbor-hackathon, team@email)`; no key is needed. Send `Accept: application/geo+json`.
- Rate limits are not published. Over the limit you get an error that clears in about 5 s. Docs: `https://www.weather.gov/documentation/services-web-api`.
- **`GET /points/{lat},{lon}`** returns `forecastZone` (e.g. `.../zones/forecast/FLZ151`), `county` (`.../zones/county/FLC057`), `timeZone`, `gridId` and `observationStations`. Cache the result per ZIP for good.
- **`GET /alerts/active?point={lat},{lon}`**, `GET /alerts/active/zone/{FLZ151}` and `GET /alerts/active?zone=FLZ151,FLC057` all return 200.
  - Hurricane and tropical-storm watches/warnings are issued on **forecast zones (FLZ)**. Flood and tornado alerts often use **counties (FLC)**. Query both.
- Each feature's `properties` include:
  - `event`, `headline`, `severity`, `urgency`, `certainty`, `messageType` (`Alert`/`Update`/`Cancel`).
  - `sent`, `effective`, `onset`, `expires`, `ends`. These carry **local offsets (`-04:00`), not Z**, so normalise them to UTC.
  - `geocode.UGC`, `affectedZones`, and `parameters.VTEC`.
- Relevant `event` strings (from `/alerts/types`): `Hurricane Watch`, `Hurricane Warning`, `Tropical Storm Watch`, `Tropical Storm Warning`, `Storm Surge Watch`, `Storm Surge Warning`, `Extreme Wind Warning`, `Tropical Cyclone Local Statement`. Map them to the API's `type`: `hurricane_watch`, and so on.
- **Historical limit:** `/alerts` only covers about the last 7 days. NCEI keeps the CAP archive. **Historical alerts are the hardest data to get; use IEM, below.**

#### 1.5 Historical alerts: Iowa Environmental Mesonet (IEM)

- `https://mesonet.agron.iastate.edu/json/vtec_events_bypoint.py?lat=27.9506&lon=-82.4572&sdate=2024-10-04&edate=2024-10-13&fmt=json` returns `{"events":[{issue, expire, phenomena, significance, name, wfo, eventid, ugc, url}]}`. Times are already UTC Z.
- Verified for downtown Tampa during Milton:
  - Hurricane Watch (HU.A), FLZ151: 2024-10-07T09:33Z → 2024-10-07T21:07Z.
  - Hurricane Warning (HU.W): 2024-10-07T21:07Z → 2024-10-10T08:57Z.
  - Storm Surge Watch and Warning (SS.A, SS.W): same times as the hurricane alerts.
  - Extreme Wind Warning (EW.W), FLC057: 2024-10-09T22:36Z.
- Filter to phenomena `HU`, `TR`, `SS`, `EW`.
- Matching is by UGC, not polygon. IEM is a university service, so fetch once per demo ZIP and commit the result. Its rate limits are UNVERIFIED.

#### 1.6 ZIP → lat/lon (no key)

- **Use the Census Gazetteer ZCTA file:** `https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip`.
  - It is 1.0 MB zipped and holds a 6.8 MB tab-separated text file with 33,791 rows.
  - Columns: `GEOID ALAND AWATER ALAND_SQMI AWATER_SQMI INTPTLAT INTPTLONG`.
  - **Quirk:** the last header and every row carry long trailing spaces, so `.strip()` everything and keep `GEOID` as a string (leading zeros).
  - Example: `33602 → 27.953704, -82.45631`.
  - Ship a trimmed `zcta.csv` (about 1 MB) in the repo.
- **ZCTA is not the same as a ZIP.** PO-box-only ZIPs are missing (verified: `33601` is absent, `33602` is present). Return `400 zip_not_supported` and suggest a nearby ZIP.
- The Census geocoder (`https://geocoding.geo.census.gov/geocoder/locations/onelineaddress`) needs a street address. Whether it works with a ZIP alone is UNVERIFIED, so it is not used.

### 2. Storm data for demo replay

| | Milton 2024 (`al142024`) | Ian 2022 (`al092022`) |
|---|---|---|
| Cone files | 23 full advisories (001–023) plus 18 intermediates (003A–022A) | 68 files in all (001–038 plus `A`s) |
| Advisory 001 | 2024-10-05 15:00Z | (from TCM) |
| Wind speed probabilities | Every synoptic time from 2024100500 to 2024101112 is present (`…101218` is missing, which doesn't matter) | `2022092712` confirmed present |
| Arrival-time KMZ | 001 and 023 confirmed | Confirmed (`AL092022_020adv…`) |
| Best track | 254 KB | 253 KB |
| Demo ZIPs | 33602 Tampa, 34236 Sarasota | 33901 Fort Myers |

**Hard to get historically:**

1. **NWS alerts.** Use IEM instead.
2. **`CurrentStorms.json` snapshots** don't exist. Rebuild them from the `5day_pts` record with `TAU=0` plus the TCM.
3. **Interval wind probabilities.** Only the PWS text has them per city. GRIB2 archive access is UNVERIFIED.
4. **Arrival times before 2018.**
5. **GIS files lag the text advisory** in live mode by an amount that is UNVERIFIED; plan on about 10–30 min.

Also note that the API.md example puts Milton advisory 14 on 10-07 at 15:00. The archive shows advisory 15 at 2024-10-08T21:00Z, so advisory 14 is around 10-08T15Z. **Derive every time from the files; never hardcode.**

### 3. Ingestion design

**Libraries** (pure Python, Windows-friendly): `httpx` (async), `pyshp` (reads shapefiles from bytes inside the zip, no GDAL), `shapely>=2` (prepared geometries, `contains`, `distance`), and stdlib `zipfile` and `xml.etree`. **Avoid** geopandas, fiona and cfgrib/eccodes; they are painful to install on Windows and not worth it in 48 h.

**Modules (`harbor/forecast/`):**

```
sources/base.py      ForecastSource protocol: active_storms(now), bundle(storm_id, adv), alerts(zone_ids, point, now)
sources/nhc_live.py  CurrentStorms + GIS downloads, ETag cache, keeps last good bundle
sources/nws_live.py  /points cache, /alerts/active?zone=...
sources/replay.py    reads data/replay/<storm>/manifest.json, filters by DemoClock.now()
parse_nhc.py         5day zip → cone/track/points/ww GeoJSON; TCM UTC time + intensity
wsp.py               half-degree grid dict + 5 km band rings → prob_at(lat, lon, kt)
toa.py               KMZ → [(utc_time, LineString)], 5% ring; eta_at(lat, lon)
alerts.py            NWS / IEM → Alert{type, headline, issued, expires, ugc, source}
geocode.py           zcta.csv lookup; zone resolution (live /points, replay pre-baked)
geo.py               local equirectangular projection (x scaled by cos lat), haversine, prepared polygons
risk.py              pure next_level(prev_state, inputs, now) -> (level, reason, state)
poller.py            asyncio tasks started in FastAPI lifespan; emits Events
```

**Poller schedule (live mode):**

| Job | Interval | Notes |
|---|---|---|
| `CurrentStorms.json` | 5 min (2 min when an Atlantic storm is active) | Conditional GET. A change in `forecastAdvisory.advNum` or `fileUpdateTime` starts a bundle fetch. |
| Bundle fetch | On change | Fetch the cone zip, both wind probability zips, and both arrival-time KMZs. If a file is missing or stale (its `advNum` doesn't match), retry every 2 min for up to 45 min and keep serving the previous bundle. Emit `advisory_issued`. |
| NWS alerts | 2 min per distinct zone set while a storm's p34 ≥ 5% for any user; 15 min otherwise | Dedupe users by `forecastZone` + `county`; one call covers many zones. |
| Risk evaluation | After any bundle or alert change, and every 5 min | Pure function. Each level change is written as a `risk_changed` Event pushed over SSE. |

Advisory times: full advisories at 03/09/15/21Z, and intermediates (`A`) at 00/06/12/18Z once watches are up (seen in the Milton archive). Set `next_advisory_time` = advisory time + 6 h (+3 h while watches or warnings are active).

**Point lookups per user (on each new advisory):**

- `in_forecast_cone` = prepared cone polygon `.contains(Point(lon, lat))`. Add a buffer of 0.1° (about 10 km), because the cone is a centre-track error area, not a wind footprint.
- `ts_wind_probability_5day` and `hurricane_wind_probability_5day` come from `wsp.prob_at` for 34 and 64 kt.
- **`earliest_ts_winds_eta`, in order of preference:**
  1. **Arrival-time KMZ.** Resolve each "Wed 8 am" label to UTC: take the first matching weekday on or after the `pubAdvTime` date, apply the document `timezone` (fixed map: EDT −4, CDT −5, EST −5, CST −6, AST −4), and require the times to increase.
     - If the point is outside the 5% ring, the ETA is `null`.
     - Otherwise, project the point and the lines. Find the nearest isochrone *i* and its nearer neighbour *j*, then compute `t = t_i + (t_j − t_i)·d_i/(d_i + d_j)`. Floor the result to the hour; err early.
     - If the point is nearer the storm than the first line, use `min(t_0, now)`.
  2. **PWS text** for the nearest listed city within 50 miles: the start of the first window where the cumulative 34 kt value is ≥ 10%.
  3. **Rough estimate:** advisory time + (distance from centre − 34 kt radius) / forward speed, from `movementSpeed`.
  - Return the source with the value (`eta_source`), so the AI summary can say how confident it is.

### 4. Risk state machine

Inputs per user:

- `p34`, `p64` (0–1), `in_cone`, `eta` (earliest reasonable arrival).
- `alerts` (a set of `HU.A`, `HU.W`, `TR.A`, `TR.W`, `SS.A`, `SS.W`, `EW.W`).
- `sensor_flag`, from the sensors module: pressure falling at least 3 mb in 3 h within 150 mi while a storm centre is within 500 mi.
- `storm_active`, plus the bookkeeping fields `low_count` and `entered_at`.

**Escalation is immediate and can skip levels.** The level becomes the highest one whose condition holds:

| To | Condition |
|---|---|
| `monitor` | `p34 ≥ 0.05` OR `in_cone` |
| `prepare` | `p34 ≥ 0.20` OR any `TR.A`/`SS.A` OR (`p34 ≥ 0.10` AND `sensor_flag`) |
| `act` | `p34 ≥ 0.50` OR `p64 ≥ 0.20` OR any `HU.A`/`HU.W`/`TR.W`/`SS.W` OR (`p34 ≥ 0.20` AND `eta − now ≤ 60 h`) |
| `shelter` | (`HU.W` or `TR.W`) AND `eta − now ≤ 12 h`; OR `EW.W` active; OR `eta ≤ now` AND `p34 ≥ 0.50` |

The 60 h rule in `act` ties the forecast to T+1 settlement: a sale placed before roughly 2 pm ET settles the next business day, which leaves buffer for a weekend. The planner should own the exact settlement rule.

**De-escalation has hysteresis.** It only happens after **two consecutive full advisories** below the lower threshold, and it never happens out of `shelter` except into `recover`:

| From → To | Condition |
|---|---|
| `monitor` → `clear` | `p34 < 0.03` and not in cone ×2, or the storm leaves `activeStorms` |
| `prepare` → `monitor` | `p34 < 0.12` ×2 and no watches. The plan becomes `expired`. |
| `act` → `recover` | `p34 < 0.20` ×2 and no HU/TR/SS alerts. The storm turned away, but money already moved and has to go back. |
| `shelter` → `recover` | No HU/TR/SS/EW alert active for the zone (every one has passed `expires`, or got `messageType: Cancel`) AND (not in the latest cone, OR the storm is post-tropical/gone, OR the centre is more than 200 mi away and moving off) AND at least 6 h in `shelter` |
| `recover` → `clear` | The planner reports the plan `restored`, OR 72 h have passed with `p34 < 0.03` |

Two more rules:

- **Re-arming:** from `recover`, escalation to `act` is allowed only if `p34 ≥ 0.50` again, from a new storm or a looping one. That starts a new plan.
- **Multiple storms:** the user's level is the maximum over active storms. The wind speed probabilities are already all storms combined.

Every transition records a `reason` string, e.g. "Milton wind chance at your ZIP reached 62%". That string goes into the Event and into the Claude prompt.

### 5. Demo replay format

**Repo layout** (Milton is about 12 MB raw; clip it to cut the size):

```
data/replay/milton-2024/
  manifest.json
  raw/5day/al142024_5day_{001..023,003A..022A}.zip
  raw/wsp/{YYYYMMDDHH}_wsp_120hr5km.zip, _wsp_120hrhalfDeg.zip   (one per full advisory)
  raw/toa/AL142024_{NNN}adv_{earliest_reasonable,most_likely}_toa_34.kmz
  raw/text/al142024.{fstadv,wndprb,discus}.{NNN}.shtml
  raw/al142024_best_track.zip
  alerts/{zip}.json          # IEM response, filtered to HU/TR/SS/EW
  zones.json                 # {"33602": {"forecast": "FLZ151", "county": "FLC057"}}
```

**Two build scripts:**

1. `tools/fetch_replay.py <storm>` builds the URLs listed in §1–2 and downloads them politely (1 request/s, the same User-Agent).
2. `tools/build_replay.py` writes `manifest.json`:

```json
{ "storm_id": "al142024", "name": "Milton", "demo_zips": ["33602", "34236"],
  "start": "2024-10-06T03:00:00Z", "end": "2024-10-12T00:00:00Z",
  "advisories": [
    { "adv": "015", "issued_at": "2024-10-08T21:00:00Z", "intermediate": false,
      "category": 5, "classification": "HU", "lat": 22.7, "lon": -87.5,
      "cone": "raw/5day/al142024_5day_015.zip", "wsp_synoptic": "2024100818",
      "toa_er": "raw/toa/AL142024_015adv_earliest_reasonable_toa_34.kmz",
      "pws": "raw/text/al142024.wndprb.015.shtml" } ] }
```

- `issued_at` comes from the TCM's "HHMM UTC" line, not from `ADVDATE`.
- `A` entries carry `cone` (positions and watches) but no `wsp` or `toa`. The replay reuses those from the last full advisory.
- Optionally, pre-convert the cones to GeoJSON and clip the 5 km wind probability bands to lon −98…−75, lat 18…35 to shrink the repo.

**How the fake clock serves the files.** The clock is a `DemoClock` with fields `{anchor_real (monotonic), anchor_storm, speed, paused}`:

- `now()` = `anchor_storm + (monotonic() − anchor_real) × speed`.
- `advance(h)` moves `anchor_storm` forward by `h` hours.
- `ReplaySource.bundle()` returns the last manifest entry with `issued_at ≤ now`.
- `ReplaySource.alerts()` returns IEM events with `issue ≤ now < expire`.

It implements the same `ForecastSource` interface as the live sources, so `risk.py`, the planner and the SSE feed can't tell the difference. When the clock crosses an `issued_at`, the poller emits `advisory_issued`.

Storm times stay in their real 2024 timestamps, and `server_time` echoes them. Nessie transaction dates will be real 2026 dates; the UI should label the demo "Replay of Hurricane Milton".

**Default run:** start at 2024-10-06T03:00Z. At `speed: 3600`, the 117 h to Oct 11 take under 2 minutes; 900–1800 is easier to present. For Tampa, expect the level to rise through monitor and prepare first. It reaches **act** by the 2024-10-07T09:33Z Hurricane Watch at the latest, then **shelter** when the warning is up and ETA ≤ 12 h (around Oct 9 midday). **Recover** comes after the warning ends at 2024-10-10T08:57Z. Only the 09:33Z watch time is checked against IEM; **the monitor/prepare times and the shelter time are estimates, not measured.** Run `risk.py` over the manifest once to confirm the order before judging.


---

## Sensors layer ("Sensors for Good")

### 1. Why sensors matter in Harbor

A forecast is a probability. A sensor is a measurement. Harbor uses sensors for three things the forecast cannot do on its own:

1. **Raise risk sooner.** If pressure is falling fast at a nearby station, Harbor can move from `monitor` to `prepare` before the next NHC advisory, which comes out every 6 hours.
2. **Tell people something concrete about their own area.** For example: "Water at the Fort Myers tide gauge is 5.3 ft above the predicted tide."
3. **Hold back or confirm all-clear.** Rivers often crest days after landfall. Harbor should not return evacuation cash to savings while the river next to the user is still rising.

### 2. Data sources (verified against live endpoints on 2026-10-16)

#### 2.1 NOAA CO-OPS Tides & Currents: SHIP (main source)
One API gives observed water level, the predicted tide, air pressure and wind. That is everything needed for the storm-surge story.

- **Data API:** `GET https://api.tidesandcurrents.noaa.gov/api/prod/datagetter`
  - Example: `?product=water_level&station=8726520&begin_date=20241009 18:00&end_date=20241010 12:00&datum=MLLW&units=english&time_zone=gmt&format=json&application=harbor`
  - **Products:** `water_level` (6-minute preliminary or verified), `predictions` (add `interval=h` for hourly, or 6-minute by default), `hourly_height`, `air_pressure`, `wind`, `one_minute_water_level`.
  - **Date formats:** `yyyyMMdd`, `yyyyMMdd HH:mm`, `MM/dd/yyyy`, `MM/dd/yyyy HH:mm`. You can also send `date=latest|recent|today` or `range=<hours>`.
  - **Request size limits:** 1-minute data up to 4 days, 6-minute data up to 1 month, hourly data up to 1 year, predictions up to 1 year.
  - `datum` is required for water-level products. Always send `time_zone=gmt` and the `application` name, which NOAA uses to trace issues in its logs.
- **Response shape (verified):**
  - Top level: `{"metadata":{"id":"8726520","name":"St. Petersburg","lat":"27.7606","lon":"-82.6269"},"data":[...]}`
  - Water level row: `{"t":"2024-10-10 02:24","v":"-0.44","s":"0.056","f":"0,0,0,0","q":"v"}`
  - Predictions use the top-level key `predictions` with rows `{t,v}`.
  - `air_pressure` rows are `{t,v,f}`, with values in mb.
  - `wind` rows are `{t,s,d,dr,g,f}`.
  - Every value is a **string**. Times have **no "Z"** and are UTC only because we send `time_zone=gmt`.
  - Errors come back as `{"error":{"message":...}}` with HTTP 200, so check for that key.
- **Metadata API:**
  - Station list: `https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=waterlevels`. Each station has `id, name, lat, lng, state`.
  - Per-station resources: `/stations/{id}/floodlevels.json`, `/sensors.json`, `/datums.json`, `/products.json`.
  - The list also accepts `&expand=floodlevels,sensors`.
  - Flood levels for St. Petersburg 8726520: `nos_minor 7.36, nos_moderate 8.32, nos_major 9.56, nws_minor 8.33, nws_moderate 10.63, nws_major 11.63`.
  - **UNVERIFIED: which datum these thresholds are relative to.** The response doesn't say. So Harbor's main metric is **surge = observed − predicted**, using the same datum for both. That needs no datum conversion.
- **There is no radius search.** Download the station list once, keep the Florida and Gulf Coast stations, and compute haversine distance locally.
- **Rate limits:** none published (UNVERIFIED). Poll every 6 minutes at most, and cache.

**Real numbers for the demo (fetched from the API):**

| Storm / station | Observed (MLLW) | Predicted | Surge |
|---|---|---|---|
| Milton, Fort Myers 8725520, 2024-10-10 03:00Z | 6.23 ft | 0.92 ft | **+5.3 ft** |
| Milton, St. Petersburg 8726520, 2024-10-10 02:24Z | −0.44 ft | ~1.6 ft | **−2.0 ft** (reverse surge) |
| Milton, St. Pete air pressure | 1006.5 mb at 09 12Z, 991.9 at 21Z, **978.1 at 10 01Z** | | −14.6 mb in 9 h |
| Helene, St. Petersburg, 2024-09-27 04:00Z | 8.46 ft | ~1.7 ft | **≈ +6.8 ft** |

**Important for the demo:** Milton did **not** flood Tampa Bay. It made landfall at Siesta Key, and winds on its north side pushed water *out* of the bay. News coverage reported the water level at a NOAA gauge near Tampa dropping about 5 ft. If the demo user lives in Tampa (33602, as in API.md), Milton produces a *negative* surge. Pick one of these:
- (a) Make the Milton demo user live in Fort Myers or Sarasota, for example ZIP 33901 or 34236.
- (b) Keep Tampa and replay Helene 2024 for the surge moment.
- (c) Use the reverse surge as a safety message. People walked out onto the exposed bay floor during Milton, so Harbor would say: "Water is 2 ft below normal at St. Pete. Stay off the exposed bay floor; it returns fast."

Option (a) plus the river story in 2.2 is the strongest.

#### 2.2 USGS stream gauges + NWS flood stages: SHIP
River flooding is the post-landfall danger, and it drives recovery decisions.

- **Do not build on legacy `waterservices.usgs.gov/nwis/iv`.**
  - It now returns a 301 redirect to `nwis.waterservices.usgs.gov`.
  - USGS says WaterServices will be decommissioned in Q1 2027, and the final decommission campaign runs **November 2026 to February 2027**. That starts next month, during or right after this hackathon.
  - It still works today: path `value.timeSeries[0].values[0].value[]`, entries like `{"value":"8.45","qualifiers":["A"],"dateTime":"2024-10-08T20:00:00.000-04:00"}`, with a local offset rather than UTC. Treat it only as a fallback.
- **New Water Data API (OGC API Features, GeoJSON):**
  - Historical: `GET https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items?f=json&monitoring_location_id=USGS-02301500&parameter_code=00065&datetime=2024-10-10T00:00:00Z/2024-10-13T00:00:00Z&limit=500`. This call was verified working.
  - Each feature's `properties` has `time_series_id, monitoring_location_id, parameter_code` (00065 = gage height in ft, 00060 = discharge), `statistic_id`, `time` (UTC with offset), `value` (a **string**), `unit_of_measure`, `approval_status`, `qualifier` and `last_modified`.
  - Data is at 15-minute intervals. The top level has `numberReturned` and `links`. Follow the `rel=next` link to page through results.
  - Live readings: `collections/latest-continuous/items`.
  - The docs show `/ogcapi/v1/` for `daily`, while `v0` worked for `continuous`. Check `GET /ogcapi/v1/collections` at build time and pin one version (UNVERIFIED which is canonical).
  - **API key:** optional but gives higher limits. Sign up at `https://api.waterdata.usgs.gov/signup` and pass `api_key=`. Store it in a `USGS_API_KEY` env var. Numeric rate limits are UNVERIFIED.
- **Flood stages come from NWS's National Water Prediction Service (NWPS)**, not from USGS:
  - Find gauges: `GET https://api.water.noaa.gov/nwps/v1/gauges?bbox.xmin=-82.6&bbox.ymin=27.7&bbox.xmax=-82.0&bbox.ymax=28.4&srid=EPSG_4326`. The response has a top-level `gauges` array. Each gauge has `lid, name, latitude, longitude, status.observed{primary, primaryUnit, floodCategory, validTime}` and `status.forecast{...}`.
  - Gauge details: `GET https://api.water.noaa.gov/nwps/v1/gauges/LITF1`. This returns `usgsId: "02301500"` and `flood.categories.{action,minor,moderate,major}.stage` = **11 / 13 / 16 / 19 ft**. It also returns `flood.crests` (historic crests) and `datums`.
  - Time series: `GET /nwps/v1/gauges/{lid}/stageflow` returns `observed.data[]{validTime, primary, secondary}` at 15-minute intervals, covering only about **30 days**. Historical replay must therefore come from USGS.
  - **Quirks:**
    - Missing values are `-999` or `-9999`, with `validTime "0001-01-01T00:00:00Z"`.
    - Many gauges have `floodCategory: "not_defined"`, meaning no flood stages exist. Only keep gauges whose categories are defined.
    - Some "gauges" are tide gauges whose names end in "(in MHHW)".
    - `usgsId` can be `""`.
- **Demo fact (verified):** the Alafia River at Lithia (NWPS `LITF1`, USGS `02301500`) crested at **24.36 ft on 2024-10-11 around 14:00Z**. That is 5.4 ft above *major* flood stage, about 37 hours after Milton made landfall. It is the second-highest crest on record. On the stage chart, the river is still rising after the NHC alerts expire. That is the core of the recovery story.
- Other Tampa-area gauges with defined categories: `ZPHF1` (Hillsborough River near Zephyrhills), `MORF1` (Morris Bridge), `FOWF1` (Fowler Ave), `RVWF1` (Alafia River at Riverview), `WRGF1` (Cypress Creek).

#### 2.3 NOAA NDBC buoys: SHIP (offshore early warning)
- **Realtime:** `https://www.ndbc.noaa.gov/data/realtime2/{STATION}.txt`. Covers the last **45 days**, newest row first.
  - The header is 2 lines (verified):
    ```
    #YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
    #yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft
    ```
  - Columns are separated by whitespace. Missing values are `MM`. All times are UTC.
  - **`PTDY` is NDBC's own pressure tendency.** Use it directly as a cross-check on the computed 3-hour pressure change.
  - Units are metric: convert m/s to mph (×2.23694) and m to ft (×3.28084).
  - Most stations report hourly, with data available about 25 minutes after the hour. NDBC asks users to keep retrievals to a minimum, so poll each station every 15–30 minutes.
- **Historical:** `https://www.ndbc.noaa.gov/data/historical/stdmet/42036h2024.txt.gz`. A plain-text view is available at `view_text_file.php?filename=42036h2024.txt.gz&dir=data/historical/stdmet/`.
  - The historical format differs from realtime:
    - There is **no `PTDY` column**.
    - `VIS` is in `mi`.
    - Missing values are `99.0`, `999`, `999.0` or `9999.0` instead of `MM`.
  - Use separate parsers for realtime and historical files.
- **Station metadata:**
  - `https://www.ndbc.noaa.gov/data/stations/station_table.txt` is pipe-separated: `STATION_ID | OWNER | TTYPE | HULL | NAME | PAYLOAD | LOCATION | ...`. Location looks like `28.500 N 84.505 W`.
  - `https://www.ndbc.noaa.gov/activestations.xml` has lat/lon attributes and is easier to parse (UNVERIFIED field names; inspect before parsing).
- **Tampa-area buoys:**
  - `42036` (3 m discus, 112 NM WNW of Tampa, full met data)
  - `42013` (USF COMPS C10)
  - `42098` (Egmont Channel) and `42099` (Offshore St. Pete) are **Waverider buoys: waves only, with no pressure or wind.** Don't select them for pressure.
- **Milton at 42036 (verified from the 2024 file):** PRES went from 1005.5 hPa at 09 12:00Z to 1000.5 at 21:00Z to a minimum of **997.9 at 23:00Z**. Max sustained wind was 20.3 m/s (45 mph), gusts 26.4 m/s (59 mph), and waves 5.54 m (18 ft) at 23:10Z.

#### 2.4 NWS station observations: STRETCH (live mode only)
- **Find stations:** `GET https://api.weather.gov/points/{lat},{lon}` gives `properties.observationStations`, a URL to `/gridpoints/{wfo}/{x},{y}/stations`. Assuming nearest-first ordering is UNVERIFIED; sort by distance yourself.
- **Readings:**
  - `GET /stations/KTPA/observations/latest?require_qc=false`
  - `GET /stations/KTPA/observations?start=...&end=...&limit=1..500`
- **A `User-Agent` header is required**, for example `(harbor-hackathon, you@example.com)`. Rate limits aren't published. If you hit them, retry after about 5 seconds. Data can lag up to 20 minutes.
- **Units are WMO:** `barometricPressure` is `{"unitCode":"wmoUnit:Pa","value":101422.34,"qualityControl":"V"}` (divide by 100 for mb). `windSpeed` is in `wmoUnit:km_h-1`. `value` is often `null`, with `qualityControl:"Z"`.
- **No history:** a request for KTPA observations from October 2024 returned an empty FeatureCollection, because this API keeps only about the last week (UNVERIFIED exact retention). For replay, use the Iowa Environmental Mesonet archive:
  - `https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=TPA&data=mslp&data=sknt&data=gust&year1=2024&month1=10&day1=5&year2=2024&month2=10&day2=13&tz=Etc/UTC&format=onlycomma&latlon=yes&missing=null`
  - IEM throttles each IP to 1 request per second and returns HTTP 429 above that. Whether IEM IDs drop the leading "K" (`TPA` vs `KTPA`) is UNVERIFIED.
- This source adds little beyond CO-OPS `air_pressure` and `wind`, so it is stretch only.

#### 2.5 Phone sensors: STRETCH (geolocation only)
- **Barometer:** no browser exposes one. The Generic Sensor API (MDN) defines `Accelerometer`, `Gyroscope`, `Magnetometer`, `AmbientLightSensor`, `GravitySensor`, `LinearAccelerationSensor` and the orientation sensors, but **no pressure sensor**. It works only in secure contexts and is Chromium-only (Safari and Firefox support UNVERIFIED-absent).
  - The "Compute Pressure API" measures CPU load, not air pressure. Don't confuse the two.
  - Native apps can read the barometer (Android `Sensor.TYPE_PRESSURE`, iOS `CMAltimeter`). That is not feasible in a Next.js site in 48 hours.
- **Geolocation:** `navigator.geolocation.getCurrentPosition` works in all browsers over HTTPS (localhost counts) after a permission prompt. Use it to:
  - offer "use my location" at sign-up, so we keep the exact lat/lon instead of the ZIP centroid;
  - optionally post `PATCH /me {location}` when the user evacuates, so Harbor re-selects sensors, ATMs and the cone check for their new location.
- **Pitch line:** "Your phone is a sensor too. When you evacuate, Harbor re-checks the gauges and ATMs where you actually are."

### 3. What to ship

| Priority | Source | Why |
|---|---|---|
| **Ship 1** | CO-OPS (water level + predictions + air pressure + wind) | Surge vs predicted and fast pressure falls from one API, with strong real numbers for Milton and Helene |
| **Ship 2** | USGS `continuous` + NWPS flood categories | River crest after the storm drives the recovery hold. Alafia: 24.36 ft vs 19 ft major |
| **Ship 3** | NDBC `42036` | Offshore pressure and waves seen ~12 h before landfall. Simple text files |
| Stretch | NWS `/observations` (live), IEM (replay) | Duplicates CO-OPS data |
| Stretch | Browser geolocation for evacuee location | Easy add-on if time permits |

### 4. SensorService design

**Module layout:**
```
app/sensors/
  registry.py        # station catalogue: load stations.json, nearest-N per category
  sources/coops.py   # fetch + parse -> list[Reading]
  sources/usgs.py    # continuous / latest-continuous (+ NWPS categories via nwps.py)
  sources/nwps.py
  sources/ndbc.py    # realtime2 parser + historical stdmet parser
  trends.py          # pure functions: pressure_change_3h, surge_ft, stage_vs_flood, rising_rate
  status.py          # thresholds -> normal/watch/warning + reason text
  service.py         # SensorService: get_for_user(user, now) / history(id, hours, now)
  replay.py          # ReplaySource reading recorded JSONL using the demo clock
tools/build_station_registry.py  # one-off: writes data/stations.json (FL/Gulf subset, committed)
tools/record_storm.py            # one-off: writes data/storms/<storm>/sensors.jsonl
```

**Interface:** `SensorSource.fetch(station, start, end) -> list[Reading]` has two implementations:
- `LiveSource` (httpx with a 10 s timeout; results cached in memory for 5 minutes per station)
- `ReplaySource(clock)`

Everything after the source layer is identical in live and demo modes.

**Normalized reading (stored in SQLite, one row per metric):**
```
sensor_readings(station_id TEXT, source TEXT, observed_at TEXT /*UTC ISO Z*/, metric TEXT, value REAL, PRIMARY KEY(station_id, observed_at, metric))
```
- Metrics: `pressure_mb`, `wind_speed_mph`, `wind_gust_mph`, `wave_height_ft`, `water_level_ft`, `predicted_ft`, `surge_ft`, `stage_ft`.
- Convert units and parse strings at ingest. Never store `MM`, `-999` or `99.0` placeholders; drop them.
- Store CO-OPS heights relative to MLLW, and keep the datum in the station record.

**Choosing stations per user** (recompute when ZIP or location changes):
- up to **2 CO-OPS water-level stations** within 60 mi;
- **1–2 NDBC buoys with pressure** within 200 mi (skip Waveriders by checking the realtime file has a non-`MM` PRES);
- up to **3 river gauges within 25 mi** whose NWPS flood categories are defined;
- **1 NWS station** if that stretch is built.

Distance is haversine from `user.location`. "Nearest" is good enough for a hackathon. A real product would also consider which bay or basin the user is in.

**Trends (pure functions, unit-tested with the Milton numbers above):**
- `pressure_change_3h`: value at `now` minus the value closest to `now−3h` (within ±30 min); otherwise `None`. On NDBC realtime, prefer `PTDY` when it's present.
- `surge_ft`: observed minus the prediction at the same timestamp, both at 6-minute intervals. Use the median over the last 30 minutes to remove wave noise.
- `stage_margin_ft`: `stage_ft` minus the NWPS `action`, `minor` and `major` stages. `rise_ft_per_hr` is computed over the last 3 hours.
- **Staleness:** a reading is stale if it's more than 2× the station's normal interval old (CO-OPS 6 min, USGS 15 min, NDBC 60 min). **A station that goes silent while at watch or warning keeps its last status, marked `stale`.** Gauges fail at the peak; Ian's Fort Myers gauge reportedly stopped reporting (UNVERIFIED). Missing data never counts as all-clear.

**Status thresholds** (tunable constants in `status.py`):

| Metric | watch | warning |
|---|---|---|
| `pressure_change_3h_mb` | ≤ −3 | ≤ −6 (about the METAR "pressure falling rapidly" rate) or pressure < 990 |
| `surge_ft` | ≥ +1.0, or ≤ −2.0 (water drawn out) | ≥ +2.0, or water level ≥ station `nws_minor` once the datum is confirmed |
| `stage_ft` | ≥ action stage, or rising ≥ 0.5 ft/hr | ≥ minor flood stage (show "MAJOR" at ≥ major) |
| `wind_speed_mph` (sustained) | ≥ 39 (tropical-storm force) | ≥ 58 |

- A station's status is the worst status across its metrics.
- Each status carries a `reason` string written by the rules, not the AI. For example: `"Surge +5.3 ft above predicted tide at Fort Myers (14 mi)"`. These strings feed straight into `sensor_alert` events and give Claude grounded facts for "why" answers.

**API contract additions** (proposed; API.md not edited):
- Add `noaa_tide` to `source`.
- Tide readings: `water_level_ft`, `predicted_ft`, `surge_ft`.
- Every reading gets `status_reason` and `stale: bool`.
- River gauges also get `flood_category` (`none/action/minor/moderate/major`) and `crest_rising: bool`.

### 5. How sensors feed the risk engine
The forecast stays in charge, and sensors can only move risk **toward safety**. All of these rules are deterministic:

1. **Escalation:** `monitor` → `prepare` if any selected station is at `warning`, or two stations of different kinds are at `watch`. This is already listed as a `prepare` trigger in API.md. Sensors alone never move risk to `act`, because selling assets needs forecast support. But if risk is already `prepare` and the nearest coastal gauge is at surge `warning`, cash moves are brought forward: the `withdraw_cash` move is rescheduled to now (the user still approves).
2. **Shelter confirmation:** wind ≥ 39 mph or surge at warning at the nearest station → the UI shows `shelter` messaging, even if the next advisory is hours away.
3. **Recovery gate (the key part):** `recover` requires the forecast to be all-clear (alerts expired, out of the cone) **and** all of the following:
   - pressure 3-hour change ≥ 0 and within 5 mb of the pre-storm baseline;
   - surge < 1 ft for 3 consecutive hours;
   - every selected river gauge below action stage, or below minor stage **and** falling for 6 hours.

   If any check fails, Harbor stays at `shelter`/hold and emits:
   > "NHC alerts have ended, but the Alafia River at Lithia is still rising (23.9 ft, major flood stage is 19 ft). Harbor is keeping your evacuation cash in checking."

   In the Milton replay, this hold lasts about a day past alert expiry, until the crest passes on October 11.
4. Each sensor-driven change emits `sensor_alert` and `risk_changed` events whose `data` includes `{station_id, metric, value, threshold}`.

### 6. Recording and replay for the demo
- `python tools/record_storm.py milton-2024 --start 2024-10-05T00:00Z --end 2024-10-13T00:00Z` fetches, for the chosen stations:
  - CO-OPS `water_level` and `predictions` (6-minute), `air_pressure` and `wind`, in one request per week (within the 1-month limit);
  - USGS `continuous` 00065, following pagination;
  - the NDBC `42036h2024` historical file;
  - optionally IEM for KTPA.

  It runs the same normalizers as live mode and writes `data/storms/milton-2024/sensors.jsonl` plus `stations.json`. That is about 30–40k rows, a few MB, **committed to git** so the demo works offline and doesn't depend on NOAA being up during judging. Record Helene 2024 and Ian 2022 the same way if there's time.
- **ReplaySource:** `offset = demo_clock.start − storm_window.start`, applied identically to NHC advisories and sensor rows so they stay in sync. The API.md example uses 2026 dates, so the offset is about 730 days. At demo time `now`, it returns rows with `observed_at + offset ≤ now`. Trend code doesn't need to know it's a replay.
- `POST /demo/advance` and `/demo/reset` don't need special sensor handling; the clock alone drives it.
- **Recommended demo user:** Fort Myers (33901) for the +5.3 ft surge. Show a Tampa user alongside for the reverse surge and the Alafia flood hold.

### 7. What will make the Sensors for Good judges happy
- **Every protective action is tied to a real measurement the user can see.** A chart from `/me/sensors/{id}/history` shows observed vs predicted tide with the surge shaded, and river stage against flood-stage bands.
- **Messages about people, not data:**
  - "Surge already 5 ft above the predicted tide at Fort Myers, 14 miles from you. Your $1,280 is in checking; withdraw cash at the Capital One ATM outside the cone."
  - "Water pulled 2 ft below normal in Tampa Bay; do not walk out on the exposed bay floor."
  - "River still rising: we're holding your cash."
- **Sensors save people from false all-clears.** River crest timing and "silence is not safety" handling are protective uses beyond what the forecast gives.
- **Honesty:** show each station's distance, last-update time and `stale` badge, and credit NOAA CO-OPS, USGS, NWS NWPS and NDBC on screen.

### 8. Gotchas checklist
- Every API returns values as strings.
- NDBC realtime and historical files use different columns and missing-value markers.
- CO-OPS times have no "Z"; legacy USGS times have local offsets.
- NWS units are Pa and km/h; `null` values are common.
- The legacy USGS service enters decommission in November 2026.
- NWPS keeps only about 30 days of stage data.
- Waverider buoys have no pressure.
- The datum for CO-OPS flood thresholds is UNVERIFIED.
- Keys live only in env vars (`USGS_API_KEY` is optional); the NWS User-Agent contact also comes from env.

**Files read:** `C:\Users\matth\harbor\docs\API.md`, `C:\Users\matth\harbor\README.md` (no files were changed).


---

## Nessie bank layer

### What was verified, and how (probed 2026-10-16)

The old docs page `http://api.nessieisreal.com/documentation` is gone. Port 80 refuses connections and `/documentation` returns API Gateway's `403 Missing Authentication Token`. The current primary sources are:

- Site and docs (a JavaScript single-page app): https://nessieisreal.com/docs, plus a Getting Started page at https://nessieisreal.com/getting-started.
- **OpenAPI 3.0.3 spec**: https://nessieisreal.com/nessie-openapi-spec.yaml. It lists the servers `https://prod-api.nessieisreal.com` and `https://qa-api.nessieisreal.com`. `https://api.nessieisreal.com` also works and behaves the same as `prod-api`.
- Legacy JavaScript SDK, which shows the request bodies: https://github.com/nessieisreal/nessie-javascript-sdk (`lib/transfer.js`, `lib/withdrawal.js`, `lib/atm.js`, `lib/tests/*`).
- Live unauthenticated and dummy-key GET probes against `https://api.nessieisreal.com`. No POST, PUT or DELETE was sent with a key, so **every write behaviour below is from the spec or SDK, not tested**.

### Base URL and auth

- Base URL: `https://api.nessieisreal.com`. Use **HTTPS only**, because HTTP on port 80 refuses connections. Make it configurable with `NESSIE_BASE_URL` so we can switch to `prod-api`.
- Auth: the query parameter `?key=<NESSIE_API_KEY>`. The spec's `securitySchemes.ApiKeyAuth` is `in: query, name: key`. You get a key by logging in to nessieisreal.com with GitHub, then opening Profile.
- **Quirk 1: no key gives a 502, not a 401.** On most routes a missing `key` returns `502 {"message":"Internal server error"}`. Only `/atms` returns `401 "unauthorized"`. So a 502 can mean "config bug", not "server down".
- **Quirk 2: a wrong key is not rejected.** `?key=probe12345` returned `200 []` for `/customers`. The key seems to act as a tenant namespace. A typo in `NESSIE_API_KEY` would silently show an empty bank, so `/health` must check that the seeded customer exists.
- **Quirk 3: the enterprise endpoints can read everyone's data.** The Getting Started page says enterprise routes are read-only "analyst" views of *all* data. With a dummy key, `/enterprise/customers` returned 3,908 customers and `/enterprise/accounts` returned 8,346 accounts across all users, including `account_number`. **Seed only fictional people and never put real personal information in Nessie.** Say this in the pitch as a privacy decision.
- **Quirk 4: written errors are plain JSON strings.** Errors are often bare strings, for example `404 "Customer not found"` or `"Account with this id does not exist"`. The spec's `{code,message}` shape is not always what comes back.
- **Quirk 5: ID formats don't match the spec.** The spec says `_id` is 24 characters (a Mongo ObjectId). The live customer, account and transfer data uses 36-character UUIDs, while ATMs and branches still use 24-character IDs. Do not validate ID length.
- **Rate limits are not documented (UNVERIFIED).** No 429 was seen in about 150 GET calls. `/enterprise/deposits` timed out (over 25 s) on every try. Never call it.

### Endpoints Harbor uses

The spec is incomplete: it leaves out `POST /accounts/{id}/transfers` and the purchase creation route. The gateway routes those paths, and the official docs Quick Start lists `POST /accounts/{id}/transfers`. The table marks the source of each route.

| Purpose | Method and path | Source / status |
|---|---|---|
| Create customer | `POST /customers` | spec |
| Get / update customer | `GET`, `PUT /customers/{id}` | spec (**no DELETE for customers**) |
| Customer's accounts | `GET`, `POST /customers/{id}/accounts` | spec |
| Account | `GET`, `PUT` (nickname only), `DELETE /accounts/{id}` | spec |
| All my accounts | `GET /accounts` | spec, probed 200 |
| Transfers | `GET`, `POST /accounts/{id}/transfers` (`?type=payer\|payee` on GET) | SDK and docs Quick Start; GET probed (an empty account gives 404 `"No transfers found for this account"`, **not** `[]`) |
| One transfer | `GET`, `PUT`, `DELETE /transfers/{transfer_id}` | spec, probed 404 |
| Withdrawals | `GET`, `POST /accounts/{id}/withdrawals` | spec, probed 200 |
| One withdrawal | `GET`, `PUT`, `DELETE /withdrawal/{withdrawal_id}` (**singular**; `/withdrawals/{id}` is unrouted) | spec, probed |
| Deposits | `GET`, `POST /accounts/{id}/deposits`; `GET`, `PUT`, `DELETE /deposits/{id}` | spec, probed |
| Purchases | `GET /accounts/{id}/purchases`, `GET /merchants/{id}/purchases`; `GET`, `PUT`, `DELETE /purchase/{purchase_id}` (singular). The `POST /accounts/{id}/purchases` body is UNVERIFIED. | spec and probe |
| Merchants | `GET`, `POST /merchants`; `GET`, `PUT /merchants/{id}` | spec |
| Bills | `GET /customers/{id}/bills`, `GET`, `POST /accounts/{id}/bills`, `GET`, `PUT`, `DELETE /bills/{billId}` | spec |
| Loans | `GET`, `POST /accounts/{id}/loans`; `GET`, `PUT`, `DELETE /loans/{id}` | spec |
| ATMs | `GET /atms`, `GET /atms/{id}` | spec, probed |
| Branches | `GET /branches`, `GET /branches/{id}` | spec, probed |
| Enterprise (read-only) | `/enterprise/customers[/{id}]`, `/enterprise/accounts`, `/enterprise/transfers[/{id}]`, `/enterprise/bills`, `/enterprise/merchants`, `/enterprise/withdrawal/{id}` | probed 200 (not needed by Harbor) |
| Bulk delete | the classic `DELETE /data?type=...` | **gone**: the gateway returns `403 Missing Authentication Token`, which means the route isn't there |

### Request and response shapes

- **CustomerCreate**: `{"first_name","last_name","address":{"street_number","street_name","city","state","zip"}}`. All address fields are required strings.
- **AccountCreate**: `{"type":"Checking"|"Savings"|"Credit Card","nickname":str,"rewards":int>=0,"balance":int>=0}`. Only those three types exist; there is no brokerage type. `PUT /accounts/{id}` takes only `nickname`, so **a balance can't be set after the account is created**.
- **Account** (live): `{"_id","type","nickname","rewards","balance","account_number"(16 digits),"customer_id"}`.
- **Transfer body** (SDK test): `{"medium":"balance","payee_id":"<to account>","amount":4525,"transaction_date":"2016-01-22","status":"pending","description":"..."}`. The account in the path is the **payer**. `medium` is `balance` or `rewards`.
- **Withdrawal body** (SDK test): `{"medium":"balance","transaction_date":"YYYY-MM-DD","status":"completed","amount":25,"description":"Teller withdrawal"}`.
- **DepositCreate** (spec): `medium`, `transaction_date`, `status`, `amount` (integer), `description`. All are required.
- **BillCreate**: `status` (`pending|cancelled|completed|recurring`), `payee`, `payment_amount` (float). Optional: `nickname`, `payment_date`, `recurring_date` (1 to 31). The returned Bill also has `creation_date` and `upcoming_payment_date`.
- **POST responses**: the spec says `201` with a bare string such as `"Withdrawal created"` or `"Account created"`, **with no ID**. Classic Nessie returned `{"code":201,"message":...,"objectCreated":{...}}`, so the current shape is UNVERIFIED. Design for the worst case: find the new object's ID by listing and matching our tag (below).
- **PUT** returns `202 "Accepted ... update"`. **DELETE** returns 200 per the spec; the old SDK tests expected 204.

### Amounts: whole dollars, not cents

The spec types `balance`, deposit `amount` and loan `amount` as **integer**. Bills use a `payment_amount` float. Live enterprise transfer data confirms it: descriptions say `$73.96` and `$18.06` but the stored `amount` values are `74` and `18`. **Nessie keeps whole dollars and rounds the cents away.** No float showed up in 1,584 transfers or 8,346 balances. Harbor's decision:

- Harbor keeps exact integer cents in its own ledger. A Nessie amount is `nessie_dollars = ceil(cents/100)` for money moving *toward* the user's safety (checking and cash) and `floor` for restores. The rounding difference is stored on the Move.
- Cash withdrawals round **up to a multiple of $20** (ATM notes). That gives the plan a natural, explainable reason for whole dollars.
- `Account.balance_cents = nessie.balance * 100`.

### Status lifecycle and execution (UNVERIFIED)

`status` is a string the client sets when it creates a transaction, and Nessie does not seem to check it. Live data contains `completed` 1,351, `pending` 229, `cancelled` 2, and `"bogus"` 2. Transfers marked `pending` and dated 2026-09-12 are still `pending` five weeks later, so **Nessie does not run pending transactions on any schedule we can see**. Whether creating a transaction changes `balance` right away, and whether that depends on `status`, is **UNVERIFIED**. Harbor therefore:

1. Creates every transaction with `status:"completed"` and `transaction_date` = the **demo clock's** UTC date (`YYYY-MM-DD`). The client supplies the date, so it can follow the replayed storm.
2. Reads the account balance before and after (`GET /accounts/{id}`) and checks the change. If the balance doesn't move within 2 s, the Move becomes `failed` with `error.code="nessie_balance_not_applied"`. **Test this in hour 1 with a real key.** If Nessie needs a status change, also send `PUT /transfers/{id} {"status":"completed"}`.
3. Keeps Harbor's own Move lifecycle (`proposed → scheduled → executing → pending_settlement → done`). Nessie's `status` is just a mirror.

Whether Nessie rejects an overdraft is UNVERIFIED (`balance` has `minimum: 0`). The rules engine must never plan a move bigger than the Nessie balance it last read.

### ATMs and branches: what the data really covers

- `GET /atms` returns **13 ATMs, all in Arlington, VA** (around 38.87–38.90, -77.11–-77.15). It **ignores `lat`, `lng`, `rad` and `page`**: a Tampa search with `rad=50` returns the same 13. The old paging wrapper is gone, and the response is a plain array.
- ATM shape: `{"_id","name","language_list":[...],"geocode":{"lat","lng"},"hours":["24 hours a day, 7 days a week"],"accessibility":bool,"amount_left":int}`. **`amount_left`**, the cash left in the machine, is a field worth showing off.
- `GET /branches` returns **207 branches, all in MD (109), VA (79) and DC (19)**, with `phone_number`, `hours[]`, `notes[]` (for example "Safe Deposit Box", "Branch Drive-Up", "ATM Available", "Open on Saturday") and an address but **no geocode**.
- Consequences:
  - For a Florida storm (Milton or Ian), Nessie has **no ATMs or branches near the user**. Harbor needs its own ATM source for real Florida locations. OpenStreetMap Overpass with `amenity=atm` is one option (UNVERIFIED for coverage and licence wording). Show Nessie's schema and fields, and label each ATM's source honestly. Never invent "Capital One ATM" addresses.
  - **Standout option: add a second, "Nessie-native" demo storm in the DC area**, with the user at ZIP 22207, Arlington, which is a real Nessie branch ZIP. Isabel 2003, Irene 2011 and Sandy 2012 all affected MD, VA and DC. There, every ATM and branch Harbor shows is real Nessie data. Whether NHC GIS cone archives exist for those storms is UNVERIFIED (the storms area must check). Branch addresses have to be geocoded once and cached, for example with the US Census Geocoder (UNVERIFIED).
- ATMs and branches don't change, so fetch them once at startup and cache them in memory.

### Data deletion and demo reset

There is no bulk `/data` delete, no customer DELETE, and no way to set a balance. **Demo reset** (`POST /demo/reset`) therefore:

1. Keeps the Nessie customer.
2. Runs `DELETE /accounts/{id}` on each Harbor account.
3. Recreates the accounts with their starting balances through `POST /customers/{id}/accounts`.
4. Lists the accounts again to pick up the new IDs, and stores them.

That is 3 deletes, 3 creates and 1 list, about 2 s. This is faster and safer than reversing transactions one by one. Whether DELETE on an account also removes its transactions is UNVERIFIED and doesn't matter, because Harbor reads only the accounts it owns.

### `NessieClient` design (`harbor/bank/nessie.py`)

- Built on `httpx.AsyncClient(base_url=NESSIE_BASE_URL, timeout=httpx.Timeout(8.0, connect=4.0))`. Adds `params={"key": os.environ["NESSIE_API_KEY"]}` to every call and never logs the URL with its query string. Logs are redacted, because the key travels in the URL.
- Methods:
  - Customers and accounts: `create_customer`, `get_customer`, `list_accounts(customer_id)`, `get_account`, `create_account`, `delete_account`.
  - Money: `transfer(from_id, to_id, dollars, date, tag, memo)`, `withdraw(account_id, dollars, date, tag, memo)`, `deposit(account_id, dollars, date, tag, memo)`, `purchase(account_id, merchant_id, dollars, date, tag, memo)`.
  - Bills: `list_bills(customer_id)`, `update_bill(id, **fields)`, `create_bill`.
  - Reference data: `list_atms()`, `list_branches()`.
  - Lookup: `find_by_tag(account_id, kind, tag)`.
- **Retries**:
  - GETs retry on timeouts, `502`, `503`, `504` and connection errors, up to 3 tries with jittered backoff (0.3 s, 1 s, 2.5 s).
  - A `404` with an expected "none found" string becomes `[]`.
  - A `502` *without* a key configured raises `NessieConfigError` immediately.
- **Idempotency.** Nessie has no idempotency keys, and POST may not return an ID. So every write carries a tag in `description`, `"[harbor:{move_id}:{attempt}] Evacuation fund, savings to checking"`, and the Move records `nessie_request_tag` *before* the POST.
  - A POST is **never retried blindly**. On a timeout, 5xx or unclear response, call `find_by_tag`: list `/accounts/{id}/transfers?type=payer` (or `/withdrawals` or `/deposits`) and look for the tag.
  - Found: record its `_id` as `nessie_transfer_id` and treat the write as done.
  - Not found after 2 lookups spaced 1 s apart: increment `attempt` and POST again.
  - After a 201, always look the object up by tag to get its ID.
- **Concurrency.** One `asyncio.Lock` per Nessie account, so balance-before/after checks never interleave. Moves run one at a time in a single executor task driven by the demo clock.
- **Errors.** Raise typed exceptions (`NessieUnavailable`, `NessieNotFound`, `NessieRejected`, `NessieConfigError`). The executor maps them to a Move `error` of `{code, message, retryable}`. While Nessie is unavailable, scheduled moves stay `scheduled` and are retried every 30 s on the real clock, and an Event `move_failed` with `retryable:true` drives the UI's "bank unreachable" banner.
- **`NESSIE_MODE=live|fake`.** `FakeNessie` is an in-memory version with the same interface. It is used in tests and as a **fallback for judging**, given the 502s and timeouts seen. `/health` reports `"nessie": "ok" | "degraded" | "fake"`.

### Mapping Harbor Moves to Nessie calls

| Move kind | Nessie call(s) | Notes |
|---|---|---|
| `transfer` | `POST /accounts/{savings}/transfers` `{medium:"balance", payee_id: checking, amount: ceil$, transaction_date: demo_date, status:"completed", description: tag}` | Verify both balances moved. |
| `withdraw_cash` | `POST /accounts/{checking}/withdrawals` `{medium:"balance", amount: round_up_20$, ...}` | Pair it with the recommended ATM (outside the cone, on the route, `amount_left` above the amount). |
| `sell_etf` | At sale: **no Nessie call**. The value sits in Harbor's `brokerage_cash` with status `pending_settlement`. At `expected_available_at` (T+1 on the demo clock): `POST /accounts/{settlement}/deposits` then a `transfer` to checking, or a direct deposit into checking. | Recommended: a 3rd Nessie account, `Savings` nicknamed "Brokerage Settlement (Harbor)", so judges *see* the settled money arrive and then move. The Harbor DB stays authoritative for holdings and lots. |
| `restore_transfer` | `POST /accounts/{checking}/transfers` `payee_id: savings`, `amount: floor$` of the cash not spent | Unspent cash: user-reported, or `withdrawn − purchases logged`. |
| `rebuy_etf` | `POST /accounts/{checking}/purchases` with `merchant_id` = a seeded merchant "Harbor Brokerage (simulated)" | The purchase POST body is UNVERIFIED (`merchant_id, medium, purchase_date, amount, status, description` in the classic version). Fallback: a withdrawal tagged as a purchase. |

### Seeding the demo customer (`python -m harbor.seed`, idempotent)

1. `GET /customers`. If no customer has `last_name == "Lopez (Harbor demo)"`, create Maria Lopez with a fictional Tampa address, or Arlington 22207 for the DC storm.
2. Ensure these accounts exist:
   - Checking "Everyday", $420
   - Savings "Emergency fund", $2,500
   - Savings "Brokerage Settlement (Harbor)", $0
   - optionally a Credit Card "Backup card", $0, used only to *display* available credit and never auto-drawn
3. Seed bills on checking: Rent $1,450 (`recurring`, day 1), Electric $140 (`recurring`, day 12), Car insurance $96 (`pending`, dated inside the storm window).
4. Seed the merchant "Harbor Brokerage (simulated)" plus a few evacuation merchants (hotel, gas, grocery) with geocodes along the route, so post-storm spending can be logged as purchases.
5. Save every Nessie ID in Harbor's DB (`users.nessie_customer_id`, `accounts.nessie_id`).

### Ideas to stand out for "Best Use of Nessie"

- **ATM picker:** rank ATMs by outside-the-cone, then on the evacuation route, then `amount_left ≥ withdrawal`, then accessibility and language match from `language_list` against the user's language. Show "this ATM reported $X left."
- **Branch plan:** the nearest branch outside the cone that is "Open on Saturday" and has "Safe Deposit Box". Prompt: "move documents and valuables before landfall"; a phone number appears in the plan.
- **Bill shield:** read `/customers/{id}/bills`. Any bill whose `upcoming_payment_date` falls in the shelter window is flagged, and on approval Harbor `PUT`s its `payment_date` to after recovery. This simulates a hardship deferral, and the AI explains it. Each bill change is a separate Move that needs its own approval.
- **Evacuation spend log:** record hotel and gas spending as Nessie purchases at seeded route merchants, so the `recover` screen can compute "unspent = withdrawn − spent" and size `restore_transfer` correctly.
- **Bank-down mode:** at `shelter`, Harbor stops all Nessie writes and shows the last balances it read, with timestamps, which mirrors real post-landfall outages.
- Avoid Nessie loans: offering credit to people in a disaster works against the "responsible" theme. At most, show the credit card's available credit as information.

### State Harbor must keep itself

- Exact cents and the rounding difference per Move.
- The Move/Plan lifecycle and the cancel deadlines.
- The idempotency tags and attempts.
- The ETF holdings, lots, cost basis and `brokerage_cash` settlement queue (T+1).
- The demo clock.
- ATM and branch geocodes plus the in-cone and on-route flags.
- Non-Nessie ATM data.
- Bill-deferral decisions.
- The last balances read, for offline display.
- The mapping between Nessie IDs and Harbor IDs, since Nessie IDs change on every demo reset.

### Check in the first hour with a real key (still UNVERIFIED)

1. What a POST actually returns (a string or `objectCreated`).
2. Whether a POSTed transfer, withdrawal or deposit changes `balance` right away, and whether that depends on `status`.
3. Whether a float `amount` is rounded or rejected.
4. Whether an overdraft is rejected.
5. The purchase POST body.
6. Whether `DELETE /accounts/{id}` also removes its transactions.
7. Any throttling once you send around 10 requests a second.


---

## ETF portfolio, plan engine and responsible AI

### 1. Market data: where real ETF prices come from

| Source | Free terms (checked Oct 2026) | Use in Harbor |
|---|---|---|
| **Alpaca Market Data** (primary) | Free "Basic" plan: **200 historical calls/min**, equities on the **IEX feed only**, history back to 2016. Historical requests are limited in the latest 15 minutes, so ask for data at least 15 min old. Websocket limit is 30 symbols. Auth headers are `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`. Base host `https://data.alpaca.markets/v2/...`. Source: https://docs.alpaca.markets/docs/about-market-data-api | Daily bars for the demo replay and latest prices for the portfolio page. Python SDK: `alpaca-py` (`StockHistoricalDataClient`, `StockBarsRequest`, `feed=DataFeed.IEX`). Exact bars path and params (`/v2/stocks/bars?symbols=&timeframe=1Day&start=&feed=iex&adjustment=all`): **UNVERIFIED**, check the API reference. |
| **yfinance** 1.7.0 (released 2026-08-26) | No key. Unofficial Yahoo scraper. Its PyPI page says the Yahoo API "is intended for personal use only". Yahoo returns HTTP 429, which yfinance raises as `YFRateLimitError`. These blocks were common in 2025 (issues #2422, #2480), sometimes during the cookie/crumb handshake. | Fallback only. Never call it on the request path. |
| **Twelve Data** Basic | **8 credits/min, 800/day**, reset at 00:00 UTC (https://support.twelvedata.com/en/articles/5194820-api-credits-limits) | Second fallback. Needs a key. |
| **Finnhub** free | 60 calls/min (third-party claim). One report says a free key gets "You don't have access to this resource" on candles. **UNVERIFIED** for ETF candles. | Skip. |
| **Stooq** | Since early 2026 the `q/d/l` CSV endpoint returns an HTML page asking for an API key, obtained through a CAPTCHA, and it has a daily hit limit (pandas-datareader issue #1012). | Avoid. Fetching a key means solving a CAPTCHA. |

**Rules for prices:**
- Never price on the request path. A small `price_snapshots(symbol, as_of, close_cents, source)` table is filled by a background job, and the API reads only from the DB. The `Holding` response should carry `price_as_of` and `price_source` so the UI can show "priced 15:45 ET via Alpaca IEX".
- **Demo replay:** fetch the real daily closes for the storm's actual dates once (Milton: Sep 25 to Oct 31, 2024) and commit them as fixture JSON (`fixtures/prices/milton-2024.json`). The demo then never depends on a network call, and the prices are still real. If the demo clock shifts the storm into 2026 dates (API.md does this), map each demo day to its historical trading day by offset.
- IEX volume is thin for small active ETFs, so the "latest trade" can be hours old. Use the daily close plus the bar time. Liquidity on IEX for TBUX, TOTR etc.: **UNVERIFIED**.

### 2. Sample portfolio (T. Rowe Price ETFs)

The tickers come from T. Rowe Price's ETF page (https://www.troweprice.com/financial-intermediary/us/en/investments/etfs.html). It lists, among others: TCAF (Capital Appreciation Equity, large blend, about 0.31%), TSPA (U.S. Equity Research*), TCHP (Blue Chip Growth*), TGRW (Growth Stock*), TVAL (Value), TEQI (Equity Income*), TDVG (Dividend Growth*), TOUS (International Equity), TOTR (Total Return bond), TAGG (QM U.S. Bond), **TBUX (Ultra Short-Term Bond)**, TCAL (Premium Income) and TKNZ (Active Crypto ETF, *not* registered under the '40 Act). Funds marked * publish a daily proxy portfolio instead of their full holdings.

Suggested starter portfolio (about $8,000):

| Ticker | Weight | Role |
|---|---|---|
| TCAF | 35% | Core equity |
| TSPA | 20% | Core equity |
| TOUS | 15% | International |
| TOTR | 20% | Bonds |
| TBUX | 10% | Cash-like "storm sleeve", sold first because it moves the least |

Label it in the UI as "sample portfolio for the demo, not a recommendation".

- **Ian 2022 replay:** TCAF only launched in 2023. Use tickers that already existed in Sept 2022 (TCHP, TEQI, TDVG from 2020, or VTI/BND). Other launch dates: **UNVERIFIED**.
- **Storage:**
  - Store lots, not just holdings: `lots(id, user_id, symbol, shares_micro BIGINT, cost_basis_cents, acquired_at)`.
  - Shares are integer millionths of a share, so there are no floats, just as money is integer cents.
  - `proceeds_cents = floor(shares_micro * price_cents / 1_000_000)`.
  - Seed lots with mixed acquired dates and bases (some long-term gains, one short-term gain, one loss) so the lot picker visibly does something.

### 3. Settlement, calendars and ACH timing

- **T+1:** the SEC moved standard settlement from T+2 to T+1, with a compliance date of **May 28, 2024** (https://www.sec.gov/newsroom/press-releases/2023-29). ETFs settle like stocks. The Ian 2022 replay happened under T+2, so the replay applies **today's rules (T+1)** and says so on screen.
- **Two calendars.** Python can't treat these as one.
  - *Trading days:* weekdays minus NYSE holidays.
    - 2026: Jan 1, Jan 19, Feb 16, **Apr 3 (Good Friday)**, May 25, Jun 19, Jul 3, Sep 7, Nov 26, Dec 25.
    - Early closes at 1:00 pm ET: Nov 27 and Dec 24, 2026.
    - 2027: Jan 1, Jan 18, Feb 15, Mar 26, May 31, Jun 18, Jul 5, Sep 6, Nov 25, Dec 24.
    - Source: https://www.nyse.com/markets/hours-calendars
  - *Settlement days:* weekdays minus Federal Reserve bank holidays. **Columbus Day and Veterans Day are trading days but not settlement days** (FINRA trade-date/settlement-date notices, e.g. https://www.finra.org/rules-guidance/notices/02-60). Good Friday is the reverse: no trading, but settlement still happens (**UNVERIFIED** for 2026, check the DTCC calendar).
  - This matters right in hurricane season:
    - A sale on Fri **Oct 9, 2026** settles **Tue Oct 13**, not Mon Oct 12 (Columbus Day).
    - A sale on Tue Nov 10, 2026 settles Thu Nov 12 (Veterans Day is Nov 11).
- **Implementation:** hard-code both holiday tables for 2022 to 2027 in `harbor/calendar.py`. That is deterministic and needs no dependency. Optionally cross-check with `exchange_calendars` (XNYS).
  - Compute in `America/New_York` with `zoneinfo`, store UTC.
  - **Windows quirk:** `zoneinfo` needs `pip install tzdata` on Windows.
  - Orders run only in the regular session (09:30 to 16:00 ET, or 13:00 on early-close days). Schedule sells for 10:00 ET to avoid the opening auction, and nothing after 15:45 ET.
- **Emergency closures:** NYSE closed for two days during Sandy (Oct 29 to 30, 2012). If execution fails because the market is closed, the move goes to `failed`, the engine re-plans, and the shortfall shifts to savings and cash.
- **ACH assumption:** this is a setting, `SETTLED_TO_CHECKING_LAG`.
  - **Demo default: 0.** The brokerage is treated as the same bank, so on the settlement date at 09:00 ET a book transfer moves the money from `brokerage_cash` to checking.
  - **"Realistic" mode: +1 settlement day** for standard ACH. A Nacha rule effective 2026-09-18 requires non-same-day ACH credits to be available by 09:00 RDFI local time on the settlement date (secondary source; verify on nacha.org).
  - Same Day ACH windows of 1:00, 5:00 and 6:00 pm ET: **UNVERIFIED**, not needed for the MVP.
  - Show the assumption in the UI ("assumes your brokerage is at the same bank").

### 4. Tax lots and the wash-sale rule

- **Lot selection:** this needs specific identification at the time of the sale, otherwise FIFO applies (Treas. Reg. §1.1012-1(c), IRS Pub. 550). The engine records which lots each move sells.
  - Holding period over 1 year means long-term; 1 year or less means short-term.
- **Lot ranking** (deterministic). The "cost" of selling $1 from a lot is `gain_per_dollar × assumed_rate`. The rates are illustrative, set in config and labelled as estimates: 15% long-term, 24% short-term. The order:
  1. **TBUX lots first.** Cash-like, the gain is near zero, and selling them barely changes the allocation.
  2. Then the lowest tax cost per dollar. That means long-term lots with the smallest gain, then short-term with the smallest gain.
  3. **Loss lots** depend on the rebuy setting:
     - Rebuy on: loss lots go *last*. Rebuying within 30 days washes the loss.
     - Rebuy off: loss lots go *first*. The realised loss offsets other gains.
  4. Ties: sell from the holding most overweight against its target.
- **Wash sale** (IRS Pub. 550, https://www.irs.gov/publications/p550):
  - If you sell at a **loss** and buy substantially identical securities within **30 days before or after** the sale, the loss is disallowed. That is a 61-day window in **calendar days**, including weekends.
  - The disallowed loss is added to the new shares' basis, so it is deferred, not lost. The holding period carries over.
  - If the repurchase is in an IRA, the loss is lost for good.
  - Gain sales are not affected at all.
  - "Substantially identical" is a facts-and-circumstances test. The IRS has not said whether two ETFs tracking similar indexes count, so Harbor must not suggest swapping to a "lookalike" ETF.
  - The 30 days *before* the sale count too, so a dividend reinvestment in the prior 30 days can wash a storm sale.
- **Rebuy behaviour:**
  - For each lot sold at a loss, compute `wash_window_end = sale_date + 30 days`. In recovery, offer two choices: "rebuy now (loss deferred into new basis)" or "rebuy on or after {date}".
  - Default: rebuy now for gain lots; for loss lots, ask the user.
  - This fills `plan.warnings` and `tax_note`.

### 5. Plan engine: deterministic algorithm (`harbor/engine/plan.py`, pure functions, unit-tested)

**Inputs:** user, household, evacuation, settings, account balances, lots, prices, storm status, `now` (demo clock).

**5.1 Evacuation budget** (integer cents; each line keeps its `source` for the UI):

| Line | How it is calculated |
|---|---|
| **Lodging** | `rooms = ceil(people/4)`, then `rooms × nights × nightly_rate`. The user value wins; otherwise use the GSA per-diem lodging rate. GSA's **FY2026 standard rate is $110 lodging and $68 M&IE**, unchanged from FY2025 (FTR Bulletin 26-01, https://www.govinfo.gov/content/pkg/FR-2025-08-19/html/2025-15771.htm). **Today (2026-10-16) is in FY2027**, and FY2027 rates are **UNVERIFIED**. Keep the rate in config. GSA's per-diem-by-ZIP API (`https://api.gsa.gov/travel/perdiem/v2/rates/zip/{zip}/year/{year}`, api.data.gov key) is **UNVERIFIED**. |
| **Food** | `(adults + 0.5×children) × days × M&IE`, with the first and last day at 75% (the federal travel rule). |
| **Fuel** | `round_trip_miles / mpg × price_per_gal × 1.25`. The 1.25 congestion factor is an assumption; mpg defaults to 25. Gas price: the EIA API v2 weekly retail series (route `petroleum/pri/gnd`, free key passed as the `api_key` query param, updated weekly on Monday; the state `duoarea` code is **UNVERIFIED**). Fallback: a configured constant. AAA state averages (gasprices.aaa.com) have no public API, so cite AAA for display only. If there is no car, add a "transport" line with a placeholder value, and point to county evacuation buses. |
| **Pets** | `pets × nights × $25` (assumed fee or boarding cost, **UNVERIFIED**). |
| **Buffer** | `max(15% of subtotal, $100)`. |

**5.2 Timing**
- `cash_needed_by = earliest_ts_winds_eta − evac_lead_hours`. The default of 18h matches the API.md example.
- Physical cash (`withdraw_cash`): `min(budget, $300 + $100 × people)`. This is a heuristic; Ready.gov advises keeping cash on hand. It is scheduled no later than `cash_needed_by`, at an ATM outside the cone.

**5.3 Waterfall** (amounts above protected floors only):
```
need      = budget_total
from_chk  = min(need, checking − checking_floor)          # floor e.g. $50
need     -= from_chk
from_sav  = min(need, savings − savings_floor)            # floor default $0, user-settable
need     -= from_sav
etf_target = min(ceil(need × 1.03), settings.max_etf_sell_cents,
                 0.25 × portfolio_value)                  # 3% price-drop haircut, hard caps
if 0 < etf_target < 2500: etf_target = 2500 if allowed else 0   # $25 minimum sale
shortfall = need − etf_target   (if >0: show "Harbor can't cover $X", plus free resources: 211, Red Cross shelters, FEMA)
```
Then pick lots (section 4) until the proceeds reach `etf_target`. Sell whole lots where possible; split the last lot in micro-shares.

**5.4 Sell timing** (working back from the deadline):
```
exec_at = next_session_time(max(now, approved_at + cancel_window))   # 10:00 ET or ASAP within session
avail_at = settle_date(exec_at.date) @ 09:00 ET + SETTLED_TO_CHECKING_LAG
latest_trade_day = max D in trading_days where settle_date(D)@09:00 ET + lag ≤ cash_needed_by
```
- If `exec_at.date > latest_trade_day`, mark the move `arrives_late` and leave it **out** of the default plan. The amount moves to the shortfall and gets a larger cash withdrawal. The UI offers "sell anyway for post-storm costs".
- The plan also exposes `latest_safe_approval_at` so the UI can show a countdown ("approve by Wed 15:45 ET so it settles in time").

**5.5 Cancel windows and approval**
- `scheduled_for ≥ approved_at + cancel_window_minutes`. `cancel_deadline = scheduled_for − 5 min` (execution lock).
- *Contract note:* API.md's example puts `cancel_deadline` two hours before `scheduled_for`. Align this with the frontend.
- **Demo quirk:** at 1 s = 1 storm hour, a 120-minute window lasts 2 seconds. Auto-pause the demo clock while a plan is `awaiting_approval`, and count cancel windows in real time while the demo runs.
- `auto_approve` applies only to transfers between the user's own accounts. **ETF sells always need an explicit tap.**

**5.6 Re-planning**
- Re-run on every advisory. The plan versions if the budget changes by more than 10% or a move is added or removed. A new version needs fresh approval; otherwise only the times update.
- Re-price at execution. If the price dropped by more than 5% since approval, pause and ask again.

**5.7 Recovery** (triggered by `risk_level = recover`)
1. Keep a recovery buffer in checking (default: 7 days of M&IE for the household). Repairs and delays in aid make cash scarce after the storm.
2. `restore_transfer` puts back into savings `min(amount taken, what remains above the buffer)`.
3. `rebuy_etf` happens only if the user opted in, and they **re-confirm** because prices changed. The amount is `min(etf_proceeds, what remains after step 2)`. Buy at the next session at the current price. Apply the wash-sale choices from section 4.

The plan reverses in the opposite order of the waterfall. Every move links back to the move it reverses.

### 6. AI layer (Claude API, Python `anthropic` SDK)

**Model:** `claude-opus-5-5`. Verified at https://platform.claude.com/docs/en/about-claude/models/overview: $4/$20 per MTok input/output, 1M context, retirement not before 2027-09-22.
- Notes for Opus 5.5:
  - Thinking is always on and can't be disabled. Use `output_config={"effort": "low"}` for speed; the default is `medium`.
  - `temperature` is rejected.
  - Assistant prefill is rejected.
  - Forced `tool_choice` is rejected.
- `HARBOR_MODEL` env override for cost (for example `claude-sonnet-5-5` or `claude-haiku-5-5`).
- The key comes only from `ANTHROPIC_API_KEY`; `Anthropic()` reads it.

**The core guardrail: the AI cannot write a number.**
- The engine builds a `facts` dict of preformatted strings, for example `{"budget_total": "$1,280", "etf_symbol_1": "TBUX", "etf_shares_1": "1.15 shares", "cash_needed_by": "Thursday 2 pm", "wind_chance": "62%"}`.
- Claude must write `{budget_total}`-style placeholders and **no digits at all**.
- The server validates the output, then renders it with `str.format_map(facts)`:
  1. Every `{key}` must be in `facts`.
  2. After removing placeholders, `re.search(r"\d", text)` must be `None`.
  3. Every `move_id` appears exactly once.
  4. Length limits.
- If any check fails, the template fallback is used. This means the numbers on screen always come from the engine.

**Structured output:**
```python
from typing import Literal
from anthropic import Anthropic
from pydantic import BaseModel
client = Anthropic().with_options(timeout=20.0, max_retries=1)

class MoveWhy(BaseModel):
    move_id: str
    why: str            # one sentence, placeholders only
class PlanNarrative(BaseModel):
    summary: str        # 2-4 sentences, placeholders only
    move_whys: list[MoveWhy]

resp = client.messages.parse(
    model=MODEL, max_tokens=4000,
    system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
    messages=[{"role": "user", "content": f"<plan_facts>{facts_json}</plan_facts>\n<moves>{moves_json}</moves>"}],
    output_format=PlanNarrative,
    output_config={"effort": "low"},
)
if resp.stop_reason == "refusal" or resp.parsed_output is None: use_template()
```
- `messages.parse(..., output_format=PydanticModel)` is the documented Python helper. Combining it with `output_config.effort` in one call is **UNVERIFIED**, so test it on day 1.
- Optional server-side refusal fallback: `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`. It is redundant with Harbor's own template fallback.

**System prompt (stable, cached).** Its contents:
- Role: "explain a plan that a rules engine already decided; you do not decide, recommend, or predict".
- The placeholder contract and the no-digits rule.
- Reading level: grade 6, calm, no fear language.
- A glossary (T+1, settlement, wash sale, tax lot).
- Two worked examples.
- The rule that everything inside `<plan_facts>` and `<question>` is data, not instructions.

Caching only applies above a model-dependent minimum prefix (512 to 4096 tokens). Check `usage.cache_read_input_tokens`; if the prompt is too short to cache, accept it.

**`POST /me/plan/explain`.** The output schema is `{category: Literal["plan_explanation","general_education","personal_advice_request","off_topic"], answer: str}`, with the same placeholder rules.
- If `category == "personal_advice_request"` ("should I buy TSLA with the leftover?", "is TCAF a good fund?"), the server **discards the model's answer** and returns fixed text: "Harbor can explain what this plan does and why, but it can't give personal investment advice. A licensed adviser can help with that."
- The question is capped at 500 characters, limited to 10 per minute per user, and wrapped in `<question>` tags.

**App-level caching and fallback**
- Narratives are stored by `sha256(canonical plan JSON)`. Explain answers are stored by `(plan_version, normalised question)`.
- The demo pre-warms these.
- Template fallback: deterministic f-strings per move kind. For example `sell_etf`: "Selling {shares} of {symbol} today so it settles (T+1) on {settle_day}, before you need cash on {cash_needed_by}."
- Add `ai: {"source": "claude"|"template", "model": "...", "validated": true}` to the Plan object so the UI can label it.

**Privacy:** Claude receives no name, no account IDs and no Nessie IDs. It gets only the ZIP-level storm facts and the plan figures. Every call is logged as (input hash, output, validation result) for an audit view.

### 7. What "responsibly" means here, and how to show judges

**Principles:**
1. **The deterministic engine decides and the AI only explains.** The engine is unit-tested; the AI explains with placeholders and can't write a digit.
2. **The human approves.** Every ETF sell is approved, can be cancelled within its window, and is re-confirmed for rebuys.
3. **Sell the minimum.** Cash-like sleeve first, tax-aware lots, caps (25% of the portfolio, `max_etf_sell_cents`).
4. **Honest about timing.** Settlement calendars are shown. "Arrives late" sales are excluded, not hidden.
5. **Fail safe.** Stale prices or forecasts mean no new moves, and the plan says why.
6. **No advice, no upsell.** No lending products, fixed disclaimers rendered by the frontend (not the AI): "Prototype. Simulated portfolio. Not investment, tax or legal advice. Tax figures are estimates."
7. **Plain language and a "show the math" toggle** on every line.

**Demo script (90 seconds):**
1. Plan card with "Decided by rules / Explained by AI" badges.
2. Ask "Why sell TBUX and not TCAF?" and get a grounded answer.
3. Ask "Should I put the leftover in Tesla?" and get the fixed refusal.
4. Flip the "AI offline" toggle: same numbers, template text.
5. Show the failing unit test where a forged "$9,999" from a mocked LLM is rejected.
6. Cancel a move inside its window.
7. Point at the Columbus Day settlement shift on the timeline.

### 8. Tokenization: skip it

T. Rowe Price has a tokenization-adjacent product (TKNZ, a non-'40-Act Active Crypto ETF). Building anything on-chain in 48 hours adds custody and regulatory surface and does not help protect evacuees.

Use it as one **future-work** line on the pitch slide instead: tokenized fund shares or deposits that settle 24/7 would remove the T+1 and weekend/holiday gap. Harbor could then sell on a Saturday for a Sunday landfall, which today's calendar logic has to plan around.


---

## Website: Next.js frontend and how it talks to the FastAPI backend

### 1. Repo layout (one repo, two folders)

With two people and 48 hours, use one repo. Each person owns one folder, so merge conflicts are rare, and the API contract sits in the same commit as the code that implements it.

```
harbor/
  backend/            # user: FastAPI, rules engine, Nessie client, scheduler
    app/main.py
    scripts/dump_openapi.py   # writes ../docs/openapi.json
  web/                # teammate: Next.js App Router
    src/app/...       # screens
    src/api/schema.d.ts       # generated, committed
    src/api/client.ts         # openapi-fetch + X-User-Id middleware
    src/mocks/        # MSW handlers + fixtures
  docs/
    API.md            # human contract (exists)
    openapi.json      # machine contract, regenerated by backend owner on every API change
```

Rule: if a commit changes a Pydantic model or a route, it also regenerates `docs/openapi.json`. The frontend generates types from that file, not from a running server, so the teammate never needs the backend running just to compile.

On Vercel, set the project's Root Directory to `web`. On Railway or Render, set the root or working directory to `backend`.

### 2. Local development

| Process | Command | Port |
|---|---|---|
| Backend | `uvicorn app.main:app --reload --port 8000` (one worker; see SSE below) | 8000 |
| Web | `npm run dev` | 3000 |

**Call the backend directly with CORS. Don't use a Next.js rewrite proxy.** Next.js rewrites can proxy to an external URL (`source: '/api/:path*', destination: 'http://localhost:8000/api/:path*'`), and that would remove CORS entirely. The risk is SSE: there are community reports that the rewrites proxy buffers streamed responses, and the Next.js docs say nothing on streaming through rewrites (UNVERIFIED either way; one third-party report, no official issue found). A buffered event stream would break the live demo, so it isn't worth the risk.

`web/.env.local` (gitignored):
```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_API_MOCKING=0        # 1 = MSW mocks, no backend needed
```
`NEXT_PUBLIC_*` values are inlined into the browser bundle at build time. If you change one on Vercel, you must redeploy. Never put a secret in a `NEXT_PUBLIC_` variable. The frontend has no secrets at all: Nessie and Anthropic keys live only in the backend's env.

FastAPI CORS (https://fastapi.tiangolo.com/tutorial/cors/):
```python
origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,                                   # localhost + prod Vercel URL
    allow_origin_regex=r"https://harbor-[a-z0-9-]+\.vercel\.app",  # Vercel preview deploys
    allow_methods=["*"],
    allow_headers=["X-User-Id", "Content-Type"],
    allow_credentials=False,   # we use a header, not cookies
    max_age=3600,
)
```
Quirks:
- `X-User-Id` is a custom header, so every request triggers a preflight `OPTIONS` request. That's fine. `max_age` caches the preflight; FastAPI's default is 600 s.
- If you ever set `allow_credentials=True`, none of `allow_origins`, `allow_methods` or `allow_headers` may be `"*"`.
- `allow_headers` defaults to `[]`. If `X-User-Id` is missing from the list, every call fails in the browser while curl still works. This is the classic first-hour bug.

### 3. Typed TypeScript client from FastAPI's OpenAPI schema

Use **openapi-typescript 7.13.0** (latest on npm) plus **openapi-fetch**: zero runtime codegen and a small fetch wrapper (https://openapi-ts.dev/openapi-fetch/).

```bash
cd web
npm i openapi-fetch @tanstack/react-query
npm i -D openapi-typescript typescript
# package.json script:
"gen:api": "openapi-typescript ../docs/openapi.json -o src/api/schema.d.ts"
```
Backend side (`scripts/dump_openapi.py`): `json.dump(app.openapi(), open("../docs/openapi.json","w"), indent=2)`.

For good TypeScript names:
- Give FastAPI `generate_unique_id_function=lambda r: r.name`, so operationIds are `get_plan`, not `get_plan_api_v1_me_plan_get`.
- Give every route a `response_model`.
- Declare error responses (`responses={404: {"model": ErrorEnvelope}}`), or the TypeScript `error` branch is `unknown`.

```ts
// src/api/client.ts
import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";
export const api = createClient<paths>({ baseUrl: process.env.NEXT_PUBLIC_API_URL });
const auth: Middleware = { onRequest({ request }) {
  const id = localStorage.getItem("harbor_user_id");
  if (id) request.headers.set("X-User-Id", id);
  return request;
}};
api.use(auth);
// usage: const { data, error } = await api.GET("/me/plan");
```
Wrap calls in TanStack Query hooks (`usePlan`, `useStorm`...) so the SSE handler can invalidate them. The TanStack version is UNVERIFIED; v5 API assumed.

Alternative: orval can generate React Query hooks and MSW mocks from the same schema. It's more automation but also more config to debug. It wasn't checked for this report.

### 4. Mock data before the backend exists

Use **MSW 3.0.3** (current npm `latest`) in the browser, switched on by `NEXT_PUBLIC_API_MOCKING=1`.
- Fixtures go in `web/src/mocks/fixtures/*.json`. Copy them straight from the API.md examples (User, Plan with 3 to 4 moves, Storm status, 6 sensors, 5 ATMs, 20 events, and a small cone GeoJSON).
- SSE is supported: `import { sse } from 'msw/sse'` and `client.send({ data: ... })` (https://mswjs.io/docs/sse/). It works only in the browser, which is all we need. A mock stream can push a scripted `risk_changed` → `plan_created` → `move_done` sequence every few seconds, so the teammate can build the live dashboard on day 1.
- Setup is `npx msw init public/`, then start the worker in a client-only provider before rendering. The v2 handler syntax (`http.get(url, () => HttpResponse.json(...))`) is assumed to carry over into v3: UNVERIFIED. Read https://mswjs.io/docs/migrations/2.x-to-3.x first.

Anti-drift: the backend has one pytest that loads each fixture into its Pydantic model. If the contract changes and a fixture no longer validates, CI or a local `pytest` catches it before the frontend breaks.

### 5. Live updates: SSE from FastAPI to EventSource

**Backend:** FastAPI ≥ **0.135.0** has built-in SSE, so `sse-starlette` isn't needed (https://fastapi.tiangolo.com/tutorial/server-sent-events/).
```python
from fastapi.sse import EventSourceResponse, ServerSentEvent

@app.get("/api/v1/me/events/stream", response_class=EventSourceResponse)
async def stream(user_id: str, last_event_id: Annotated[str | None, Header()] = None):
    async for evt in broker.subscribe(user_id, after=last_event_id):
        yield ServerSentEvent(data=evt, id=evt.id)   # data is JSON-encoded
```
FastAPI does three things for you here:
- It sends a `ping` comment every 15 s when the stream is idle.
- It sets `Cache-Control: no-cache` and `X-Accel-Buffering: no`.
- It hands you the `Last-Event-ID` header on reconnect, so you can replay events the client missed from the DB.

`broker` is an in-process dict of `asyncio.Queue`s per user. That means you must run **one uvicorn worker**. With several workers, events published in one process never reach a client connected to another.

**Contract problem: `EventSource` cannot send custom headers.** It can't send `X-User-Id`. The stream endpoint must take `?user_id=usr_7f3a` as a query parameter. Note this in API.md.

**Frontend hook:**
```ts
useEffect(() => {
  const es = new EventSource(`${API}/me/events/stream?user_id=${id}`);
  es.onmessage = (m) => { const e = JSON.parse(m.data); onEvent(e); };
  es.onerror = () => setLive(false);   // browser auto-reconnects
  es.onopen = () => setLive(true);
  return () => es.close();
}, [id]);
```
- Don't set the SSE `event:` field. Everything then arrives on `onmessage`, and the type is read from `data.type`. Named events need one `addEventListener` per type and are easy to miss.
- `onEvent` maps the type to the queries to refetch:

| Event type | Queries to refetch |
|---|---|
| `risk_changed`, `advisory_issued` | storm, me |
| `sensor_alert` | sensors |
| `plan_*`, `move_*` | plan, accounts, portfolio |
| every event | events |

- While `live` is false, turn on `refetchInterval: 10_000` as a polling fallback.

### 6. Map and charts

**Map: react-leaflet 5.0.0.** Its peer dependencies are React ^19 and Leaflet ^1.9. Next 16.4.2, the current `latest`, supports React 19.

- Leaflet touches `window`, so put the map in a `"use client"` file and load it with `dynamic(() => import("./StormMap"), { ssr: false })`. Per the Next docs, `ssr: false` errors if used in a Server Component (https://nextjs.org/docs/app/guides/lazy-loading).
- Layers:
  - The cone, as `<GeoJSON>` from `cone_geojson_url`, with a translucent white fill, plus the track `LineString` and forecast points.
  - The user's home, as a pulsing `CircleMarker`.
  - Sensors, as `CircleMarker`s coloured by `status` (normal / watch / warning).
  - ATMs, with "outside cone" ones visually emphasised.
- Use `CircleMarker` or `divIcon` instead of Leaflet's default `Marker`. Bundlers break the default icon image paths, a well-known quirk.
- Tiles: `https://tile.openstreetmap.org/{z}/{x}/{y}.png` is fine for a demo. The policy requires visible attribution, a valid Referer, and no prefetching or bulk download (https://operations.osmfoundation.org/policies/tiles/). Leave Leaflet's attribution control on.
- MapLibre is the alternative if you want vector styling. It's heavier, and Leaflet is enough here.

**Charts: Recharts 3.10.1** (React 19 OK), in a client component.
- `LineChart` of `pressure_mb` over `observed_at` from `/me/sensors/{id}/history?hours=24`. Add a `ReferenceLine` at the "fast-falling" threshold, so judges see why the risk level changed. That moment is the Sensors-track story.
- Gauges plot `water_level_ft` with a `ReferenceLine` at `flood_stage_ft`.

### 7. Screens and the endpoints each one calls

All data screens are client components, since the user id lives in `localStorage`.

| Route | Screen | Endpoints |
|---|---|---|
| `/` | Landing: problem statement and "Get started" / "Use demo household" | none, or `GET /health` |
| `/onboarding` | ZIP, household (adults/children/pets/car), evacuation nights, lodging cost, distance, auto-approve toggle | `POST /users` → store `id`; then `GET /me/accounts` and `GET /me/portfolio` to show "your bank + ETFs are connected" |
| `/dashboard` | Big risk-level banner; storm card (name, category, wind %, ETA); balances; portfolio; mini map; latest 5 events; "Live" dot | `GET /me`, `GET /me/storm`, `GET /me/accounts`, `GET /me/portfolio`, `GET /me/events?limit=5`, SSE stream |
| `/plan` | Budget lines; sources (checking / savings / ETF); move timeline with per-move `why`, `cancel_deadline` countdown and Cancel; tax note and warnings; Approve all / Cancel all | `GET /me/plan`, `POST /me/plan/approve`, `POST /me/plan/cancel`, `POST /me/plan/moves/{id}/cancel` |
| `/plan` (drawer) | "Ask why" chat, with suggested questions ("Why sell VTI and not BND?", "Why withdraw cash?") | `POST /me/plan/explain` |
| `/map` | Full map: cone, track, home, sensors, ATMs; side list of sensors with pressure chart on click | `GET /me/storm`, `GET /storms/{id}/cone.geojson`, `GET /me/sensors`, `GET /me/sensors/{id}/history`, `GET /me/atms` |
| `/atms` | List sorted by "outside cone, on route", hours, distance, "Open in Maps" link | `GET /me/atms?radius_miles=150` |
| `/activity` | Full feed, filter by type | `GET /me/events?limit=50`, SSE |
| `/history` | Past plans and restored outcomes | `GET /me/plans` |
| `/settings` | Edit ZIP/household, `max_etf_sell_cents`, `cancel_window_minutes` | `GET /me`, `PATCH /me` |
| `/demo` | Judge panel: pick storm, Start, Advance 6h / to next advisory, Pause/Resume, Reset; shows demo clock and `/health` status for Nessie and NHC | `GET /demo/storms`, `POST /demo/start`, `/advance`, `/pause`, `/resume`, `/reset`, `GET /demo/clock`, `GET /health` |

Make the risk level drive the dashboard layout, not just its colour:

| Level | What the dashboard shows |
|---|---|
| `clear` | Calm summary and balances |
| `monitor` | Storm card, map promoted |
| `prepare` | Plan approval call-to-action takes over the top |
| `act` | Move progress timeline |
| `shelter` | Cash-in-hand amount, nearest open ATMs, offline tips; no buttons that move money |
| `recover` | Restore progress |

### 8. Gaps and awkward spots in docs/API.md

1. **SSE auth.** `EventSource` can't send `X-User-Id`, so add `?user_id=` to `/me/events/stream`.
2. **Demo clock and cancel windows clash.** At `speed: 3600`, a 120-minute `cancel_window_minutes` lasts **2 real seconds**, so the judge can't cancel anything. Fix: in demo mode, the backend auto-pauses the clock when a plan reaches `awaiting_approval` and resumes on approve. Also default the demo to a slower speed, e.g. 600 (120 storm-minutes is about 12 s).
3. **Countdowns need the server's "now".** `Plan` has no `server_time`. Add `server_time` to every response, or an `X-Server-Time` response header with `expose_headers=["X-Server-Time"]` in CORS. The client then extrapolates demo time as `now + (Date.now() - fetchedAt) * speed / 1000`.
4. **Missing event types.**
   - `demo_reset`: the frontend must drop all cached data and possibly the user.
   - `plan_updated`: the AI summary may arrive after the plan is created.
   - `balance_changed`.
   - `clock_tick`, roughly every 1 to 5 s in demo mode, so the clock display doesn't need polling.
5. **`GET /me/plan` returns 404 when no plan exists.** That's normal state, not an error. Prefer `200 { "plan": null }`.
6. **Error shape.** FastAPI's default 422 and `HTTPException` bodies are `{"detail": ...}`, not the contract's `{"error": {code, message}}`. Add exception handlers for `HTTPException` and `RequestValidationError`. Also give onboarding field-level errors, e.g. `error.fields: {"zip": "Unknown ZIP"}`.
7. **ZIP preview.** Onboarding wants "33602 → Tampa, FL" before signup. Add `GET /zip/{zip}` → `{ city, state, lat, lon }`.
8. **Demo identity.** If `localStorage` is cleared, or the backend's SQLite is wiped on redeploy, the user id dangles. Add `POST /demo/persona` (returns a seeded "Maria" user) and have the client re-onboard on any `401` or `user_not_found`. The demo panel also needs to say which user the global clock affects.
9. **`/demo/advance`.** Support `{ "to": "next_advisory" }` and `{ "to_risk": "prepare" }` as well as `hours`. Judges want "skip to the interesting part". Also define the response shape of `/demo/storms`: `[{ id, name, year, landfall_at, description }]`.
10. **`cone_geojson_url` is origin-relative** (`/api/v1/...`), while `NEXT_PUBLIC_API_URL` already ends in `/api/v1`. Either return an absolute URL or document "prefix with the API origin". Similarly, `/health` sits outside `/api/v1`.
11. **Explain endpoint.** Add an optional `move_id` (context for "why this move?") and return `suggested_questions`. Make the timeout generous (10 to 20 s) and show a typing indicator. Streaming isn't needed for the demo.
12. **Portfolio freshness.** Add `priced_at` and `price_source` to `/me/portfolio`. The T. Rowe track judges will ask whether the prices are real.
13. **Pagination.** `/me/events` should take `before=<event_id>`.

### 9. Deployment for the demo (facts checked 2026-10-16)

**Frontend: Vercel Hobby.** It's free, for non-commercial use only (a hackathon qualifies), and functions get a 300 s maximum duration (https://vercel.com/docs/plans/hobby). That limit doesn't matter here, because the browser calls the backend directly.
- Set `NEXT_PUBLIC_API_URL=https://<backend-host>/api/v1` for Production and Preview, then redeploy.
- Add the Vercel URL to the backend's `CORS_ORIGINS`.

**Backend: needs an always-on process.** The scheduler that advances the demo clock, polls NHC and sensors, and executes scheduled moves runs inside the FastAPI process, and so does the SSE broker. Hosts that sleep the service kill all of it.

| Host | Free reality | Fit |
|---|---|---|
| **Railway** | Trial is a one-time $5 credit for up to 30 days, 1 GB RAM, shared vCPU; afterwards a Free plan with $1/month credit (https://docs.railway.com/reference/pricing/free-trial). Sleeping ("Serverless") is a per-service opt-in, so leave it off (https://docs.railway.com/reference/app-sleeping). | **Recommended primary.** Always-on for the whole hackathon well within $5 (UNVERIFIED exact burn rate). Trial volumes are deleted 30 days after credits expire. |
| **Render Free** | Spins down after 15 min with no *inbound* traffic; about 1 min to wake; 750 instance-hours/month; ephemeral filesystem; single instance; free Postgres expires after 30 days; background workers and cron are not free (https://render.com/docs/free). | Backup. Needs an external pinger hitting `/health` every 10 min. Whether an open SSE stream counts as inbound traffic is UNVERIFIED, so don't rely on it. 750 h covers one service around the clock. |
| **Fly.io** | No free tier for new orgs; trial is 2 h of machine runtime or 7 days, whichever comes first; shared-cpu-1x 256 MB is $2.19/month with a card (https://docs.fly.io/about/pricing). | Only if you add a card. |

Backend env vars: `NESSIE_API_KEY`, `ANTHROPIC_API_KEY`, `CORS_ORIGINS`, `HARBOR_MODE=demo`, `DATABASE_URL`, set in the host's dashboard and never committed.

Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`.

On boot the backend should be idempotent: create tables, seed the demo persona if missing, and reload demo-clock state from the DB. Store the clock state as `(real_start, storm_start, speed, paused)` so a restart computes the same "now".

**Local fallback on the demo laptop.** This is required, because venue Wi-Fi and cold starts are the top demo killers.
- `uvicorn ... --port 8000`, plus `cd web && npm run build && npm start` on port 3000. A production build is faster and steadier than `next dev`.
- `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` goes in `web/.env.production.local` before the build.
- Pre-cache the replay storm's advisories, cone GeoJSON and sensor history as files in `backend/data/replays/milton-2024/`. Then only Nessie, Anthropic and the map tiles need internet, and a phone hotspot is enough.
- Have the UI show a banner from `/health` when `nessie != "ok"`.
- Rehearse the full demo once on hotspot only.
- Last resort if the network dies completely: MSW mock mode (`NEXT_PUBLIC_API_MOCKING=1`) with the scripted event sequence still shows the full UX story.


---

## Routing and Shelter Layer (RouteService and ShelterService)

### Goal and principles

Harbor's evacuation guide answers four questions for the household: where to go, how to get there, where to sleep, and when to leave. The same rules as the money engine apply here.

- **Deterministic code decides.** Code picks the destination, the shelters and the hotel budget band. Claude only writes the explanation and the advice text.
- **There is no map UI.** Every output is text, numbers, and Google Maps or Apple Maps deep links that open the phone's own navigation app.
- **No routing API is strictly required.** The deep link is the one path that is always available. A routing API only adds distance, drive time and printed turn-by-turn steps. For the demo we ship a precomputed route JSON, so the Milton demo never depends on a live network call.
- **Safety copy is fixed text, not AI text.** Every guide includes: "Follow your local officials' evacuation orders. If officials say evacuate, go." Ready.gov tells people to "Always follow the instructions of local officials" and to leave "early enough to avoid being trapped by severe weather" (https://www.ready.gov/evacuation).

### 1. Routing providers (Python, no map)

| Provider | Endpoint | Auth | Free limits | Text instructions | Terms and quirks |
|---|---|---|---|---|---|
| **OpenRouteService (primary)** | `POST https://api.openrouteservice.org/v2/directions/driving-car/json` (or `/geojson`); Python client `openrouteservice` | Free key from HeiGIT, sent in the `Authorization` header | Standard (free) plan: **2,000 directions requests per day, 40 per minute** (https://openrouteservice.org/plans/) | Yes. `routes[].segments[].steps[].instruction` holds plain English text, plus distance and duration for each step | Restrictions page (https://openrouteservice.org/restrictions/): with `avoid_polygons` the route is capped at **150 km**; each polygon is capped at **200 km²** and **20 km** in height or width; 50 waypoints; 3 alternative routes, and only on routes of 100 km or less. **The NHC cone is hundreds of km wide, so ORS cannot route around it.** Attribution required: "© openrouteservice.org by HeiGIT, Map data © OpenStreetMap contributors". |
| **OSRM public demo (fallback)** | `GET https://router.project-osrm.org/route/v1/driving/{lon},{lat};{lon},{lat}?steps=true&overview=simplified&geometries=geojson` | None | "Do not exceed 1 request per second"; "reasonable, non-commercial use-cases" only (https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server) | **No.** Each step gives only `maneuver.type`, `maneuver.modifier` and the road `name`. We need a small Python formatter (about 40 lines), for example "turn left onto I-75 N" | No uptime guarantee. Fine for a hackathon. Send an identifying User-Agent anyway. |
| GraphHopper | `https://graphhopper.com/api/1/route` | API key | **500 credits per day**, non-commercial only, "a limited credit count per minute" with no number given, "no guarantees" (https://www.graphhopper.com/pricing/) | Yes, `instructions[].text` | Whether the free plan supports polygon avoidance (custom models / `block_area`) is **UNVERIFIED**. Not needed. |
| Google Routes API, Mapbox Directions | Paid, billing account required | Key | Per-SKU free caps since 1 March 2025 (https://developers.google.com/maps/billing-and-pricing/march-2025). Exact numbers **UNVERIFIED**. | Yes | Skip both. Billing risk for no demo benefit. |

**Geocoding.** Harbor already has the user's ZIP code.

- **Origin:** use the ZCTA centroid from the Census Gazetteer file, bundled as a CSV. That needs no API call.
- **Street addresses (optional):** use the free, keyless US Census geocoder: `https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=...&benchmark=Public_AR_Current&format=json`.
- **Avoid Nominatim** for anything user-facing. Its policy (https://operations.osmfoundation.org/policies/nominatim/) allows at most 1 request per second, requires an identifying User-Agent and caching, and forbids autocomplete.
- **Privacy:** never put a user's address into a URL that we log. Round origins to 2 decimal places (about 1 km) before logging or caching.

**Deep links. These are always returned and need no key.**

- **Google Maps** (https://developers.google.com/maps/documentation/urls/get-started):
  `https://www.google.com/maps/dir/?api=1&origin=27.95,-82.46&destination=29.65,-82.32&travelmode=driving&dir_action=navigate`
  - `api=1` is required. Without it, "all parameters are ignored".
  - URLs are limited to 2,048 characters.
  - `waypoints` are separated by `|` (encoded as `%7C`): up to 3 on mobile browsers and 9 elsewhere.
  - `avoid=tolls,highways,ferries` is available (comma encoded as `%2C`).
  - We can add one waypoint (for example a shelter or a gas stop) to push the route onto the evacuation corridor we chose.
- **Apple Maps:** `https://maps.apple.com/?saddr=27.95,-82.46&daddr=29.65,-82.32&dirflg=d`. Parameter semantics are from memory. Apple's reference page did not render, so this is **UNVERIFIED**; test it on an iPhone.

**Avoiding the cone.** Avoidance is done by **choosing the destination**, not by asking the router to avoid an area.

- After routing, run `shapely` on the route geometry against the cone polygon.
- Report `cone_overlap_pct`, plus a warning if the route runs *toward* the forecast track rather than away from it.
- With only a deep link and no geometry, check the straight segment from origin to destination against the cone as an approximation.

**Drive time during an evacuation.** Free routers return free-flow times.

- Show `drive_time_min_normal` together with a heuristic `drive_time_min_evac`, which is 2.5x normal.
- The 2.5x factor is our assumption, not an official figure. Label it "estimate; traffic during Milton was severe".

### 2. Choosing a safe destination automatically

**Guidance.** NHC director Michael Brennan, during Milton: people in storm-surge evacuation zones often only need to go **"tens of miles" inland, not hundreds**. This was reported second-hand, in an interview with ABC News Live; the primary transcript is **UNVERIFIED**. The NHC rule of thumb is "run from water, hide from wind". Ready.gov advises picking several destinations "in different directions" (a friend's home in another town, or a motel).

**Algorithm (deterministic, in `destination_picker.py`):**

1. **Inputs:**
   - the origin lat/lon
   - the user's evacuation zone
   - the current cone polygon
   - the household profile
   - the hours until tropical-storm-force winds arrive (from the NHC or NWS module)
2. **Candidates:** a bundled `fl_destinations.json` with about 40 inland Florida and south Georgia cities. Each entry has lat/lon, the main evacuation corridor, and whether it is a hotel hub. Examples: Brandon, Plant City, Lakeland, Gainesville, Ocala, Lake City, Tallahassee, Valdosta GA.
3. **Tier A, "local":** the nearest place within about 30 miles that is **outside every evacuation zone** (zone = none). For a site-built home in a surge zone, this is the recommended tier, matching the "tens of miles" guidance.
4. **Tier B, "regional":** the nearest candidate **outside the cone polygon buffered by 40 km**. This is recommended for:
   - mobile or manufactured homes
   - Category 4 or 5 storms
   - households that need power for medical equipment
   - users who choose "get out of the storm entirely"
   - **During Milton the cone covered most of the central peninsula, Orlando included, so Tier B moves north (Gainesville, Lake City or beyond).** That is a long drive, and the guide must say so honestly.
5. **Scoring:** filter candidates by `drive_time_min_evac` against the hours remaining before winds arrive, then score: `score = drive_time + penalty(cone_overlap) + penalty(heading toward track) − bonus(hotel hub)`. Return the top pick and one alternative in a different direction.
6. **Leave-by time:** `leave_by = TS-wind arrival − drive_time_evac − 3 h buffer`. Show it prominently and send it to the notification layer.

**Corridors.** Florida no longer uses contraflow. **Emergency Shoulder Use (ESU)** replaced it (https://www.fdot.gov/emergencymanagement/esu/).

- **What ESU allows:** cars may drive on the shoulder between entry and exit points marked by law enforcement. Large trucks, buses and trailers may not.
- **Milton activations:**
  - I-4 eastbound, inside shoulder, Tampa to Celebration
  - I-75 northbound, inside shoulder, Tampa to Lake City
  - Tolls were waived on the Veterans Expressway and the Suncoast Parkway
- **Demo use:** encode these as static `corridor_notes` in the destination file for the demo.
- **Live mode:** link to FDOT and FL511. A live ESU feed is **UNVERIFIED**.

**Evacuation zones ("Know Your Zone").**

- **Statewide:** FDEM's Know Your Zone app (floridadisaster.org) is Esri-based, but **no official statewide FDEM FeatureServer URL was found (UNVERIFIED)**. A third-party "Hurricane Evacuation Zones 2013" layer exists, but it is stale. Do not use it.
- **Hillsborough County layer:** `https://gisdextweb1.hillsboroughcounty.org/arcgis/rest/services/Hosted/HEAT_2026_Webmap/FeatureServer/1`, named "EvacuationZones2025", display field `zone`, max 2,000 records, JSON/GeoJSON/PBF. My fetch of it was refused (connection refused), so a live query is **UNVERIFIED**.
- **Query by point:**
  `.../FeatureServer/1/query?geometry=-82.46,27.95&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=zone&returnGeometry=false&f=json`
- **Flood zones are different.** The layer's own metadata says its zones are separate from FEMA flood insurance (FIRM) zones. Never label one as the other.
- **Fallback chain:**
  1. the county layer, for the counties in a small config (Hillsborough, Pinellas, Pasco, Manatee, Sarasota)
  2. a **zone the user picks during onboarding** (A–E, "not in a zone", or "not sure"), with a link to floridadisaster.org/knowyourzone
  3. "not sure" is treated as zone A when the home is a mobile home or near the coast
- **Mobile and manufactured homes** are always treated as "evacuate". Hillsborough's Milton order covered zones A and B plus all mobile homes (hcfl.gov, 7 Oct 2024).

### 3. Shelters

**FEMA Open Shelters (live).**

- **Service:** `https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0`. No key needed.
- **Source:** the "FEMA ESF6-SS" database, formerly the National Shelter System (NSS).
- **Refresh:** synced each morning with the American Red Cross shelter database, then re-checked every 20 minutes.
- **Format:** max 2,000 records; JSON, GeoJSON or PBF.
- **Fields:**
  - identity: `shelter_id`, `shelter_name`, `org_name`
  - location: `address`, `city`, `state`, `zip`, `latitude`, `longitude`
  - status and capacity: `shelter_status`, `evacuation_capacity`, `post_impact_capacity`, `total_population`, `hours_open`, `hours_close`
  - accessibility: `ada_compliant`, `wheelchair_accessible`, `pet_accommodations_code`, `subfacility_code`
- **Query:**
  `.../FeatureServer/0/query?where=shelter_status='OPEN'&geometry=-82.46,27.95&geometryType=esriGeometryPoint&inSR=4326&distance=60&units=esriSRUnit_StatuteMile&outFields=*&f=geojson`
- **Quirks (verified today):**
  - Only **4 shelters are open nationwide**: AL, AZ, CA and FL.
  - In every record, the pet, ADA and wheelchair fields are **blank (" ") or null**.
  - So treat these fields as tri-state (`true`, `false`, `unknown`) and **never claim a shelter is pet-friendly or ADA-accessible unless the field says so.**
  - The valid codes for `pet_accommodations_code` are **UNVERIFIED**.
- **Historical data:** I found no archive of past open shelters, on OpenFEMA or anywhere else.
- **Older layer:** `NSS/FEMA_NSS/FeatureServer/0` also exists. Whether it is maintained is **UNVERIFIED**, so we don't use it.

**Other sources (linked only, not called):**

- **American Red Cross:** redcross.org/shelter, the Red Cross Emergency App, and 1-800-RED-CROSS (1-800-733-2767). There is no public API.
- **FDEM:** the statewide open-shelter summary at https://floridadisaster.org/shelter-status. Its data loads dynamically, so there is no stable API. Do not scrape it.

**Special-needs shelters.**

- **Who they are for:** Florida Department of Health and county pages describe them as being for people on life-sustaining electrical equipment (oxygen, ventilators, dialysis), people who need caregiver help with daily tasks, people with mobility limits, and people with moderate dementia.
- **Registration:** through the state Special Needs Registry, run by FDEM, or the county. **Registering does not guarantee a space.**
- **What to bring:** a caregiver should stay with the client the whole time, and clients usually bring their own medications, supplies and bedding.
- **What Harbor does:** Harbor cannot register anyone. It shows the county's registration link and a checklist.

**Milton demo.** Ship a curated `demo/milton_shelters.json`, built by hand from Hillsborough County's 7–9 October 2024 releases (hcfl.gov) and WUSF's shelter list:

- **11 general shelters.** Pet-friendly: Burnett MS, Durant HS, Middleton HS, Shields MS, Sickles HS, Steinbrenner HS. Not pet-friendly: Pizzo ES, Reddick ES, Mulrennan MS, Lockhart ES, Collins PK-8.
- **3 special-needs shelters, all pet-friendly:** Erwin Technical College, Sumner HS, Strawberry Crest HS.
- **Pet rules:** a sturdy carrier for each pet, a collar and leash, and 7 days of supplies.
- **Full shelters:** Erwin, and at one point Durant, were reported **full**. Replay that as a timed status change, so a shelter fills up during the demo.
- **Source fields:** every record carries `source_url` and `as_of`, so judges can see the data is real and historical.
- **Precise lat/lon** must be geocoded once offline with the Census geocoder; not yet done.

### 4. Lodging matched to budget and household

- **Hotel search APIs:** no free, compliant hotel search API that includes prices exists any more. Amadeus Self-Service, the usual hackathon choice, shut down on **17 July 2026**.
- **Places (no prices):** OSM Overpass, with `tourism=hotel|motel|guest_house` within a radius of the destination.
  - Free, no key.
  - Guidelines: about 10,000 requests per day and under 1 GB per day.
  - Requires ODbL attribution.
  - OSM tags for pets or price are rare (**UNVERIFIED** coverage).
- **Alternative:** Google Places Text Search (New) returns `priceLevel`. It is a paid tier with a monthly free cap; which tier and how many free calls is **UNVERIFIED**. Only use it if a billing account already exists.
- **Budget bands (deterministic):** from the money plan's "lodging" amount, for example $0, $80–120, $120–200 or $200+ per night. Compute the number of nights from the forecast: 2 to 4. The AI money review then shows this as one allocation line ("$360 lodging, 3 nights, moved from checking").
- **Rules by household:**

| Profile | Rule |
|---|---|
| Budget $0 or near $0 | Public shelter first, then a friend or family. Hotel links only. |
| Pets | Pet-friendly shelters, or hotels flagged "call to confirm pets". Carrier, leash, 7 days of food. Ready.gov: only service animals may be allowed in public shelters. |
| Older adults, medical needs, electricity-dependent | Special-needs shelter registration link. Prefer the Tier B destination with reliable power. Leave earlier: `leave_by` buffer + 3 h. Medication list. |
| Kids | Family rooms, or 2 rooms for 5 or more people. Shelter supply list (formula, diapers, comfort items). Shorter driving legs. |
| Wheelchair, disability | Shelters marked ADA "yes" only; "unknown" gets a "call first" flag. Accessible-room note for hotels. |
| No car | No driving route. County transport to shelters (Hillsborough offered transport, then **stopped** as winds rose, per WTSP), the county EOC phone number, and the `leave_by` time for transport. |

- **Price gouging:** add a static line that Florida prohibits price gouging during a declared emergency (statute citation **UNVERIFIED**; s. 501.160 from memory).

### 5. Service design

**Shared rules for both services:**

- Each service sits behind an interface: `RouteService.plan(...)` and `ShelterService.find(...)`.
- In demo mode, providers are swapped for fixtures. `HARBOR_MODE=demo` means zero network calls.

**RouteService**

- **Inputs:** `origin {lat, lon}`, `household`, `evac_zone`, `cone_geojson`, `advisory_id`, `wind_arrival_utc`.
- **Provider order:** ORS → OSRM → deep link only. Every failure falls back silently.
- **Caching:** an in-memory or SQLite TTL cache.
  - Key: `(round(lat,2), round(lon,2), dest_id, advisory_id)`.
  - TTL: 6 hours, or until a new advisory comes out.
  - Rate-limit the OSRM fallback to 1 request per second.
- **Cone data:**
  - Live: the NHC `.../gis/forecast/archive/{storm}_5day_latest.zip`.
  - Demo: the Milton archives, `https://www.nhc.noaa.gov/gis/forecast/archive/al142024_5day_0NN.zip` (advisories 015–020, plus "A" intermediates).
  - Parse the `_5day_pgn` shapefile with `pyshp` or `geopandas`.
  - Which advisory matches each demo timestamp is **UNVERIFIED**; map them from the advisory issue times.

**ShelterService**

- **Inputs:** `center`, `radius_mi`, `needs[]`.
- **Sources:**
  - Live: FEMA, cached 10 minutes (matching FEMA's 20-minute check).
  - Demo: the curated JSON.
  - County special-needs registration links come from a static config.
- **Ranking:**
  1. needs-match (a hard filter on known `false` values)
  2. distance
  3. remaining capacity, `evacuation_capacity − total_population`

**`GET /api/evacuation/plan?user_id=...` response:**

```json
{
  "as_of": "2024-10-08T15:00:00Z",
  "advisory_id": "AL142024-018",
  "decision": {"action": "evacuate", "tier": "B", "reason_codes": ["MOBILE_HOME", "ZONE_A", "CAT4_PLUS"]},
  "leave_by": "2024-10-08T22:00:00Z",
  "destination": {"id": "gainesville_fl", "name": "Gainesville, FL", "lat": 29.65, "lon": -82.32,
                  "outside_cone": true, "outside_evac_zones": true},
  "alternative": {"id": "lakeland_fl", "name": "Lakeland, FL", "tier": "A"},
  "route": {
    "provider": "ors", "distance_mi": 132.4,
    "drive_time_min_normal": 125, "drive_time_min_evac": 312,
    "cone_overlap_pct": 18, "corridor": "I-75 N (Emergency Shoulder Use active)",
    "steps": [{"text": "Head north on N Florida Ave", "distance_mi": 0.4}],
    "links": {"google": "https://www.google.com/maps/dir/?api=1&...", "apple": "https://maps.apple.com/?saddr=...&daddr=...&dirflg=d"},
    "attribution": "© openrouteservice.org by HeiGIT | © OpenStreetMap contributors"
  },
  "shelters": [{"id": "hc-burnett-ms", "name": "Burnett Middle School", "kind": "general",
                "pets": true, "ada": "unknown", "status": "open", "capacity_left": null,
                "distance_mi": 14.2, "source": "curated:hcfl.gov 2024-10-08", "links": {"google": "..."}}],
  "lodging": {"budget_band": "80-120", "nights": 3, "planned_total_usd": 360,
              "options": [{"name": "...", "type": "motel", "pets": "call_to_confirm", "source": "osm", "links": {"google": "..."}}]},
  "checklists": {"pets": ["carrier", "leash", "7 days food"], "medical": ["medications", "registration link"]},
  "explanation": null
}
```

- **Explanation text:** Claude fills `explanation` from this JSON only, with a strict instruction never to invent shelters, times or prices.
- **Prompt input:** pass the household profile as data, but strip the address and names before sending it to Claude.
- **Teammate's Next.js site:** render the steps as a list and the links as buttons. No map is needed.

### Open items

- Confirm a statewide FDEM zone service, or ship the curated county GeoJSON.
- Verify the Apple Maps parameters on a real device.
- Find the valid codes for `pet_accommodations_code`.
- Map Milton advisory numbers to issue times.
- Geocode the curated shelters.
- Verify the Florida price-gouging citation.

Sources:
- [OSRM demo server](https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server)
- [OSRM API](https://project-osrm.org/docs/v5.24.0/api/)
- [ORS plans](https://openrouteservice.org/plans/)
- [ORS restrictions](https://openrouteservice.org/restrictions/)
- [GraphHopper pricing](https://www.graphhopper.com/pricing/)
- [Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started)
- [Google pricing changes, March 2025](https://developers.google.com/maps/billing-and-pricing/march-2025)
- [Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/)
- [Overpass usage limits](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html)
- [FEMA Open Shelters](https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0)
- [NHC GIS](https://www.nhc.noaa.gov/gis/)
- [Milton GIS archive](https://www.nhc.noaa.gov/gis/archive_forecast_results.php?id=al14&year=2024)
- [Hillsborough evacuation zones](https://gisdextweb1.hillsboroughcounty.org/arcgis/rest/services/Hosted/HEAT_2026_Webmap/FeatureServer/1)
- [FDOT Emergency Shoulder Use](https://www.fdot.gov/emergencymanagement/esu/)
- [Ready.gov evacuation](https://www.ready.gov/evacuation)
- [Hillsborough Milton shelters](https://hcfl.gov/newsroom/2024/10/09/hillsborough-county-opens-three-more-shelters-ahead-of-hurricane-milton)
- [WUSF shelter list](https://www.wusf.org/weather/2024-10-08/hurricane-milton-tampa-bay-county-by-county-shelter-list)
- [WTSP transport report](https://wtsp.com/article/weather/hurricane/hurricane-milton/hillsborough-county-florida-no-longer-able-to-transport-residents-shelters/67-349b423d-7bd8-4f0c-9e94-2d6a9042b0a9)
- [FL DOH special needs shelter qualifications](https://www.floridahealth.gov/PROGRAMS-AND-SERVICES/emergency-preparedness-and-response/disaster-response-resources/spns/qualifications.html)
- [FDEM shelter status](https://floridadisaster.org/shelter-status)
- [Amadeus shutdown](https://www.phocuswire.com/amadeus-shut-down-self-service-apis-portal-developers)
- [NHC "tens of miles" report](https://thepulseofnh.com/?p=135479)


---

## Lodging, household needs and the AI plan review

### 1. Lodging data sources (checked 2026-10-16)

| Source | Status in 2026 | Prices? | Access and limits | Verdict |
|---|---|---|---|---|
| **Amadeus Self-Service Hotel APIs** (Hotel List, Hotel Search v3) | **Shut down.** Amadeus paused new sign-ups in Feb 2026 and turned off self-service keys on **July 17, 2026**. Only the contract-based Enterprise portal remains ([PhocusWire](https://www.phocuswire.com/amadeus-shut-down-self-service-apis-portal-developers), [Tragento](https://tragento.com/en/amadeus-and-anthropic-connect-claude-with-travel-content-and-tools/)). I could not open Amadeus's own notice, so the exact date is UNVERIFIED against a primary source. | n/a | Needs an Enterprise contract | **Do not use** |
| **Booking.com Demand API** | Live but gated. You must be a Managed Affiliate Partner with a signed contract and an account manager ([prerequisites](https://developers.booking.com/demand/docs/getting-started/prerequisites)). A third party reports the partner terms forbid AI use without written approval (UNVERIFIED). | Yes | Not possible within 48 h | **Do not use** |
| **Expedia Rapid API** | Partner agreement required (UNVERIFIED: I found no official requirements page) | Yes | Not possible within 48 h | **Do not use** |
| **Google Places API (New): Text Search** | `POST https://places.googleapis.com/v1/places:searchText`. Headers: `X-Goog-Api-Key`, plus a required `X-Goog-FieldMask` (there is no default mask). | Only `priceLevel` / `priceRange`, as price bands, not nightly rates | The $200 monthly credit ended **March 1, 2025**. It was replaced by free calls per SKU each month ([March 2025 changes](https://developers.google.com/maps/billing-and-pricing/march-2025)). Text Search Pro: 5,000 free, then $32 per 1,000. Enterprise: 1,000 free, then $35. Enterprise + Atmosphere: 1,000 free, then $40 ([pricing](https://developers.google.com/maps/billing-and-pricing/pricing)). Needs a billing account. | **Optional** |
| **OpenStreetMap Overpass** | Public instance: about 10,000 requests a day and under about 1 GB a day. Overload returns HTTP 429 or 504 ([usage guidance](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html)). OSM data is ODbL, so credit "© OpenStreetMap contributors". | **No** | Free, no key | **Use** for names and locations of hotels and motels |
| **GSA per diem** | `GET https://api.gsa.gov/travel/perdiem/v2/rates/{city/{city}/state/{ST} \| zip/{zip} \| state/{ST}}/year/{FY}`. Send the key in the `x-api-key` header or as `?api_key=`. 1,000 requests an hour. New rates usually arrive mid-August, and the fiscal year runs October to September ([docs](https://open.gsa.gov/api/perdiem/)). | **Yes**, as a government cap on nightly lodging by month, not a real hotel price | Free api.data.gov key. `DEMO_KEY` worked in my test but is heavily throttled. | **Use** to estimate nightly cost |
| **FEMA open shelters** | `https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query`. Synced from Red Cross every morning, then refreshed every 20 minutes. Returns up to 2,000 records per page. Fields include `shelter_status`, `pet_accommodations_code`, `ada_compliant`, `wheelchair_accessible`, `evacuation_capacity`. | Free shelter | No key | **Use** for the $0 budget tier |

**Google field quirks.** Billing follows the most expensive field you ask for:
- `displayName`, `formattedAddress`, `location` and `accessibilityOptions` are **Pro** fields.
- `priceLevel`, `priceRange`, `rating`, `websiteUri` and `nationalPhoneNumber` are **Enterprise** fields.
- `allowsDogs` is **Enterprise + Atmosphere**.

So one pet-aware search costs at the $40 per 1,000 tier ([field SKUs](https://developers.google.com/maps/documentation/places/web-service/text-search)). The docs also say `includedType` filtering "does not apply to hotel" queries, so pass the type in the query text instead (for example "pet friendly motel in Gainesville FL").

**Google terms.** You may not prefetch, cache or store Places content. The one exception is the place ID, which you may keep indefinitely. If you show results without a Google map, which applies to the teammate's site, you must show the "Google Maps" logo or text attribution ([policies](https://developers.google.com/maps/documentation/places/web-service/policies)). So Harbor stores only `place_id` and fetches fresh details on each request.

**OSM tags to query** (Overpass QL: `nwr["tourism"~"^(hotel|motel|hostel|guest_house)$"](around:15000,lat,lon); out center tags;`):
- `wheelchair=yes|limited|no` (documented)
- `dog=yes|no|leashed` (documented on [Key:dog](https://wiki.openstreetmap.org/wiki/Key:dog), though the page doesn't mention hotels)
- `pets=*` and `pets_allowed=*` (listed as related keys, meaning UNVERIFIED)
- `rooms`, `beds`, `smoking`, `phone`, `website`, `stars`

Coverage is uneven. Treat a missing tag as "unknown", not "no".

**Recommended combination for the 48 hours:**
1. Overpass gives the candidate places.
2. GSA gives the nightly cost estimate for the destination's city or county and month.
3. FEMA open shelters gives the free option.
4. Google Places is optional, behind a feature flag. Use it only to add `priceLevel` and `allowsDogs` to the top 5 OSM matches.
5. Every lodging card says **"Estimated cost. Call to confirm availability."** Harbor never claims a room is available.

A budget tier, set by the deterministic engine, sets each place's estimated price:
- **economy** (motel or hostel): 0.75 × GSA rate
- **standard**: 1.0 × GSA rate
- **comfort**: 1.3 × GSA rate

These multipliers are a Harbor heuristic, not sourced, so label them UNVERIFIED.

**Curated Milton demo dataset** (`data/demo/lodging_milton.json`, served whenever `DEMO_MODE=1`, with no live calls). These are the FY2025 GSA October lodging caps I fetched from the API:

| Destination | GSA lodging, Oct FY2025 | Meals and incidentals | Note for the demo |
|---|---|---|---|
| Gainesville, FL | $110 (standard rate) | $68 | About 130 mi north of Tampa via I-75 |
| Atlanta, GA (Fulton/DeKalb) | $182 | $86 | Out of state. A full day's drive, so budget a fuel stop and maybe an overnight. |
| Orlando, FL (Orange) | $140 | $80 | **Flag as unsafe for Milton.** The storm crossed central Florida, so the router must reject destinations inside the forecast cone. |

Fill each city with 5 to 8 real OSM places captured once, keeping `osm_id`, name, tags and coordinates. Mark them `"source":"osm_snapshot_2026-10"` and attach the GSA estimate. Do not invent nightly prices or reviews.

**Price-gouging and sell-out advice.** This is shown as a fixed info card, not AI-generated.
- Florida's statute **§501.160** covers hotel rooms during a declared emergency. A price is presumed unconscionable if it shows a "gross disparity" from the average of the 30 days before the declaration, unless costs justify it. Civil penalties are $1,000 per violation, up to $25,000 per 24 hours. Report to the Attorney General at 1-866-9-NO-SCAM ([Carlton Fields](https://www.carltonfields.com/insights/publications/2026/sellers-beware-price-gouging-before-during-and-after-hurricane-isaias-makes-landfall), [Alachua County](https://alachuacounty.us/News/Article/Pages/Florida-Price-Gouging-Laws-Are-in-Effect.aspx)). The text comes from secondary sources, so verify it at flsenate.gov (UNVERIFIED).
- During Milton, lawmakers cited a $600 one-night Hampton Inn rate ([CPC statement](https://punchbowl.news/wp-content/uploads/CPC-price-gouging-statement.pdf)).

So Harbor's advice is:
- Book a **refundable** room as soon as the destination is chosen. Rooms on evacuation routes fill early. This is common knowledge, not sourced.
- Screenshot the quoted price.
- Compare the quote to the GSA estimate. If a quote is more than 2× the estimate, show the gouging card. The 2× threshold is a Harbor heuristic, not the law.

### 2. Household needs: checklists and budget effects

Household profile fields on `POST /api/household`: `adults`, `children[] (ages)`, `seniors`, `pets[] (type, count)`, `mobility`, `power_dependent_device`, `oxygen`, `dialysis`, `refrigerated_meds`, `has_car`, `county`.

| Need | Advice Harbor shows (sourced) | Effect on the budget and route |
|---|---|---|
| **Everyone** | 1 gallon of water per person per day for several days, non-perishable food, a radio, a flashlight, batteries, phone chargers, local maps ([Ready.gov kit](https://www.ready.gov/kit)) | Supplies line = people × days × a per-person allowance. Meals = GSA meals rate × people × days, at 0.75 for children (a Harbor heuristic). |
| **Infants and kids** | Formula, bottles, diapers, wipes, diaper cream ([Ready.gov kit](https://www.ready.gov/kit)) | Rooms: ceil(people ÷ 4), assuming 2 queen beds. This occupancy rule is UNVERIFIED and must be confirmed with each hotel. Prefer rooms with a fridge. Add a rest stop every 2 hours (Harbor heuristic). |
| **Older adults** | Pack medicines, copies of Medicare/Medicaid and insurance cards, and assistive devices. Build a support network, one person with a spare key. Plan transportation. Ask the dialysis clinic about its emergency plans and backup providers ([Ready.gov older adults](https://www.ready.gov/older-adults)). | Filter lodging to ground floor or `wheelchair=yes`. Cap one day's driving (default 6 h, a Harbor heuristic). |
| **Disability or medical** | Several days of medicines plus a list of drugs, doses and allergies. A cooler for refrigerated meds. Backup oxygen. Know more than one dialysis or treatment facility. Ask the power company for priority restoration. Spare wheelchair battery or a manual chair. Communication cards ([Ready.gov disability](https://www.ready.gov/disability)). | Require `wheelchair=yes` or ADA shelters. Route via a pharmacy. Add a "call your oxygen supplier" step. |
| **Medication refills (FL)** | **§252.358**: when the county is under an NWS hurricane warning, a declared emergency, or an activated emergency operations center, insurers must waive "refill too soon" limits and pay for at least 30 days of supply ([statute](https://florida.public.law/statutes/fla._stat._252.358), [OIR notice](https://content.govdelivery.com/accounts/FLOIR/bulletins/32ea391)). Schedule II drugs are excluded, according to one secondary source (UNVERIFIED). | Budget line for copays. Shown as a task with a deadline before departure. |
| **Special-needs shelter** | Each county must keep a registry under F.S. 252.355. Registration is in advance and renewed every year. Special-needs shelters **cannot** provide hemodialysis, hospital beds or full ventilator support ([Martin Co.](https://www.martin.fl.us/node/852), [WLRN](https://www.wlrn.org/medical-assistance-hurricane-shelters-florida)). Hillsborough: Health Dept 813-307-8063. It stops reviewing registrations **72 h before landfall**, though nurses assess walk-ins ([WUSF](https://www.wusf.org/weather/2026-07-28/how-special-needs-residents-can-prepare-for-hurricane-evacuations)). | If dialysis or a ventilator is flagged, Harbor tells the user to **leave early and plan with their doctor**, not to rely on a shelter. |
| **Pets** | Microchip, carrier (ideally one per pet), multi-day food and water, medicines, records, a recent photo with the owner. "Many public shelters and hotels do not allow pets" ([Ready.gov pets](https://www.ready.gov/pets)). Hillsborough: pet-friendly shelters, the 813-301-PETS line, 7 days of supplies ([county](https://hillsboroughcounty.org/en/residents/social-services/disaster-assistance)). | Filter lodging by `dog=yes`, Google `allowsDogs`, or FEMA `pet_accommodations_code`. Pet fee line: default $25 to $75 a night (UNVERIFIED, confirm with each hotel). |
| **No car** | Hillsborough's registration form arranges rides through Sunshine Line, and Emergency Management is at (813) 236-3800. During Milton the state ran free buses to shelters, 7 am to 7 pm (help line 800-729-3413), and HART ran free routes to shelters ([county](https://hillsboroughcounty.org/en/residents/social-services/disaster-assistance), [HCFL newsroom](https://hcfl.gov/newsroom/2024/10/08/state-offering-charter-buses-to-help-get-hillsborough-residents-to-shelters)). These details change with each storm. | The fuel line becomes $0, and the route becomes a "pickup or shelter" plan. Flag tickets if a bus or rail ride out of the region is chosen. |

The fuel line is computed by the deterministic engine, not the AI:

`fuel = route_miles ÷ mpg (default 25) × gas price × 1.3`

The 1.3 covers contraflow and idling. It is a Harbor heuristic, labelled as such.

### 3. AI review of the money plan and evacuation guide

**Principle.** The rules engine (`engine.plan()`) creates every number. Claude only reads the finished plan and writes the review. It never calculates, and it never calls Nessie.

**Model:** `claude-opus-5-5`, set to `effort: "low"` for speed. The current ID, its $4 / $20 per million token price, and its default effort of `medium` are confirmed on the [models overview](https://platform.claude.com/docs/en/about-claude/models/overview). Use the Python SDK's `client.messages.parse()` with a Pydantic model, which sends `output_config.format` ([structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)).

Schema limits to plan around:
- Numeric `minimum`/`maximum` and string length limits are **not supported** by the API. The SDK moves them into field descriptions and checks the response afterwards.
- Every object needs `additionalProperties: false`.
- Check `stop_reason` for `refusal` or `max_tokens` before parsing.
- Enum casing may change, so compare enum values case-insensitively.
- On Opus 5.5, `thinking: {type:"disabled"}` returns a 400, so leave it out. Assistant prefill also returns a 400.
- Optionally, set `fallbacks: "default"` with the beta header `server-side-fallback-2026-07-01` so refusals go to a fallback model.

**Prompt caching** ([docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)):
- Put the frozen system prompt first, then the schema, the guardrails, and the household checklists from §2 (this part exceeds the 512-token minimum for Opus 5.5).
- Mark the last stable block with `cache_control: {"type":"ephemeral"}`.
- Send the plan JSON afterwards, in the user message.
- Cache reads on Opus 5.5 cost $0.20 per million tokens.
- Confirm the cache is working by checking `usage.cache_read_input_tokens` is above 0.
- Never put timestamps in the system prompt.

**Input** (the `PlanSnapshot` built by the engine, with stable sorted keys):

```json
{"plan_id":"p_123","household":{...},"storm":{"name":"Milton","landfall_eta":"..."},
 "moves":[{"id":"m1","source":"checking","amount":800.00,"dest":"cash_withdrawal","available":"immediate"},
          {"id":"m2","source":"etf_sale","ticker":"VTI","amount":1200.00,"est_gain":140.00,
           "est_tax_note":"short-term gain, taxed as ordinary income","settles":"T+1"}],
 "accounts":{"checking":2100.00,"savings":3500.00,"etf_value":9800.00},
 "budget_lines":[{"id":"b1","kind":"lodging","nights":3,"rooms":1,"rate":110,"total":330,"basis":"GSA FY2025 Gainesville"}],
 "lodging_picks":[{"id":"l1","name":"...","source":"osm","dog":"yes","wheelchair":"unknown"}],
 "route":{"dest":"Gainesville, FL","miles":131,"fuel_total":...},
 "alternatives_precomputed":[{"id":"alt1","label":"Use savings instead of selling VTI","moves":[...],"delta_tax":-140.00}]}
```

US stock and ETF trades have settled T+1 since May 28, 2024 (SEC rule). The engine, not the AI, should state when sale proceeds become available.

**Output schema** (`PlanReview`):

```json
{"summary":"string",
 "label":"Suggestion only - not financial advice",
 "total_cited":{"ref":"plan.total_moved"},
 "per_source":[{"move_id":"m1","source":"checking|savings|etf_sale","reasoning":"string","cited_refs":["moves.m1.amount"]}],
 "alternatives":[{"alt_id":"alt1","why_consider":"string","tradeoff":"string"}],
 "risks":[{"kind":"liquidity|tax|settlement|gouging|availability|medical|other","text":"string"}],
 "double_check":["string"],
 "household_notes":[{"need":"pets|kids|seniors|medical|no_car|disability","advice":"string","source_url":"string"}],
 "lodging_comments":[{"lodging_id":"l1","comment":"string"}]}
```

**Guardrails:**
1. **No invented numbers.** Claude cites values only through `cited_refs` and `move_id`/`alt_id`, which must point into the snapshot. After parsing, a validator removes every digit sequence in the free-text fields that doesn't match a value in the snapshot (after normalising "$1,200" to 1200). If any are found, Harbor regenerates once, then falls back to the template.
2. Claude may only mention alternatives the engine has already computed in `alternatives_precomputed`. It may not suggest new amounts.
3. The `source_url` values in `household_notes` must come from a list of allowed sources: the URLs in §2.
4. The UI always shows the `label` text and a "This is a suggestion, not advice" banner. Prompt wording: "never say 'you should buy/sell'; say 'the plan proposes…'".

**Template fallback** (`review_template.py`). Use it when there's no API key, on a timeout over 8 seconds, after a refusal, or when the validator fails. It builds the same `PlanReview` using Jinja strings filled with the engine's numbers. For example: "Harbor proposes moving ${total} from {sources}. Selling {ticker} realises an estimated ${gain}, which may be taxable; using savings would avoid that." Demo mode always pre-caches one Claude review and the template version for Milton.

**Accept or edit loop.** If the user edits (for example "use savings instead of selling", "2 rooms", "add a dog"), Harbor sends the edit to the engine. `engine.plan()` re-runs deterministically and issues a new `plan_version`, then a new review is generated. The AI output is never applied directly. Accepting locks `plan_version` and enables the Nessie transfer step, which still needs approval for each move.

### 4. API endpoints Harbor should add (FastAPI)

| Method and path | Purpose |
|---|---|
| `POST /api/household` | Save the household profile above |
| `GET /api/lodging?dest_lat=&dest_lon=&checkin=&nights=&tier=economy\|standard\|comfort&household_id=` | Overpass + GSA (+ Google if the flag is on) + FEMA shelters, filtered by needs. Demo mode uses the Milton snapshot. |
| `GET /api/lodging/estimate?city=&state=&month=` | Proxy for the GSA per diem rate (cached 24 h; this is government data, so caching is allowed) |
| `GET /api/shelters/open?lat=&lon=&radius_mi=&pets=&ada=` | Proxy for the FEMA OpenShelters layer |
| `GET /api/household/{id}/checklist` | Sourced checklist items, deadlines (e.g. "special-needs registration closes 72 h before landfall") and budget changes |
| `POST /api/plan/{id}/review` | Builds the PlanSnapshot and calls Claude, or the template. Returns `PlanReview` plus `generated_by: "claude-opus-5-5" \| "template"`. |
| `POST /api/plan/{id}/edits` | Body `{changes:[{op,path,value}]}` or `{alt_id}`. Re-runs the engine, returns the new `plan_version` and a new review. |
| `POST /api/plan/{id}/accept` | Locks the version. The response lists the Nessie moves still waiting for approval. |

**Keys needed:** `GSA_API_KEY` (api.data.gov), `ANTHROPIC_API_KEY`, and optionally `GOOGLE_MAPS_API_KEY` (needs billing). Keep them all in `.env` and never commit them. Overpass and FEMA need no key. Set a User-Agent on Overpass requests and back off on HTTP 429.
