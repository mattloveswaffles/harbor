# Harbor 48-hour roadmap

Two people: **B** = backend (FastAPI), **F** = frontend (Next.js). **S** marks a sync point where you
both stop and connect your parts. The design is in [DESIGN.md](DESIGN.md); the contract is in [API.md](API.md).

## Schedule

| Hours | Backend (B) | Frontend (F) |
|---|---|---|
| H0–2 | Repo layout, `.env.example`, **Nessie probe** (`tools/probe_nessie.py`), API v1.1 | Next.js app, `openapi-fetch` typed client, MSW mocks built from API.md |
| **S1 · H2** | Agree contract v1.1 together | |
| H2–8 | Config, SQLite, Clock, error envelope, CORS, `/health`, NessieClient + FakeNessie, seed Maria, `POST /users`, `/me`, `/me/accounts`, export `openapi.json` | Onboarding (ZIP, household), dashboard shell by risk level, SSE hook, `/demo` judge panel |
| H8–14 | Milton replay build, forecast source, `risk.py` + table tests, `/me/storm`, `/me/map` (cone, track, home), `/demo/*`, scheduler tick | Map (react-leaflet): cone, track, home. Storm card, demo clock |
| **S2 · H14** | F switches user/accounts/storm/demo calls to the real backend. **Milestone: the replay walks the risk levels on screen** | |
| H14–20 | `calendar.py`, destination picker (fixture cities + GSA rates feed the lodging budget line), budget, waterfall, tax lots, `plan.build`, executor, EventBus/SSE, approve/cancel | Plan screen: budget, money sources, move timeline, countdowns, approve/cancel. Activity feed |
| H20–26 | Sleep, staggered (F H20–25, B H21–26) | |
| H26–32 | Sensors (CO-OPS St. Pete, Alafia River) + risk integration + recovery hold. Prices + portfolio. Settlement deposit → transfer | Sensor dots on the map, tide and river charts, portfolio page |
| **S3 · H32** | **Milestone: full Milton run from clear to recover against real Nessie** | |
| H32–36 | **Evacuation guide:** route (ORS + precomputed fixture), shelters (curated), lodging (OSM + GSA), household checklists, `/me/evacuation`, map layers for route/shelters/lodging, `leave_by` | Evacuation page: route line on the map, destination picker, shelter and hotel cards with needs badges, "Open in Maps" buttons, checklists |
| H36–40 | **AI:** `PlanReview` + validator + template, edits loop, `/explain` + refusal, wrap-up report. Restore/rebuy, bill shield | Review panel ("Suggestion only"), "Decided by rules / Explained by AI" badges, explain drawer, recover screen + report |
| **H40** | **FEATURE FREEZE: bug fixes only after this** | |
| H40–44 | Deploy (Railway, always on, 1 worker), `test_demo_e2e`, pre-warm the AI cache, test with AI offline and with FakeNessie | Deploy (Vercel), local fallback, banners for degraded services |
| H44–46 | **Rehearse 3×**: deployed, local only, and with all fallbacks on. Time it to 3:00 | |
| H46–48 | Devpost write-up, record a backup demo video, submit | |

## Hour-1 checklist (backend)

- [ ] Get a Nessie key (log in to nessieisreal.com with GitHub → Profile) and put it in `backend/.env`
- [ ] Run `tools/probe_nessie.py` and write the answers into DESIGN.md §1.8
- [ ] Get a free OpenRouteService key and an api.data.gov key (GSA per diem)
- [ ] Get an Anthropic API key; check that `messages.parse` works with `claude-opus-5-5`
- [ ] Agree API v1.1 with F (S1)

## Scope

**Must-have**
- Milton replay + DemoClock
- risk engine
- plan engine (transfer, ETF sale with T+1, cash withdrawal)
- real Nessie writes + reconcile
- approve/cancel
- SSE
- map with cone and route
- CO-OPS + Alafia recovery hold
- Maria's destination, route, shelters and lodging
- AI review with validator and template
- explain refusal
- restore
- FakeNessie
- runs locally

**Stretch**
- bill shield
- spend log
- NDBC buoy
- rebuy with wash-sale choice
- OSM ATMs on the map
- Google Places price levels
- wrap-up report
- second persona (an older couple with no car, to show the household logic)
- live mode
- ESP32 community barometer

**Cut first if behind, in this order:**
1. second persona and live mode
2. rebuy
3. NDBC
4. bill shield
5. spend log
6. wrap-up report
7. explain chat (keep the review)
8. deployment

**Never cut:** the recovery hold, real Nessie moves, the AI validator and Maria's evacuation guide.
These four carry the three tracks.

## 3-minute demo script

Setup: the `/demo` panel beside Maria's dashboard, replaying `milton-2024`.

| Time | Beat | Track |
|---|---|---|
| 0:00 | **The problem.** 1 in 4 Americans couldn't afford to evacuate. Maria in Tampa has $420 in checking and a T. Rowe ETF portfolio. "Replay of Milton, real NOAA data." | Nessie, T. Rowe |
| 0:20 | **The storm appears.** The cone draws on the map; risk goes clear → monitor → prepare ("wind chance at your ZIP reached 23%"). | context |
| 0:45 | **Plan + AI review.**<br>• About $1,313 budget: Valdosta lodging (GSA $110 × 3 nights), fuel for the 461 mi round trip, food, dog, buffer.<br>• Money comes from checking → savings → TBUX sale.<br>• Weekend gap: "sells Mon, settles Tue, approve by Mon 15:45".<br>• The review explains each source and offers "use savings instead of selling".<br>• "Should I buy Tesla?" is refused.<br>• With AI offline, the numbers stay identical. | T. Rowe |
| 1:20 | **Evacuation guide.**<br>• Route line to Valdosta, GA via I-75 N, with a `leave_by` time. Harbor skipped Orlando and Gainesville: Sunday's real cone covered them.<br>• A pet-friendly shelter; motels in budget, each marked "call to confirm".<br>• Kid and pet checklist.<br>• A shelter flips to "full". | Sensors for Good |
| 1:50 | **Act.** Approve. Live over SSE, each with its Nessie ID:<br>• Nessie transfer<br>• ETF sale → settlement deposit → transfer<br>• $320 cash withdrawal | Nessie |
| 2:15 | **Shelter.** Wind passes 39 mph, so all money moves freeze. Reverse surge −2 ft at St. Pete: "stay off the exposed bay floor". | Sensors |
| 2:35 | **Premature all-clear blocked.** NHC alerts have ended, but the Alafia is still rising toward its 24.36 ft crest (major flood is 19 ft), so the cash stays. Sunday 13 Oct the river is out of major flood and falling: recover, restore to savings, wrap-up line. | Sensors, Nessie |
| 2:55 | **Close.** "Rules decide, you approve, AI explains, real sensors keep you safe." | all |
