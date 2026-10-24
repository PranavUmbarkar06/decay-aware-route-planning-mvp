# Project context (summary of the two input decks)

Source files (read-only copies): `inputs/round1_brief_deck.pptx`, `inputs/solution_deck.pptx`, plus the
team's `inputs/Source_Register_round1_brief.md`. Everything below is taken from those files; slide
numbers are given so each line can be checked. Nothing here is new evidence.

## 1. Round 1 Problem Brief: "The Journey After Harvest" (Team Mandi Algos, NIT Warangal)

**Problem statement (S2).** Dispatchers of perishable F&V consignments (commission agents, traders, FPO
marketing staff) have difficulty getting each load to a market where it arrives still saleable at a
fair price, because of transit time, heat, handling and destination conditions that vary after
dispatch in mostly non-refrigerated trucks. The "because" clause is tagged partly HYPOTHESIS · VALIDATE.

**Scope (S2).**
- In scope: highly perishable F&V (examples given: tomato, guava, banana, mango, gourds); road movement
  after first aggregation up to sale at the receiving market; ambient (non-reefer) transport; variation
  by distance, season and region.
- Out of scope: grains and pulses (market-stage loss only ≈0.6–1.2% [1]); farm-level harvest losses;
  household waste; long-term cold storage of potato and onion; any proposed solution.

**Evidence tags used in the brief:** DOCUMENTED · INTERPRETATION · HYPOTHESIS · VALIDATE.

**Key evidence the brief cites (reuse only with these caveats):**
| Claim | Source (brief ref) | Caveat stated in the brief |
|---|---|---|
| 19.3 Mt F&V lost per year (fruits 7.36 + vegetables 11.97 Mt), all stages farm→retail | NABCONS 2022 for MoFPI, ref. 2020–22, via PIB PRID 2151371 Annex-II Table 1 [1] | Not a transport figure; the sum is the team's |
| Market-level loss %: wheat 0.56, paddy 0.61, potato 0.86, onion 1.96, banana 2.40, mango 2.5, tomato 3.25, guava 3.46 | [1] Annex-II Table 2 | "Market level" bundles transport, wholesale, retail and processing; **does not measure transit loss** |
| ₹1.53 lakh crore value of loss | [1] (secondary check) | All 54 commodities, not F&V only |
| Transit causes: heat, vibration, permit/traffic/breakdown delays, waiting at market; no reefers in study area | WRI India 2024 Tomato Trail (MP) [3] | One crop, one state, local flows 25–30 km; extension to long hauls is a hypothesis |
| 15% farm / 1% wholesale / 12% retail tomato loss; 11% sold as Grade II at ~half price | [3] | Small samples (80 farmers; 20 wholesale/retail) |
| Deterioration 2–3× faster per +10 °C | Kader & Rolle, FAO AGS Bulletin 152 §3.2 [6] | Generic rule of thumb; crop-specific rates differ |
| Reefer gap 85%, pack-house gap 99.6% (2014–15) | NCCD/NABCONS 2015 [4] | Ten years old |
| Farmers' share of consumer rupee: tomato ~33%, onion ~36%, potato ~37% | RBI WPS 08/2024 [5] | Reflects all chain costs and margins, not losses alone |
| Fresh F&V need no GST e-way bill, so freight records largely miss these trips | CGST Rule 138(14)(e) [14] | Team's reading; check current CBIC text |
| No public trip-level spoilage or rerouting dataset found | Team audit [15] | Absence of evidence, not proof of absence |

**Gaps named (S9):** data gap (no trip-level data, e-way bill exemption, Agmarknet records arrivals and
prices not trips); research gap (dynamic quality-aware routing open, no agreed decay model, 65-paper
review); practice gap (how dispatchers decide is unknown: HYPOTHESIS).

**Explicit statement (S5, S10, Source Register):** no interviews, field visits, surveys or simulations
of the team's own are reported. Dispatcher needs are **not yet validated by interviews**.

## 2. Solution Concept Deck, Round 1: "Quality-aware routing for fresh produce"

- **System (S5):** a simulation-led, quality-aware routing decision-support system for the
  **Nagpur Division, Maharashtra**. Commodities: **tomato, Nagpur orange, onion** (S1).
- **Inputs named (S5):** market arrivals & crop profiles from Agmarknet / ICAR-KVK; road graph & travel
  time from OpenStreetMap / OSMnx; weather replay from Open-Meteo historical; demand & hub capacity from
  "Census / intake norms / cold-chain directory" (exact datasets not named).
- **Engine (S5):** discrete-time simulation tracking each consignment's location, quantity and quality at
  hourly ticks.
- **Routing (S5):** baseline = static travel-time weights; proposed = weather + congestion + quality
  urgency + disruption signals. Decision outputs: **ROUTE** (path & ETA), **REROUTE** (alternate hub or
  market), **REDIRECT** (processing / NGO sink).
- **Alternatives compared (S3–S4):** A static shortest path, B market-information dashboard, C
  quality-aware dynamic rerouting. C selected "for testing"; scoring is "a reasoned project-team
  assessment … do not present as stakeholder-verified".
- **User journey (S6):** enter load → assess conditions → compare routes (static vs quality-aware) →
  receive alert → choose action (stay / reroute / redirect).
- **Metrics (S7):** primary: wastage rate (waste t ÷ injected t), unmet demand; secondary: quality at
  arrival, stock saved vs baseline; guardrail: travel time, km, reroute count.
- **Fair test (S7):** same supply, demand, weather replay, network, starting inventory and seed; repeat
  across seeds and seasons; report averages, variability and failure cases.
- **Explicitly provisional (S7):** "Do not promise a fixed percentage reduction yet." "The 14% calibration
  target is provisional." This project therefore states **no target reduction**.
- **Week-2 plan (S8):** data + graph ("clean nodes.csv and edges.csv"; these files do not exist and are
  generated here, see `docs/GRAPH_BUILD.md`), simulation core, baseline, proposed policy, evaluate.
  Stack: Python + pandas, NetworkX/OSMnx, config.yaml, CSV logs + plots, ML only after the baseline works.
- **Validation checkpoints (S8):** mass balance holds; no isolated graph nodes; baseline reproducible;
  proposed policy beats baseline on pre-registered metrics.
- **Guardrails (S5, S6, S8):** the system recommends, humans decide; benefits are hypotheses to test;
  interview dispatchers before deployment.

## 3. Tensions between the decks and the feature list (resolved in DECISIONS.md)

1. **Commodity set.** The brief's in-scope examples (tomato, guava, banana, mango, gourds) differ from the
   solution deck's (tomato, Nagpur orange, onion). We follow the solution deck. Onion is fine: the brief
   excludes only *long-term cold storage* of onion, not its transit.
2. **Geography.** Feature-list examples name Nashik/Pune/Vashi/Satara/Solapur. The submitted deck commits
   to the Nagpur Division (ADR-001).
3. **Orange loss benchmark.** NABCONS market-level figures in the brief cover tomato and onion but not
   orange/citrus; status tracked in DATA_GAPS.
4. **Solution deck title slide** still carries placeholders ("[Team name]", "[Add names]"); the brief
   names Team Mandi Algos, NIT Warangal. Not something this repo resolves.
5. **Team simulation code:** none was found in the provided files (`source/build_deck.js` only generates
   the brief's slides). The simulation is built from the deck spec (ADR-005).
