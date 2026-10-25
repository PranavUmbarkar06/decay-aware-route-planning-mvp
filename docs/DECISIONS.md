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

(Further ADRs are appended per phase.)
