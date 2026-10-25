# Final report: Impact Tank Post-Harvest Platform (working title), prototype v0.1.0

Date: 2026-10-25. 15 commits, phases 0–8 (`docs/PROGRESS.md` has every gate).

## 1. How to run (tested from a clean clone)
```bash
git clone <repo> phl && cd phl
python tasks.py setup      # Python 3.11 venv from requirements.lock.txt + npm ci   (3.5 min, verified)
python tasks.py demo       # SQLite + committed data → http://localhost:8000
```
- App: **http://localhost:8000** · Guided demo: `/demo` · API docs: `/api/docs` · health: `/healthz`, `/readyz`.
- Demo personas (fictional): `+910000000001` farmer … `+910000000007` analyst; sign-in codes appear on screen (DEV AUTH).
- `make <target>` = `python tasks.py <target>` (no GNU make on Windows). Tests: `python tasks.py test`, `python tasks.py e2e`.
- Verified on 2026-10-25: clean clone → setup → demo → `/readyz` ready (171 nodes); guided-demo E2E passed against the
  clone's server; the clone's test run surfaced one issue (fixed in b72c01f).

## 2. What is real vs synthetic vs assumed
| Dataset | Rows | Provenance |
|---|---|---|
| Agmarknet market list (6 districts) | 57 | REAL_FETCHED (captcha-free master endpoint) |
| Agmarknet arrivals (owner exports: tomato, onion, orange, potato) | 4,452 rows → 3,989 market-days | REAL_FETCHED → REAL_DERIVED |
| Road network (OSM, Geofabrik extract 2026-10-24) | 22,644 edges · 9,677 nodes | REAL_DERIVED (94% of edge speeds are class-default ASSUMPTIONS) |
| Business nodes | 170 | 100 REAL_FETCHED (57 markets, 38 storage, 3 processing, 2 NGO), 69 ASSUMPTION (town origin proxies), 1 SYNTHETIC_DEMO (+1 demo cold store at load) |
| OD matrix | 21,170 pairs | REAL_DERIVED (free-flow model) |
| Weather replay (Open-Meteo, 6 points, 2025-11-01 → 2026-10-18) | 50,688 hours | REAL_FETCHED |
| NABCONS loss table (PIB 2151371) · FAO 152 Table 1 · reference shelf lives · Census 2011 | 54 · 5 · 3 · 6 | REAL_FETCHED |
| Demo people, demo lots, Demo NGO 1, Demo Cold Store 1, simulation supply lots | n/a | SYNTHETIC_DEMO (badged everywhere; excluded from experiments) |
| Thresholds, speeds, congestion, decay extrapolation, simulation behaviour | A1–A29 | ASSUMPTION (`docs/ASSUMPTIONS.md`) |

## 3. Data gaps and the manual steps you must do
From `docs/DATA_GAPS.md` (generated): **MISSING**: hub/cold-storage capacity, mandi capacity (so the crowd meter is
"arrivals vs 14-day median", never "% full"), per-capita consumption norms, traffic/disruption data. **RESTRICTED**:
data.gov.in API (no key). **PARTIAL**: Agmarknet arrivals (only Nagpur and Chandrapur districts report the pilot crops;
orange has none May–Aug), crop profiles (cold-storage lives only), OSM POIs (sparse). **UNVERIFIED**: context evidence
cited via the brief (WRI, RBI, NCCD not re-fetched).

Your manual steps:
1. **Review 24 flagged places** (21 markets incl. APMC Kamthi and Parshiwani, which report real arrivals): copy
   `reports/nodes_needing_review.csv` → `inputs/node_review.csv`, add `reviewer` + `decision`, run
   `python tasks.py graph-apply-review` then `python tasks.py load`. Open `reports/graph_report.html` to check them on a map.
2. **More Agmarknet exports** (optional): same report page, other dates/crops → drop CSVs in `inputs/`.
3. **data.gov.in key** (optional, prices only): when the portal works, put `DATAGOV_API_KEY` in `.env`.
4. **Choose a licence** for the repo (`LICENSE` is a placeholder) and a product name (`config/config.yaml`).
5. Before any pilot: set `PHL_JWT_SECRET`, connect an SMS provider (`docs/INTEGRATIONS_TODO.md`), restore the OTP limit to
   5/min, get the legal reviews in `docs/COMPLIANCE_TODO.md`, get HI/MR strings reviewed by native speakers.

## 4. Decisions made (override any of these)
D1 Nagpur Division only · D2 React+Vite PWA · D3 FastAPI+SQLAlchemy+Alembic · D4 SQLite demo / Postgres compose
(compose **untested**) · D5 no team simulation code found, built from the deck · D6 MapLibre, OSM tiles dev-only ·
D7 OSMnx graph, no live traffic · D8 Open-Meteo replay (you confirmed non-commercial research) · D9 rules first, ML
surrogate not built · D10 OTP dev stub · D11 EN/HI/MR with review flags · D12 hash chain, not blockchain · D13 placeholder
name. Plus ADR-014…025, notably: **ADR-015** Agmarknet captcha is never automated; **ADR-019** pilot crops stay as the
deck (tomato, orange, onion; potato ingested but unused); **ADR-021** Geofabrik instead of Overpass; **ADR-022**
review-gated market geocoding; **ADR-023** deviation log for post-hoc variants; **ADR-024** business vs security clock.

## 5. Known limitations and risks (full list: `docs/LIMITATIONS.md`)
- **No validated user needs:** dispatcher, supervisor and NGO needs have not been checked in interviews.
- **No real trip-level data:** the simulation runs synthetic lots on real roads, weather and market volumes.
- **Pre-registered result is negative:** QualityAwareDynamic did **not** beat StaticShortestPath in any season.
  - Summer wastage 12.1% → 6.2%, but unmet demand 12.1% → 24.0%.
  - Monsoon wastage 11.1% → 6.4%, unmet demand 11.1% → 19.4%.
  - Winter is worse on both: wastage 2.8% → 5.0%, unmet demand 2.8% → 22.8%.
  - Same pattern in the 4 sensitivity variants and 3 post-hoc variants.
  - **Simulation output, not field-validated.** No reduction is claimed; the deck's 14% target is not used.
- **Decay levels are uncertain:** reference shelf lives are cold-storage values extrapolated to ambient heat.
  Simulated tomato loss is 23.7% vs NABCONS market-level 3.25%, which the plausibility check flags.
- **Congestion is modelled, not observed.**
- **Licensing:** the free Open-Meteo API and public OSM tiles are non-commercial only; OSM-derived CSVs are ODbL (share-alike).
- **Reviews still needed:** HI/MR translation, food-donation safety and liability, data protection.
- **Untested deployment path:** Docker/Postgres. The rate limiter is single-instance only.

## 6. Test results (actual output, `reports/final/test_results.txt`)
```
ruff: All checks passed! · mypy: no issues in 37 files · honest-claims check: 0 violations
pytest: 105 passed  (unit, Hypothesis property tests for mass balance / non-negativity / chain / single location,
                     tamper detection incl. tail deletion, 6-thread confirm race, RBAC matrix, PIN lockout, M3–M7,
                     pipelines on recorded raw responses, simulation determinism + mass balance)
vitest: 6 passed (incl. provenance lint: SYNTHETIC_DEMO always badged)
tsc + eslint: clean · npm audit: 0 vulnerabilities · pip-audit: no known vulnerabilities
playwright (Pixel 7, Chrome): 10 passed (onboarding ×4 roles, QR handshake via code+PIN, wastage + undo,
                     two NGOs claim at once → one wins, offline handover → sync, guided demo, evidence page)
Reproducibility: registered summer/seed-101 runs re-executed in a fresh process match recorded event-log SHA-256.
Graph: rebuild byte-identical nodes.csv / edges.csv; all §9A checks pass.
```
**Lighthouse 12.8.2** (mobile, localhost, measured):
- **/welcome:** Performance 82, Accessibility 100, Best Practices 82 (HTTP only on localhost), SEO 100.
- **/evidence:** Performance 76 (layout shift when data loads).
- Lighthouse 12 has no PWA category, so no PWA score is claimed. Installability is provided by the manifest and service worker.

## 7. Next steps from prototype to pilot
1. **Interview 10–15 dispatchers, supervisors and NGO coordinators** in Nagpur and Chandrapur mandis. Test the
   hypotheses tagged HYPOTHESIS · VALIDATE and which signals people actually use.
2. **Rethink the routing objective before field use.** The simulation shows the current value weights (A29) trade
   waste for unmet demand. Make the trade-off explicit (or a dispatcher choice), re-register, and re-run.
3. **Field data collection with the operations layer** at 2–3 collection centres:
   - handover weights and timestamps;
   - wastage reasons;
   - a few temperature loggers in trucks.

   This produces the trip-level data that calibrates decay (A2, A3, A17, A18) and speeds (A7).
4. **Pilot site selection:** markets that report to Agmarknet and have reviewed locations, plus at least one NGO
   partner willing to share capacity.
5. **Approvals and partners:**
   - APMC / market committee consent;
   - NGO agreements and the food-donation legal review;
   - data-protection review;
   - SMS provider and template registration;
   - a licensed weather source if any commercial use.
6. Before any pilot: translation review, accessibility testing with real users in sunlight and with gloves, HTTPS
   deployment, and Postgres tested.
