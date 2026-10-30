# ShadowMap — Complete Project Blueprint

Copy of the online blueprint, exported 29 Oct 2026. Where it differs from TECH_DECISIONS in BUILD_PLAN.md, BUILD_PLAN.md wins.

## 1. Vision and the problem

ShadowMap is a live map of how safe each street is at night, built from fresh street photos taken by riders who are already on the road. It routes people along the safest path, an AI explains that route in plain words, and it watches over them until they arrive.

**One line for judges:** "Google Maps knows the shortest way home. ShadowMap knows the safest way home, as of ten minutes ago."

### The problem

- **Maps optimise for distance, not safety.** At 11:30 pm the shortest path is often a dark lane, an empty underpass or a deserted market.
- **Maps are frozen in time.** Street imagery and map data are months or years old. Nobody knows which streetlights are broken *tonight* or which street emptied out an hour ago.
- **Safety apps react too late.** Most rely on an SOS button, which helps only after the person is already in danger.
- **Nobody tells the city what to fix.** A broken streetlight can stay broken for weeks because no one reports it in a way the city can act on.

### The insight

Thousands of delivery riders, cab drivers, auto drivers and ambulance crews cross every street of a city every night. Their phones are already mounted on dashboards and handlebars. If each phone looked at the street every 5 to 10 seconds, the whole city would be seen, fresh, all night long, at almost no cost.

### The goal

Make walking home at night measurably safer, especially for women, by helping people avoid danger before it happens rather than only call for help after.

## 2. Who it's for

ShadowMap serves five groups. The night walker is the main user; everyone else either feeds the map or acts on it.

| Who | Example | What they need | What ShadowMap gives them |
| --- | --- | --- | --- |
| **Night walker** (main user) | A student walking from the bus stop to her hostel at 11 pm | A route she can trust, and someone watching over her | Safest route, AI briefing read aloud, Walk With Me |
| **Sentinel** (rider who feeds the map) | A Zomato or Swiggy rider, a cab or auto driver, an ambulance crew | Their own safety on night shifts, and recognition for helping | Sentinel Mode on their phone; the same safety map for themselves |
| **Trusted contact** | Her parent, roommate or friend | To know she reached safely, and to know fast if she didn't | Live trip link, alerts when she stops or goes off-route |
| **Police control room** | The local station or city control room | Early warning, with an exact live location | Alert dashboard with live position and route |
| **City / municipality** | The streetlight and roads department | To know which lights are broken and which dark streets matter most | Ranked repair list of dark streets, with photos |

**Primary persona for the demo: Priya, 21.** She finishes a late class or shift and walks 1.5 km home. Today she picks the route Google Maps shows, or the one she "feels" is fine. With ShadowMap she sees the safest route, hears why it's safer, and her roommate can follow her walk live.

## 3. What ShadowMap does

ShadowMap does three jobs, in this order of priority: help people **avoid** danger, **get help fast** if something feels wrong, and help the city **fix** the cause.

| Job | What happens | Features (detailed below) |
| --- | --- | --- |
| **1. Avoid danger** | Before and during the walk, the person takes streets that are lit, busy and close to open places | Safe Places (§4), Sentinel photos (§5), AI street analysis (§6), safety score (§7), safest route + AI briefing (§8), community reports (§10) |
| **2. Get help fast** | If the person stops, strays or doesn't respond, the right people are told within minutes | Walk With Me, one-tap help calls and "Are you safe?" (§9), nearest safe spot (§10), police dashboard (§11) |
| **3. Fix the problem** | Dark and broken streets are turned into a ranked repair list for the city | City dashboard (§11) |

**What ShadowMap never does:** it never rates neighbourhoods or the people who live there. It only judges the physical street at that moment: is it lit, is anyone around, is anything open. Those are fair and fixable.

## 4. Feature 1: Safe Places, open right now

Every place a person could walk into for help is on the map, marked **open now**, **closed**, or **hours unknown** for the exact time of the walk.

### What counts as a safe place

| Category | Why it matters at night | Default if no hours are listed |
| --- | --- | --- |
| Police station / police booth | Help on the spot | Open 24 hours |
| Hospital (with emergency) | Staffed all night, security present | Open 24 hours |
| Petrol pump | Lit, staffed, often open late | Hours unknown |
| Pharmacy / chemist | Staffed, some open 24 hours | Hours unknown |
| 24-hour shop, dhaba, tea stall | People around, lights on | Hours unknown |
| ATM with guard | Lit, often guarded | Hours unknown |
| Bus stop, metro or railway station | People around, lit | Hours unknown |
| Hotel reception | Staffed all night | Open 24 hours |

### How "open now" works

1. Each place's opening hours come from OpenStreetMap (for example "Mo-Su 08:00-23:00" or "24/7").
2. ShadowMap checks those hours against the **time of the walk**, not the time of planning. A 10:45 pm plan for an 11:15 pm walk uses 11:15 pm.
3. Places with no listed hours show as **hours unknown** and count for less in the safety score than places confirmed open.
4. Sentinel photos can confirm a place is actually open (shutters up, lights on), which upgrades it to **seen open** with a time: "seen open 12 min ago".
5. Community reports can correct wrong hours ("closes at 10, not 11").

### On the map

- Each category has its own icon. Open places are bright; closed places are greyed out.
- Tapping a place shows its name, category, hours, distance from the route, and when it was last seen open.
- A filter lets the person show only places open right now.

## 5. Feature 2: The Sentinel network (a photo every 5 to 10 seconds)

Riders who are already on the road at night become the city's eyes: their phone takes a street photo every 5 to 10 seconds, tags it with the exact location, and sends it to ShadowMap's AI.

*Diagram (in the online doc): Rider's phone (photo + GPS every 5 to 10 s) → ShadowMap server (snap to street, blur faces and plates) → Vision AI (lighting, people, open places, hazards) → Safety score (fresh photos count most) → Live map (street colour updates, latest photo on tap) → Safest route + briefing (rerouted around streets that just went dark).*

Each photo is analysed within seconds; the street's colour, its latest photo and any route through it update for everyone who has the map open.

### Who can be a Sentinel

- **Partner-company riders** (vision): Uber, Ola, Rapido, Zomato, Swiggy, ambulance services. A "Sentinel" switch inside their existing driver app.
- **Individual volunteers** (works today, no partnership): any delivery rider, cab or auto driver, night-shift worker or student can turn on Sentinel Mode in the ShadowMap app.
- **City vehicles** (later): police patrol vans, municipal night vehicles, ambulances.

### When a photo is taken

| Rule | Value | Why |
| --- | --- | --- |
| Capture interval | Every 5 to 10 seconds | About one photo every 35 to 70 m at bike speed (25 km/h) |
| Only while moving | Speed above \~5 km/h | A rider waiting at a restaurant would send 100 photos of the same spot |
| Skip duplicates | No new photo within \~30 m of the last one | Saves data and AI cost |
| Only at night | 6 pm to 6 am by default | Daytime photos don't help night safety |
| Only on duty | Sentinel switch on | The rider decides; nothing is captured otherwise |

### What is sent with each photo

- The photo, shrunk to about 640 pixels wide.
- GPS position and its accuracy, direction of travel, speed and exact time.
- A Sentinel ID (for example "Zomato Rider #01") and the source (partner app or volunteer).

### Data cost for the rider (approximate)

A 640-pixel photo is roughly 50 to 80 KB. At one photo every \~7 seconds that is about 25 to 40 MB per hour of riding. Three ways to cut it: smaller photos (480 pixels), uploading in batches on Wi-Fi, or (production) running the AI on the phone and sending only the results, about 1 KB each.

### In the prototype

- **Live mode:** a team member opens the Sentinel page on a phone, mounts it on a bike or holds it while walking, and rides the demo area. Photos and GPS flow to the server and the map updates live.
- **Video mode (backup):** we upload a night video of a route and trace the path on the map. ShadowMap takes one frame every 5 seconds and places each frame along the traced path by time.
- Sentinels are labelled like partner riders ("Zomato Rider #01", "Rapido #02") to show how the fleet version would look.

## 6. Feature 3: AI street analysis and the photo cache

Every Sentinel photo is examined by a vision AI that describes the street's safety in a fixed format, and the latest photo of each street is kept for a few hours so anyone can see what it looked like minutes ago.

### What the AI reports for each photo

| Field | Possible values | Example |
| --- | --- | --- |
| Lighting | bright / dim / dark | dim |
| Streetlights | how many visible, how many working | 1 of 3 working |
| People around | none / few / many | none |
| Open places visible | count and type | 0 |
| Vehicles passing | none / some / busy | some |
| Isolation | open road / lane / underpass / empty plot / market | lane |
| Hazards | broken road, construction, flooding, stray dogs, none | broken road |
| Description | one plain sentence | "Narrow lane, one working streetlight, no people or open shops." |
| Confidence | low / medium / high | high |

### Rules the AI must follow

1. **Describe the place, never the people.** No guessing anyone's age, gender, religion or intentions; only how many people are around.
2. **Never guess.** A blurry or blocked photo is marked "unclear" and ignored, not scored.
3. **Fixed format.** The AI fills the fields above, so the safety score is computed by code, the same way every time.

### The photo cache

- Tap any street on the map to see its **latest photo**, the AI's note, the time and which Sentinel took it: *"Dim, 1 of 3 streetlights working, nobody around. Seen 8 min ago by Rapido #02."*
- A strip of the last few photos shows how the street changed through the night (for example, shops shutting at 10:30 pm).
- **Photos are deleted automatically after a few hours** (6 hours by default). The AI's text and scores are kept, because they hold no faces.
- **Faces and number plates are blurred** before a photo is shown to anyone. In the prototype this is done when the photo is displayed; in production it happens on the rider's phone before upload.

### Cost and limits

In the prototype one free AI account handles roughly one or two active Sentinels, which is enough for a live demo. At city scale, a small AI model runs on the rider's phone itself and sends only the results, so thousands of riders cost almost nothing.

## 7. Feature 4: The street safety score

Every stretch of street gets a safety score from 0 to 100, recalculated whenever a new photo or report arrives: fresh photos count most, and as they age the score slides back to what the map alone says.

### Two ingredients

**Map score (always available).** What we know without any photos:

| Factor | Points (starting values) |
| --- | --- |
| Main road | 60 |
| Residential street | 45 |
| Lane or footpath | 35 |
| Underpass or path through an empty plot | 25 |
| Each safe place open now within 50 m | +5 (max +15) |
| Police station or hospital within 200 m | +10 |

**Photo score (when a Sentinel has passed recently).** Built from the AI's fields:

| AI field | Points (starting values) |
| --- | --- |
| Lighting: bright / dim / dark | +40 / +15 / 0 |
| People: many / few / none | +25 / +12 / 0 |
| Each open place visible | +5 (max +15) |
| Vehicles passing | +5 |
| Lane, underpass or empty plot | −5 to −10 |
| Hazard seen | −5 |

### How they combine: freshness

A photo's weight halves every 60 minutes. A photo from 10 minutes ago dominates; one from 3 hours ago barely counts, and the score is back to the map score.

```latex
w = 0.5^{\text{age in minutes} / 60}
\qquad
S = w \cdot S_{\text{photo}} + (1 - w) \cdot S_{\text{map}} + R
```

Here *R* is the adjustment from community reports (§10), for example −15 for "broken streetlight" until a newer photo shows it working. When several photos exist, the newest ones are averaged, each weighted the same way.

### Colours on the map

| Score | Colour | Meaning |
| --- | --- | --- |
| 70 to 100 | Green | Lit, people around, open places nearby |
| 40 to 69 | Yellow | Some concerns; fine if nothing better |
| 0 to 39 | Red | Dark, empty or isolated; avoid at night |

Every street also shows **how fresh** its score is ("seen 8 min ago" or "map data only"), so nobody mistakes an old guess for a live fact. All point values are starting values and will be tuned while testing in the demo area.

## 8. Feature 5: Safest route and the AI route briefing

The person enters where they are going and when; ShadowMap draws the shortest and the safest route side by side, then an AI explains the safest route in plain words and reads it aloud.

### Finding the safest route

1. The street network of the area is a graph: every stretch of street is an edge with a length and a safety score.
2. Each stretch gets a "walking cost": its length, made longer the less safe it is. A dark 100 m lane might "cost" like 250 m of bright main road.
3. The route finder (Dijkstra's algorithm) picks the path with the lowest total cost. With plain length as the cost, the same finder gives the shortest route.
4. **Detour limit:** the safest route may be at most 50% longer than the shortest. If no route within that limit avoids red streets, ShadowMap says so plainly and suggests the nearest safe spot or a cab.

```latex
\text{cost} = \text{length} \times \left(1 + 3 \times \frac{100 - S}{100}\right)
```

The cost only ever grows with danger, never goes below the length itself. That keeps the route finder correct (it cannot handle negative costs).

### What the person sees

|  | Shortest | Safest |
| --- | --- | --- |
| Distance and time | 1.1 km · 13 min | 1.3 km · 16 min |
| On red streets | 300 m | 0 m |
| Safe places passed | 1 | 4 (pharmacy, petrol pump, police booth, hospital) |
| Freshest photo on route | 25 min ago | 6 min ago |

*(Example values; real numbers come from the demo area.)*

### The AI route briefing

The AI is given only facts: each stretch of the route, its latest photo notes and their times, safe places along it and the time of the walk. It writes 4 to 6 short sentences, in English or Hindi, and the phone reads them aloud.

> *"Your route is 1.3 km, about 16 minutes. The first 500 m on MG Road is bright and busy; a rider passed 6 minutes ago. I'm avoiding the lane behind the market: it was dark and empty 10 minutes ago. You'll pass a 24-hour pharmacy and a police booth. The last 200 m to your hostel is dim but has people around."*

**Rules for the briefing:**

- Every claim must come from the data given; the AI may not invent shops, lights or people.
- Every observation says how old it is ("6 minutes ago").
- If data is old or missing, it says so: "I don't have fresh photos of the last stretch."
- It never promises safety. It describes conditions and choices.

### During the walk

As the person walks, short spoken updates come at key points: "Turn left onto Station Road, it's well lit." If a fresher photo shows a problem ahead ("the next 200 m went dark 15 minutes ago"), the route recalculates and the person is told why.

## 9. Feature 6: Walk With Me, one-tap help calls and "Are you safe?"

Once the person starts walking, ShadowMap watches the trip, asks "Are you safe?" when something looks wrong, and alerts their chosen contacts, then the police, if they don't answer.

### Starting a walk

1. The person picks the safest route and taps **Start walk**.
2. They choose up to 3 trusted contacts (saved once).
3. Each contact gets a **live trip link**: a map with the moving dot, the planned route and the expected arrival time. No app install needed.
4. On arrival, contacts get "Priya reached safely at 11:24 pm" and the link stops sharing.

### What triggers a check

| Trigger | Starting value |
| --- | --- |
| Stopped moving, away from a safe place or the destination | 3 minutes |
| Off the planned route | more than 50 m for 30 seconds |
| Running late | 10 minutes past expected arrival |
| Phone battery low | below 10% (contacts told, not an alarm) |
| Panic: press and hold the SOS button | immediately skips to step 3 |

*Diagram (in the online doc): Trigger (stopped, off-route, running late, or SOS) → "Are you safe?" → yes: walk continues (I'm safe + PIN; a duress PIN escalates silently) · no answer in 60 s → Alert contacts (live location, latest street photo) → 2 more min → Police dashboard (live position, route, phone). SOS skips straight to the police.*

A confirmed "I'm safe" ends the check; silence moves the alert up one level at a time, and SOS jumps straight to the police.

### The escalation ladder

1. **Ask.** The phone vibrates and shows a large **"Are you safe?"** with an **I'm safe** button. 60 seconds to answer.
2. **Alert contacts.** No answer: trusted contacts get an alert with the live location, the route, and the latest photo of the street she is on. The phone asks again, louder.
3. **Alert police.** No answer after 2 more minutes, or SOS pressed: the alert appears on the police dashboard with live location, route, name and phone number.

### Protection against misuse and coercion

- **I'm safe** needs a 4-digit PIN, so someone else can't cancel it by grabbing the phone.
- A second **duress PIN** looks like it cancels the alert but silently escalates.
- Location is shared only during a walk the person started, and only with the people they chose.
- False alarms cost nothing: one tap of "I'm safe" with the PIN ends it and tells contacts it was a false alarm.

### Help on one tap: never alone on the route

During every walk a **help bar** stays at the bottom of the screen, so if she feels scared of the route or of anyone around her, a real person is one tap away.

| Button | Who it calls | When to use it |
| --- | --- | --- |
| **Call 112** | National emergency line: police, fire and health services | Immediate danger |
| **Women helpline 181** | Women Helpline | Harassment, being followed, feeling unsafe, needing advice |
| **Nearest police station** | That station's own number, with its name and distance (from map data, where listed); falls back to 100 (police) | Wants local police who know the area |
| **Call my contact** | A trusted contact, who can also see her live location | Feeling scared and wanting company; she can stay on the call for the whole walk |
| **Fake call** | Her phone rings with a pretend incoming call | To make someone nearby think she is talking to somebody |

**What happens when she taps a call button:**

1. The phone's dialler opens with the number already filled in. For 112 she presses and holds for one second, so it can't be dialled by accident.
2. At the same moment, her trusted contacts get her live location and the line "Priya is calling 181", so if the call drops, someone already knows.
3. A large **"Where am I"** card shows her street, the nearest landmark and the nearest open safe place ("MG Road, near Apollo Pharmacy, police booth 300 m ahead"), so she can tell the operator exactly where she is, even when frightened.
4. The map and route stay on screen behind the call.

**Other details:**

- The numbers are saved on the phone, so the buttons work even without mobile internet; a call needs only phone signal.
- Numbers are set per state and city, so local helplines can be added.
- The AI briefing names help points along the route: "A police booth is 300 m ahead, on your left."

Helpline numbers from the Government of India's [national helpline directory](https://india.gov.in/directory/helpline), checked on 29 October 2026.

### In the prototype

Timers are shortened for the demo (for example, 15 seconds stopped triggers the check). Contacts' alerts appear on a contact page on a second phone, and the police alert appears on the police dashboard (§11). Sending real SMS or WhatsApp messages is a later step. In demo mode the help-call buttons ring a team member's phone: we never call real emergency numbers during a demo.

## 10. Feature 7: Community reports and the nearest safe spot

Anyone can correct the map with a one-tap report, and anyone feeling unsafe can find the nearest open place to walk into with one button.

### One-tap reports

| Report | Effect on the street's score | Fades after |
| --- | --- | --- |
| Broken streetlight | −15, and added to the city repair list | When a newer photo shows it lit, or 7 days |
| Dark here | −15 | 3 hours |
| Deserted / nobody around | −10 | 2 hours |
| Felt unsafe here | −10 | 2 hours |
| Well lit and busy | +10 | 2 hours |
| Place is closed / open | Corrects that place's hours | Until contradicted |

- A report is tied to the exact spot and time. Photos are optional.
- **Agreement counts:** two or more matching reports on the same stretch within an hour count more than one.
- **Abuse limits:** a few reports per person per hour; a fresh Sentinel photo always outweighs reports.
- Reports describe the street, never people. There is no free-text field that could name or accuse anyone.

### Nearest safe spot

One large button on the main screen: **"Nearest safe spot"**.

1. It finds the closest place that is **open right now** (police booth, hospital, petrol pump, 24-hour pharmacy or shop), preferring places reachable along green streets.
2. It shows walking time and draws the route there.
3. It offers to start Walk With Me for that short walk and to tell trusted contacts where she is going.

## 11. Feature 8: Police and city dashboards

Two screens turn ShadowMap's data into action: the police dashboard handles live alerts, and the city dashboard turns dark streets into a repair list.

### Police / control-room dashboard

- **Live alerts list**, newest first: name, time, what triggered it (no reply, SOS, stopped, off-route).
- **For each alert:** live position on the map, the planned route, the last place she was seen moving, the latest street photo there, and her phone number.
- **Status buttons:** Acknowledged → Unit sent → Resolved, so everyone sees who is handling it.
- **Map of active walks** (only during an alert; no tracking of people otherwise).
- **Sentinel coverage:** which streets were seen in the last hour, so gaps are visible.

### City / municipality dashboard

- **Dark-street hotspots:** streets that were red most nights over the last week.
- **Broken-light repair list, ranked:** each entry shows the street, the photo evidence, how many nights it was dark, and how many people walked or routed through it. Most-walked first, because fixing those helps the most people.
- **Before and after:** when a light is fixed, the next Sentinel photo turns the street green, and the dashboard shows the improvement.
- **Export:** the list as a spreadsheet for the streetlight department.

**Why this matters for the pitch:** ShadowMap does not only route people around problems. It gives the city a free, constantly updated list of exactly what to fix, with photo proof.

## 12. Where the data comes from

ShadowMap stacks several free sources so the map is useful on day one and gets better with every Sentinel ride; no company partnership is needed to start.

| Source | What it gives | In the prototype | Limits |
| --- | --- | --- | --- |
| **Sentinel photos + AI** | Fresh lighting, people, open shops, hazards, every 35 to 70 m | ✅ Core feature: our own rides or video | Only where a Sentinel has passed recently |
| **OpenStreetMap** | Every street and its type; police, hospitals, pharmacies, petrol pumps, ATMs, shops; often opening hours | ✅ Downloaded for the demo area | Opening hours and streetlight tags are often missing in Indian cities |
| **Time of day** | Which places are open at the time of the walk | ✅ | Only as good as the listed hours |
| **Community reports** | Broken lights, dark or deserted spots, closed shops | ✅ Judges can report live | Can be wrong or abused; outweighed by fresh photos |
| **Public street photo projects** (e.g. Mapillary) | Streetlights already detected in public street photos | Optional, where coverage exists | Coverage in Indian cities varies; photos may be old |
| **Government open data** | Police station lists, streetlight records in some smart cities | Optional | Published for some cities only |
| **Partner fleets** (Uber, Ola, Rapido, Zomato, Swiggy, ambulances) | Citywide photo coverage all night | 📄 Pitch only; simulated with labelled Sentinels | Needs partnership agreements |

**What we deliberately do not use: crime statistics.** They are reported by large areas, arrive months late, and would label whole neighbourhoods "dangerous", which stigmatises the people who live there. ShadowMap judges only the physical street, right now.

## 13. Privacy, safety and ethics

ShadowMap handles street photos and live locations, so privacy is designed in from the first version, not added later; these are the rules.

### Street photos

- **Faces and number plates are blurred** before any person sees a photo (in production, on the rider's phone before upload).
- **Photos are small** (about 640 pixels) and **deleted after 6 hours**. Only the AI's description and scores are kept.
- Photos are used for one purpose only: judging street safety. They are never sold, searched for people, or used to track anyone.
- The AI describes places, never people (§6).

### Walkers' location

- Shared **only during a walk the person started**, only with contacts **they chose**, and it stops automatically on arrival.
- Trip links expire when the walk ends.
- The police see a location only when an alert is raised.

### Sentinels (riders)

- Capture happens only when the rider switches Sentinel Mode on.
- Riders appear under a pseudonym ("Rapido #02"). Their own routes are never shown to the public; only the streets they covered.

### Fairness

- No crime data and no neighbourhood ratings (§12). Only fixable physical conditions: light, activity, open places.
- Reports have no free-text field, so nobody can be named or accused through the app.

### Honesty about limits

- ShadowMap never says a route is "safe". It says "safer" and explains why, with how fresh the information is.
- When data is old or missing, the app says so.

### Law

India's Digital Personal Data Protection Act, 2023 expects clear consent, use limited to a stated purpose, and deletion when no longer needed. ShadowMap's design (opt-in, one purpose, automatic deletion) follows those principles. A legal review would be needed before a real launch.

## 14. Partners, rider incentives and business model

ShadowMap starts with individual volunteer riders, proves the map works in one area, and then uses that proof to win company and city partners; walkers never pay.

### Growth path

1. **Volunteers in one neighbourhood.** A handful of riders and students run Sentinel Mode; the map covers one campus area at night.
2. **One fleet partner pilot.** A delivery or ride company adds the Sentinel switch for riders in one zone. Coverage jumps from a few streets to the whole zone.
3. **City partnership.** The city uses the dashboard and repair list, and helps fund or promote the service.
4. **More fleets and cities.** Each new fleet multiplies coverage at almost no extra cost.

### Why a company would join

- **Their own riders' safety:** the same map protects their delivery partners and drivers on night shifts.
- **Hiring more women:** night safety is a common reason women avoid gig work; a visible safety programme helps.
- **Reputation and CSR:** a public-safety programme that is easy to explain, and that CSR budgets can fund.
- **Almost no cost:** a switch in an app they already run; with on-phone AI, only tiny results are uploaded.

### Why a rider would turn it on

- It protects **them** first: they ride these streets every night.
- Recognition: Sentinel badges and a "streets lit up this month" count.
- Possible rewards funded by sponsors (fuel or data vouchers). These are ideas to test, not promises.

### Who pays (later)

| Payer | What they pay for |
| --- | --- |
| City / municipality, Safe City projects | The city dashboard, repair list and coverage reports |
| Companies (CSR or safety budgets) | Sponsoring coverage in an area; safety data for their own fleets |
| Walkers | Nothing. The walker app is always free. |

## 15. Showcase prototype: what's real, simulated, or pitch-only

Everything a judge touches in the demo works for real; only the partner fleet and real police integration are simulated, and we say so openly.

| Part | Status in the prototype | How |
| --- | --- | --- |
| Real map of the demo area (streets, safe places, hours) | ✅ Real | OpenStreetMap data for the chosen area |
| Open now / closed | ✅ Real | Listed hours checked against the walk time |
| Sentinel photos every 5 to 10 seconds | ✅ Real | Our phone on a bike or walking, or our recorded video |
| AI street analysis of each photo | ✅ Real | Vision AI (Google Gemini) |
| Photo cache with blurred faces | ✅ Real | Latest photo per street, deleted after 6 hours |
| Safety score and colours | ✅ Real | §7 formula |
| Shortest vs safest route | ✅ Real | Our own route finder on the real street network |
| AI route briefing, read aloud | ✅ Real | AI writes from the data; the phone speaks (English, Hindi) |
| Community reports | ✅ Real | Judges can report from their own phones |
| Nearest safe spot | ✅ Real |  |
| Walk With Me + "Are you safe?" | ✅ Real, shorter timers | A second phone acts as the trusted contact; help calls ring a team member in demo mode |
| Police dashboard | 🟡 Simulated | Our own dashboard; no connection to real police |
| City dashboard and repair list | ✅ Real | From our rides and reports |
| Partner fleets (Uber, Zomato, etc.) | 🟡 Simulated | Our Sentinels labelled as partner riders |
| Real SMS / WhatsApp alerts | 📄 Later | Alerts shown in-app on the contact's phone |
| On-phone AI for riders | 📄 Pitch only | Production plan for scale |

**What we say to judges:** "Everything you're touching is live. The only thing we can't show is a fleet of 10,000 riders, so we became the first Sentinels ourselves."

## 16. Demo plan: script, roles, backups

The demo runs about 5 minutes, follows Priya's walk home from start to finish, and every step has a backup if the venue's internet or a phone fails.

### Roles

| Role | Does what |
| --- | --- |
| Presenter | Tells Priya's story, explains each step, answers questions |
| Laptop operator | Runs the map and dashboards on the projector |
| Walker | Holds the "Priya" phone: route, briefing, Walk With Me |
| Contact | Holds a second phone as Priya's roommate, receives alerts |
| Sentinel | Plays the night ride video (or rides live outside if the venue allows) |

### Script

| Time | On screen | What we say |
| --- | --- | --- |
| 0:00 | Title + the problem | "At 11:30 pm, the shortest way home is often the most dangerous. Maps don't know that. Safety apps help only after something goes wrong." |
| 0:30 | Map of the demo area at 11:30 pm, shortest route through a dark lane | "Here's what Google Maps would give Priya." |
| 0:50 | Toggle ShadowMap: coloured streets, safe places open now | "Every street coloured by photos riders took in the last hour. Every place open right now." |
| 1:15 | Safest route appears, comparison card | "Three minutes longer, zero metres of dark street, four places she can walk into." |
| 1:35 | AI briefing read aloud on the phone | Let the room hear it. |
| 2:00 | Sentinel video plays; one street turns red live; route redraws | "A Zomato rider just passed. That lane went dark. ShadowMap already rerouted her." |
| 2:40 | Tap the street: blurred photo + AI note + "seen 1 min ago" | "Proof, not guesses. Faces blurred, deleted in 6 hours." |
| 3:00 | A judge scans a QR and reports "broken light" | "You just helped the map." |
| 3:20 | Start walk; show the help bar and "Where am I" card (the call rings a team phone); then the walker stops; "Are you safe?"; no answer | Contact phone buzzes, then the police dashboard lights up. |
| 4:10 | City dashboard: ranked repair list | "And the city gets a free list of exactly which lights to fix first." |
| 4:40 | Closing line | "Google Maps knows the shortest way home. ShadowMap knows the safest way home, as of ten minutes ago." |

### Setup checklist (morning of the showcase)

- [ ] Backend awake (open it 10 minutes before), map loaded, demo data reset
- [ ] Demo clock set to 11:30 pm
- [ ] Night ride photos already loaded, so the map is coloured before the live part
- [ ] Both phones charged, volume up, logged in, Hindi voice tested
- [ ] QR code for judges' reports printed
- [ ] Mobile hotspot ready in case venue Wi-Fi fails

### Backups

| If this fails | Do this |
| --- | --- |
| Venue internet | Switch to phone hotspot; or run everything on the laptop locally |
| AI service slow or down | Use the photos and notes already analysed from the night ride; the map, routing and alerts still work |
| Phone voice silent | Read the briefing from the screen; show the recorded demo video |
| Everything | Play the full recorded demo video (record it after the build is finished) |

## 17. Night ride plan (collecting the demo data)

Before the showcase, two team members ride the demo area at night with the Sentinel page running, so the map is full of real, fresh observations and the demo story uses real streets.

### Plan the route

- Pick a loop of about 3 to 5 km that covers **the demo walk** (start and destination), **the main road** of the safest route, and **the dark lane** the shortest route uses.
- Include at least one street with shops that close around 10 pm, to show time-of-day changes.

### Two rides, two times

| Ride | Time | Purpose |
| --- | --- | --- |
| Early ride | About 8 to 9 pm | Shops open, streets busy: shows the "before" |
| Late ride | About 11 pm to midnight | Shops shut, streets empty: the demo's "now" |

### Equipment

- One phone with the Sentinel page open: location allowed, screen kept on, interval set to 7 seconds.
- A handlebar mount, **or** a pillion rider holding the phone (safer and steadier).
- A power bank; mobile data on.
- A second phone recording **continuous video** of the same ride, as a backup for video mode.

### Safety and etiquette

- **Ride in pairs**, wear helmets, follow traffic rules. Never stop alone in a dark lane to get a better photo.
- Point the camera at the road ahead, not at people or into homes.
- If someone asks, explain it's a student project mapping streetlights.

### After the ride

1. Open the map and check every street on the demo routes has fresh observations.
2. Re-ride any gaps.
3. Save that night's observations as the demo's starting data, so the map is already coloured when the demo begins.

## 18. Technical design

ShadowMap is one Python server and four web apps that run in any phone or laptop browser (no app store); the server holds the street map, scores every street, asks the AI about each photo and runs the walk alerts.

*Diagram (in the online doc): four browser apps (Walker app, Sentinel app, Contact page, Police and city dashboards) ↔ ShadowMap server (Python: route finder, safety score, walk alerts and escalation, blur and 6-hour deletion, SQLite database) ↔ Vision AI (Gemini); the server also reads the prepared OpenStreetMap data (streets, places, opening hours).*

The apps only talk to the server; the server alone talks to the AI and reads the prepared map data.

### Building blocks

| Part | What it does | Built with |
| --- | --- | --- |
| Walker app (phone) | Map, safest route, spoken briefing, Walk With Me, reports, nearest safe spot | React + Tailwind, Leaflet map with OpenStreetMap tiles, browser voice |
| Sentinel app (phone) | Camera photo + GPS every 5 to 10 s, upload; video-upload mode | Browser camera and location; same React project |
| Contact page | Live trip link, alerts | Same React project |
| Police + city dashboards (laptop) | Alerts, live positions, repair list | Same React project |
| Server | All logic below, as web addresses the apps call | Python, FastAPI |
| Map data | Streets as a graph, safe places with hours | OpenStreetMap extract, prepared once into files |
| Route finder | Shortest and safest paths | Dijkstra's algorithm on the street graph |
| AI | Reads each photo; writes the route briefing | Google Gemini (free tier) |
| Privacy step | Blurs faces and plates; deletes photos after 6 h | Face/plate detector on the server (prototype); on the phone (production) |
| Storage | Streets, places, observations, reports, walks, alerts | SQLite file (prototype); PostgreSQL with map extensions (production) |
| Hosting | Online so phones can use camera and GPS (they require https) | Vercel (apps), Render (server) |

### What is stored

| Table | One row per | Key fields |
| --- | --- | --- |
| streets | stretch of street between two junctions | length, road type, shape, map score |
| places | safe place | name, category, location, opening hours, last seen open |
| observations | analysed Sentinel photo | street, Sentinel, time, AI fields (§6), photo file, photo delete time |
| reports | community report | street, kind, time, fade time |
| walks | Walk With Me trip | route, contacts, PIN, last position, last moved, status |
| alerts | escalation | walk, level, time, status (new / acknowledged / unit sent / resolved) |

### Main server addresses

| Address | Used by | Does |
| --- | --- | --- |
| POST /api/sentinel/photo | Sentinel app | Receives photo + GPS, matches it to a street, queues it for the AI |
| GET /api/map | Walker app, dashboards | Every street's score, colour and freshness; safe places open at a given time |
| POST /api/route | Walker app | Shortest and safest routes + comparison |
| POST /api/route/briefing | Walker app | The AI's spoken summary of a route |
| POST /api/reports | Walker app | One-tap report |
| GET /api/safe-spot | Walker app | Nearest place open now |
| POST /api/walks, /position, /safe | Walker app | Start a walk, send position, answer "Are you safe?" |
| GET /api/alerts, /api/city/repairs | Dashboards | Live alerts; ranked repair list |

### How a photo travels

1. The phone takes the photo, shrinks it, and sends it with GPS and time.
2. The server snaps the GPS point to the nearest street (within \~25 m), blurs faces and plates, and saves the photo with a 6-hour delete time.
3. The AI returns the fields in §6. Unclear photos are dropped.
4. The street's score is recalculated (§7), and every open map refreshes within a few seconds.
5. A background job deletes expired photos every few minutes.

## 19. Build plan and milestones

We build in this order, each milestone usable on its own, and move to the next only when its "done when" check passes; there are no fixed dates, we go until it's complete.

1. **Map foundation.** Choose the area; download and prepare its OpenStreetMap data; show streets and safe places with open/closed at any chosen time.
   - *Done when:* the map of the area shows every police station, hospital, pharmacy and petrol pump, correctly open or closed at 11:30 pm.
2. **Route finder.** Shortest and safest routes using map scores only; the comparison card.
   - *Done when:* for the demo walk, the two routes differ and the safest avoids the lane.
3. **Sentinel capture.** The phone page sends a photo + GPS every 5 to 10 s; the server matches it to a street and stores it.
   - *Done when:* walking one street with the page open puts a row of photos on that street.
4. **AI street analysis.** Each photo analysed into the §6 fields; scores and colours update live; photo cache with blurring and 6-hour deletion.
   - *Done when:* a dark-street photo turns that street red on the map within seconds.
5. **Video mode.** Upload a video, trace the path, frames placed along it.
   - *Done when:* a recorded ride colours the same streets as a live one.
6. **AI route briefing + voice.** Written from real data, in English and Hindi, read aloud.
   - *Done when:* the briefing mentions only real places and observation times.
7. **Community reports + nearest safe spot.**
   - *Done when:* a report from a second phone changes the route.
8. **Walk With Me + escalation.** Trip link, triggers, PIN, one-tap help calls with the "Where am I" card, contact page, police dashboard.
   - *Done when:* stopping during a walk leads to "Are you safe?", then a contact alert, then a police alert.
9. **City dashboard + repair list.**
   - *Done when:* reported broken lights appear ranked, with photos.
10. **Night rides.** Collect real data (§17); tune the score points.
    - *Done when:* every street on both demo routes has fresh observations.
11. **Online + phone testing.** Host it; test camera, GPS and voice on Android and iPhone.
    - *Done when:* a judge's phone can scan the report QR and it works.
12. **Polish for the showcase.** README, architecture picture, recorded demo video, rehearsal with the script (§16), Q&A practice (§21).
    - *Done when:* the full demo runs twice in a row without a hitch.

## 20. Risks and mitigations

The biggest risks are missing map data in our area, the AI misjudging photos, and the demo depending on live internet; each has a fallback.

| Risk | What could happen | Mitigation |
| --- | --- | --- |
| Thin map data | OpenStreetMap lacks opening hours or some places in our area | Pick the area early and check it; add missing places by hand for the demo area; Sentinel photos confirm "seen open" |
| AI misjudges a photo | Calls a lit street dark, or the reverse | Fixed format, "unclear" option, several photos per street averaged, fresh reports outweigh single photos; test on the night-ride photos first |
| AI free-tier limits | Too many photos per minute get refused | One Sentinel at a time in the demo; photos queued and retried; night-ride photos pre-analysed |
| Venue internet | Live demo stalls | Hotspot; local laptop copy; recorded video (§16) |
| Phone camera/GPS blocked | Browsers allow them only on secure (https) sites | Use the hosted https site on phones; test early on Android and iPhone |
| GPS jumps in narrow streets | Photo placed on the wrong street | Snap only within \~25 m; ignore readings with poor accuracy |
| Phone voice missing | Briefing is silent on some devices | Text always shown on screen; test the demo phones beforehand |
| Privacy questions from judges | Concern about photos of people | Blurring, 6-hour deletion, describe-places-not-people rule (§13), explained confidently |
| False sense of safety | User trusts "green" too much | Always "safer", never "safe"; freshness shown on every street |
| Night ride safety | Team members at risk while collecting data | Ride in pairs, helmets, don't stop in dark lanes (§17) |

## 21. Judge questions and answers

These are the questions judges are most likely to ask, with short, honest answers anyone on the team can give.

| Question | Answer |
| --- | --- |
| Where does your data come from without Uber or Zomato? | Free map data, community reports, and our own Sentinel rides. Any rider can switch on Sentinel Mode today; companies just make it bigger. |
| Why would Uber or Zomato join? | It protects their own riders, helps them hire more women, fits CSR budgets, and costs almost nothing. |
| Isn't photographing streets a privacy problem? | Faces and plates are blurred, photos are deleted after 6 hours, and the AI describes places, never people. |
| What if the AI is wrong about a street? | It reports in a fixed format, can say "unclear", and several photos and reports are combined. Every street shows how fresh its information is. |
| How is this different from Google Maps or SOS apps? | Google routes by distance with old data. SOS apps act after danger. ShadowMap avoids danger using photos from minutes ago, and still raises the alarm if needed. |
| Doesn't this label areas as dangerous? | No. We never use crime data or rate neighbourhoods; only light, activity and open places, which are fair and fixable. |
| What if there's no fresh photo of a street? | It falls back to the map score and says "map data only", so the user knows. |
| How does it scale to a whole city? | The AI moves onto riders' phones and sends tiny results, so thousands of riders cost almost nothing. |
| What stops someone cancelling her alert by grabbing her phone? | "I'm safe" needs her PIN, and a duress PIN silently escalates. |
| Who pays for this? | Cities and companies (dashboard, sponsorships, fleet safety data). The walker app is always free. |
| What does the city get? | A ranked list of broken and dark streetlights with photo proof, sorted by how many people walk there. |
| Is any of this live, or just slides? | Everything you touched is live. Only the partner fleet and the police connection are simulated. |

**"What if she isn't in danger, just scared?"** She taps "Call my contact" or 181 on the help bar. Her contacts see her live location at once, and the "Where am I" card tells her exactly what to say. She never has to walk alone, even before anything goes wrong.

## 22. Roadmap after the showcase

After the showcase, ShadowMap moves from one demo area to a real pilot, then to fleet partners and city adoption.

1. **Pilot on our campus area.** Volunteer Sentinels from the student community; real users walking home at night; measure how often the safest route is chosen.
2. **On-phone AI.** A small model runs on the rider's phone; only results are uploaded. Cuts data cost and removes photo privacy concerns.
3. **Real alerts.** SMS and WhatsApp alerts to trusted contacts.
4. **More languages.** Bengali, Assamese and other Indian languages for the briefing and app.
5. **First fleet partner.** One delivery or ride company pilots the Sentinel switch in one zone.
6. **City partnership.** Share the repair list with the municipality; track lights fixed.
7. **Police integration.** Connect alerts to a real control room, with their agreement and process.

## 23. Team roles and how we work

Four people, four clear owners: one builds the product with Claude Code, and the other three own the street data, the look, and the story, so building and everything around it move at the same time.

### Roles

| Role | Who | Owns | Main tools |
| --- | --- | --- | --- |
| **Tech lead** | Jivitesh | All code: map, route finder, Sentinel capture, AI analysis, alerts, dashboards; hosting; technical judge questions; the team's only Claude user | Claude Code and Claude chat on his laptop, GitHub, Vercel, Render |
| **Field and data lead** | To assign | Choosing and checking the demo area; adding missing safe places and opening hours; night rides and backup videos (§17); testing on Android and iPhone | Phone, Google Maps, Google Drive, the Sentinel page (all free) |
| **Design and demo lead** | To assign | How every screen looks (walker app, Sentinel, dashboards); logo; printed QR and posters; the recorded demo video | Figma (free), Canva Pro, screen recorders |
| **Pitch and research lead** | To assign | The story and script (§16); slide deck; judge Q&A practice (§21); facts and sources; talking to organizers; feedback from women who walk at night | Canva or Google Slides, Google Forms (free) |

Everyone tests. Before each milestone is marked done, all four try it on their own phones.

### Which tool for what

| Work | Where we do it | Why |
| --- | --- | --- |
| Writing and running code | Claude Code on the tech lead's laptop | Works directly in the project folder: runs, tests and fixes the code there |
| Storing code | One GitHub repository | A safe copy of every change; Vercel and Render deploy straight from it |
| Screen designs | Figma (free) | Draw and agree every screen before it's built; exported images guide Claude Code |
| Logo, QR card, demo video editing | Canva (free) | The design lead's Canva Pro: Brand Kit, premium templates, QR Code app and video editor in one place |
| Pitch deck | Canva or Google Slides (free) | Easy to share; downloads as PDF or PowerPoint |
| Interviews | Playbook tables plus Google Forms (free) | Real users' answers in one place |
| Shared plan and playbooks | Google Docs copies of this blueprint and the playbooks | Everyone can edit and comment without a Claude account |
| AI help for teammates | The tech lead's Claude | Only he has a subscription; teammates send him requests |

### How we work

1. **Agree the plan.** Everyone reads this blueprint and comments. The tech lead settles the open decisions (§24).
2. **Start three things at once.** The tech lead builds milestones 1 and 2 (map and route finder). The field lead picks and checks the area and records a first night video. The design lead mocks up the walker app and dashboards.
3. **Build to the designs.** Once a screen design is agreed, the tech lead builds it in Claude Code.
4. **Collect real data.** As soon as Sentinel capture works (milestone 3), the field lead does the night rides.
5. **Test together after every milestone.** All four phones; problems go in as comments here.
6. **Prepare the pitch alongside.** The pitch lead writes the script and deck as features land, and runs Q&A practice.
7. **Rehearse.** Run the full demo twice in a row without a hitch before the showcase (milestone 12).

**Short daily check-in (about 10 minutes):** what each person finished, what's next, and anything blocking.

Step-by-step setup for each role: Team setup guide

## 24. Open decisions

Six things must be decided before building starts; the first one blocks everything else.

- [ ] **Demo area:** which neighbourhood (about 2 km × 2 km), ideally around the college or the showcase venue.
- [ ] **AI key:** create a free Google Gemini key (it powers photo analysis and the briefing).
- [ ] **Night ride:** who rides, which nights, which phone (§17).
- [ ] Confirm the photo interval: every 5 to 10 seconds while moving (current plan).

* [ ] **Roles:** who takes field and data, design and demo, and pitch and research (§23).
* [ ] **Code home:** set up Claude Code on the tech lead's laptop and create the GitHub repository.
