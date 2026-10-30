# Final integration audit (2026-10-30)

Audit of the whole application against BLUEPRINT.md, before the testing day. No new features were added except automatic deletion, which the blueprint already requires (§6, §13) and which was missing.

**Verdict: a working showcase prototype with clearly stated gaps. Not production-ready.**

| # | Area | Result | Evidence / gap |
| --- | --- | --- | --- |
| 1 | Frontend ↔ backend | OK | Dev (Vite proxy) and production build cross-origin (`VITE_API_BASE` + `CORS_ORIGINS`): all pages load, no failed requests; other origins refused |
| 2 | Database persistence | OK | persistence test; safe column upgrades; `DATA_DIR` for a persistent disk; map built only into an empty database |
| 3 | Map loading | OK | 147 street lines, 27 markers in the production build; offline: tiles blank, our data still drawn |
| 4 | Safe places | OK | open/closed/unknown, never assumed open; sources + confidence; data gaps documented |
| 5 | Routes | OK | 39 scoring/routing tests; real campus routes |
| 6 | Sentinel video | Partly verified | Pipeline verified with generated clips; **owner's videos not yet run** |
| 7 | Gemini photo analysis | **Missing (M6)** | Photos stay "pending" and never affect scores; no blurring, so photos are never displayed |
| 8 | Street score updates | OK for reports | Reports change scores/routes (tested); photo-based updates wait for M6 |
| 9 | Community reports | OK | limits, no self-agreement, fading, place reports |
| 10 | AI briefing | Partly verified | Data summary EN/HI verified live; Gemini path + fact check tested with simulated answers only |
| 11 | Walk With Me | OK (backend) | Full 3-device sequence in tests; live background clock: ask 18 s → contacts 38 s → police 68 s; UI to be clicked through on phones |
| 12 | Contact page | OK | Production build, phone size: live dot, ALERT banner, timeline |
| 13 | Police dashboard | OK (simulated) | Access code, alerts, positions only while open, status flow, history |
| 14 | City dashboard | OK | Ranked list, hotspots, CSV |
| 15 | Mobile | OK in emulation | All pages at 390 px: no sideways scrolling; real Android/iPhone not yet tested |
| 16 | API errors | OK | Plain-language messages with codes; tested invalid input, missing data, wrong codes, unreachable services |
| 17 | Security & privacy | Improved | Access codes (Sentinel, police), walker token, unguessable trip links, server-enforced capture rules, keys only on the server, `.env` and videos git-ignored. **Fixed now:** photos/uploads were never deleted and walk personal data was kept forever → automatic deletion (tested). Residual: shared codes, public reports, no rate limit on route/walk creation, one process |
| 18 | Browser permissions | Handled in code | Camera/GPS/location errors explained; need https on phones (deployment prepared); simulated walk for http |
| 19 | WebSocket reconnection | Not applicable | No WebSockets are used: all live screens poll every 3–5 s and recover by themselves after an outage (checked by stopping/starting the backend) |

## Bugs fixed during this audit
1. **Critical (privacy):** nothing deleted expired photos, uploaded videos or old walk data → `services/retention.py`, run every ~5 min by the walk clock; test `test_retention.py`.
2. **Deployment:** frontend used relative `/api` only (works only behind a proxy; large uploads through a Vercel proxy could fail) → `VITE_API_BASE`; backend `CORS_ORIGINS` from settings.
3. **Deployment:** data folder fixed to `backend/data` → `DATA_DIR`; map build at start would have rebuilt over real data → `build_map --if-empty`.

## Automated tests
`pytest`: **80 passed** (health, persistence, hours, map, places matching, scoring, routing, route API, Google Places (simulated), Sentinel, security audit, walker features, walks, retention). `npm run build`: passes (one size warning: main bundle ~506 kB, ~150 kB compressed).

## Not verified (to do in the testing phase)
Real night videos · real Gemini key · Android Chrome and iPhone Safari on real devices · camera/GPS over https · `docker build` · Render/Vercel deployment · two people walking for real.
