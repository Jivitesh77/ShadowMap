"""M6: Gemini photo analysis, face/plate redaction, fail-closed privacy, photo endpoint, deletion, score integration.

All images are generated in the test (shapes and drawn rectangles) — no real photos, nobody's face.
These tests prove the pipeline's logic and fail-closed behaviour. They do NOT measure real-world detection accuracy.
"""

import io
import json
import urllib.error
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import engine, init_db, utcnow
from app.main import app
from app.services import photo_analysis, photo_worker, redaction, retention
from app.services.photo_analysis import AnalysisError, Analysis, validate
from app.services.scoring import Photo, street_score
from app.services.street_state import score_streets

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

GOOD = {"unclear": False, "lighting": "dark", "streetlights_visible": 3, "streetlights_working": 1, "people": "none",
        "open_places_count": 0, "open_places_types": [], "vehicles": "some", "isolation": "lane", "hazards": ["broken road"],
        "description": "Narrow lane with one working streetlight and no open shops.", "confidence": "high",
        "uncertainty": "", "privacy": {"unredacted_faces": 0, "legible_number_plates": 0}}


def jpeg(w=800, h=500, seed=1) -> bytes:
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    cv2.rectangle(img, (500, 380), (660, 420), (255, 255, 255), -1)  # a plate-like white box
    cv2.putText(img, "AS01 AB 1234", (505, 410), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PHOTO_DIR", tmp_path / "photos")
    monkeypatch.setattr(config, "REDACTED_DIR", tmp_path / "photos" / "redacted")
    (tmp_path / "photos").mkdir()
    init_db()
    return tmp_path


def new_obs(dirs, db, data=None, **kw) -> models.Observation:
    o = models.Observation(sentinel_label="Test #01", source="live", captured_at=utcnow(), lat=0, lon=0,
                           photo_delete_at=utcnow() + timedelta(hours=6), analysis_status="pending", **kw)
    db.add(o)
    db.flush()
    p = config.PHOTO_DIR / f"live_test_{o.id}.jpg"
    p.write_bytes(data or jpeg(seed=o.id))
    o.photo_path = str(p)
    db.commit()
    return o


def fixed_detector(faces=(), plates=()):
    return lambda img: (list(faces), list(plates))


# ---------------- Gemini output validation ----------------

def test_validate_accepts_the_fixed_format():
    a = validate(GOOD)
    assert a.lighting == "dark" and a.streetlights_working == 1 and a.unredacted_faces == 0
    assert validate({"unclear": True, "privacy": {"unredacted_faces": 0, "legible_number_plates": 0}}).unclear


@pytest.mark.parametrize("bad", [
    "not a dict",
    {**GOOD, "lighting": "medium"},
    {**GOOD, "streetlights_working": 5},  # more working than visible
    {**GOOD, "people": 3},
    {**GOOD, "hazards": ["aliens"]},
    {**GOOD, "privacy": None},
    {**GOOD, "unclear": "no"},
    {**GOOD, "description": ""},
    {**GOOD, "description": "A young woman walks alone past a shop."},  # describes a person: rejected
    {**GOOD, "open_places_count": -1},
    {**GOOD, "streetlights_visible": True},
])
def test_validate_rejects_malformed_or_personal_output(bad):
    with pytest.raises(AnalysisError) as e:
        validate(bad)
    assert e.value.kind == "invalid"


# ---------------- Gemini call: key, errors, timeouts ----------------

class FakeRes(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def gemini_reply(obj) -> FakeRes:
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return FakeRes(json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode())


def test_analyse_without_key(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(AnalysisError) as e:
        photo_analysis.analyse(b"x")
    assert e.value.kind == "no_key"


def test_analyse_success_sends_image_with_key_in_header(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    seen = {}

    def fake(req, timeout):
        seen["url"], seen["headers"], seen["body"] = req.full_url, dict(req.header_items()), json.loads(req.data)
        return gemini_reply(GOOD)

    monkeypatch.setattr(photo_analysis.urllib.request, "urlopen", fake)
    a = photo_analysis.analyse(b"\xff\xd8jpeg")
    assert a.description.startswith("Narrow lane")
    assert "fake-key" not in seen["url"] and seen["headers"]["X-goog-api-key"] == "fake-key"
    parts = seen["body"]["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/jpeg"


@pytest.mark.parametrize("failure,kind", [
    (urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b"")), "rate_limited"),
    (urllib.error.HTTPError("u", 500, "Err", {}, io.BytesIO(b"")), "http"),
    (urllib.error.URLError("timed out"), "timeout"),
    (TimeoutError(), "timeout"),
])
def test_analyse_errors(monkeypatch, failure, kind):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")

    def boom(req, timeout):
        raise failure

    monkeypatch.setattr(photo_analysis.urllib.request, "urlopen", boom)
    with pytest.raises(AnalysisError) as e:
        photo_analysis.analyse(b"x")
    assert e.value.kind == kind and "fake-key" not in e.value.message


def test_analyse_invalid_json(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(photo_analysis.urllib.request, "urlopen", lambda req, timeout: gemini_reply("this is not json"))
    with pytest.raises(AnalysisError) as e:
        photo_analysis.analyse(b"x")
    assert e.value.kind == "invalid"


# ---------------- Redaction ----------------

def test_blur_changes_only_the_detected_regions(dirs, tmp_path):
    src, dest = tmp_path / "in.jpg", tmp_path / "out.jpg"
    src.write_bytes(jpeg(640, 400))
    r = redaction.redact_file(src, dest, detector=fixed_detector(faces=[(100, 100, 60, 60)], plates=[(400, 300, 120, 30)]))
    assert (r.faces, r.plates) == (1, 1)
    before = cv2.imdecode(np.frombuffer(src.read_bytes(), np.uint8), cv2.IMREAD_COLOR).astype(int)
    after = cv2.imdecode(np.frombuffer(dest.read_bytes(), np.uint8), cv2.IMREAD_COLOR).astype(int)
    face_box = (slice(105, 155), slice(105, 155))
    assert np.abs(before[face_box] - after[face_box]).mean() > 30  # random noise inside the face box is smoothed away
    assert after[face_box].std() < before[face_box].std() / 3
    far = (slice(0, 60), slice(560, 640))
    assert np.abs(before[far] - after[far]).mean() < 12  # elsewhere only JPEG re-encoding differences


def test_redacted_copy_is_small_and_has_no_exif(dirs, tmp_path):
    raw = jpeg(1600, 1000)
    exif = b"\xff\xe1" + (30).to_bytes(2, "big") + b"Exif\x00\x00" + b"GPS-LAT-26.0804" + b"\x00" * 7
    src, dest = tmp_path / "in.jpg", tmp_path / "out.jpg"
    src.write_bytes(raw[:2] + exif + raw[2:])  # a phone photo with location metadata
    assert b"Exif" in src.read_bytes()
    r = redaction.redact_file(src, dest, detector=fixed_detector())
    assert r.width == 640 and b"Exif" not in dest.read_bytes() and b"GPS-LAT" not in dest.read_bytes()


def test_real_detectors_load_and_run_on_synthetic_images(dirs, tmp_path):
    """Smoke test only: the bundled detectors load and run. It says nothing about accuracy on real night photos."""
    img = cv2.imdecode(np.frombuffer(jpeg(), np.uint8), cv2.IMREAD_COLOR)
    faces, plates = redaction.detect(img)
    assert isinstance(faces, list) and isinstance(plates, list)
    src = tmp_path / "x.jpg"
    src.write_bytes(jpeg())
    assert redaction.redact_file(src, tmp_path / "y.jpg").width == 640


def test_redaction_fails_closed(dirs, tmp_path, monkeypatch):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    with pytest.raises(redaction.RedactionError):
        redaction.redact_file(bad, tmp_path / "o1.jpg")
    good = tmp_path / "good.jpg"
    good.write_bytes(jpeg())

    def broken_detector(img):
        raise RuntimeError("model crashed")

    with pytest.raises(redaction.RedactionError):
        redaction.redact_file(good, tmp_path / "o2.jpg", detector=broken_detector)
    assert not (tmp_path / "o2.jpg").exists()
    monkeypatch.setattr(redaction, "_detectors", None)
    monkeypatch.setattr(redaction, "_load", lambda: (_ for _ in ()).throw(redaction.RedactionError("OpenCV is not installed")))
    with pytest.raises(redaction.RedactionError):
        redaction.redact_file(good, tmp_path / "o3.jpg")


# ---------------- Pipeline + photo endpoint ----------------

def ok_ai(**over):
    """A valid analysis; by default an empty dark lane (no people, no vehicles) so it can pass every privacy check."""
    base = {**validate(GOOD).__dict__, "vehicles": "none", "people": "none"}
    return lambda data: Analysis(**{**base, **over})


def test_clean_photo_is_analysed_approved_served_and_original_deleted(dirs):
    with Session(engine) as db:
        o = new_obs(dirs, db)
        original = o.photo_path
        assert photo_worker.process(o, utcnow(), redact_fn=None, analyse_fn=ok_ai()) == "done"
        db.commit()
        assert o.analysis_status == "done" and o.photo_public and o.photo_score is not None
        assert o.photo_path is None and not __import__("os").path.exists(original)  # original gone
        oid, redacted = o.id, o.redacted_path
    with TestClient(app) as c:
        r = c.get(f"/api/photos/{oid}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.headers["cache-control"] == "no-store"
        assert r.content == open(redacted, "rb").read()


def test_ai_still_sees_a_face_keeps_photo_private_but_uses_analysis(dirs):
    with Session(engine) as db:
        o = new_obs(dirs, db)
        photo_worker.process(o, utcnow(), analyse_fn=ok_ai(unredacted_faces=1))
        db.commit()
        assert o.analysis_status == "done" and o.photo_public is False and "face" in o.privacy_note
        oid = o.id
    with TestClient(app) as c:
        assert c.get(f"/api/photos/{oid}").status_code == 404


def test_redaction_failure_blocks_analysis_and_display(dirs):
    def failing(src, dest):
        raise redaction.RedactionError("detector not loaded")

    called = []
    with Session(engine) as db:
        o = new_obs(dirs, db)
        assert photo_worker.process(o, utcnow(), redact_fn=failing, analyse_fn=lambda d: called.append(1)) == "blocked"
        db.commit()
        assert o.redaction_status == "failed" and o.analysis_status == "blocked" and not o.photo_public and o.redacted_path is None
        assert called == []  # the unblurred original was never sent to the AI
        oid = o.id
    with TestClient(app) as c:
        assert c.get(f"/api/photos/{oid}").status_code == 404


def test_original_is_never_served(dirs):
    with Session(engine) as db:
        o = new_obs(dirs, db)  # only an original exists
        trick = new_obs(dirs, db)
        trick.photo_public, trick.redaction_status, trick.redacted_path = True, "done", trick.photo_path  # points at an original
        db.commit()
        ids = (o.id, trick.id)
    with TestClient(app) as c:
        for i in ids:
            assert c.get(f"/api/photos/{i}").status_code == 404
        assert c.get("/api/photos/999999999").status_code == 404


def test_retries_rate_limits_and_give_up(dirs):
    def limited(data):
        raise AnalysisError("rate_limited", "429")

    with Session(engine) as db:
        o = new_obs(dirs, db)
        now = utcnow()
        assert photo_worker.process(o, now, analyse_fn=limited) == "retry"
        assert o.analysis_status == "pending" and o.analysis_attempts == 1 and o.next_attempt_at > now
        for _ in range(config.ANALYSIS_MAX_ATTEMPTS - 1):
            photo_worker.process(o, now, analyse_fn=limited)
        assert o.analysis_status == "failed" and not o.photo_public and o.photo_path is None
        db.commit()


def test_no_key_waits_without_changing_anything(dirs, monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with Session(engine) as db:
        o = new_obs(dirs, db)
        assert photo_worker.process(o, utcnow()) == "waiting"
        assert o.redaction_status == "done" and o.analysis_status == "pending" and not o.photo_public and o.photo_path
        db.commit()


def test_unclear_photo_is_never_scored(dirs):
    with Session(engine) as db:
        o = new_obs(dirs, db)
        photo_worker.process(o, utcnow(), analyse_fn=lambda d: Analysis(unclear=True))
        db.commit()
        assert o.analysis_status == "unclear" and o.photo_score is None


# ---------------- Six-hour deletion ----------------

def test_six_hour_deletion_removes_original_and_blurred_copy(dirs):
    with Session(engine) as db:
        done = new_obs(dirs, db)
        photo_worker.process(done, utcnow(), analyse_fn=ok_ai())
        waiting = new_obs(dirs, db)
        photo_worker.redact_step(waiting)
        for o in (done, waiting):
            o.photo_delete_at = utcnow() - timedelta(minutes=1)
        db.commit()
        files = [done.redacted_path, waiting.photo_path, waiting.redacted_path]
        retention.run(db, utcnow())
        db.refresh(done)
        db.refresh(waiting)
        assert all(not __import__("os").path.exists(f) for f in files)
        assert done.redacted_path is None and not done.photo_public and done.description  # AI text kept
        assert waiting.analysis_status == "expired"
        ids = (done.id, waiting.id)
    with TestClient(app) as c:
        for i in ids:
            assert c.get(f"/api/photos/{i}").status_code == 404


# ---------------- Score integration ----------------

def test_uncertain_evidence_never_raises_a_score():
    assert street_score(40, [Photo(85, 5, uncertain=True)], []).score == 40  # would have raised it: ignored
    lowered = street_score(60, [Photo(0, 5, uncertain=True)], [])
    assert lowered.score < 60  # may lower it
    assert street_score(40, [Photo(85, 5)], []).score > 70  # a confident photo counts fully (blueprint formula)


def test_only_done_observations_change_street_scores(dirs):
    with Session(engine) as db:
        s = models.Street(osm_way_id=550001, name="Photo Test Rd", road_type="residential", road_class="residential",
                          start_node=550001, end_node=550002, length_m=100, geometry=[[33.0, 96.0], [33.0009, 96.0]])
        db.add(s)
        db.commit()
        base = score_streets(db, utcnow())[s.id].score
        pending = new_obs(dirs, db, street_id=s.id)
        assert score_streets(db, utcnow())[s.id].score == base  # pending: no effect
        photo_worker.process(pending, utcnow(), analyse_fn=ok_ai())  # dark empty lane, confident, approved
        db.commit()
        after = score_streets(db, utcnow())[s.id]
        assert after.score < base and after.photo_score is not None and after.freshest_photo_age_min is not None
        failed = new_obs(dirs, db, street_id=s.id)
        failed.analysis_status = "failed"
        db.commit()
        assert score_streets(db, utcnow())[s.id].score == after.score  # failed analysis changes nothing


def test_yunet_model_is_checked_and_fails_closed(dirs, tmp_path, monkeypatch):
    src = tmp_path / "x.jpg"
    src.write_bytes(jpeg())
    monkeypatch.setattr(redaction, "_detectors", None)
    monkeypatch.setattr(config, "YUNET_SHA256", "0" * 64)  # a tampered or wrong model file
    with pytest.raises(redaction.RedactionError, match="checksum"):
        redaction.redact_file(src, tmp_path / "o1.jpg")
    monkeypatch.setattr(redaction, "_detectors", None)
    monkeypatch.setattr(config, "YUNET_MODEL", tmp_path / "missing.onnx")
    with pytest.raises(redaction.RedactionError, match="missing"):
        redaction.redact_file(src, tmp_path / "o2.jpg")
    assert not (tmp_path / "o1.jpg").exists() and not (tmp_path / "o2.jpg").exists()
    monkeypatch.setattr(redaction, "_detectors", None)  # leave a clean state for other tests


def test_yunet_is_loaded_and_used(dirs):
    redaction._detectors = None
    cv2_, d = redaction._load()
    assert "yunet" in d and cv2_.__version__.startswith("4.")
    img = cv2.imdecode(np.frombuffer(jpeg(), np.uint8), cv2.IMREAD_COLOR)
    faces, plates = redaction.detect(img)  # runs YuNet (twice) + Haar; synthetic image: accuracy not tested
    assert isinstance(faces, list) and isinstance(plates, list)



# ---------------- Regression tests for the M6 review fixes ----------------

def with_boxes(faces=0, plates=0):
    """A real redaction run with injected detector boxes (so we know how many faces/plates were blurred)."""
    def fn(src, dest):
        return redaction.redact_file(src, dest, detector=fixed_detector(
            faces=[(10 + 60 * i, 10, 40, 40) for i in range(faces)], plates=[(10 + 130 * i, 300, 110, 30) for i in range(plates)]))
    return fn


@pytest.mark.parametrize("nested", [
    {**GOOD, "hazards": [["broken road"]]},
    {**GOOD, "open_places_types": [{"type": "shop"}]},
    {**GOOD, "hazards": "none"},
    {**GOOD, "privacy": {"unredacted_faces": "0", "legible_number_plates": 0}},
    {**GOOD, "uncertainty": ["dark"]},
    {**GOOD, "lighting": ["dark"]},
])
def test_malformed_nested_answers_are_controlled_errors(nested):
    with pytest.raises(AnalysisError) as e:
        validate(nested)
    assert e.value.kind == "invalid"


def test_malformed_answer_counts_as_attempt_in_worker(dirs):
    with Session(engine) as db:
        o = new_obs(dirs, db)
        assert photo_worker.process(o, utcnow(), analyse_fn=lambda d: validate({**GOOD, "hazards": [["x"]]})) == "retry"
        assert o.analysis_attempts == 1 and not o.photo_public
        db.commit()


def test_missing_blurred_file_ends_cleanly(dirs):
    with Session(engine) as db:
        o = new_obs(dirs, db)
        photo_worker.redact_step(o)
        __import__("os").unlink(o.redacted_path)
        assert photo_worker.process(o, utcnow(), analyse_fn=ok_ai()) == "failed"
        assert o.analysis_status == "failed" and not o.photo_public and o.photo_path is None
        expired = new_obs(dirs, db)
        photo_worker.redact_step(expired)
        __import__("os").unlink(expired.redacted_path)
        expired.photo_delete_at = utcnow() - timedelta(minutes=1)
        assert photo_worker.process(expired, utcnow(), analyse_fn=ok_ai()) == "expired"
        db.commit()


def test_five_failed_attempts_end_in_failed_state_for_any_error(dirs):
    def crash(data):
        raise KeyError("unexpected")  # not an AnalysisError

    with Session(engine) as db:
        o = new_obs(dirs, db)
        results = [photo_worker.process(o, utcnow(), analyse_fn=crash) for _ in range(config.ANALYSIS_MAX_ATTEMPTS)]
        assert results[:-1] == ["retry"] * (config.ANALYSIS_MAX_ATTEMPTS - 1) and results[-1] == "failed"
        assert o.analysis_status == "failed" and o.analysis_attempts == config.ANALYSIS_MAX_ATTEMPTS
        assert not o.photo_public and o.photo_path is None
        db.commit()
        oid = o.id
    with Session(engine) as db:
        assert oid not in [x.id for x in photo_worker.due(db, utcnow() + timedelta(days=1))]  # never picked up again


def test_crashing_photo_does_not_block_the_next_one(dirs, monkeypatch):
    with Session(engine) as db:
        bad, good = new_obs(dirs, db), new_obs(dirs, db)
        ids = (bad.id, good.id)

    def boom(o, now, redact_fn=None, analyse_fn=None):
        if o.id == ids[0]:
            raise RuntimeError("database row vanished")
        return real_process(o, now, redact_fn, analyse_fn)

    real_process = photo_worker.process
    monkeypatch.setattr(photo_worker, "process", boom)
    with Session(engine) as db:
        r1 = photo_worker.process_safely(db, ids[0], utcnow(), analyse_fn=ok_ai())
        r2 = photo_worker.process_safely(db, ids[1], utcnow(), analyse_fn=ok_ai())
        assert r1 == "retry" and db.get(models.Observation, ids[0]).analysis_attempts == 1
        assert r2 == "done" and db.get(models.Observation, ids[1]).photo_public is True


def test_vehicles_without_a_blurred_plate_stay_private(dirs):
    with Session(engine) as db:
        o = new_obs(dirs, db)
        photo_worker.process(o, utcnow(), redact_fn=with_boxes(faces=0, plates=0), analyse_fn=ok_ai(vehicles="some"))
        assert o.analysis_status == "done" and o.photo_public is False and "no number plate" in o.privacy_note
        db.commit()


def test_people_without_a_blurred_face_stay_private(dirs):
    with Session(engine) as db:
        o = new_obs(dirs, db)
        photo_worker.process(o, utcnow(), redact_fn=with_boxes(faces=0, plates=0), analyse_fn=ok_ai(people="few"))
        assert o.photo_public is False and "no face" in o.privacy_note
        db.commit()


def test_both_checks_passing_makes_photo_public_and_scored(dirs):
    with Session(engine) as db:
        o = new_obs(dirs, db)
        photo_worker.process(o, utcnow(), redact_fn=with_boxes(faces=2, plates=2), analyse_fn=ok_ai(people="few", vehicles="some"))
        assert (o.faces_blurred, o.plates_blurred) == (2, 2)
        assert o.photo_public is True and o.privacy_note is None and o.analysis_status == "done"
        db.commit()


def test_uncertain_or_unclear_analysis_stays_private(dirs):
    with Session(engine) as db:
        low = new_obs(dirs, db)
        photo_worker.process(low, utcnow(), analyse_fn=ok_ai(confidence="low"))
        unclear = new_obs(dirs, db)
        photo_worker.process(unclear, utcnow(), analyse_fn=lambda d: Analysis(unclear=True))
        assert low.photo_public is False and "uncertain" in low.privacy_note
        assert unclear.photo_public is False and unclear.analysis_status == "unclear"
        db.commit()


def test_private_observations_never_change_scores(dirs):
    with Session(engine) as db:
        s = models.Street(osm_way_id=550101, name="Private Photo Rd", road_type="residential", road_class="residential",
                          start_node=550101, end_node=550102, length_m=100, geometry=[[34.0, 97.0], [34.0009, 97.0]])
        db.add(s)
        db.commit()
        base = score_streets(db, utcnow())[s.id].score
        o = new_obs(dirs, db, street_id=s.id)
        photo_worker.process(o, utcnow(), redact_fn=with_boxes(), analyse_fn=ok_ai(vehicles="busy"))  # analysed, not approved
        db.commit()
        assert o.analysis_status == "done" and not o.photo_public
        assert score_streets(db, utcnow())[s.id].score == base


def test_abandoned_tmp_files_are_cleaned_but_fresh_ones_kept(dirs):
    import os
    import time
    config.REDACTED_DIR.mkdir(parents=True, exist_ok=True)
    old, fresh, keep = config.REDACTED_DIR / "obs1.tmp", config.REDACTED_DIR / "obs2.tmp", config.REDACTED_DIR / "obs3.jpg"
    for f in (old, fresh, keep):
        f.write_bytes(b"x")
    past = time.time() - 3600
    os.utime(old, (past, past))
    os.utime(keep, (past, past))
    with Session(engine) as db:
        result = retention.run(db, utcnow())
    assert result["tmp_files_removed"] >= 1 and not old.exists()
    assert fresh.exists()  # may still be being written
    assert keep.exists()  # a .jpg is only removed by the 6-hour rule via its observation
