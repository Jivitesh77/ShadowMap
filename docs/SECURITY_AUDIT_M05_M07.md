# Security and correctness audit — Sentinel live (M5) and video mode (M7)

Date: 2026-10-30. Scope: `backend/app/routers/sentinel.py`, `backend/app/services/video.py`, `backend/app/services/video_jobs.py`, the Sentinel page, and how the dev servers expose them. No map, routing or M6 changes.

Method: read the code, probed the running dev server (status codes only — no file contents read), wrote tests for each question **before** fixing (7 of 9 new tests failed on the old code), fixed, re-ran everything. Result: `pytest` 63 passed.

## Findings by severity

### High

**H1 — Sentinel endpoints had no access control, and the dev server listened on the whole network.**
`vite --host` exposed the app (and, through its proxy, the backend) to every device on the same Wi-Fi. Anyone there could upload fake street photos (polluting the safety map), upload videos up to 4 GB (filling the disk), delete video jobs, and read riders' traced routes.
*Fixed:* every Sentinel endpoint except `/api/sentinel/status` requires the **Sentinel access code** (`SENTINEL_TOKEN` in `backend/.env`, sent as the `X-Sentinel-Token` header; 401 missing, 403 wrong, constant-time comparison; 503 if the server has no code). The Sentinel page asks for it once. `npm run dev` is now local-only; `npm run dev:lan` exposes it on purpose.
*Tests:* `test_sentinel_endpoints_require_the_access_code`, `test_access_code_missing_on_server_blocks_writes`.

### Medium

**M1 — The 6 pm–6 am rule was enforced only in the browser.** A direct API call could upload at any hour.
*Fixed:* the server checks India time (`SENTINEL_ENFORCE_NIGHT`, default on). *Test:* `test_night_rule_enforced_by_server`. Verified live: a daytime upload with the right code was refused (`outside_hours`).

**M2 — The "only while moving" rule was enforced only in the browser.**
*Fixed:* the server requires a reported speed ≥ 5 km/h (`SENTINEL_ENFORCE_MOVING`, default on), keeps the 30 m duplicate rule, and rejects positions that jump faster than 150 km/h since the device's last photo (only judged when the phone sends its own capture time, to avoid false alarms from uploads queued during a signal drop). *Tests:* `test_movement_rule_enforced_by_server`, `test_impossible_jump_rejected`.
*Residual (accepted):* GPS position, accuracy and speed are reported by the phone and cannot be proven by any server. The access code limits who can send them.

**M3 — A failed video job left half its work behind.** Frames and observations were saved one by one, so a failure part-way left them in the database (they would later be analysed and coloured the map) plus a half-written frame file.
*Fixed:* on any failure the job's observations and all its frame files (including half-written ones) are removed before it is marked failed. *Test:* `test_failed_job_leaves_nothing_behind`.

**M4 — Riders' traced routes were readable by anyone** (`GET /api/sentinel/videos/jobs`), against blueprint §13 ("their own routes are never shown to the public").
*Fixed by H1:* job lists and details need the access code.

**M5 — Unblurred source videos were kept forever.** Uploaded copies (full resolution, faces and plates) had no delete time; uploads never turned into a job stayed forever; `assets/videos/` was not excluded from git, so footage could be pushed to GitHub.
*Fixed:* uploaded copies get `file_delete_at` = processing end + 6 h (also for failed jobs), to be executed by the M6 cleanup; abandoned uploads older than 24 h are removed when the server starts; `assets/videos/*` is git-ignored (files there are never changed or deleted by ShadowMap). *Test:* `test_upload_retention_and_orphan_cleanup`.

### Low

**L1 — Duplicate prevention was safe under simultaneous uploads only by accident** (no pause between the check and the save inside the request). *Fixed:* explicit lock around check + save. *Test:* `test_concurrent_duplicate_uploads_save_only_one` (8 simultaneous identical uploads → exactly 1 saved, 7 refused as duplicates). Note: valid for the single server process we run; several processes would need a database-level rule.

**L2 — Speed check could misfire on uploads that arrive together after a signal drop.** Found while testing M2; handled by judging speed only with phone capture times.

**L3 — Photo paths are stored as absolute paths.** Moving the project folder would break deletion. *Not changed (working code):* the M6 cleanup must also accept files by name inside `backend/data/photos`.

**L4 — The live photo endpoint does a little blocking work inside an async handler.** Negligible at prototype scale (73 streets). Not changed.

### Checked and fine

| Question | Result |
| --- | --- |
| Are photos, videos, the database or `.env` downloadable? | No. Vite refuses `/@fs/...` paths to `backend/` (403); `/.env`-style paths only return the app page; the backend listens on 127.0.0.1 only; no endpoint returns photos or file paths. Path tricks on asset names and video refs return 404 (tested). |
| Database consistent after deleting a video job? | Yes. Only that job's observations and frames are removed; other jobs untouched; asset videos never deleted (`test_deleting_one_job_leaves_others_intact`). |
| Photo retention ready for M6? | Yes: every photo has `photo_delete_at` (live: capture + 6 h; video: processing + 6 h); uploaded videos have `file_delete_at`. The deletion job itself is M6. |

## What the owner must know

- **Access code:** in `backend/.env` (`SENTINEL_TOKEN`). To see it: `grep SENTINEL_TOKEN ~/Projects/shadowmap/backend/.env`. Give it only to team members who capture.
- **Daytime / on-foot testing of Live mode:** set `SENTINEL_ENFORCE_NIGHT=false` and/or `SENTINEL_ENFORCE_MOVING=false` in `backend/.env`, restart, and set them back to `true` afterwards.
- **Phones on the same Wi-Fi:** use `npm run dev:lan` only when needed (camera/GPS still need https — M12).
