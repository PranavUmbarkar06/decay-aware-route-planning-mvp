# Changelog

## 0.1.0 (2026-10-25): first prototype
- Data pipelines with provenance + audit (Agmarknet master + owner exports, OSM via Geofabrik, Open-Meteo, FAO 152,
  NABCONS via PIB, USDA HB66, Census 2011); generated DATA_SOURCES / DATA_GAPS.
- Road graph and generated nodes.csv / edges.csv (Nagpur Division) with validation and review loop.
- Domain model with invariants; tamper-evident custody log; M1–M7 APIs; Alembic migrations.
- Pre-registered simulation: quality-aware policy did not beat the static baseline (see reports/simulation_report.html).
- Installable PWA: onboarding, operations screens, route advisor, Simulation lab with live dashboard, guided demo.
