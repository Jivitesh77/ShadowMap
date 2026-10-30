from fastapi.testclient import TestClient

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
