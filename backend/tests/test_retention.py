"""Photos, uploaded videos and walk personal data are deleted when promised."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app import config, models
from app.db import engine, init_db, utcnow
from app.services import retention


def test_expired_photos_videos_and_old_walks_are_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PHOTO_DIR", tmp_path / "photos")
    monkeypatch.setattr(config, "VIDEO_DIR", tmp_path / "videos")
    (tmp_path / "photos").mkdir()
    (tmp_path / "videos").mkdir()
    old, fresh, up = tmp_path / "photos" / "old.jpg", tmp_path / "photos" / "fresh.jpg", tmp_path / "videos" / "upload_x__r.mp4"
    for f in (old, fresh, up):
        f.write_bytes(b"x")
    outside = tmp_path / "keep.jpg"
    outside.write_bytes(b"x")
    now = utcnow()
    init_db()
    with Session(engine) as db:
        o1 = models.Observation(sentinel_label="t", source="live", captured_at=now, lat=0, lon=0, photo_path=str(old),
                                photo_delete_at=now - timedelta(minutes=1), description="Dark lane", analysis_status="done")
        o2 = models.Observation(sentinel_label="t", source="live", captured_at=now, lat=0, lon=0, photo_path=str(fresh),
                                photo_delete_at=now + timedelta(hours=5))
        o3 = models.Observation(sentinel_label="t", source="live", captured_at=now, lat=0, lon=0, photo_path=str(outside),
                                photo_delete_at=now - timedelta(minutes=1))  # a path outside the photo folder is never deleted
        job = models.VideoJob(original_name="r.mp4", source_kind="upload", file_path=str(up), sentinel_label="t",
                              file_delete_at=now - timedelta(minutes=1))
        w = models.Walk(id="ret-walk", walker_name="Priya", walker_phone="9", route=[[0, 0], [0, 1]], dest_lat=1, dest_lon=1,
                        pin_hash="x", status="ended", ended_at=now - timedelta(hours=25), last_lat=1, last_lon=1, events=[{"t": 1}])
        w.contacts.append(models.Contact(name="Roommate", phone="8"))
        w.alerts.append(models.Alert(level="police", trigger="sos", lat=1.0, lon=1.0))
        db.add_all([o1, o2, o3, job, w])
        db.commit()
        result = retention.run(db, now)
        assert result["photos_deleted"] == 2 and result["videos_deleted"] == 1 and result["walks_anonymised"] >= 1
        assert not old.exists() and fresh.exists() and not up.exists() and outside.exists()
        db.refresh(o1)
        assert o1.photo_path is None and o1.description == "Dark lane"  # AI text kept
        db.refresh(w)
        assert w.walker_name == "(deleted)" and w.walker_phone is None and w.contacts == [] and w.last_lat is None
        assert w.alerts[0].lat is None and w.alerts[0].trigger == "sos"  # the alert record stays, without location
