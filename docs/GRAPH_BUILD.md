# Graph build (`nodes.csv`, `edges.csv`)

`nodes.csv` and `edges.csv` **were not supplied**; they are generated, reproducibly, by:

```bash
python tasks.py graph
```

That runs `pipelines/osm_extract.py` (cache-first) → `pipelines/build_graph.py` → `pipelines/audit.py`.
Outputs: `data/processed/{nodes,edges}.csv`, `data/processed/geo/{nodes,edges_simplified}.geojson`,
`data/processed/graph_meta.json`, `data/cache/graph.graphml`, `data/cache/od_matrix.parquet`,
`reports/graph_report.html`, `reports/nodes_needing_review.csv`. The CSVs are never hand-edited.

## Source and versions (build of 2026-10-25)
- OSM data: Geofabrik `asia/india/western-zone-latest.osm.pbf` (OSM data up to 2026-10-24T20:20:51Z per
  Geofabrik's page; downloaded 2026-10-25T06:44Z; checksum in `data/raw/geofabrik_india_western_zone/MANIFEST.json`).
  © OpenStreetMap contributors, ODbL 1.0: attribution is required, and the generated CSVs are a derived
  database (share-alike).
- Why not Overpass (ADR-021): three public instances timed out or returned 502/504 on 2026-10-25, one answered a
  tiny query in 80 s with data from 2026-07-28, and the main instance asks automated users to self-host.
- Coverage: the Western Zone polygon covers 100% of the division and ~95% of the 5 km buffer; the remaining
  buffer strip lies in neighbouring states (in the Central/Southern Zone extracts, not downloaded).
- Libraries: OSMnx 2.1.1, NetworkX 3.6.1, pyosmium 4.3.2, GeoPandas 1.2.0 (all pinned in `requirements.lock.txt`).

## Road graph
| Step | Result |
|---|---|
| Highway ways intersecting division bbox + 5 km | 15,596 ways → 456,420 nodes / 871,774 directed segments |
| Classes kept (ADR-017) | motorway, trunk, primary, secondary, tertiary (+ `_link`) |
| `ox.simplify_graph` (length and time summed) | 11,182 nodes / 25,950 edges |
| Clip to division polygon + 5 km buffer | −1,229 nodes / −2,909 edges (outside pilot geography) |
| Remove self-loops | −6 edges (closed ways collapse to loops after simplification) |
| Remove zero-length edges | 0 |
| Keep largest strongly connected component | −276 nodes / −391 edges (stubs cut at the extract edge, isolated fragments, one-way dead ends) |
| **Final** | **9,677 nodes / 22,644 directed edges; 1 strongly connected component; 0 isolates** |

Directionality follows OSM tags: `oneway=yes|true|1` forward only, `oneway=-1` reversed, roundabouts one-way unless
`oneway=no`; everything else is two-way.

**Speeds** (`speed_source` per edge): OSM `maxspeed` when numeric (capped at the 60 km/h laden-truck cap,
ASSUMPTION A7), otherwise the class default from `config/speeds.yaml` (ASSUMPTION). Result: 21,210 edges
`class_default_ASSUMPTION`, 1,204 `osm_maxspeed`, 230 `mixed` (simplified edges spanning both). No edge falls outside
the plausible 5–120 km/h range; outliers would be flagged in `speed_flag`, never clipped.

## Business nodes
| Type | How it is built | Count (real / demo) | Needs review |
|---|---|---|---|
| ReceivingMarket | Agmarknet market that reports pilot-commodity arrivals in the owner's exports | 9 / 0 | 2 |
| AssemblyMandi | Other Agmarknet markets in the six districts | 48 / 0 | 19 |
| FarmGatherPoint | OSM `place=city|town` nodes inside the division: **origin proxies, not real collection centres** (ASSUMPTION) | 69 / 0 | 3 |
| TransitStorageNode | OSM `industrial=cold_storage`, name ~ "cold storage/शीतगृह", `building=warehouse`, `industrial=warehouse` | 38 / 0 | 0 |
| ProcessingSink | OSM `industrial=food_industry|food`, `man_made=works`+`product~food`, name ~ "food processing/agro industries" | 3 / 0 | 0 |
| NGOSink | OSM `office=ngo|charity`, `social_facility=food_bank|soup_kitchen`, `amenity=food_bank` | 2 / **1 DEMO** | 0 |

OSM coverage of NGOs and processors is, as expected, very sparse. Demo nodes ("Demo NGO 1 DEMO") are added only to
reach a minimum of 3 NGO / 2 processing / 3 storage nodes for the demo; they sit on real graph nodes, carry
`provenance=SYNTHETIC_DEMO`, have fictional names and are excluded from any metric labelled real.

Equivalent Overpass QL of the POI filters (for reference; the build uses the local extract):
```
[out:json];
area["name"="Nagpur"]["admin_level"]->.a;   // repeat per district relation in district_boundaries.geojson
( nwr["industrial"~"^(cold_storage|warehouse|food_industry|food)$"](area.a);
  nwr["building"="warehouse"](area.a);
  nwr["office"~"^(ngo|charity)$"](area.a);
  nwr["social_facility"~"^(food_bank|soup_kitchen)$"](area.a);
  nwr["amenity"~"^(food_bank|marketplace)$"](area.a);
  nwr["name"~"cold stor|शीतगृह|APMC|Krishi Utpan|Bazar Samiti|market yard|mandi",i](area.a); );
out center;
```

### Market geocoding rules (`geocode_confidence`)
Agmarknet gives market labels, not coordinates. No coordinate is hand-typed.
1. Parse the town token: `APMC <town>`, `<town>(<locality>)`, or the operator town of private markets.
2. **0.85 `osm_tag`**: a unique OSM marketplace/APMC feature in the same district whose name contains the town.
3. **`agmarknet_name_match`** to an OSM place inside the market's district polygon (town centroid used as a
   proxy for the market yard): city/town **0.65**, village 0.55, hamlet 0.45; −0.1 if fuzzy (difflib ≥ 0.85);
   −0.15 if several same-rank candidates; private markets capped at 0.45 (the site is unknown).
4. **0.45 transliteration suggestion**: skeleton match tolerant of Marathi romanisation (w/v, ao/au→av, h,
   vowels), e.g. Savner→Saoner, Varora→Warora, Pavani→Pauni. Always below the review threshold.
5. Otherwise no location (APMC Tiroda in this build).

`needs_review = confidence < 0.6 or snap distance > 2,000 m or no location`. **Result: 36 of 57 markets are
routable; 21 await review** (7 with transliteration suggestions). Flagged nodes are excluded from routing, the UI
says why, and they are listed in `reports/nodes_needing_review.csv`.

## Snapping and OD matrix
Each node snaps to the nearest graph node (haversine BallTree); `snap_distance_m` is stored. The access leg adds
`snap_distance × 1.3` metres at 20 km/h (ASSUMPTION A8). `data/cache/od_matrix.parquet` holds free-flow travel time and
road distance for all ordered pairs of routable business nodes (21,170 pairs, `policy=free_flow_static`).

## Validation (brief §9A step 5): all pass in this build
One strongly connected component; no isolated nodes; no duplicate node/edge ids; no zero/negative lengths; no
self-loops; speeds within range (0 flagged); every row has `provenance` + `source_manifest_id`; every routable
business node reaches ≥1 receiving market and ≥1 NGO/processing sink (5 real sinks available). Results are
written to `graph_meta.json` and the report; `python tasks.py test` asserts the CSV schemas.

**Reproducibility:** rebuilding from the same raw cache produced byte-identical `nodes.csv` and `edges.csv`
(SHA-256 compared on 2026-10-25).

## Human review loop
1. Open `reports/graph_report.html` (serve it: `python -m http.server 8765 --directory reports`).
2. Copy `reports/nodes_needing_review.csv` to `inputs/node_review.csv`; add `reviewer` and `decision`
   (`accept` / `move` with new `lat`,`lon` / `reject`).
3. Run `python tasks.py graph-apply-review`, which writes `data/processed/node_overrides.csv` (USER_ENTERED). The
   generated CSVs are untouched; overrides are applied when the database is loaded.

## Extending to a new geography
Add a block under `geographies:` in `config/geography.yaml` (districts with Agmarknet spelling + Nominatim query,
road classes, buffer), set `active:`, check which Geofabrik extract covers it (`POLY_URL`/`PBF_URL` in
`pipelines/osm_extract.py`), then run `python tasks.py data` and `python tasks.py graph`.

## What is missing
Capacities for every node (no verified source); real collection centres (origin proxies only); NGOs and
processors (2 and 3 real in OSM); traffic (none, modelled later as ASSUMPTION); measured speeds (94% class defaults).
