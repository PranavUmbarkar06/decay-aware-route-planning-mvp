# FreshRoute Live: prototype

A browser-only demo of spoilage-aware dispatch on real Nagpur Division roads (OSM, 9,677 nodes / 13,924 edges).
There is no backend. Routing, Arrhenius kinetics and the simulation all run in the browser.

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # kinetics + router unit tests, scenario checks on the real graph
npm run build      # static site in dist/ — host anywhere
npm run graph      # rebuild public/graph.json from ../data/processed/geo/edges_simplified.geojson
```

## What the model does
- **Spoilage**: first-order quality loss `Q = exp(−∫k dt)` with an Arrhenius rate
  `k = k_ref · exp(Ea/R · (1/T_ref − 1/T)) · f_RH`.
  - `k_ref` is calibrated to the sourced shelf lives in `config/commodities.yaml`.
  - `Ea` is derived from the Q10 slider (FAO 152: 2–3).
  - Cargo temperature is ambient + sun load + idling heat in traffic.
  - The sellable fraction uses the lognormal spread from `backend/app/domain/decay.py` (σ = 0.25).
- **Edge weight** (₹): `driver/truck time + diesel per km + λ · k · t`. Here λ is the marginal ₹ value of quality for this cargo at its expected arrival quality.
- **Smart truck**:
  - Runs Dijkstra from its next node and scores every buyer (mandis + processors) on expected net.
  - Re-plans on every condition change and every 30 sim-minutes.
  - Switches when the gain is more than 1% of the cargo value.
- **Status-quo truck** (dashed, grey): picks the buyer by price minus transport cost (ignoring spoilage), drives the fastest route, and never re-plans.
- **KPIs** compare the two trucks for each consignment, using projections for trucks still on the road.
  - Throughput = sellable t per truck-day, assuming a 12 h operating day and an empty return trip.

## 3-minute demo script
1. Press **Run trucks** at 15 min/s. Three consignments leave at 06:00: tomato from Wardha, orange from Katol, onion from Warora.
2. After about 2 s, click **Festival traffic**.
   - The trucks re-plan live. A driver alert pops up in Hindi and Marathi, and the decision log explains each change.
   - The KPIs start to separate.
3. Click **Monsoon flood**. NH-44 goes under water at Jamtha. The tomato truck takes a new road; the status-quo truck crawls through the flood.
4. Open **Compare routes** and pick a truck. It shows Route A (fastest) against Route B (FreshRoute), the quality-over-time chart, and how every buyer ranks right now.
5. Open **Investor view**. Drag the trucks slider to 5,000: tonnes saved per year, ₹ for farmers, payback period, and reefer capex compared with software.
6. Freestyle: drop 🔥 / ⛈️ / 🚦 cells, drag them onto a route, or use ⛔ to close a road under a truck.

**Caveats to say out loud.** Prices are Agmarknet medians (some marked indicative). Cell effects, humidity sensitivity, meals per kg and the scale-up multipliers are assumptions, and they are shown on screen.
