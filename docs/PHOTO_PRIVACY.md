# Sentinel photos: analysis and privacy (M6)

## The pipeline (backend only, `services/photo_worker.py`)

```
original photo/frame  ──►  1. blur faces + plates (local, OpenCV)  ──►  2. Gemini analyses the BLURRED copy
 (restricted folder,          fails? → kept private, never sent         ├─ street fields (§6) → safety score
  never served)               to the AI, never scored                    └─ privacy double-check:
                                                                            faces still recognisable? plates readable?
                                                                         3. public only if BOTH checks are clean
                                                                         4. original deleted right after analysis
```

- **Originals** (`backend/data/photos/*.jpg`) are never served by any endpoint. They are deleted as soon as analysis finishes, or at the 6-hour deadline at the latest.
- **Blurred copies** (`backend/data/photos/redacted/obsN.jpg`): max 640 px wide, re-encoded (phone EXIF/GPS metadata removed), served only by `GET /api/photos/{id}` and only when *all* of these hold: blurring succeeded, the AI privacy check found no recognisable face and no readable plate, and the 6-hour deadline has not passed. Every other case answers the same 404. Responses are `Cache-Control: no-store`.
- **Fail closed:** OpenCV missing, detector not loaded, unreadable image, detector crash, encoding failure → `redaction_status = failed`, `analysis_status = blocked`, nothing sent to Gemini, nothing shown, nothing scored. Without a Gemini key, photos are blurred but stay private (no double-check possible) and are not scored.
- **Deletion:** the existing `services/retention.py` (runs at start-up and every ~5 minutes) deletes original *and* blurred copy at `photo_delete_at` (6 h). A photo deleted before analysis is marked `expired`. Removing a video job deletes both files of every frame.

## Detection technology and its limits

| What | How | Limits (be honest about these) |
| --- | --- | --- |
| Faces (main) | **YuNet** (`cv2.FaceDetectorYN`, OpenCV model zoo, MIT licence), model `backend/models/face_detection_yunet_2023mar.onnx` (232,589 bytes, SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`, matches the official Git LFS checksum; re-checked at every load — missing or altered model = fail closed). Run on the photo and on a brightened (CLAHE) copy; score threshold 0.5 (favours blurring too much over too little) | A small modern neural detector, much better than Haar on varied faces, but still **misses** tiny, very dark, heavily blurred or hidden faces. |
| Faces (backup) | OpenCV Haar cascades: frontal + profile (both directions) on a contrast-equalised grey image | Daylight, roughly frontal faces; adds a few extra detections and false positives. |
| Number plates | OpenCV Haar cascades `russian_plate_number` + `license_plate_rus_16stages` | Trained on **Russian** plates. Indian plates (different size, fonts, colours, two-line plates on two-wheelers) are often **not** detected. |
| Blurring | Every box enlarged by 25 %, pixelated (1/12) then Gaussian-blurred | Only what is detected gets blurred. |
| Safety net | Gemini looks at the *blurred* copy and counts faces still recognisable and plates still readable; any non-zero count keeps the photo private | Depends on the model's judgement; it can also miss things. Two imperfect checks are better than one, but **not a guarantee**. |

**No accuracy has been measured.** The automated tests use generated images (shapes, drawn rectangles) to prove the pipeline logic and the fail-closed behaviour. They say nothing about how many real faces or plates are found at night. That needs the team's real night photos (see below).

The AI is told to describe the place, never people (no age, gender, religion, clothing, identity or intentions; only how many). Its description is also checked by code and rejected if it contains words about people.

## Approval rule (conservative prototype rule)

A blurred photo becomes public only if **every** check passes (`approval()` in `services/photo_worker.py`):
1. blurring completed; 2. the analysis is clear and its confidence is medium or high; 3. Gemini sees no recognisable face and no readable plate in the blurred copy; 4. **if Gemini reports vehicles, our detector must have found and blurred at least one plate**; 5. **if Gemini reports people, our detector must have found and blurred at least one face**; 6. the analysis is complete.
Gemini's judgement is never treated as proof that an undetected face or plate is safe. Any doubt keeps the photo private.

**This is not reliable Indian number-plate detection.** The plate cascades are trained on Russian plates. The rule only means that photos with vehicles where nothing was blurred stay private. It does not guarantee every plate in a photo was blurred: with several vehicles, a photo where one plate was found passes rule 4 and then relies on Gemini's readability check for the others. Expect most night street photos with vehicles to stay private until a detector trained on Indian plates is added.

## Errors and retries

Every error (rate limit, timeout, server error, malformed or oddly structured answer, unexpected crash) counts as one attempt; after 5 the photo is `failed` (private, never scored, original deleted). Each photo is processed in its own error handler, so one bad photo cannot block the others. A blurred copy that disappears mid-way ends as `failed` (or `expired` after the 6-hour limit). Abandoned `.tmp` files in the blurred-photo folder are removed by the existing retention job after 10 minutes.

## What the score uses

Only observations that are analysed (`analysis_status = done`) **and privacy-approved** (`photo_public`) count (blueprint §7 formula unchanged, with freshness). Pending, blocked, failed, unclear, expired and private observations never affect scores or the route briefing. Consequence: while plate detection is weak, many night photos with vehicles will not affect scores. Low-confidence analyses may only **lower** a score, never raise it (the formula is computed with and without them and the lower value is used).

## Still needed

1. **A Gemini key** (`GEMINI_API_KEY` in `backend/.env`) — without it no photo is analysed, scored or shown.
2. **Real night photos/videos** to measure: how many faces/plates the detectors miss, how often Gemini's double-check catches them, how often photos end up private, and whether Gemini's lighting/people judgements match reality. Look at 30–50 processed photos by hand before the demo.
3. Better detectors before any real use (e.g. a modern face detector such as YuNet/RetinaFace and a plate detector trained on Indian plates), or blurring on the phone before upload (blueprint production plan).

## Versions and installation notes

- `opencv-python-headless==4.14.0.94` and `numpy==2.5.4` (pinned in `requirements.txt`). **OpenCV 5 cannot be used**: it removed the Haar cascade classifier and its bundled face/plate files.
- On 2026-10-30 pip's download from PyPI was extremely slow (~20 KB/s) although the line is fast: IPv6 to PyPI's CDN failed and single IPv4 connections were throttled. The wheels were fetched over IPv4 in 8 parallel ranges and **verified against PyPI's SHA-256** before an offline install (`pip install --no-index --find-links <folder> ...`). If this happens on another machine, do the same rather than trusting a partial download.
