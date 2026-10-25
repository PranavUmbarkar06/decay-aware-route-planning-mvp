# Architecture Decision Records

Format: context → options → decision → consequences. "Default" means chosen by the agent per the
project brief (Section 4) and open to override by the project owner. Status values: Accepted / Proposed
/ Superseded.

---
## ADR-001 Pilot geography (D1): Accepted (default, owner to confirm)
- **Options:** (a) Nagpur Division only; (b) Nashik→Pune/Vashi only; (c) both.
- **Decision:** (a). Districts: Nagpur, Wardha, Bhandara, Gondia (spelled "Gondiya" in Agmarknet 2.0),
  Chandrapur, Gadchiroli. The six names were checked against the Agmarknet 2.0 district master on
  2026-10-24; OSM boundaries are fetched in Phase 2. Geography is a config block (`config/geography.yaml`).
- **Why:** the submitted Round-1 deck commits to Nagpur and tomato/orange/onion; two regions would double
  the data audit.
- **Consequences:** Nashik/Pune/Vashi examples from the feature list appear only as illustrative copy.

## ADR-002 Frontend (D2): Accepted
- **Options:** Streamlit · Next.js · React+Vite PWA. **Decision:** React + Vite + TypeScript + Tailwind,
  installable PWA. **Why:** big-tap mobile UI, offline queue and camera QR scanning. **Cost:** more code
  than Streamlit.

## ADR-003 Backend (D3): Accepted
- **Options:** Flask · FastAPI · Django. **Decision:** FastAPI + SQLAlchemy 2 + Alembic. Typed, auto
  OpenAPI, and it imports the Python simulation directly.

## ADR-004 Database (D4): Accepted
- **Decision:** SQLite for `make demo`; Postgres/PostGIS via `docker-compose.yml` with the same SQLAlchemy
  models. No PostGIS-specific SQL in v1 (geometry stays as lat/lon columns + GeoJSON files), so both
  engines run the same code. Docker is **not installed on the build machine**, so the compose file is
  written but **not tested here** (recorded in LIMITATIONS).

## ADR-005 Simulation code (D5): Accepted
- **Decision:** No team simulation code was found in `inputs/` (only a deck-generator script). The
  simulation is built per the solution deck (S5, S7, S8) behind the interfaces in the project brief §6.
  If team code appears later, it is wrapped as an alternative `SimulationEngine` behind the same interface.

## ADR-006 Maps (D6): Accepted
- **Decision:** MapLibre GL JS with a configurable raster tile URL (`config.yaml: map.tile_url`). The
  default is the OSM standard tile server, **for dev/demo only**, and attribution is always visible.
  The OSM tile usage policy discourages heavy use; production needs its own or a paid tile source.

## ADR-007 Routing (D7): Accepted
- **Decision:** OSMnx/NetworkX graph, precomputed and cached. No live traffic: congestion is a seeded,
  modelled ASSUMPTION input and never shown as observed traffic.

## ADR-008 Weather (D8): Accepted
- **Decision:** Open-Meteo historical archive replay (`archive-api.open-meteo.com/v1/archive`) for
  simulation; a forecast adapter interface with a stub.
- **Terms (read 2026-10-24 at https://open-meteo.com/en/terms):** the free API is for non-commercial use
  only (limits: <10,000 calls/day, 5,000/hour, 600/min); data is licensed CC BY 4.0, so attribution is required.
- **Owner confirmation (2026-10-25):** the project owner confirmed this is a non-commercial research
  project, so the free API is used. Attribution "Weather data by Open-Meteo.com (CC BY 4.0)" is shown
  wherever weather-derived values appear.
- **Revisit trigger:** any commercial use (subscriptions, advertising, paid pilots) needs an Open-Meteo
  paid plan or another source before launch.

## ADR-009 ML (D9): Accepted
- **Decision:** rules/physics first (Q10-form decay). An optional gradient-boosted surrogate trained on
  *simulation output* sits behind the `features.ml_surrogate` flag and is always labelled
  "simulation-trained surrogate, not field-validated".

## ADR-010 Auth (D10): Accepted
- **Decision:** phone + OTP. In demo/dev, a stub provider returns the OTP in the API response and logs it;
  the UI shows a persistent "DEV AUTH" banner. SMS provider is an adapter interface (INTEGRATIONS_TODO).

## ADR-011 Languages (D11): Accepted
- **Decision:** i18n scaffolding with EN, HI and MR. HI and MR strings are machine-drafted by the agent
  and every key is flagged `needs_native_review`. No claim of translation accuracy.

## ADR-012 Blockchain (D12): Accepted
- **Decision:** no blockchain. An append-only, SHA-256 hash-chained custody log is called a
  "tamper-evident log" everywhere.

## ADR-013 Product name (D13): Accepted
- **Decision:** `product_name` in `config/config.yaml`, default "Impact Tank Post-Harvest Platform
  (working title)"; logo is a placeholder SVG.

---
## ADR-014 Task runner without GNU make: Accepted
- **Context:** the build machine (Windows 11) has no `make` and no Docker.
- **Options:** require make via MSYS/choco; PowerShell script; Python task runner.
- **Decision:** `tasks.py` is the single source of truth for targets. `Makefile` delegates every target
  to it, so `make demo` == `python tasks.py demo`.

## ADR-015 Agmarknet arrivals are captcha-gated: do not automate: Accepted
- **Context:** Agmarknet 2.0 (go-live 2025-11-07 per its own filter metadata) is a React app backed by
  `api.agmarknet.gov.in/v1/`. The public "Daily Price and Arrival Report" page requires a captcha before
  fetching data (observed 2026-10-24). The filter/master endpoint (`/daily-price-arrival/filters`:
  states, districts, markets, commodities) loads without a captcha. robots.txt allows `/`.
- **Options:** (a) reverse-engineer an uncaptcha'd endpoint for the same data; (b) solve captchas
  automatically; (c) fetch master data only, ingest **human-downloaded** report exports, plus a data.gov.in
  API adapter that activates when the owner registers a key.
- **Decision:** (c). (a) and (b) would circumvent bot-detection and are not done.
- **Consequences:** M4 Crowd Meter and the demand proxy show "no data" until real exports or a
  data.gov.in key are supplied. The demo uses SYNTHETIC_DEMO arrivals with the DEMO badge.

## ADR-016 Python 3.11 venv: Accepted
- Python 3.11.9 from the Windows launcher; the MSYS `python` in Git Bash has no pip. All versions are
  pinned in `requirements.lock.txt`.

## ADR-017 Road classes for the truck network: Accepted
- **Context:** the full drivable OSM network of a ~51,000 km² division (area computed from the OSM
  district polygons) is very large; inter-market trucks run on the main road classes.
- **Decision:** keep motorway → tertiary (+ links) (`geography.yaml: road_classes`); business nodes join
  via a snapped access leg whose length uses the A8 detour factor. **Consequence:** village-level last-mile
  roads are not modelled.

## ADR-018 Temperature–decay model: Accepted
- **Options:** constant Q10 (2–3) from a reference shelf life; FAO 152 Table 1 curve; ML.
- **Decision:** FAO Table 1 relative-velocity curve (log-linear interpolation, held constant outside
  0–40 °C) applied to each crop's cited reference life (`commodities.yaml`). Constant Q10 = 2 and 3 runs
  give optimistic/pessimistic bounds. The curve itself is sourced; applying it to these crops and
  extrapolating cold-storage lives to ambient temperatures is an ASSUMPTION (A2, A3) shown on every output.
- **Reference lives chosen:** tomato 8 d @ 10 °C (UC Davis, citation only); onion 6 mo @ 0 °C (HB66);
  orange 12 wk @ 1 °C (HB66 maximum → optimistic).

## ADR-019 Pilot commodities stay as the deck says: Accepted (owner, 2026-10-25)
- Owner instruction: stick to the solution deck. Pilot commodities are **tomato, Nagpur orange, onion**.
  Potato arrivals (owner export) are ingested and flagged `in_pilot_commodity = False`; nothing uses them.
- Orange has no arrivals export yet (DATA_GAPS); M4 shows "no data" for orange until one is supplied.

## ADR-020 Pinned data windows: Accepted
- The weather archive window is pinned (2025-11-01 → 2026-10-18) in code instead of "today minus N", so
  `python tasks.py data` is reproducible. Extending it is a deliberate edit plus `--refresh`.

## ADR-021 OSM via Geofabrik extract instead of Overpass: Accepted
- **Context:** on 2026-10-25 three public Overpass instances timed out / returned 502–504; one answered a tiny
  query in 80 s with data dated 2026-07-28. overpass-api.de asks automated/high-volume users to self-host.
- **Options:** keep retrying Overpass; run a local Overpass; download a Geofabrik regional extract.
- **Decision:** Geofabrik `india/western-zone` .osm.pbf (211 MB, data to 2026-10-24), filtered locally with
  pyosmium in one pass (1 min 42 s), then OSMnx for simplification and cleaning. Fresher data and no load on shared
  services. **Cost:** ~95% buffer coverage (neighbouring-state strip missing); large raw file kept out of git
  (manifest + checksum committed).

## ADR-022 Market geocoding by rule, review-gated: Accepted
- Agmarknet provides no coordinates. Markets are matched to OSM features/places in their own district by documented
  rules with a confidence score (GRAPH_BUILD.md). Below 0.6 or a snap distance over 2 km → `needs_review` and
  excluded from routing until the owner reviews. Town centroids stand in for market yards (documented per node).

## ADR-023 Post-hoc exploratory simulation variants (deviation log): Accepted
- **When:** 2026-10-25, after engineering runs on the dev seed (seed 1, March window; outside the registered seeds/seasons)
  and **before any registered experiment run**.
- **Observation:** on the dev window the pre-registered QualityAwareDynamic policy was worse than the baseline. Diagnosis
  found no accounting bug, but two properties of the registered design: (1) planned destinations are drawn from each
  day's *realised* arrival shares (A24), so the baseline implicitly knows the day's demand; (2) the registered policy
  persists the current temperature into the future, so afternoon heat makes it over-predict overnight decay.
- **Decision:** the primary comparison runs **unchanged, as pre-registered**, and is reported as it comes out. Three
  variants are run as `EXPLORATORY_POSTHOC` and never enter the decision rule: plans drawn from forecast shares; a
  diurnal temperature forecast (yesterday's same-hour temperatures); both.
- **Also fixed before registered runs (engineering bug, not a design change):** the demand forecast had no history before
  the window; it now sees the 14 days of real Agmarknet arrivals before the window (as a crowd meter would).

## ADR-024 Business clock vs security clock: Accepted
- There is no live weather feed (ADR-008). In demo mode the **business clock** starts at
  `runtime.demo_clock_utc` (inside the Open-Meteo replay window) and advances in real time, so shelf-life uses replayed
  real temperatures and countdowns behave normally. JWT/OTP expiry always use the real clock. Outside demo mode the
  business clock is the real clock and temperatures outside the replay fall back to district monthly means
  (ASSUMPTION, flagged on every prediction). The UI shows a "Demo clock" indicator.

## ADR-025 Rescue broadcast in waves with a single atomic claim: Accepted
- A broadcast is offered to the nearest `rescue.wave_size` eligible NGOs at once; the first claim wins through a
  conditional UPDATE on the broadcast row (works identically on SQLite and Postgres). Unclaimed waves and expired claim
  timers cascade to the next wave. Real NGOs' capabilities are never invented: only NGOs that enter a profile (or
  fictional demo NGOs) are eligible, so with no profiles the broadcast is EXHAUSTED and says so.

(Further ADRs are appended per phase.)
