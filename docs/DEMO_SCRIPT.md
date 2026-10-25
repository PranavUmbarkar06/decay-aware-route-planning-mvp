# Demo script (about 3 minutes, spoken)

Setup: `python tasks.py demo`, open http://localhost:8000/demo on a phone-sized window. The yellow banner says
DEMO DATA: every person and lot in this demo is made up; roads, weather and market volumes are real.

**0:00 · Why.** "India loses about 19.3 million tonnes of fruit and vegetables a year across all stages (NABCONS). Nobody
records what happens on the truck, so nobody knows how much of that is transit. This prototype does two things: it helps
a dispatcher compare routes, and it creates the trip-level record that doesn't exist today."

**0:20 · Step 1: register.** Tap *Run this step*. "Demo Farmer 1 registers 1,200 kg of tomato. The app gives a QR label
and a one-time PIN. The PIN only works with the lot code, locks after five wrong tries and expires."

**0:40 · Step 2: handovers.** "Each handover needs both sides: the sender declares weight and condition, the receiver
weighs it and confirms. Every event is chained by hash, so editing or deleting history is detectable. If weights differ by
more than 2%, it is flagged as disputed: it is never booked as waste."

**1:05 · Step 3: heat.** "It's early May in Nagpur in the replayed weather: the afternoon is near 40 °C. The traffic light
uses a sourced reference shelf life and FAO's rule that deterioration roughly doubles to triples every 10 °C. Tap *How is
this calculated?*: every input is shown with whether it is real or assumed, and it says plainly that this is a model, not a
food-safety certificate."

**1:30 · Step 4: crowd meter.** "This compares today's reported arrivals with the market's usual 14-day median from
Agmarknet. We don't show '% of capacity' because no capacity data exists. If a market is unusually busy, nearby markets
with data are suggested with road time."

**1:50 · Step 5: rescue.** "The lot is offered to the nearest NGOs that accept tomato and have capacity. The first to
claim wins, with a two-hour pickup timer; we tested that two NGOs tapping at the same moment produces exactly one winner.
Pickup is another handshake, and the kilograms are booked as donated, not wasted."

**2:15 · Step 6: simulation.** "Finally the decision layer. We pre-registered the test before running it: same supply,
weather, roads and random seed, only the routing policy differs. The honest result: the quality-aware policy wasted less in
summer and monsoon, but it sent produce to processing and left more demand unmet, and in winter it was worse on both.
So it did not beat the simple baseline. The Live tab runs both side by side, hour by hour."

**2:45 · Close.** "What's missing is real trip data and real users. Next we interview dispatchers, and run this app at a few
collection centres to collect the data that calibrates the model. Everything that is assumed is listed on the Evidence &
limits page."
