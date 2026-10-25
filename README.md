# Impact Tank Post-Harvest Platform (working title)

A research prototype for perishable produce (tomato, Nagpur orange, onion) in the **Nagpur Division, Maharashtra**:

- **Decision layer:** a simulation-led, quality-aware routing assistant compared against a static shortest-path
  baseline (Round-1 solution deck).
- **Operations layer:** QR traceability with two-party handovers and a tamper-evident log, a 1-tap wastage logger,
  shelf-life traffic lights (FEFO), a mandi crowd meter, NGO rescue with a claim timer, and redistribution matching.
  The operations layer is meant to produce the trip-level data that the decks found does not exist publicly.

> **Read first:** every impact number is a **simulation output, not field-validated**. In the pre-registered
> experiment the quality-aware policy **did not beat** the static baseline (less waste in summer/monsoon, more unmet
> demand everywhere). Dispatcher needs have **not** been validated by interviews. See `docs/LIMITATIONS.md`.

## Run the demo (no Docker, SQLite, committed data)

Requirements: **Python 3.11**, **Node 22** (npm 10), Git. No API keys are needed.

```bash
git clone <this repo> phl && cd phl
python tasks.py setup
python tasks.py demo
```

Then open **http://localhost:8000** (API docs: http://localhost:8000/api/docs). Start with **Guided demo**
(`/demo`): it signs in as fictional demo personas and walks through the whole story. Sign-in codes are shown on
screen (DEV AUTH); demo phone numbers are `+910000000001` (farmer) … `+910000000007` (analyst).

`make <target>` works the same where GNU make exists (`make demo` = `python tasks.py demo`). On Windows use
`python tasks.py …` (or `py -3.11 tasks.py …`). `setup` creates `.venv` with Python 3.11 and runs `npm ci`.

## Everyday commands
| Command | What it does |
|---|---|
| `python tasks.py test` | Backend unit, property, API, RBAC, pipeline and simulation tests (offline) |
| `python tasks.py e2e` | Playwright E2E on an isolated stack (port 8001, uses local Chrome) |
| `python tasks.py lint` / `typecheck` / `honest-check` / `audit-deps` | Quality gates (also run in CI) |
| `python tasks.py data` | Re-fetch sources (cache-first; `--refresh` to re-download) and regenerate DATA_SOURCES/DATA_GAPS |
| `python tasks.py graph` | Rebuild the road graph, `nodes.csv`, `edges.csv`, OD matrix and `reports/graph_report.html` (needs the 211 MB OSM extract on first run) |
| `python tasks.py graph-apply-review` | Apply your decisions from `inputs/node_review.csv` |
| `python tasks.py experiments --set primary\|sensitivity\|exploratory\|all` | Run simulation experiments (primary = pre-registered) |
| `python tasks.py report` | Regenerate `reports/simulation_report.html` |
| `python tasks.py load` | (Re)build the demo database from the CSVs (idempotent) |

Postgres/PostGIS: `docker compose up` (see `docker-compose.yml`). **Not tested here** (no Docker on the build machine).

## What is real, synthetic or assumed
| Data | Status |
|---|---|
| Roads (OSM via Geofabrik), district boundaries, weather replay (Open-Meteo), Agmarknet market list and owner-exported arrivals, NABCONS benchmarks, Census 2011 | Real (provenance per row) |
| Demo people, demo lots, "Demo NGO 1 DEMO", "Demo Cold Store 1 DEMO", simulation supply lots | Synthetic (DEMO badge everywhere) |
| Truck speeds without OSM maxspeed, congestion, thresholds, decay extrapolation, simulation behaviour | Assumptions (`docs/ASSUMPTIONS.md`) |

## Documentation
`docs/CONTEXT.md` (the decks) · `DECISIONS.md` (ADRs) · `ASSUMPTIONS.md` · `DATA_SOURCES.md` / `DATA_GAPS.md`
(generated) · `GRAPH_BUILD.md` · `ARCHITECTURE.md` · `SECURITY.md` · `LIMITATIONS.md` · `COMPLIANCE_TODO.md` ·
`INTEGRATIONS_TODO.md` · `DEMO_SCRIPT.md` · `PROGRESS.md` · `FINAL_REPORT.md` · data columns in `data/processed/README.md`.

Attribution: road data © OpenStreetMap contributors (ODbL); weather data by Open-Meteo.com (CC BY 4.0); market data
Agmarknet 2.0 (DMI, MoA&FW). Licence for this repository: **placeholder** (see `LICENSE`; the owner has not chosen one).
