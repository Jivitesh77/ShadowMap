from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.main import app


def test_health_reports_ok_and_hides_secrets():
    with TestClient(app) as client:
        res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert isinstance(body["gemini_configured"], bool)  # only yes/no, never the key itself
    assert "GEMINI_API_KEY" not in res.text


def test_summary_counts_tables():
    with TestClient(app) as client:
        res = client.get("/api/summary")
    assert res.status_code == 200
    for table in ["streets", "places", "observations", "reports", "walks", "alerts", "active_walks", "open_alerts"]:
        assert isinstance(res.json()[table], int)


def test_root_points_to_the_app():
    with TestClient(app) as client:
        res = client.get("/")
    assert res.status_code == 200
    assert "localhost:5173" in res.json()["message"]


def test_built_app_is_served_after_the_api(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("no")
    monkeypatch.setattr(config, "FRONTEND_DIST", Path(tmp_path))
    with TestClient(app) as client:
        page = client.get("/trip/abc")  # app page addresses fall back to index.html
        asset = client.get("/assets/app.js")
        api = client.get("/api/health")
        missing_api = client.get("/api/does-not-exist")
        outside = client.get("/..%2Fsecret.txt")
    assert page.status_code == 200 and "id=root" in page.text
    assert "camera=(self)" in page.headers["permissions-policy"] and "x-frame-options" not in page.headers
    assert asset.status_code == 200 and "console.log" in asset.text
    assert api.json()["database"] == "ok"  # API routes win over the app
    assert missing_api.status_code == 404 and missing_api.headers["content-type"] == "application/json"
    assert "no" != outside.text and "id=root" in outside.text
