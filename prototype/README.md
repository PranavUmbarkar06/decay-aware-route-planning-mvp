# Saleable Routes: India-wide crop-aware routing (prototype v2)

One routing engine, three crop sensitivity profiles (grapes, tomatoes, onions), one objective: more saleable produce
per truck. Routes run on real OpenStreetMap roads across India. Traffic, disruptions and shipment outcomes are
simulated and labelled as such. The Nagpur-only v1 demo is preserved at git tag `v1-nagpur-demo`.

## Run it

```bash
.venv/Scripts/python.exe -m uvicorn platform_api.api.main:app --port 8010
```
```bash
npm --prefix prototype run dev
```
Open http://localhost:5173. Vite proxies `/api`, `/tiles` and `/geo` to the API on port 8010.

```bash
.venv/Scripts/python.exe -m pytest platform_api/tests -q
```

## Rebuild the data (one-off, about 20 minutes)

| Step | Command | Output |
|---|---|---|
| India road graph | `python -m pipelines.v2.india_roads` | `data/processed/india/{nodes,edges}.parquet`, `graph_stats.json` |
| Map tiles (render only) | `python -m pipelines.v2.render_tiles` | `data/processed/india/render/roads.pmtiles` |
| Markets + arrivals | `python -m pipelines.v2.markets_india` | `markets.parquet`, `arrivals_daily.parquet`, `states/districts.geojson` |

The pipelines need two inputs:
- `data/raw/geofabrik_india/india-latest.osm.pbf`, the Geofabrik India extract (1.7 GB, MD5-checked; see its MANIFEST).
- The Agmarknet all-India exports in `data/raw/agmarknet_manual_exports/`.

## What is where

- **`platform_api/engine/`**: the single source of truth for every calculation.
  - `deterioration.py`: Arrhenius decay, vibration, handling and grading. Mechanisms multiply, so nothing is counted twice.
  - `routing.py`: crop-weighted Dijkstra over the India graph, candidate routes, time-aware evaluation, disruptions, and the decision rule ("continue" unless the gain beats ₹500 or 1% of cargo value).
  - `decision.py`: dispatcher decision windows. It works out when a disruption matters, the diversion points, the point of no return and the decision deadline (PNR minus the communication, acknowledgement and manoeuvre buffers).
  - `batch.py`: the India-wide simulation over real Agmarknet corridors, with seeded synthetic conditions.
- **`platform_api/alerts.py`**: the alert state machine, earliest-deadline-first queue, workload warnings, hysteresis and driver messages (English, Hindi, Marathi, Telugu). Nothing is rerouted without approval and acknowledgement.
- **`config/crops_v2.yaml`**: crop profiles. Every value is tagged SOURCED (with citation) or ASSUMPTION.
- **`prototype/src/`**: the React app with six sections and the dispatcher rail. `map/IndiaMap.tsx` draws roads by zoom level: national highways from zoom 4, state highways from 6, primary and secondary from 8, links from 11. Route overlays are visible at every zoom.

## Data labels used in the UI

- **Mapped road**: OSM geometry and class.
- **Historical**: Agmarknet arrivals and prices, Nov 2025 to Oct 2026. Arrival volume is not demand.
- **Sourced**: a cited coefficient.
- **Assumption**: an illustrative coefficient awaiting calibration.
- **Simulated**: traffic, disruptions, batch results and projected wastage.

## Known limits

- **Road coverage:** motorway to secondary roads only, which is 581,000 km. Origins off that network connect by an access leg.
- **Road roughness:** about 96% of edges use road-class defaults, because OSM rarely tags surface or smoothness in India.
- **Coefficients:** vibration, humidity and handling values are illustrative. Shipment outcomes are recorded to calibrate them.
- **Market locations:** 237 of 1,507 markets resolve only to a district centre and are shown as approximate. Five terminal markets are hand-placed (`config/market_overrides.yaml`) and need verifying.
- **Speed:** `/optimise` takes 0.4–2 s on most corridors and about 5 s for Kolar→Delhi (2,000 km).
