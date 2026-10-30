# Manual testing checklist

Tick each box. If something fails, write what you did, what you expected and what happened into `docs/KNOWN_ISSUES.md` (or tell Claude).
**Never test calls with DEMO_MODE off.** In demo mode all help-call buttons ring `DEMO_CALL_NUMBER` only.

## 0. Preparation (laptop)

- [ ] `cd ~/Projects/shadowmap/backend && .venv/bin/pytest` → **286 passed**
- [ ] `backend/.env` has `DEMO_MODE=true` and a team member's number in `DEMO_CALL_NUMBER`
- [ ] Note the two codes: `grep -E "SENTINEL_TOKEN|POLICE_TOKEN" ~/Projects/shadowmap/backend/.env`
- [ ] `./start.sh`, open http://localhost:5173 → header shows **Server online**
- [ ] Phones on the same Wi-Fi: stop `start.sh`, then run the backend (`cd backend && .venv/bin/uvicorn app.main:app --port 8000`) and in a second terminal `cd frontend && npm run dev:lan`. The terminal shows a "Network" address like `http://192.168.x.x:5173` — use that on phones.
  *Over plain http, phones cannot use the camera or real GPS. Everything else works; use "simulate walk". Camera/GPS tests need the https deployment (docs/DEPLOYMENT.md).*

## 1. Laptop (Chrome or Firefox)

**Map and places**
- [ ] Walker: map shows streets in colour, dashed demo box, place markers; zoom +/−, drag
- [ ] "Tonight 11:30 pm": label changes; police/hospital show **Hours unknown** (never "open" without hours)
- [ ] Category chips hide/show markers; "Open at walk time only" leaves only places with listed hours (1 ATM, if inside view)
- [ ] Tap a street → score, breakdown, freshness "Map data only", observations, reports
- [ ] Tap a place → sources, confidence + reason, "Never checked in person", Closed now / Open now buttons

**Route and briefing**
- [ ] Planning bar: Starting point → "Use my location" (laptop location may be far away → expect a clear "more than 250 m from any mapped street" message), then Starting point → campus centre; Destination → Ranjeeta → route cards appear on the right
- [ ] Top search: type "atm" → results from the map; click → place panel opens; "Go here" → becomes the destination
- [ ] Bell shows only real items (walk running on this device, server offline, demo mode); profile shows the name saved for Walk With Me or "Guest"
- [ ] Tap two map points far outside the area → clear error, no crash
- [ ] "Hear the briefing" English → text + voice; switch to हिन्दी → Hindi text + voice (or a clear "no Hindi voice" note)
- [ ] Briefing never mentions a place that is not on the route

**Reports and help point**
- [ ] Report tab → "Dark here" → tap a street → Send → thank-you with new score; street turns redder; same report again → "already sent"
- [ ] Help point → "From a point on the map" → honest result (nothing known open → list of unknown-hours places)

**Sentinel**
- [ ] Sentinel page asks for the access code; wrong code refused; right code opens
- [ ] Video mode: copy a night video into `assets/videos/`, refresh → it appears → choose it → trace the route (≥2 taps) → recording time → Process → progress bar → done with frames on streets (they stay "waiting for AI analysis" until M6)
- [ ] Upload a non-video file → clear "not supported" message
- [ ] "Remove this video's photos and observations" works

**Dashboards**
- [ ] Police and Sentinel: refresh keeps you signed in; "Sign out …" returns to the code screen and signs out of that screen only; closing the browser signs out of both
- [ ] Police: access code → "No active alerts" (or alerts) ; label "Simulated"
- [ ] City: repair list shows your test "Dark here" report street; **Download CSV** opens in a spreadsheet

**Second city (Delhi)**
- [ ] Hover the left sidebar → it expands over the page (the map does not move), leaves → it collapses; **Demo area** → "Aastha Kunj, Delhi" → page reloads; map shows South Delhi with the dashed box around Aastha Kunj Park
- [ ] Route: Aastha Kunj Park → Nehru Place metro, and Lotus Temple → Kalkaji Mandir → both routes appear, notes say "map data only"
- [ ] Help point from Aastha Kunj Park → a Delhi place; City dashboard and CSV show only Delhi streets
- [ ] Switch back to "IIIT Guwahati" → campus map, places and routes exactly as before

## 2. Android phone (Chrome) — walker

- [ ] Open the LAN address; page fits the screen, no sideways scrolling; the ☰ menu opens the drawer, every link works and closes it
- [ ] Floating "Help point" button and the "Report a concern" shortcut scroll to the right panel
- [ ] Route with "Choose a place" for A and B; briefing plays aloud (English and Hindi)
- [ ] **Start Walk With Me**: name, contact, PIN 1234, duress PIN 9999, tick **simulate walk** → Start
- [ ] Share link → send to the iPhone (WhatsApp or copy)
- [ ] Help bar: **112 needs a 1-second hold**; every call opens the dialler with the **team number**, never 112/181/100; the contact phone shows "… is calling …"
- [ ] Fake call rings/vibrates; Answer shows a call timer; ✕ ends it
- [ ] "Where am I" card shows street / landmark / nearest police
- [ ] Tap **Demo: stand still** → after ~15 s the red **Are you safe?** screen appears (phone vibrates)
- [ ] Wrong PIN → "not correct"; right PIN (1234) → back to the walk
- [ ] Stand still again, **do not answer** → contact alerted after ~20 s, police after ~30 s more
- [ ] Stand still until *Are you safe?* appears, **do not answer**, then let the simulation reach B → the walk does **not** end; the contact page shows "phone reached the destination area … does not mean the walker is safe" once; the alert continues until the PIN
- [ ] Answer with **duress PIN 9999** → your screen looks normal; contact and police show **DURESS**
- [ ] **SOS** (hold 2 s) → police dashboard shows "SOS pressed" immediately
- [ ] "Demo: walk off route" → after ~15 s *Are you safe?* (off route)
- [ ] Let the simulation reach B → "You have arrived"; contact sees "reached safely"; location sharing shows OFF
- [ ] The walk screen always shows **"Location sharing ON · last sent N s ago (± m)"**; turn Wi-Fi off 30 s → it turns orange ("nothing sent for N s"); Wi-Fi back on → it sends at once
- [ ] **End walk & stop sharing** needs the PIN; 3 wrong PINs → "Too many wrong PINs", contact sees a warning; wait 30 s, then the right PIN works
- [ ] End with **"Also switch the trip link off now"** ticked → the contact's page says the link was switched off
- [ ] SOS pressed several times → only **one** police alert; the walker screen says "SOS sent"
- [ ] **Real GPS (https only):** untick "simulate walk"; deny location → clear message, nothing shared; allow → dot follows you; walk 50 m off the route for 30 s (real) / 15 s (demo) → "Are you safe?"
- [ ] **Screen sleep:** lock the phone for 1 minute during a walk → positions stop (check "last sent"); the contact phone eventually shows the check/alert. Note what each phone does — background tracking is not guaranteed

## 3. iPhone (Safari) — trusted contact (then swap roles)

- [ ] Open the shared `/trip/...` link: map with route and blue live dot moving; banner "… is walking"
- [ ] During the Android tests the banner turns yellow (asking) → **red ALERT** → mentions the police dashboard; timeline grows
- [ ] The trip page shows **no phone numbers** and no other contacts' names
- [ ] After arrival/end: map disappears, only the final message remains ("Location sharing has stopped"); after 1 hour the link says it expired
- [ ] Open a made-up link (`/trip/abc123`) → "does not exist"; open the link of another walk → only that walk is visible
- [ ] Swap: start a walk on the iPhone (Safari) and repeat section 2 briefly (Hindi voice on iPhone: Settings → Accessibility → Spoken Content → Voices, if missing)

## 4. Laptop — police control room (during sections 2–3)

- [ ] Alert appears within a few seconds, red ring when New; reason correct (Stopped / Off route / SOS / DURESS)
- [ ] Map: route, blue live dot, grey "last moved", red "alert raised here"; "Positions simulated (demo)" badge
- [ ] Acknowledged → Unit sent → Resolved; contact page shows each step; History tab keeps it, without live position after resolving

## 5. Failure drills

- [ ] Stop the backend (Ctrl+C) → pages show "Server offline" / clear errors; start it again → pages recover by themselves
- [ ] Turn phone Wi-Fi off for 30 s during a walk → the server still escalates (contact phone shows the alert)
- [ ] No internet on the laptop: map tiles blank, but streets, places and routes still drawn

## 6. Morning of the showcase

- [ ] `pytest` passes; `./start.sh`; header "Server online"
- [ ] DEMO_MODE=true, DEMO_CALL_NUMBER set, team phone volume up
- [ ] Clear old test data you do not want to show (ask Claude for a clean database copy — never delete by hand)
- [ ] Phones charged, browser zoom 100 %, the two access codes ready
- [ ] Hotspot ready; recorded backup video of the demo ready
