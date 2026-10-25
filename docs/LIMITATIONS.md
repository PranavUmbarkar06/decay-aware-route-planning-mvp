# Limitations and risks

This is a research prototype. Read these before using any output.

## Evidence and users
- **Dispatcher, supervisor and NGO needs have not been validated by interviews.** Every stakeholder difficulty comes
  from published studies (decks; Evidence screen). The system recommends; people decide.
- No real trip-level spoilage or rerouting data exists publicly (brief S9). The operations layer is designed to start
  producing it; nothing in this repo is field data yet.

## Simulation
- **Pre-registered result:** the quality-aware policy did **not** beat the static baseline in any season. It lowered
  wastage in summer and monsoon but raised unmet demand in every season (redirecting saleable produce to processing);
  winter was worse on both. Sensitivity and post-hoc variants showed the same trade-off. Simulation output, not
  field-validated.
- Supply lots are synthetic (seeded). Planned destinations follow each day's realised arrivals (A24), which gives the
  baseline implicit demand knowledge (ADR-023).
- Congestion and disruptions are modelled assumptions (A9), never observed traffic. No traffic source was found.
- Decay: cold-storage reference lives (UC Davis, USDA HB66) extrapolated to ambient heat with FAO's generic curve
  (A2, A3) plus an assumed within-lot spread (A17). The plausibility check flags tomato (simulated 23.7% vs 3.25%
  NABCONS market-level); NABCONS "market level" is not a transit-loss figure anyway.
- Value weights for market / NGO / processing outcomes (A29) and the market-room forecast drive the policy's
  trade-off; they are assumptions.
- No target reduction is claimed. The deck's 14% figure is provisional and unsourced and is not used.

## Data
- Agmarknet arrivals come from manual owner exports (captcha, ADR-015); only Nagpur and Chandrapur districts report the
  pilot crops; orange has no arrivals May–Aug (off-season, "not reported" is not zero).
- 21 of 57 markets await location review; town centroids stand in for market yards.
- OSM has 2 NGO and 3 processing features in the division; capacities are unknown everywhere.
- Weather is one gridded point per district (not in-truck temperature). Census populations are from 2011.
- Most road speeds (94% of edges) are class defaults (A7).

## Product
- Auth is a dev stub (codes on screen). No SMS/WhatsApp provider is connected.
- HI/MR strings are machine drafts awaiting native review.
- The Postgres/PostGIS `docker-compose.yml` and `Dockerfile` were **not built or tested** (no Docker on the build
  machine). The SQLite demo path is tested.
- The rate limiter is in-process (single instance); multi-instance needs a shared store.
- Lighthouse (mobile, measured 2026-10-25 on localhost): welcome page Performance 82, Accessibility 100, Best
  Practices 82 (HTTP only on localhost), SEO 100; evidence page Performance 76 (layout shift when data loads).
  Lighthouse 12 no longer reports a PWA category, so no PWA score is claimed.
- Free Open-Meteo API and OSM public tiles are for non-commercial use (owner confirmed non-commercial research).
- Food-donation safety/liability and data-protection compliance need review by qualified people (COMPLIANCE_TODO).
