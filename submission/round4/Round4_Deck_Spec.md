# Round 4 deck: per-slide spec

Generated with the deck (`Round4_GTM_Deck.pptx`). Each slide: (a) visual and layout, (b) on-slide text, (c) footer, (d) speaker notes.

## Slide 1: Title and team

**(a) Visual & layout direction.** Dark forest-green background. Small green kicker line, very large white title, light subtitle, commodity/region line in green. A farm-to-buyer journey motif: five icon circles joined by a dashed line. Team placeholders near the bottom.

**(b) Minimal on-slide text.**

- IMPACT TANK ’26  ·  MARKET VALIDATION + GO-TO-MARKET
- The Journey After Harvest
- Connecting traceability, operational coordination and smarter produce-distribution decisions
- Tomato · Nagpur orange · Onion   |   Nagpur Division, Maharashtra
- Farm
- Collection
- Transit
- Market
- Buyer / NGO
- [Team name]  ·  [Members]  ·  [Institution]

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

Good [morning/afternoon]. We're [Team name] from [Institution].

"The Journey After Harvest" is a working prototype for three perishable crops, tomato, Nagpur orange and onion, in the Nagpur Division of Maharashtra. In the last round we built it. This round is about a harder question: does it address a genuine need, and how would we reach our first users?

Two things up front, because they shape everything that follows. First, anything about impact in this deck is simulation output, not a field result. Second, the five people you'll meet are hypothesised personas built from published research and our prototype work, not interviewees. We'll show you exactly what we've validated and what we haven't.

The journey on this slide is the spine of the deck: farm, collection, transit, market, and finally a buyer or an NGO. Our prototype lives in the middle of that chain.

Transition: let's start with how big the problem is, and what we don't know about it.

Likely question: "Is this a real product?"
Answer: It's a runnable prototype with an operations layer and a simulation-based decision layer. Sign-in is still a development stub, so first users would join a staffed demo and a pilot waitlist, not a public app.

## Slide 2: Large losses, unknown transit share

**(a) Visual & layout direction.** Left: a large stat card (19.33 Mt) with its source, and a small card with farm- vs market-level loss for our three crops. Right: the five-stage journey with gap markers and a dashed bracket showing what the prototype covers, then two callouts: an amber 'transit share unknown' box and a slate interpretation box about time and temperature.

**(b) Minimal on-slide text.**

- Large losses, unknown transit share
- 19.33 Mt
- of fruits (7.36 Mt) and vegetables (11.97 Mt) lost after harvest
- [DOCUMENTED]
- NABCONS study (2022) for MoFPI, 54 crops, 2020–22 · PIB, 1 Aug 2025
- Our crops: % lost (NABCONS)
- Crop | Farm level | Market level · Tomato 8.37% 3.25% · Citrus (incl. orange) 5.53% 2.18% · Onion 5.31% 1.96%
- Transit is not reported separately
- Prototype covers
- Farm
- Collection
- Transit
- Mandi / market
- Buyer
- Handover
- Delays, heat
- Mandi queues
- [INTERPRETATION]
- Transit-stage share: unknown
- [HYPOTHESIS TO VALIDATE]
- NABCONS reports farm-level and market-level loss; what happens on the road is not measured separately. Closing that gap is the point of the operations layer.
- Quality falls with time and temperature
- [INTERPRETATION]
- So when and where a load goes matters. A published production-routing model treats quality as a function of time and temperature.
- Manouchehri, Shahandeh Nookabadi & Kadivar, Heliyon 2020 (models chicken meat; we use the principle only)

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

India loses about 19.3 million tonnes of fruits and vegetables after harvest every year: 7.36 million tonnes of fruit and 11.97 million tonnes of vegetables. That's from the NABCONS study for the Ministry of Food Processing Industries, covering 54 crops over 2020 to 2022, as tabled in a PIB release on 1 August 2025.

The same table gives per-crop loss in two places: farm operations and market level. For our crops: tomato loses 8.37% at farm level and 3.25% at market level; citrus, which includes orange, 5.53% and 2.18%; onion 5.31% and 1.96%.

Here's the important part: none of those numbers isolate transit. We can't take 19.3 million tonnes and call it a transport problem, and we won't. The transit share is unknown, and that's exactly the gap our operations layer is designed to start measuring: weights and condition at every handover.

Why do timing and destination matter at all? Because quality falls with time and temperature. A peer-reviewed production-routing model by Manouchehri and colleagues in Heliyon (2020) treats quality exactly that way. To be precise: that paper models chicken meat with a microbial-growth curve, not fresh produce, so we borrow the principle, not the numbers.

Transition: the losses touch different people at different stages. Let's meet them.

Likely question: "So how big is your addressable loss?"
Answer: We don't know yet, and we won't guess. The first pilot's handover records are how we'd measure it.

Sources:
- PIB, Ministry of Food Processing Industries, "NABCONS Study Assesses Post-Harvest Losses Across 54 Crops During 2020–22", posted 1 Aug 2025: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2151371 (Annexure-II, Tables 1 and 2).
- Manouchehri F., Shahandeh Nookabadi A., Kadivar M. (2020). Production routing in perishable and quality degradable supply chains. Heliyon 6(2): e03376. https://pmc.ncbi.nlm.nih.gov/articles/PMC7033347/
- [SOURCE VERIFICATION REQUIRED] The team also holds PIB PRID 1884245 for the same figures; it could not be fetched automatically. Check it before citing it.

## Slide 3: One supply chain, five different needs

**(a) Visual & layout direction.** Five equal white cards in a row, each with a large icon in a teal circle (amber for the roadmap retailer), role, a one-line pain and a one-line 'in the app'. A 'HYPOTHESISED' chip on every card; the grocery card carries an extra 'ROADMAP' badge.

**(b) Minimal on-slide text.**

- One supply chain, five different needs
- [HYPOTHESIS TO VALIDATE]
- Farmer
- PAIN
- Little record of the weight handed over
- IN THE APP
- Gets a QR label; both sides confirm the weight
- [HYPOTHESISED]
- Collection-point supervisor
- PAIN
- Handovers, wastage and crowding tracked by hand
- IN THE APP
- Scans lots, logs wastage, sees shelf-life lights
- [HYPOTHESISED]
- Grocery store owner
- PAIN
- Supply and condition don't match demand
- WOULD DO (FUTURE)
- Future: a view of incoming supply and shelf life
- [ROADMAP]
- Truck driver
- PAIN
- Blamed for spoilage that happened elsewhere
- IN THE APP
- Two-party handover record at pickup and drop-off
- [HYPOTHESISED]
- NGO owner
- PAIN
- Short notice on surplus; pickup is hard to plan
- IN THE APP
- Sees nearby offers; claims within 2 hours
- [HYPOTHESISED]

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

Post-harvest loss isn't one person's problem. It moves through a chain of people, and each one sees a different piece of it.

These five personas are hypothesised. We built them from published research on Indian fresh-produce chains and from the roles our prototype already supports. They are not real people we interviewed, and you won't see names, ages or quotes, because we'd be making those up.

Quickly, left to right:
- The farmer wants a simple record of what they handed over.
- The collection-point supervisor juggles handovers, wastage and congestion, often on paper.
- The grocery store owner is a buyer-side segment for our roadmap. The prototype has no retailer screens yet, which is why that card says ROADMAP.
- The truck driver can be blamed for spoilage that happened before or after the trip.
- The NGO owner can use surplus produce, but gets little notice and has to plan pickups fast.

Each card says what that person would actually do in the app.

Transition: let's take them one at a time, starting where the chain starts, with the farmer.

Likely question: "Why these five and not dispatchers or commission agents?"
Answer: Dispatchers are central to the routing decision and appear throughout. The driver and supervisor slides show where the dispatcher acts, and dispatcher interviews are first on our roadmap.

## Slide 4: Persona 1 · Farmer

**(a) Visual & layout direction.** Left: a large italic teal message line, then four labelled rows (Context, Goals, Pains, We offer) and an amber-tinted 'assumption to test' box. Middle: a vertical four-step flow (Produce → QR label → Handover → Weight record). Right: the real prototype screenshot of the QR label and PIN in a phone frame.

**(b) Minimal on-slide text.**

- Persona 1 · Farmer
- [HYPOTHESISED PERSONA]
- No direct farmer interviews in this window
- “Same mandi, same buyer, plus a weight record.”
- CONTEXT
- Brings tomato, orange or onion to a mandi or collection point
- GOALS
- Know how much was handed over, and to whom
- PAINS
- Little accessible record of the handover and the recorded weight
- WE OFFER
- QR-labelled lots; two-party handovers in a tamper-evident log
- ASSUMPTION TO TEST
- [HYPOTHESIS TO VALIDATE]
- Farmers value a digital handover and weight record enough to use it regularly
- Produce
- QR label
- Handover
- Weight record & history
- Prototype: QR label + PIN (demo data)

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

Meet our hypothesised farmer. They bring tomato, orange or onion to a mandi or a collection point, and today they often leave with little accessible record of what they handed over or what it weighed.

Our message to them is deliberately simple: "Same mandi, same buyer, plus a weight record." Nothing about who they sell to changes. They get a QR label for each lot, and each handover is confirmed by both sides, the sender declaring weight and condition and the receiver weighing and confirming, with every event appended to a tamper-evident, hash-chained log. If the two weights differ by more than 2%, the lot is flagged as disputed rather than silently booked as waste.

The screenshot is the real prototype screen, with demo data: a QR label, the lot code, and a one-time PIN that locks after repeated wrong tries and expires.

What we don't know yet is whether a farmer values that record enough to use it every time. That's the assumption to test, and in this short window we could not get time with working farmers, so it's untested.

Transition: the person on the other side of that handover is the collection-point supervisor.

Likely question: "Will farmers really use a smartphone app?"
Answer: That's exactly what we need to test. The label and PIN can be handled by the receiver's phone, so the farmer may not need their own device. We'd confirm that in interviews.

## Slide 5: Persona 2 · Collection-point supervisor

**(a) Visual & layout direction.** Same persona frame as slide 4 for consistency: message line, four labelled rows, assumption box, vertical flow (Incoming lot → Scan & confirm → Shelf-life light → Log wastage) and the real wastage-logger screenshot.

**(b) Minimal on-slide text.**

- Persona 2 · Collection-point supervisor
- [HYPOTHESISED PERSONA]
- Direct field validation pending
- “A red/amber/green shelf-life light and simpler lot tracking.”
- CONTEXT
- Receives incoming lots and confirms handovers at a collection point
- GOALS
- Organised lot records, visible activity, recorded wastage
- PAINS
- Handovers, wastage and congestion recorded inconsistently
- WE OFFER
- QR lots · two-party handovers · one-tap wastage logger · shelf-life lights · crowd meter · Route Advisor
- ASSUMPTION TO TEST
- [HYPOTHESIS TO VALIDATE]
- One consolidated interface makes daily collection-point management more useful
- Incoming lot
- Scan & confirm
- Shelf-life light
- Log wastage
- Prototype: wastage logger (demo data)

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

The collection-point supervisor sits at the busiest handover in the chain. Lots come in, someone has to confirm them, decide what goes out first, and note what was lost and why.

Our hypothesis is that these things are recorded inconsistently today, so the supervisor gets the most of the operations layer in one place:
- Scanning a QR lot and confirming the handover.
- A shelf-life traffic light that sorts lots first-expiring-first-out. Every estimate can be opened to show its inputs and whether each is real or assumed.
- A one-tap wastage logger with a reason and an undo window. Undo writes a correcting entry, so history is never deleted.
- The mandi crowd meter, which compares today's arrivals with the market's usual 14-day median from Agmarknet. It never says "% full", because no capacity data exists.
- The Route Advisor, when a load is about to leave.

The screenshot is the real wastage logger with demo data.

The assumption to test is whether one consolidated interface actually makes the day easier, or just adds another screen. Field validation is pending.

Transition: further down the chain is a buyer our prototype doesn't serve yet: the grocery store owner.

Likely question: "Isn't this extra work for a busy supervisor?"
Answer: It might be. That's why the wastage log is one tap, and why we'd measure time per handover in the pilot rather than assume it's faster.

## Slide 6: Persona 3 · Grocery store owner

**(a) Visual & layout direction.** Same persona frame, recoloured amber for 'roadmap'. The message line is replaced by an amber statement that no retailer screens exist. Instead of a screenshot, a dashed phone outline labelled 'FUTURE · NOT BUILT' with a store icon, so nothing looks like a real screen.

**(b) Minimal on-slide text.**

- Persona 3 · Grocery store owner
- [ROADMAP SEGMENT]
- Retailer functionality is a roadmap item
- The prototype has NO retailer screens yet. This is a buyer-side segment for the roadmap.
- CONTEXT
- Buys produce from wholesalers or distribution points
- GOALS
- The right quantities, with enough usable life left
- PAINS
- Incoming supply and condition don't match expected demand
- WE'D OFFER (FUTURE)
- A retailer view of incoming supply and estimated shelf life
- ASSUMPTION TO TEST
- [HYPOTHESIS TO VALIDATE]
- Retailers value better visibility of produce condition and incoming supply
- Order
- Incoming supply view (future)
- Shelf-life check (future)
- Receive
- FUTURE · NOT BUILT
- Retailer view: incoming supply and estimated shelf life
- Concept only: no retailer screen

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

This persona is different, and we want to be upfront about it. The prototype has no retailer screens today. The grocery store owner is a buyer-side segment on our roadmap, not a current user.

Why include them at all? Because the receiving end is where the value of a well-managed journey shows up: the right quantity arriving with enough usable life left. Our hypothesis is that retailers often see a mismatch between what arrives, its condition, and the demand they expected.

What we would build later is a retailer view of incoming supply and estimated remaining shelf life, using the same shelf-life model that already drives the traffic lights. Everything on this slide marked FUTURE is not built, and the phone outline is a concept placeholder, not a screen.

The assumption to test is simple: do retailers actually value better visibility into condition and incoming supply, and would that change what they order or accept?

Transition: between the collection point and the buyer is the person who carries the risk on the road, the truck driver.

Likely question: "Why not build the retailer view now?"
Answer: We'd rather validate the handover record with farmers and supervisors first. A retailer view only works if the records feeding it are trustworthy.

## Slide 7: Persona 4 · Truck driver

**(a) Visual & layout direction.** Same persona frame. The message line states that the Route Advisor only recommends. Vertical flow: Pickup handover → Dispatcher confirms route → Drop-off handover → Both sides on record. Right: two stacked crops of a real prototype screen: the handover form (weight, condition, Hand over) and the journey header showing 'Tamper-evident log verifies'.

**(b) Minimal on-slide text.**

- Persona 4 · Truck driver
- [HYPOTHESISED PERSONA]
- Simulation-based; not field-validated
- “The Route Advisor recommends. It does not automatically reroute trucks.”
- CONTEXT
- Moves produce between collection points, mandis and markets
- GOALS
- Deliver on time with quality intact, without unfair blame
- PAINS
- Delays and disruption; blame for spoilage that happened elsewhere
- WE OFFER
- Two-party handover record at pickup and drop-off; a dispatcher-confirmed route
- ASSUMPTION TO TEST
- [HYPOTHESIS TO VALIDATE]
- Drivers and dispatchers find the handover record and route recommendations clear and useful
- Pickup handover
- Dispatcher confirms route
- Drop-off handover
- Both sides on record
- Prototype: handover + log check (demo)

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

The truck driver carries the produce, and often the blame. Our hypothesis is that when a load arrives in poor condition, it can be hard to tell whether the damage happened before pickup, on the road, or after drop-off.

What we offer is a record, not surveillance. There's a two-party handover at pickup and another at drop-off, each with a declared and a confirmed weight and condition, on a tamper-evident log. On the right is the real prototype with demo data: the handover form, where weight and condition are entered, and below it the lot's journey header confirming the tamper-evident log verifies.

On routing, we're careful. The Route Advisor compares the usual route with a quality-aware alternative and recommends. It does not reroute trucks automatically. The route is confirmed by a dispatcher, and people decide. The recommendation itself comes from simulation and is not field-validated. There are no truck sensors or live machine learning in the prototype; those are future roadmap items.

The assumption to test is whether drivers and dispatchers find this record and the recommendations clear enough to use in a hurry.

Transition: when a load can't be sold in time, the last person in our chain can still put it to use, the NGO.

Likely question: "Won't drivers resist being tracked?"
Answer: We don't track location; we record handovers. The pitch to drivers is protection from unfair blame. Whether they see it that way is something we must test directly.

## Slide 8: Persona 5 · NGO owner

**(a) Visual & layout direction.** Same persona frame. Vertical flow: Surplus identified → NGO offer → 2-hour claim window → Claim & pickup. Right: the real NGO claim screen with its countdown timer.

**(b) Minimal on-slide text.**

- Persona 5 · NGO owner
- [HYPOTHESISED PERSONA]
- Adoption and rescue not field-validated
- “Offers for nearby surplus, with a 2-hour claim timer.”
- CONTEXT
- Can receive suitable surplus produce for redistribution
- GOALS
- Spot usable offers early and decide in time
- PAINS
- Short notice, uncertain availability, pickup coordination
- WE OFFER
- NGO rescue offers with a 2-hour claim timer
- ASSUMPTION TO TEST
- [HYPOTHESIS TO VALIDATE]
- NGOs would monitor, claim and coordinate eligible offers within the window
- Surplus identified
- NGO offer
- 2-hour claim window
- Claim & pickup
- Prototype: NGO claim timer (demo data)

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

Finally, the NGO owner. Our hypothesis is that NGOs can use surplus produce but hear about it late, with little certainty about what's available or when it can be picked up.

In the prototype, when a lot won't sell in time, it's offered to the nearest suitable NGOs: those that accept that crop and have capacity. The first claim wins. We enforce that in the database, and our tests cover two NGOs claiming at the same instant, with exactly one winner. The winner gets a two-hour pickup timer. Pickup is another two-party handover, and the kilograms are booked as donated, not wasted.

The screenshot is the real claim screen with demo data. We haven't run a rescue in a real market. Nothing here says redistribution has happened.

The assumption to test is behavioural: would an NGO actually monitor offers, claim within two hours and coordinate a pickup in practice? Two hours may be too short or too long; we don't know yet.

Transition: that's five hypotheses about people. Next, what we've actually tested, and what we haven't.

Likely question: "Who pays for the NGO side?"
Answer: Our hypothesis is that it's free for NGOs. The pricing slide shows who might pay and the exact question we'd ask each group.

## Slide 9: What we tested, and what we haven't

**(a) Visual & layout direction.** A neutral slate box at the top holding the verbatim validation-status statement with a placeholder. Below, a clean eight-row table (Assumption | How tested | Evidence | Status) with status coloured red for Unsupported and amber for Untested. A one-line interpretation note about the published research at the bottom.

**(b) Minimal on-slide text.**

- What we tested, and what we haven't
- VALIDATION STATUS
- In the short window available we could not get time with working farmers or dispatchers. Farmers were unavailable at short notice, and dispatchers and commission agents were difficult to reach quickly. So this round's evidence is mainly published research and expert/second-hand input, plus [PLACEHOLDER: number and type of any calls or surveys we did complete]. Our next step is direct interviews, listed on the roadmap slide.
- Table: Assumption | How tested | Evidence | Status — QR lots and two-party handovers are a usable workflow | Automated end-to-end tests | Software works; no user trials yet | Untested · One-tap wastage logging fits daily work | Automated tests | Software works; no user trials yet | Untested · Shelf-life lights and crowd meter are useful signals | Not yet tested with users | [PLACEHOLDER] | Untested · NGOs can act within a 2-hour claim window | Not yet tested with NGOs | [PLACEHOLDER] | Untested · Quality-aware routing improves outcomes overall | Pre-registered simulation, 3 seasons | No overall winner (next slide) | Unsupported · Dispatchers and traders would adopt it | Not yet tested | [PLACEHOLDER] | Untested · Route recommendations are commercially useful | Not yet tested | [PLACEHOLDER] | Untested · Stakeholders would pay | Not yet tested | [PLACEHOLDER] | Untested
- [INTERPRETATION]
- Published modelling (Manouchehri et al., 2020) supports treating quality as time- and temperature-dependent. It is not evidence that our system works.

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

This is the most important slide in the deck, so we'll say it plainly. [Read the validation statement on the slide.]

The table separates three kinds of claim.

First, things the software does. QR handovers and wastage logging work. They're covered by automated end-to-end tests, including two NGOs claiming at once and an offline handover that syncs later. But passing tests shows the software works, not that people want it. So those rows say Untested for users, not Supported.

Second, the one claim we tested rigorously: does quality-aware routing improve outcomes overall? We pre-registered the test before running it: same lots, weather, roads and random seeds; only the routing policy differs; 20 seeds in each of three seasons. The answer was no overall winner, so that row is Unsupported. We'll unpack it on the next slide.

Third, everything about behaviour and money: adoption, commercial usefulness, willingness to pay. All untested, with placeholders where interview evidence will go. We will not fill them with numbers we don't have.

The bottom line is our secondary evidence. A peer-reviewed production-routing model treats quality as time- and temperature-dependent, which supports the design idea. That paper models chicken meat and minimises cost with no shortages allowed. So it's an interpretation, not proof that our system works.

Transition: so what did the simulation teach us, and what did we change?

Likely question: "So you have no validation?"
Answer: We have honest secondary evidence, one rigorous negative result, and a falsifiable plan. Direct interviews are step one on the roadmap, and we'll report the numbers exactly as they come.

Source: Manouchehri F., Shahandeh Nookabadi A., Kadivar M. (2020), Heliyon 6(2): e03376, https://pmc.ncbi.nlm.nih.gov/articles/PMC7033347/

## Slide 10: What the simulation taught us, and what changed

**(a) Visual & layout direction.** Left: an evidence card titled 'Pre-registered simulation result' with four icon rows (no overall winner; summer wastage lower; monsoon wastage lower; unmet demand higher in every season, in muted red). No percentages, no winner badge. Right: two 'changes already made' cards, then a 'to investigate' list with a hypothesis chip and a placeholder for interview insights.

**(b) Minimal on-slide text.**

- What the simulation taught us, and what changed
- Pre-registered simulation result
- [DOCUMENTED]
- Overall
- No overall winner
- Summer wastage
- Lower
- Monsoon wastage
- Lower
- Unmet demand
- Higher in every season
- Same lots, weather and roads; only the routing policy differs. 20 seeds per season. Simulation output, not field-validated.
- Changes already made
- Route Advisor: “The app recommends; you decide.”
- Each result carries a caution: in simulation this policy cut waste in hot seasons but raised unmet demand. Both metrics are side by side in the Simulation Lab.
- [DOCUMENTED]
- First users join a staffed demo and pilot waitlist
- Because sign-in is still a development stub.
- [DOCUMENTED]
- To investigate next
- [HYPOTHESIS TO VALIDATE]
- Show the trade-off inside the advisor itselfClearer shelf-life view · simpler records for early usersHuman approval before any routing decision
- Field-interview insights: [PLACEHOLDER]

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

Here's what our own simulation found, and we think it's the most useful thing we learned.

We compared a static shortest-path policy with a quality-aware policy on identical inputs: the same synthetic lots, real roads, replayed weather and real market volumes, 20 seeds per season. The decision rule was committed to git before the registered runs.

Quality-aware routing lowered wastage in summer and in monsoon. But it left more demand unmet in every season, because it sent at-risk produce toward processing and NGOs instead of markets. In winter it did worse on both. So there was no overall winner, and we're not going to dress that up. No loss-reduction figures appear in this deck, on purpose.

What did we change because of it? Two real things, both visible in the prototype.

First, the Route Advisor never presents its suggestion as the answer. The screen says "The app recommends; you decide." Each result carries a caution that, in simulation, this kind of policy cut waste in hot seasons but raised unmet demand, and the Simulation Lab shows both metrics side by side.

Second, onboarding: sign-in is still a development stub, so first users come through a staffed demo and a pilot waitlist.

On the right are ideas we want to test, not things we've done: putting the trade-off inside the advisor itself, clearer shelf-life views, simpler records, and human approval before any routing decision. Interview insights will go in the placeholder.

Transition: so where does this sit among tools that already exist?

Likely question: "Why show a negative result in a pitch?"
Answer: Because the trade-off is real, and a dispatcher would hit it on day one. Knowing it now means we design for the trade-off instead of promising a number we can't back.

## Slide 11: Where we sit among existing tools

**(a) Visual & layout direction.** Left: a 2x2 matrix (x = traceability & handover operations, y = routing intelligence) with competitors as dots placed only where their public documentation supports it, and our prototype as a dashed teal circle. Right: a compact comparison table with links, and a positioning statement in a tinted box.

**(b) Minimal on-slide text.**

- Where we sit among existing tools
- Traceability & handover operations →
- Routing intelligence →
- Locus
- SourceTrace
- TraceX
- Agmarknet
- e-NAM
- The Journey After Harvest (prototype)
- Routing is simulation-based; position is intended, not proven
- Placement from each product's public website, reviewed 28 Oct 2026. Ninjacart not placed: not established from documentation.
- Table: Agmarknet | Govt portal: mandi prices and arrivals | Not described | Not described · e-NAM | Govt online agri-trading platform; has an e-NAM-Logistics section | Not established | Not established · SourceTrace | Farm-to-retail traceability and supply-chain SaaS | Yes | Not described · TraceX | Blockchain traceability, EUDR compliance | Yes | Not described · Locus | Route planning, dispatch and shipment tracking | Not described | Yes · Ninjacart | Fresh-produce B2B marketplace, farmers to buyers | Not described | Not described
- [DOCUMENTED]
- “An operational traceability and decision-support prototype designed around the journey of perishable produce after harvest.”
- We don't claim to be first, only or best.

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

There are good tools in this space already, and we want to be precise about them.

The matrix has two axes: how much a product does for traceability and handover operations, and how much routing intelligence it offers. We placed each product only where its official website supports it.
- SourceTrace and TraceX document traceability: farm-to-retail traceability and supply-chain software for SourceTrace; blockchain traceability and EUDR compliance for TraceX, which is based in Bengaluru. Neither site describes route optimisation, so they sit bottom-right.
- Locus documents route planning, dispatch and shipment tracking, but nothing about produce traceability, so it sits top-left.
- Agmarknet and e-NAM are government platforms for market information and online trading. We use Agmarknet's price and arrival data ourselves.
- Ninjacart runs a fresh-produce B2B marketplace. Its site doesn't establish traceability or routing features, so we didn't place it.

Where we sit is intended, not proven. We combine handover records, wastage, shelf life, crowd awareness and NGO rescue with route comparison, for one region's perishables. But our routing is simulation-based and didn't beat the baseline, so the top-right position is a design goal. We don't claim to be first, only or best.

Transition: if that's the position, who might actually pay?

Likely question: "Why wouldn't a SourceTrace or Locus customer just use them?"
Answer: They might, and for traceability alone they could be the better choice. Our hypothesis is that small collection points and commission agents in Vidarbha need something lighter that joins handover records with destination decisions. That's what interviews will test.

Sources (official sites, reviewed 28 Oct 2026):
- Agmarknet: https://agmarknet.gov.in
- e-NAM: https://enam.gov.in
- SourceTrace: https://www.sourcetrace.com
- TraceX: https://tracextech.com
- Locus: https://locus.sh
- Ninjacart: https://ninjacart.com

## Slide 12: Who might pay: hypotheses, not prices

**(a) Visual & layout direction.** Two group labels (FREE and PAID, both hypotheses) over four segment cards with an icon, the model, a price placeholder and the exact non-leading interview question. A full-width strip below for larger operators, with the reminder that willingness to pay is not demand.

**(b) Minimal on-slide text.**

- Who might pay: hypotheses, not prices
- FREE · hypothesis
- PAID · hypothesis
- Farmers
- Free access
- Price: none
- WE'LL ASK
- “How do you keep a record of what you hand over today, and what would make you keep using a record like this?”
- NGOs
- Free access
- Price: none
- WE'LL ASK
- “How do you learn about surplus produce today, and what would you need to claim it within two hours?”
- Collection centres
- Tier: lot records, handover history, monitoring
- Price: [PLACEHOLDER]
- WE'LL ASK
- “What do lot records and wastage tracking cost you today, in time or money, and what would you pay to change that?”
- Dispatchers
- Tier: route comparison and trade-off view
- Price: [PLACEHOLDER]
- WE'LL ASK
- “How do you choose a market for a load today, and what would you pay for help comparing options?”
- Later: larger operators · multi-location deployments and integrations · Price: [PLACEHOLDER] · We'll ask: “Would one system across several locations change how you run operations?”
- [HYPOTHESIS TO VALIDATE]
- Willingness to pay ≠ demand

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

No prices on this slide, and that's deliberate. We haven't asked anyone yet, so any number would be invented.

What we do have is a hypothesis about who pays and why.
- Free for farmers and NGOs. Farmers are the source of the handover record. If they pay, they won't adopt, and without them there's no record. NGOs receive surplus for redistribution, and charging them would undercut the rescue flow.
- Paid tiers for collection centres and dispatchers, because they'd get operational value: consolidated lot records, handover history and monitoring for collection centres; route comparison with the waste-versus-unmet-demand trade-off for dispatchers.
- Later, larger operators with several locations and integrations.

Each card has the exact question we'll ask, and they're written not to lead. We start from what people do and spend today, before we ever mention a price. And we'll treat any "yes, I'd pay" as a hypothesis until someone commits to a pilot. Willingness to pay is not demand.

Transition: to ask those questions at all, we need to reach people. Here's how we'd spend ten thousand rupees.

Likely question: "How will you make money, then?"
Answer: Most likely from collection centres and dispatchers, the people who'd save time or reduce disputes. Whether they value that enough to pay, and how much, is the first thing our interviews will test.

## Slide 13: How ₹10,000 reaches our first users

**(a) Visual & layout direction.** Top-left: a native donut chart of the eight budget lines with '₹10,000' in the centre, and a legend with exact rupee values. Top-right: a 'four field days' panel with three icon rows and a fallback line. Bottom-left: four large target numbers labelled TARGETS, not results. Bottom-right: a four-step funnel and the activation definition.

**(b) Minimal on-slide text.**

- How ₹10,000 reaches our first users
- ₹10,000
- team estimates
- Donut: Travel ₹2,500 · Posters + banner (Marathi/Hindi) ₹1,800 · Handouts ₹700 · 300 QR stickers ₹600 · Demo desk ₹1,000 · Refreshments ₹1,000 · Mobile data ₹500 · Reserve ₹1,900
- Travel
- ₹2,500
- Posters + banner (Marathi/Hindi)
- ₹1,800
- Handouts
- ₹700
- 300 QR stickers
- ₹600
- Demo desk
- ₹1,000
- Refreshments
- ₹1,000
- Mobile data
- ₹500
- Reserve
- ₹1,900
- Four field days
- Visual posters per persona, in Marathi and Hindi
- Staffed demo desk near commission-agent shops (APMC permission first)
- Partner-led demos via FPOs, KVKs and NGOs
- If APMC permission is delayed: digital-first (WhatsApp demo videos, QR-linked info, waitlist) or a partner-led split via FPOs/KVKs.
- Demo targets
- [TARGETS, NOT RESULTS]
- 15
- farmers / FPO members
- 8
- dispatchers
- 3
- supervisors
- 3
- NGOs
- Reach
- Demo
- Activation
- Pilot
- Activation = a completed demo handover or a pilot-lot commitment. Not sign-ups or QR scans.
- First users join through a staffed demo and pilot waitlist. Prototype sign-in is a development stub.

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

Here's how we'd turn ten thousand rupees into first-user learning. These amounts are our own estimates; we'll confirm them against real prices before spending.

Budget, line by line:
- Travel, ₹2,500: four field days, mostly at Nagpur mandi plus one Chandrapur trip, because dispatchers and supervisors are reached where they work.
- Posters and one banner in Marathi and Hindi, ₹1,800: one poster per persona, wordless, a four-picture "how it works".
- Handouts, ₹700: something to leave behind, with a QR link to the demo.
- 300 QR stickers, ₹600: so people can try a real handover on their own lots.
- Demo desk, ₹1,000: a table and standee near commission-agent shops. We need APMC permission first.
- Refreshments, ₹1,000: hospitality during demos, never payment for sign-ups.
- Mobile data, ₹500: for reliable live demos.
- Reserve, ₹1,900: reprints and surprises.

The poster messages match the persona slides:
- Farmer: "Same mandi, same buyer, plus a weight record."
- Dispatcher: "Compare your usual route with a quality-aware option; you decide."
- NGO: "Offers for nearby surplus with a two-hour claim timer."
- Supervisor: "A red/amber/green shelf-life light and simpler lot tracking."
We promise no earnings and no avoided loss.

Our targets are 15 farmers or FPO members, 8 dispatchers, 3 supervisors and 3 NGOs trying a demo. These are targets, not results.

We count activations, not sign-ups. Sign-in is a development stub, so sign-ups would mean nothing. An activation is a completed demo handover or a commitment to run a pilot lot. The funnel runs reach, demo, activation, pilot.

If APMC permission is slow, we have two fallbacks: a digital-first route with WhatsApp demo videos, or a partner-led split through FPOs and KVKs.

Transition: what happens after those four days?

Likely question: "Why not spend it on ads?"
Answer: Our main users trust people more than ads, and we need conversations, not impressions. A small digital piece, the WhatsApp videos, costs almost nothing and is our fallback.

## Slide 14: From prototype to pilot

**(a) Visual & layout direction.** Dark background. Three columns of translucent cards: NOW, NEXT, and LATER (dashed border, 'FUTURE · NOT BUILT' badge). The closing line in large italic white text across the bottom.

**(b) Minimal on-slide text.**

- From prototype to pilot
- NOW
- Direct interviews: farmers, dispatchers, commission agents, supervisors, NGOsStaffed pilot at 2–3 collection centres in Nagpur DivisionReal operational feedback
- NEXT
- Retailer view (grocery store owner)SMS / WhatsApp notificationsPostgres persistence and real authenticationRefine from pilot evidence
- LATER
- [FUTURE · NOT BUILT]
- Sensors in trucks and transit pointsLearned machine-learning modelsWider deployment
- “Our next milestone is not more technology. It is proving that the right information, at the right handover, can help make better decisions after harvest.”

**(c) Mandatory footer.** Simulation output, not field-validated · personas are hypothesised

**(d) Speaker notes.**

Let's finish with where this goes.

Now: close the validation gap. That means direct interviews with farmers, dispatchers, commission agents, supervisors and NGOs, then a staffed pilot at two or three collection centres in Nagpur Division. The pilot isn't just for feedback. Its handover records are the trip-level data that doesn't exist today, and the data our model needs for calibration.

Next: the things the pilot will tell us we need. A retailer view for the grocery store owner, SMS and WhatsApp notifications, and production basics like a Postgres database and real authentication in place of the current stub. Then refinement based on what the pilot shows.

Later, and clearly future: sensors in trucks and at transit points, learned models trained on real trips, and a wider rollout. None of that is built. We'd only start it once the records prove useful and trustworthy.

[Read the closing line.]

Thank you. We're happy to take questions, especially the hard ones about what we still have to show.

Likely question: "What would make you stop or pivot?"
Answer: If farmers and supervisors won't keep the handover record in a pilot, the decision layer has nothing to stand on. We'd focus on the simplest record-keeping problem before anything else.
