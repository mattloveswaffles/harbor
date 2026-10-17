# Harbor API contract (v1.1)

This is the contract between the Harbor backend (Python + FastAPI) and the Next.js frontend. The
frontend can build against it now with mock data (MSW). Once the server runs, the live, clickable docs
are at `http://localhost:8000/docs`, and the machine-readable schema is `docs/openapi.json` (generate
a typed client from it with `openapi-typescript`).

**Example values are illustrative.** Real Milton advisory times and numbers come from the replay
archive. Design notes are in [DESIGN.md](DESIGN.md).

## Conventions

- **Base URL:** `http://localhost:8000/api/v1`. Paths in this doc are relative to it, except `/health`
  and the demo GeoJSON URLs, which are relative to the API origin.
- **Format:** JSON in and out, with `snake_case` field names.
- **Money is integer cents** (`amount_cents: 64000` = $640.00). Nessie itself stores whole dollars; the
  backend converts.
- **Times are ISO 8601 UTC.** In demo mode, "now" is the **demo clock**, so always use
  `server_time` (in every response body) or the `X-Server-Time` header, never the device clock.
- **Replay dates:** the replay keeps the **real 2024 dates** of Hurricane Milton.
- **Auth:** users sign up or log in (see [Accounts](#accounts)) and get a token. Send it on every
  request as `Authorization: Bearer <token>`. The SSE stream can't send headers, so it takes
  `?token=<token>` instead. Tokens last 30 days; logging out ends one at once.
  - No token: `401 auth_required`. A wrong, expired or logged-out token: `401 invalid_token`
    (send the user back to the login screen).
  - **Demo mode only:** `X-User-Id: <user_id>` (and `?user_id=` on the stream) still works for the
    demo personas. In live mode it's refused, because anyone could pretend to be anyone.
- **Errors** always have this shape, including validation (422) errors:
  ```json
  { "error": { "code": "plan_not_found", "message": "No active plan for this user.", "fields": null } }
  ```
  For a 422, `fields` is a list of `{ "loc": ["body", "household", "adults"], "msg": "..." }`. For
  `zip_not_supported`, it's `{ "zip": "Unknown ZIP" }`.
- **Bank errors:** `503 bank_unavailable` (Nessie down or timing out; try again), `503 bank_not_configured`
  (no `NESSIE_API_KEY`) and `502 bank_rejected` (Nessie refused the request).
- **Map data** is GeoJSON in `[lon, lat]` order, ready for react-leaflet's `<GeoJSON>`.

## Risk levels

Each user is always at exactly one level.

| Level | Meaning | Typical trigger |
|---|---|---|
| `clear` | No storm threatens this ZIP. | Nothing in the 5-day outlook. |
| `monitor` | A storm might come this way. | Tropical-storm wind chance at the ZIP ≥ 5%. |
| `prepare` | Harbor builds the plan, AI review and evacuation guide; the user approves. | Wind chance ≥ 20%, or a sensor flag near the user. |
| `act` | Approved money moves run now. | Wind chance ≥ 50%, or a hurricane watch/warning. |
| `shelter` | The storm is here. No new money moves; last-known balances are shown. | Warning + winds within 12 h, or sustained wind ≥ 39 mph. |
| `recover` | It has really passed. Harbor puts money back. | Alerts ended, out of the cone, **and** the sensors say all-clear (rivers falling, surge gone). |

The response always includes `risk_reason`, a plain sentence explaining why the user is at this level.

## Objects

### User
```json
{
  "id": "usr_7f3a",
  "name": "Maria Lopez",
  "zip": "33602",
  "location": { "lat": 27.9506, "lon": -82.4572 },
  "location_source": "zcta",
  "household": {
    "adults": 2,
    "children_ages": [7],
    "seniors": 0,
    "pets": [{ "type": "dog", "count": 1 }],
    "mobility": "none",
    "medical": { "power_dependent_device": false, "oxygen": false, "dialysis": false, "refrigerated_meds": false },
    "has_car": true,
    "home_type": "site_built",
    "evac_zone": "A"
  },
  "settings": {
    "auto_approve": false,
    "max_etf_sell_cents": 300000,
    "cancel_window_minutes": 120,
    "rebuy_opt_in": false
  },
  "nessie_customer_id": "b3c1...",
  "risk_level": "prepare"
}
```
- `location_source`: `zcta` (the ZIP's centre point) or `gps`.
- `mobility`: `none`, `walker` or `wheelchair`.
- `home_type`: `site_built` or `mobile`.
- `evac_zone`: `A`–`E`, `none` or `unsure`.

### Account (mirrors Nessie)
```json
{ "id": "acc_chk", "nessie_id": "6a1f...", "type": "checking", "nessie_type": "Checking",
  "nickname": "Everyday", "balance_cents": 42000, "balance_synced_at": "2024-10-06T15:00:00Z" }
```
`type` is one of:
- `checking`
- `savings`
- `brokerage_cash`: ETF sale money waiting to settle. It's backed by a Nessie Savings account named
  "Brokerage Settlement (Harbor)".

### Holding (simulated ETFs, real prices)
```json
{
  "symbol": "TBUX",
  "name": "T. Rowe Price Ultra Short-Term Bond ETF",
  "shares": 7.2,
  "shares_micro": 7200000,
  "price_cents": 5012,
  "price_as_of": "2024-10-04T20:00:00Z",
  "price_source": "fixture",
  "value_cents": 36086,
  "cost_basis_cents": 35800,
  "unrealized_gain_cents": 286,
  "lots": [{ "id": "lot_1", "shares_micro": 7200000, "cost_basis_cents": 35800, "acquired": "2023-03-14" }]
}
```
`GET /me/portfolio` returns `{ "total_value_cents", "priced_at", "disclaimer", "holdings": Holding[] }`.
`price_source` is `fixture` or `alpaca_iex`. `shares` is for display only; `shares_micro` is exact.

### Storm status
```json
{
  "server_time": "2024-10-08T21:00:00Z",
  "risk_level": "act",
  "risk_reason": "A hurricane warning is in force for your area.",
  "storm": {
    "id": "al142024",
    "name": "Milton",
    "classification": "hurricane",
    "category": 5,
    "advisory_number": "15",
    "advisory_time": "2024-10-08T21:00:00Z",
    "next_advisory_time": "2024-10-09T00:00:00Z",
    "is_replay": true,
    "headline": "MILTON BACK TO CATEGORY 5 STRENGTH",
    "position": { "lat": 22.7, "lon": -87.5 },
    "max_wind_mph": 167
  },
  "at_your_zip": {
    "ts_wind_probability_5day": 0.86,
    "hurricane_wind_probability_5day": 0.3,
    "in_forecast_cone": true,
    "earliest_ts_winds_eta": "2024-10-09T21:00:00Z",
    "eta_source": "toa_kmz",
    "alerts": [
      { "type": "hurricane_warning", "headline": "Hurricane Warning for FLZ151 (NWS TBW)",
        "issued": "2024-10-07T21:07:00Z", "expires": "2024-10-10T08:57:00Z", "source": "iem" }
    ]
  }
}
```
(These are the real replay values for Maria at advisory 15; the storm surge warning is left out.)
- `storm` is `null` when nothing threatens the ZIP (no active advisory, or the user is `clear`, outside
  the cone, under 5% and without alerts). `at_your_zip` is always present; with no storm it holds zeros,
  `false`, `null` and `[]`.
- `risk_level` and `risk_reason` come from the last scheduler tick (every 2 s in demo mode, and right
  after every `/demo/*` clock change). The forecast numbers are read at `server_time`.
- `classification` is `hurricane`, `tropical_storm`, `tropical_depression`, `post_tropical`,
  `subtropical_storm`, `subtropical_depression` or `potential_tropical_cyclone`. `category` (1–5) is
  `null` below hurricane strength. `advisory_number` has an `A` for intermediate advisories (`"15A"`).
- `headline` is the public advisory's summary line, in NHC's capitals. `position` is the centre at the
  advisory; `max_wind_mph` the maximum sustained wind.
- `eta_source` is `toa_kmz` (NHC's earliest-reasonable arrival product) or `estimate` (when that
  product is missing); `pws_text` is reserved and not produced yet. `earliest_ts_winds_eta` is `null`
  when the ZIP is outside the product's 5% contour.
- Each alert looks like `{ "type", "headline", "issued", "expires", "source": "nws|iem" }`. `type` is
  `hurricane_watch`, `hurricane_warning`, `tropical_storm_watch`, `tropical_storm_warning`,
  `storm_surge_watch`, `storm_surge_warning` or `extreme_wind_warning`. In the replay only the demo ZIPs
  (33602, 34236) have archived alerts; other ZIPs get `[]`.

### Sensor reading
```json
{
  "id": "coops_8726520",
  "source": "noaa_tide",
  "name": "St. Petersburg tide gauge",
  "location": { "lat": 27.7606, "lon": -82.6269 },
  "distance_miles": 18,
  "observed_at": "2024-10-10T03:00:00Z",
  "readings": { "water_level_ft": -1.1, "predicted_ft": 0.9, "surge_ft": -2.0, "pressure_mb": 975.4, "wind_speed_mph": 41 },
  "status": "warning",
  "status_reason": "Water is 2.0 ft below the predicted tide (reverse surge). Stay off the exposed bay floor.",
  "stale": false,
  "attribution": "NOAA CO-OPS"
}
```
**Fields**
- `source` is `noaa_tide`, `usgs_gauge`, `noaa_buoy` or `nws_station`.
- `status` is `normal`, `watch`, `warning` or `stale`.
- River gauges (`usgs_gauge`) add:
  - `readings.stage_ft`
  - `flood_stages: { "action", "minor", "moderate", "major" }` in ft
  - `flood_category`: `none`, `action`, `minor`, `moderate` or `major`
  - `crest_rising` (bool)

**Endpoints**
- `GET /me/sensors?radius_miles=200` returns `SensorReading[]`, closest first.
- `GET /me/sensors/{id}/history?hours=48&metrics=surge_ft,stage_ft` returns rows of
  `{ "observed_at", "readings": {...} }` using the same keys, ready for a chart.

### Plan
The rules engine builds the plan. The AI review (below) explains it.
```json
{
  "id": "pln_19c2",
  "version": 1,
  "status": "awaiting_approval",
  "decided_by": "rules",
  "server_time": "2024-10-06T15:02:00Z",
  "created_at": "2024-10-06T15:02:00Z",
  "storm_id": "al142024",
  "cash_needed_by": "2024-10-08T18:00:00Z",
  "latest_safe_approval_at": "2024-10-07T19:45:00Z",
  "budget": {
    "total_cents": 128000,
    "lines": [
      { "label": "Lodging: Gainesville, 1 room × 3 nights", "amount_cents": 33000, "source": "gsa_per_diem_fy2025" },
      { "label": "Fuel: 262 mi round trip", "amount_cents": 4400, "source": "route" },
      { "label": "Food and water: 2 adults + 1 child, 3 days", "amount_cents": 56100, "source": "gsa_per_diem_fy2025" },
      { "label": "Pet: dog, 3 nights", "amount_cents": 7500, "source": "household" },
      { "label": "Supplies (kit, medicine, chargers)", "amount_cents": 12000, "source": "household" },
      { "label": "Emergency buffer", "amount_cents": 15000, "source": "rules" }
    ]
  },
  "sources": {
    "already_in_checking_cents": 42000,
    "from_savings_cents": 50000,
    "from_etf_sales_cents": 36000
  },
  "shortfall_cents": 0,
  "help_resources": [],
  "moves": [ "...Move objects..." ],
  "alternatives": [
    { "id": "alt_savings_only", "label": "Use more savings instead of selling TBUX", "delta_tax_cents": -1200, "feasible": false, "why_not": "Savings only has $500." }
  ],
  "summary": "Milton could bring tropical-storm winds to Tampa by Wednesday...",
  "tax_note": "Selling 7.18 shares of TBUX realises about $3 of gains.",
  "warnings": ["Rebuying TBUX within 30 days at a loss would trigger the wash-sale rule."],
  "ai": { "source": "template", "model": null, "validated": true }
}
```
**Status lifecycle**

`draft` → `awaiting_approval` → `approved` → `running` → `complete` → `restoring` → `restored`

A plan can also end as `cancelled`, `expired` (the storm turned away) or `superseded` (replaced by a
newer version).

**Fields to know**
- `help_resources[]`: `{ "label", "phone", "url" }` (211, Red Cross, FEMA). Filled in only when
  `shortfall_cents > 0`.
- `ai.source`: `template` for now. The plan's `summary` is always the rules engine's template text;
  the Claude-written explanation lives in `GET /me/plan/review` (its `generated_by` says who wrote it).

### Move
One money action inside a plan.
```json
{
  "id": "mv_03",
  "kind": "sell_etf",
  "status": "scheduled",
  "from": "brokerage",
  "to": "acc_chk",
  "symbol": "TBUX",
  "shares_micro": 7183000,
  "lots": ["lot_1"],
  "price_locked_cents": 5012,
  "amount_cents": 36000,
  "nessie_amount_dollars": 360,
  "rounding_cents": 0,
  "scheduled_for": "2024-10-07T14:00:00Z",
  "expected_available_at": "2024-10-08T13:00:00Z",
  "cancel_deadline": "2024-10-07T13:55:00Z",
  "arrives_late": false,
  "requires_explicit_approval": true,
  "depends_on": [],
  "reverses_move_id": null,
  "why": "Sold Monday so it settles Tuesday (T+1) and reaches checking before you leave.",
  "nessie_object_id": null,
  "nessie_object_type": null,
  "attempts": 0,
  "error": null
}
```
| kind | What it does |
|---|---|
| `transfer` | Savings → checking through a Nessie transfer. Available right away. |
| `sell_etf` | Sells ETF shares. Settles T+1 into `brokerage_cash`, then a Nessie deposit and a transfer move it to checking. |
| `withdraw_cash` | A Nessie withdrawal (a multiple of $20) for cash in hand before ATMs go down. Optional `atm_id`. |
| `defer_bill` | **Bill shield:** moves a Nessie bill due during the storm to after recovery. Adds `bill_id`, `from_date`, `to_date`. |
| `log_purchase` | **Spend log:** records evacuation spending as Nessie purchases. |
| `restore_transfer` | Recovery: unspent money goes back to savings. |
| `rebuy_etf` | Recovery: buys back the sold ETFs (only if `rebuy_opt_in`). |

**Status lifecycle**

`proposed` → `scheduled` → `executing` → `pending_settlement` → `done`

A move can also end as `cancelled` or `failed`. When it fails, `error` is
`{ "code", "message", "retryable" }`.

### Plan review (the AI allocation review)
A suggestion, shown before approval. Every number in it comes from the plan.
```json
{
  "server_time": "2024-10-06T15:02:00Z",
  "plan_id": "pln_19c2",
  "plan_version": 1,
  "label": "Suggestion only – not financial advice",
  "summary": "The plan proposes gathering $1,280 for a 3-night evacuation to Gainesville...",
  "per_source": [
    { "source": "checking", "move_id": null, "amount_cents": 42000, "reasoning": "Already available; used first." },
    { "source": "savings", "move_id": "mv_01", "amount_cents": 50000, "reasoning": "Moves instantly, no tax." },
    { "source": "etf_sale", "move_id": "mv_03", "amount_cents": 36000, "reasoning": "Covers the rest. TBUX is the steadiest holding, so selling it changes your mix least." }
  ],
  "alternatives": [{ "alt_id": "alt_savings_only", "why_consider": "Avoids selling.", "tradeoff": "Not enough in savings." }],
  "risks": [{ "kind": "settlement", "text": "The sale can't run until Monday; approve by Monday 3:45 pm ET." }],
  "double_check": ["Is the $420 in checking already committed to a bill?"],
  "household_notes": [{ "need": "pets", "advice": "Bring a carrier, leash and 7 days of food.", "source_url": "https://www.ready.gov/pets" }],
  "lodging_comments": [{ "lodging_id": "osm_node_123", "comment": "Pet-friendly per OpenStreetMap; call to confirm." }],
  "generated_by": "claude-opus-5-5",
  "validated": true
}
```
- `generated_by` is the model id, or `template`. The template has the same numbers, so the UI can show
  it the same way (with an "Explained by rules" badge instead of "Explained by AI").
- `validated` is always `true`: Claude's text is only used when every number in it is found in the
  plan; otherwise (or after one failed regeneration, a timeout, a refusal, the AI toggle off, or no
  `ANTHROPIC_API_KEY`) the template is returned. A request never waits more than about 20 s.
- The server fills in every amount, `move_id` and `alt_id` from the plan; Claude only writes the
  text fields. `per_source` has one row for checking, one for savings and **one per ETF sale** (for
  example TBUX and TCAF), in the order the money is used. Sales that would settle too late aren't
  listed (they show up in `risks`).
- `household_notes` and `lodging_comments` come straight from the evacuation guide (sourced
  checklists, OpenStreetMap tags) and are empty before the guide exists.
- `risks[].kind` is one of `liquidity`, `tax`, `settlement`, `gouging`, `availability`, `medical` or `other`.
- A Claude review is cached per plan version, so reloading is instant. `404 plan_not_found` when
  there's no active plan.

### Evacuation guide
```json
{
  "server_time": "2024-10-06T15:02:00Z",
  "decision": { "action": "evacuate", "tier": "B", "reason_codes": ["ZONE_A", "CAT4_PLUS"] },
  "leave_by": "2024-10-08T14:00:00Z",
  "destinations": [
    { "id": "gainesville_fl", "name": "Gainesville, FL", "tier": "B", "location": { "lat": 29.65, "lon": -82.32 },
      "drive_time_min_normal": 125, "drive_time_min_evac": 312, "outside_cone": true, "recommended": true },
    { "id": "lake_city_fl", "name": "Lake City, FL", "tier": "B", "location": { "lat": 30.19, "lon": -82.64 },
      "drive_time_min_normal": 160, "drive_time_min_evac": 400, "outside_cone": true, "recommended": false }
  ],
  "chosen": "gainesville_fl",
  "route": {
    "provider": "ors",
    "distance_mi": 131.0,
    "drive_time_min_normal": 125,
    "drive_time_min_evac": 312,
    "drive_time_note": "Evacuation estimate (normal time plus up to 5 hours of traffic); traffic during Milton was severe.",
    "cone_overlap_pct": 18,
    "corridor": "I-75 N (Emergency Shoulder Use active)",
    "steps": [{ "text": "Head north on N Florida Ave", "distance_mi": 0.4 }],
    "links": { "google": "https://www.google.com/maps/dir/?api=1&origin=27.95,-82.46&destination=29.65,-82.32&travelmode=driving", "apple": "https://maps.apple.com/?saddr=27.95,-82.46&daddr=29.65,-82.32&dirflg=d" },
    "attribution": "© openrouteservice.org by HeiGIT | © OpenStreetMap contributors"
  },
  "shelters": [
    { "id": "hc_burnett_ms", "name": "Burnett Middle School", "kind": "general", "status": "open",
      "pets": "yes", "ada": "unknown", "capacity_left": null, "distance_mi": 14.2,
      "location": { "lat": 27.98, "lon": -82.30 }, "source": "curated: hcfl.gov 2024-10-08", "links": { "google": "..." } }
  ],
  "lodging": {
    "band": "standard",
    "nights": 3,
    "rooms": 1,
    "nightly_estimate_cents": 11000,
    "estimate_source": "GSA per diem FY2025, Gainesville, October",
    "options": [
      { "id": "osm_node_123", "name": "Example Motel", "type": "motel", "pets": "unknown", "wheelchair": "yes",
        "location": { "lat": 29.66, "lon": -82.33 }, "source": "osm", "note": "Estimated cost. Call to confirm availability.", "links": { "google": "..." } }
    ]
  },
  "checklists": [
    { "need": "everyone", "items": ["1 gallon of water per person per day", "Phone chargers", "Copies of IDs"], "source_url": "https://www.ready.gov/kit" },
    { "need": "kids", "items": ["Comfort items", "Snacks", "Medicines"], "source_url": "https://www.ready.gov/kit" },
    { "need": "pets", "items": ["Carrier", "Leash", "7 days of food", "Vaccination records"], "source_url": "https://www.ready.gov/pets" }
  ],
  "advice_cards": [
    { "kind": "price_gouging", "title": "Price gouging is illegal during a declared emergency", "text": "Screenshot quotes. Report: 1-866-9-NO-SCAM." },
    { "kind": "official_orders", "title": "Follow local officials", "text": "If officials say evacuate, go." }
  ],
  "explanation": null
}
```
Value sets:
- `pets`, `ada` and `wheelchair`: `yes`, `no`, `unknown` or `call_to_confirm`. Never show "unknown" as "yes".
- `decision.action`: `evacuate`, `shelter_in_place` or `use_public_shelter`.
- `route` is `null` when `has_car` is false. In that case, `advice_cards` holds the county transport details.

### Map layers
`GET /me/map` returns every layer as GeoJSON, ready to draw:
```json
{
  "server_time": "2024-10-06T15:02:00Z",
  "layers": {
    "home":         { "type": "FeatureCollection", "features": [ { "type": "Feature", "geometry": { "type": "Point", "coordinates": [-82.4572, 27.9506] }, "properties": { "label": "Home" } } ] },
    "cone":         { "type": "FeatureCollection", "features": [ "...Polygon, properties.advisory..." ] },
    "track":        { "type": "FeatureCollection", "features": [ "...LineString (kind: line) + forecast Points (kind: point), see below..." ] },
    "route":        { "type": "FeatureCollection", "features": [ "...LineString, properties.distance_mi, corridor..." ] },
    "destinations": { "type": "FeatureCollection", "features": [ "...Point, properties.id, name, recommended..." ] },
    "shelters":     { "type": "FeatureCollection", "features": [ "...Point, properties.id, name, status, pets, ada..." ] },
    "lodging":      { "type": "FeatureCollection", "features": [ "...Point, properties.id, name, type, pets..." ] },
    "atms":         { "type": "FeatureCollection", "features": [ "...Point, properties.source = osm|nessie, in_cone..." ] },
    "sensors":      { "type": "FeatureCollection", "features": [ "...Point, properties.id, source, status, label..." ] }
  },
  "attribution": ["NOAA NHC", "NOAA CO-OPS", "USGS", "© OpenStreetMap contributors", "© openrouteservice.org by HeiGIT"]
}
```
**Rules for each layer**
- An empty layer is an empty `FeatureCollection`, never `null`.
- Colour sensor dots by `properties.status`.
- Use the `id` in `properties` to match a map item to its card.
- `home`: one Point, `properties { id: "home", label: "Home", zip, location_source }`.
- `cone`: the current advisory's 5-day cone, one Polygon, `properties { advisory, storm_id, name, issued_at }`.
  Empty when no advisory is active.
- `track`: one LineString (`properties { kind: "line", advisory }`) and one Point per forecast time
  (`properties { kind: "point", advisory, tau_h, valid_time, intensity_kt, max_wind_mph, category,
  storm_type, label }`). `label` is NHC's local-time label, e.g. `"4:00 PM Tue"`; use `valid_time` for logic.
- `route`, `destinations`, `shelters`, `lodging`, `atms` and `sensors` are empty until their roadmap blocks land.
- `attribution` lists only the sources behind the layers that have data.

### ATM
```json
{ "id": "osm_atm_991", "source": "osm", "name": "ATM (Bank of America)", "location": { "lat": 28.54, "lon": -81.38 },
  "address": "123 Example Ave, Ocala, FL", "distance_miles": 84, "in_forecast_cone": false,
  "on_evacuation_route": true, "amount_left_cents": null, "accessibility": "unknown" }
```
- Florida ATMs come from OpenStreetMap (`source: osm`).
- Nessie's own ATMs (`source: nessie`, with `amount_left_cents`) are all in VA, MD and DC.

### Bill (mirrors Nessie)
```json
{ "id": "bill_44", "nessie_id": "...", "payee": "Sunshine Auto Insurance (demo)", "amount_cents": 18900,
  "due_date": "2024-10-15", "original_due_date": "2024-10-09", "deferred": true,
  "status": "pending", "in_storm_window": true }
```

### Event (activity feed and live updates)
```json
{ "id": "evt_88", "at": "2024-10-06T15:00:00Z", "type": "risk_changed",
  "message": "Risk raised to PREPARE: Milton's wind chance at your ZIP reached 23%.",
  "data": { "from": "monitor", "to": "prepare" } }
```
`type` is one of:
- **Risk and storm:** `risk_changed`, `advisory_issued`, `sensor_alert`, `recovery_hold`
- **Plan:** `plan_created`, `plan_updated`, `plan_approved`, `plan_complete`, `plan_expired`, `plan_restoring`, `plan_restored`
- **Moves:** `move_scheduled`, `move_done`, `move_failed`, `move_cancelled`
- **Bank:** `balance_changed`, `bank_mode_changed`
- **Evacuation:** `evacuation_updated` (for example, a shelter filled up)
- **Demo:** `clock_tick`, `demo_reset`

Live in this build: `advisory_issued`, `risk_changed`, `recovery_hold`, `plan_created`,
`plan_approved`, `plan_complete`, `plan_expired`, `plan_restoring`, `plan_restored`, `move_done`,
`move_failed`, `move_cancelled` and `demo_reset`. Treat any other `type` as a generic feed item.

**The live stream** (`GET /me/events/stream?token=...`, Server-Sent Events; `?user_id=` in demo mode):
- Each event is one `data:` line holding the Event JSON above. There is **no `event:` field**, so
  listen with `onmessage` and switch on `data.type`.
- The SSE `id` is the event's sequence number (`id: 1042`), not the `evt_...` id. The browser sends it
  back as `Last-Event-ID` when it reconnects, and the stream first replays every stored event after
  it, oldest first, then continues live. (An `evt_...` id is accepted there too.) A fresh connection
  without `Last-Event-ID` starts with new events only, so load `GET /me/events` first.
- The first frame is a `: connected` comment with `retry: 3000` (reconnect after 3 s). While idle the
  server sends a `: ping` comment every 15 s. `EventSource` ignores comments.
- Events appear on the stream the moment they're saved, including those from the scheduler and
  `/demo/*` calls.
- Up to 5 open streams per user; a 6th closes the oldest (the browser then reconnects it).
- An unknown `user_id` gets `401 user_not_found` before the stream starts.

## Endpoints

### Accounts
| Method | Path | Does |
|---|---|---|
| `POST` | `/auth/signup` | Body: `email`, `password` (8–128 characters), `name`, `zip`, optional `location` and `household` (as in `POST /users`). Creates the account, the Nessie customer, accounts and starter portfolio. Returns **`201`** `{ token, token_type: "bearer", expires_at, user }`. `409 email_taken` if the email (case-insensitive) is registered; `400 zip_not_supported`; `422` for a bad email or short password. The email and password stay in Harbor; Nessie only sees a pseudonym. |
| `POST` | `/auth/login` | Body `{ email, password }`. Returns `{ token, token_type, expires_at, user }`. A wrong password and an unknown email both return `401 invalid_credentials` (so nobody can test which emails exist). After 5 wrong passwords in 15 minutes: `429 too_many_attempts` for 15 minutes. |
| `POST` | `/auth/logout` | Ends the current token. `204`. |
| `GET` | `/auth/me` | The logged-in `User` (same as `GET /me`). |
| `POST` | `/auth/demo-login?persona=maria` | **Demo mode only.** A token for a demo persona (`maria` or `ruth`), so the website uses the same Bearer login for judges. |

Store the token in memory or `sessionStorage`. Send it on every call, and on `401 invalid_token`
go back to the login screen.

### Users, household and money
| Method | Path | Does |
|---|---|---|
| `GET` | `/zip/{zip}` | `{ zip, city, state, lat, lon }`, or `400 zip_not_supported` (PO-box ZIPs, and anything outside Florida for now). A ZIP that isn't 5 digits is a 422. Use it to preview during onboarding. |
| `POST` | `/users` | **Demo mode only** (`403 demo_mode_only` in live mode; real accounts use `POST /auth/signup`). A user without a password, used with `X-User-Id`. Body: `name`, `zip`, optional `location` (`{lat, lon}`; sets `location_source: "gps"`), optional `household` (any field left out takes the default: 1 adult, no children/pets, `has_car: true`, `evac_zone: "unsure"`). Creates the Nessie customer, the three accounts and a starter ETF portfolio (the same sample balances and lots as Maria). Returns **`201`** with the `User`. Nessie gets a pseudonym, never the user's real name. |
| `GET` / `PATCH` | `/me` | Read or update the user. `PATCH` body (all optional): `name`, `zip` (moves `location` to the new ZIP's centre), `location` (`{lat, lon}`), `settings` (send only the keys that change). Returns the `User`. |
| `PATCH` | `/me/household` | Update the household; send only the fields that change. Returns the `User`. This will re-run the plan and the evacuation guide once those exist. |
| `GET` | `/me/accounts` | `Account[]` (checking, savings, brokerage_cash) with live Nessie balances. If Nessie is unreachable, the last balances read come back with their older `balance_synced_at`; show "as of". |
| `GET` | `/me/portfolio` | Holdings (see Holding). |
| `GET` | `/me/bills` | `Bill[]`, with `in_storm_window` flagged. |
| `GET` | `/me/atms?radius_miles=150` | `ATM[]`, ones outside the cone and on the route first. |

### Storm, sensors and map
| Method | Path | Does |
|---|---|---|
| `GET` | `/me/storm` | Storm status for the user's ZIP. |
| `GET` | `/me/sensors?radius_miles=200` | `SensorReading[]`. |
| `GET` | `/me/sensors/{id}/history?hours=48&metrics=...` | Chart rows. |
| `GET` | `/me/map` | Every map layer (see Map layers). |

### Plan and AI review
| Method | Path | Does |
|---|---|---|
| `GET` | `/me/plan` | `{ "plan": Plan }`, or `{ "plan": null }` when there's no plan. |
| `GET` | `/me/plan/review` | The `PlanReview` for the current plan version (see Plan review). `404 plan_not_found` without a plan. |
| `POST` | `/me/plan/edits` | Body `{ "alt_id": "..." }` or `{ "changes": [{ "op", "path", "value" }] }`. The engine re-runs, so this returns the new `Plan` (version + 1) and a fresh review follows. |
| `POST` | `/me/plan/approve` | Body `{ "plan_version": 1 }`. Moves become `scheduled`. A `409 plan_version_stale` means the plan changed since you loaded it. |
| `POST` | `/me/plan/cancel` | Cancels every move that hasn't run yet. |
| `POST` | `/me/plan/moves/{move_id}/cancel` | Cancels one move before its `cancel_deadline`. |
| `POST` | `/me/plan/explain` | Body `{ "question", "move_id"? }`. Returns `{ server_time, category, answer, ai: { source, model, validated }, suggested_questions[] }` (see Explain below). Max 500 characters (`422`), 10 per minute per user (`429 rate_limited` with a `Retry-After` header in seconds). `404 plan_not_found` without a plan, `404 move_not_found` for a `move_id` that isn't in it. Personal investment-advice questions get a fixed refusal. |
| `GET` | `/me/plans` | Past plans. |
| `GET` | `/me/plans/{id}/report` | The post-storm wrap-up, available once a plan is `restored`: what was moved, spent, restored and rebought, plus the tax note. |

**Explain** (`POST /me/plan/explain`)
```json
{
  "server_time": "2024-10-06T15:05:00Z",
  "category": "plan_explanation",
  "answer": "Checking and savings come first because they cost nothing. The rest comes from selling $358.20 of TBUX ...",
  "ai": { "source": "claude", "model": "claude-opus-5-5", "validated": true },
  "suggested_questions": ["When do I need to approve the plan by?", "Why take some of it out as cash?", "What happens if I cancel?"]
}
```
- `category` is `plan_explanation`, `general_education` (T+1, tax lots, wash sales),
  `personal_advice_request` or `off_topic`.
- `personal_advice_request` ("Should I put the leftover in Tesla?", "Is TCAF a good fund?") always
  gets the same fixed text: *"Harbor can explain what this plan does and why, but it can't give
  personal investment advice. A licensed adviser can help with that."* `off_topic` also gets fixed text.
- With AI off or failing, a template answers from the plan (`ai.source: "template"`, `model: null`).
  Same numbers, plainer words.
- `move_id` (optional) asks about one move; the answer uses that move's amount, timing and reason.

### Evacuation
| Method | Path | Does |
|---|---|---|
| `GET` | `/me/evacuation` | The evacuation guide, or `{ "guide": null }` before `prepare`. |
| `POST` | `/me/evacuation/destination` | Body `{ "destination_id" }` or `{ "custom": { "lat", "lon", "label" } }`. This re-runs the route, the lodging and the plan budget. |

### Activity and live updates
| Method | Path | Does |
|---|---|---|
| `GET` | `/me/events?limit=50&before=evt_80` | `Event[]`, newest first. `limit` is 1–200 (default 50). `before` is the `id` of the oldest event you have; you get the ones older than it. `404 event_not_found` for an unknown `before`. |
| `GET` | `/me/events/stream?token=hbr_...` | Server-Sent Events. Each `Event` arrives as `data:` JSON, so read the `data.type` field. It reconnects automatically and replays from `Last-Event-ID`. Details under Event. |

### Demo
| Method | Path | Does |
|---|---|---|
| `GET` | `/demo/storms` | `[{ id, name, year, landfall_at, description, demo_zips, start, end, advisories }]`. `start` is where `/demo/start` puts the clock, `end` is when the replay's storm is gone, `advisories` is how many there are. |
| `POST` | `/demo/start` | Body (optional) `{ "storm": "milton-2024", "speed": 1800 }`; `speed` is storm seconds per real second (default 1800, max 86400). Moves the clock to the replay start and runs it, and puts every user's risk level back to `clear` (then evaluates it at once). Balances, plans and the feed are untouched; call `/demo/reset` first for a fresh run. Returns the `/demo/clock` body. `404 storm_not_found` for an unknown storm. |
| `POST` | `/demo/advance` | Body: exactly one of `{ "hours": 6 }` (0–240), `{ "to": "next_advisory" }` or `{ "to_risk": "shelter" }` (the first moment any user is at that level; nothing moves if someone already is). Keeps the clock running or paused as it was. Every advisory and alert crossed on the way is evaluated in order, so the feed shows each change at its real replay time. Returns the `/demo/clock` body. Errors: `409 demo_not_started`, `409 no_more_advisories`, `409 risk_level_not_reached` (the clock doesn't move), `422 validation_error`. |
| `POST` | `/demo/pause` · `/demo/resume` | Pauses (`paused_reason: "manual"`) or resumes the clock. Returns the `/demo/clock` body; `409 demo_not_started` before `/demo/start`. |
| `POST` | `/demo/persona` | Body `{ "persona": "maria" }` (default) or `{ "persona": "ruth" }`. Seeds the demo user and returns the `User`. **Maria** (33602 Tampa): 2 adults, a child, a dog, a car. **Ruth** (34236 Sarasota): two seniors in a mobile home, no car, home oxygen, so she gets shelters and transport instead of a route. Safe to call again: it returns the same user and repairs missing Nessie data. |
| `POST` | `/demo/ai` | Body `{ "enabled": false }`. The "AI offline" toggle: the review and explain switch to their templates; the numbers stay identical. Returns `{ enabled, ai }` where `ai` is `ok` only if the toggle is on **and** `ANTHROPIC_API_KEY` is set (same as `/health.ai`). It lasts until the server restarts. |
| `POST` | `/demo/reset` | Puts every account, the portfolio and the plan back to the starting state, clears the activity feed (leaving one `demo_reset` event) and resets the clock. Returns `{ ok, server_time, users_reset, clock }` (`clock` has the `/demo/clock` shape). User ids stay the same; Nessie account ids change. |
| `GET` | `/demo/clock` | `{ running, storm, now, speed, paused_reason }`. `paused_reason` is set to `awaiting_approval` when the clock pauses for approval. Before `/demo/start` the clock waits paused at the replay start: `running: false`, `storm: null`, `now: "2024-10-06T03:00:00Z"`. |

Every `/demo/*` route returns `403 demo_mode_only` when the backend runs with `HARBOR_MODE=live`.

## Health
`GET /health` → `{ "ok": true, "mode": "demo", "nessie": "ok|degraded|fake|missing_key", "nhc": "ok|replay", "ai": "ok|off", "clock": "..." }`

`nessie: ok` means the seeded customer was found. A wrong Nessie key returns an empty bank, not an
error, so the backend checks this explicitly; `degraded` covers a wrong key, an unseeded bank and an
outage. `missing_key` means `NESSIE_API_KEY` isn't set. The check is cached for 30 seconds.

`ai: ok` means Claude can be called: `ANTHROPIC_API_KEY` is set and the `/demo/ai` toggle is on.

## Changelog

- **H2–8 backend (2026-10-17):** `POST /users` returns `201`; documented the `PATCH /me` and
  `PATCH /me/household` bodies, the `401` auth codes, the bank error codes, the `/demo/reset` response,
  the clock before `/demo/start`, `403 demo_mode_only`, and `nessie: missing_key` in `/health`. No
  existing field changed. `docs/openapi.json` is regenerated with `python tools/export_openapi.py`.
- **H8–14 backend (2026-10-17):** `GET /me/storm`, `GET /me/map`, `GET /demo/storms`, `POST /demo/start`,
  `/demo/advance`, `/demo/pause` and `/demo/resume` are live on the Milton replay. The Storm status
  example now uses real replay values. Added fields: `storm.headline`, `storm.position`,
  `storm.max_wind_mph`; `start`, `end` and `advisories` on `/demo/storms`. Documented: `at_your_zip` is
  always present, `category` is `null` below hurricane strength, the classification and alert type
  values, the `cone`/`track`/`home` properties (`intensity_kt` and `max_wind_mph` on track points), the
  `/demo/*` clock responses and error codes. The scheduler writes `advisory_issued`, `risk_changed`
  and `recovery_hold` events. **Heads-up for the demo script:** in the real archive Tampa's wind chance
  is already 50% at Milton's first advisory and 68% at the replay start, so Maria goes `clear → act`
  on `/demo/start`, then `shelter` at 2024-10-09T09:00Z and `recover` at 2024-10-10T08:57Z. She never
  passes through `monitor` or `prepare`.
- **H36–40 backend (2026-10-17):** `GET /me/events`, `GET /me/events/stream` (SSE), `GET /me/plan/review`,
  `POST /me/plan/explain` and `POST /demo/ai` are live. Documented the stream (SSE `id` = event
  sequence number, `Last-Event-ID` replay, `: connected` / `: ping` comments, 5 streams per user),
  the feed's `limit`/`before` and `404 event_not_found`, the review rules (server-filled amounts, one
  `per_source` row per ETF sale, caching, template fallback) and the explain response with its error
  codes (`429 rate_limited` + `Retry-After`, `404 move_not_found`). Added `server_time` to the review
  and explain bodies. `/health.ai` now also follows the toggle. The Plan's `ai.source` stays
  `template`: the Claude text lives in the review, not in a `plan_updated` event.
