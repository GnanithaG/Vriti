import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import app.db as db_module

    importlib.reload(db_module)
    monkeypatch.setattr(db_module, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "data" / "jobpilot.db")
    db_module.DATA_DIR.mkdir(exist_ok=True)

    import app.routers.jobs as jobs_module
    import app.routers.profile as profile_module

    monkeypatch.setattr(jobs_module, "db", db_module.db)
    monkeypatch.setattr(profile_module, "db", db_module.db)

    import app.main as main_module

    importlib.reload(main_module)
    monkeypatch.setattr(main_module, "init_db", db_module.init_db)

    with TestClient(main_module.app) as test_client:
        yield test_client


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_job_create_list_and_dedupe(client):
    payload = {
        "url": "https://example.com/job/1",
        "title": "Engineer",
        "company": "Acme",
        "location": "Remote",
    }
    res = client.post("/api/jobs", json=payload)
    assert res.status_code == 200
    job = res.json()
    assert job["title"] == "Engineer"
    assert job["stage"] == "saved"

    # Deduping by URL returns the existing row, not a second insert.
    res2 = client.post("/api/jobs", json=payload)
    assert res2.json()["id"] == job["id"]

    res3 = client.get("/api/jobs")
    assert len(res3.json()) == 1


def test_job_stage_update(client):
    job = client.post("/api/jobs", json={"url": "https://example.com/job/2"}).json()
    res = client.patch(f"/api/jobs/{job['id']}/stage", json={"stage": "applied"})
    assert res.status_code == 200
    assert res.json()["stage"] == "applied"

    res_invalid = client.patch(f"/api/jobs/{job['id']}/stage", json={"stage": "bogus"})
    assert res_invalid.status_code == 400

    res_missing = client.patch("/api/jobs/999/stage", json={"stage": "applied"})
    assert res_missing.status_code == 404


def test_profile_roundtrip(client):
    res = client.put(
        "/api/profile",
        json={"full_name": "Ada Lovelace", "email": "ada@example.com"},
    )
    assert res.status_code == 200
    assert res.json()["full_name"] == "Ada Lovelace"

    res_prefill = client.get("/api/prefill")
    data = res_prefill.json()
    assert data["first_name"] == "Ada"
    assert data["last_name"] == "Lovelace"
    assert data["email"] == "ada@example.com"
