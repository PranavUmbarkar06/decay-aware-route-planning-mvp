# Architecture

```
            ┌──────────────────── data pipelines (Python, offline-capable, cache-first) ─────────────────────┐
 sources →  │ fetch_agmarknet · fetch_boundaries · fetch_weather · fetch_references · fetch_census ·            │
            │ fetch_datagov (key-gated) · osm_extract (Geofabrik .pbf) → build_graph → audit                    │
            └───────────── data/raw (immutable + MANIFEST) → data/processed (CSV, provenance per row) ───────────┘
                                             │  python tasks.py load
                                             ▼
 ┌──────────────── backend (FastAPI, SQLAlchemy 2, Alembic) ────────────────┐      ┌──── frontend (PWA) ────┐
 │ api/        routes_core (auth, M1, M2, sync) · routes_ops (M3–M7, lab,     │ HTTP │ React 19 · Vite · TS   │
 │             evidence, admin)                                               │◄────►│ Tailwind · MapLibre    │
 │ services/   custody · wastage · shelf_life · crowd · rescue · advisor      │ SSE  │ i18next (EN/HI/MR)     │
 │ domain/     model (invariants) · hashchain · pin · decay   (pure Python)  │      │ IndexedDB sync queue   │
 │ simulation/ network · scenario · engine · policies · runner · report      │      │ service worker (shell) │
 │ core/       config (strict) · db · security (OTP/JWT/RBAC) · ratelimit ·  │      └────────────────────────┘
 │             clock (business vs security) · provenance                      │
 │ models/     ORM (SQLite demo / Postgres via compose)                       │
 └────────────────────────────────────────────────────────────────────────────┘
```

## Layers and rules
- **Domain** (`backend/app/domain`) is pure Python: consignment and node operations, the invariants (mass balance,
  non-negative, chain verifies, single location), the hash chain, PIN logic and the decay model. It is shared by the
  simulation and the services and is property-tested.
- **Services** apply the same state transitions to the database inside one transaction each. Concurrency uses an
  optimistic `version` column and conditional UPDATEs (handover confirm, rescue claim): identical on SQLite and Postgres.
- **Adapters** for everything external sit behind interfaces with stubs: OTP sender (dev stub only), notifications
  (in-app only; SMS/WhatsApp stubs), weather (replay; forecast adapter not implemented), tiles (configurable URL),
  data.gov.in (key-gated). See INTEGRATIONS_TODO.md.
- **Simulation** reads only the committed CSVs (edges, graph_nodes, nodes, arrivals, weather) so it runs from a clean
  clone; every exogenous random draw is generated once per (season, seed) and shared by both policies.
- **Clocks:** business clock (demo: starts inside the weather replay window) vs security clock (real) (ADR-024).
- **Provenance** travels with every datum to the UI; SYNTHETIC_DEMO always renders a DEMO badge (tested).

## Observability
Structured JSON logs with request ids (`X-Request-ID`), `/healthz`, `/readyz` (DB + nodes loaded), an append-only
audit log of every state change, OpenAPI docs at `/api/docs`.

## Security headers
`Content-Security-Policy` (self + configured tile host; CDN only for API docs/report pages), `X-Content-Type-Options`,
`X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` (camera/geolocation self). See SECURITY.md.
