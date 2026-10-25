# Demonstration video: shot list and recording guide

Target length: **about 3 minutes**. The narration follows `docs/DEMO_SCRIPT.md`, and every shot below is a screen you
can reach in the running app.

## Before recording
1. `python tasks.py demo` and wait until http://localhost:8000/readyz reports ready.
2. For a clean guided demo with no lots left over from earlier runs: stop the server, delete
   `data/cache/phl_demo.sqlite`, then run `python tasks.py demo` again (it reloads all data on start).
3. Browser at 1366×860 (desktop shots). For phone shots, use Chrome DevTools device mode (Pixel 7) or a real phone on
   the same network.
4. Leave the yellow **DEMO DATA** and **DEV AUTH** banners visible. They are part of the honesty story; don't crop them.
5. Close other tabs and turn off notifications. Record at 1080p or higher.

## Shots

| # | Time | Screen (URL) | What to do on screen | What to say (short form) |
|---|---|---|---|---|
| 1 | 0:00–0:20 | `/evidence` or a title card | Scroll slowly past the 19.3 Mt figure and its source | Loss is large; nobody records what happens on the truck, so the transit share is unknown. Two layers: a route assistant, and the trip record that doesn't exist today. |
| 2 | 0:20–0:40 | `/demo` → Step 1 (phone view) | Tap *Run this step*; show the QR label and PIN | Demo Farmer 1 registers 1,200 kg of tomato. QR label plus a one-time PIN that locks and expires. |
| 3 | 0:40–1:05 | `/demo` Step 2, then the lot page | Show the handover and the *Journey* chain with "verifies" | Both sides confirm each handover. Every event is hash-chained, so editing history is detectable. A weight gap over 2% is flagged as disputed, not waste. |
| 4 | 1:05–1:30 | Step 3 → `/storage` | Show the red/amber/green lights; open *How is this calculated?* | Replayed May weather near 40 °C. Sourced shelf life plus FAO's 10 °C rule. Every input shows whether it is real or assumed. A model, not a safety certificate. |
| 5 | 1:30–1:50 | Step 4 → `/crowd` | Pick a busy market; show the suggested alternatives | Arrivals compared with the usual 14-day median from Agmarknet. Never "% full", because no capacity data exists. |
| 6 | 1:50–2:15 | Step 5 → `/rescue` as the NGO (phone view) | Tap *Claim*; show the 2-hour timer | Surplus is offered to the nearest suitable NGOs. The first claim wins (tested with two NGOs claiming at once). Booked as donated, not wasted. |
| 7 | 2:15–2:30 | `/advisor` as the dispatcher | Set *Hours since harvest* to 28, then *Compare routes* | Usual route against the quality-aware option, with quality on arrival and the crowd at the destination. It recommends; the person decides. |
| 8 | 2:30–2:45 | `/lab` → *Pre-registered results*, then *Replay on map* → *Busiest hour* | Show the verdict, then the flow map with both policies | Pre-registered: same supply, weather and roads; only the policy differs. Honest result: less waste in summer and monsoon, more unmet demand everywhere. It did not beat the baseline. |
| 9 | 2:45–2:55 | `/lab` → *Live run* → *Run live* | Let it run for a few seconds; drag the hour scrubber | Both policies side by side, hour by hour, with a mass-balance check every hour. Simulation output, not field-validated. |
| 10 | 2:55–3:10 | `/evidence` (limits section) | Scroll the limitations | What's missing is real trip data and real users. Next: interview dispatchers and collect data at a few collection centres. Everything assumed is listed here. |

## Phrases to keep exactly
- "Simulation output, not field-validated."
- "It did not beat the baseline." Don't soften this, and don't quote a loss-reduction percentage.
- "Demo data": the people and lots are made up; the roads, weather and market volumes are real.

## Reference stills
`submission/screenshots/` has a still for every shot (01–14) if you need cut-aways or a thumbnail.
