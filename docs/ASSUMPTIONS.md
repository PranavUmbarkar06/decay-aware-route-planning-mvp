# Assumptions register

Every parameter we chose (provenance `ASSUMPTION`) is listed here with its rationale and a
needs-validation flag. All of them need validation; none is taken from a source. Values live in
`config/*.yaml`, which is the source of truth; this file explains them.

| # | Assumption | Value (config) | Rationale | How to validate |
|---|---|---|---|---|
| A1 | Traffic-light thresholds on predicted remaining saleable life | Red < 24 h, Yellow 24–72 h, Green ≥ 72 h (`thresholds.yaml`) | User spec left a gap between "3+ days" and "24–48 h"; closed with contiguous bands | Confirm with warehouse operators |
| A2 | Applying FAO Table 1 (generic crop) to tomato/orange/onion | `commodities.yaml: temperature_model` | Only cited temperature curve available; FAO notes crop-specific rates differ | Field temperature + quality logs from M1/M2 |
| A3 | Extrapolating cold-storage reference lives to 25–40 °C ambient | tomato 192 h @10 °C, orange 2016 h @1 °C, onion 4380 h @0 °C | Only cited lives found are at optimal storage temperatures | Same as A2; compare with NABCONS market-level plausibility |
| A4 | Tomato ripeness at dispatch = firm-ripe | tomato reference life | Ripeness is not observed in any data | Supervisor grade/ripeness capture in M1 |
| A5 | Orange reference life is the HB66 maximum ("up to 12 weeks") | 2016 h | No lower bound given → **optimistic**; US sweet orange ≠ Nagpur mandarin | Local study / field data |
| A6 | Handling damage per 100 km | tomato 1%, orange 0.5%, onion 0.2% | Placeholder, no measured value | CRUSHED events per km from M2 logs |
| A7 | Class-default truck speeds when OSM has no `maxspeed`; 60 km/h cap | `speeds.yaml` | Conservative for laden trucks; not sourced | Scan timestamps between nodes (M1) |
| A8 | Access-leg detour factor 1.3 and 20 km/h | `speeds.yaml: access_leg` | Typical rule-of-thumb choice, not sourced | GPS traces |
| A9 | Congestion/disruption = seeded random multipliers by road class and hour | (Phase 4 config) | No traffic source (DATA_GAPS) | Real adapter if a licensable source appears |
| A10 | Weight-mismatch tolerance before DISPUTED_WEIGHT | 2% (`config.yaml: handover`) | Placeholder | Scale accuracy at actual handover points |
| A11 | Crowd-meter glut warning ratio | arrivals > 1.3 × trailing 14-day median | Placeholder | Back-test against Agmarknet price dips |
| A12 | NGO "safe window" shown = 50% of model remaining life | `config.yaml: rescue.safety_margin_frac` | Conservative margin, not a food-safety standard | Food-safety review (COMPLIANCE_TODO) |
| A13 | Matching weights road time / life margin / capacity fit | 0.4 / 0.4 / 0.2 | Placeholder | NGO interviews |
| A14 | Quality thresholds: saleable ≥ 0.5, processing ≥ 0.25 | `thresholds.yaml: quality` | Placeholder mapping of the 0–1 score | Grade outcomes at sale |
| A15 | One weather point per district represents the whole district | `weather_points.csv` | Archive is gridded; trucks cross districts | Higher-resolution sampling along routes |
| A16 | Demand proxy (see DATA_GAPS: consumption norms MISSING) | Phase 4 | No cited per-capita norm | Field data / cited norm |

## Wastage reasons with no simulation driver (M2)

The decay model's drivers are temperature × time (→ `HEAT_ROT`) and handling distance (→ `CRUSHED`).
The decks define **no driver** for:
- `WET` (wet/moisture): **logged-only** until a driver is defined (precipitation is in the weather
  replay, but no cited relation between rain exposure and loss was found).
- `UNSOLD` (unsold at market): a **demand-side outcome**, not decay. It feeds M5 rescue and redirection
  and the unmet-demand side of the simulation, never the decay model.
