import importlib

import httpx
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

    import app.routers.imports as imports_module
    import app.routers.jobs as jobs_module
    import app.routers.profile as profile_module

    monkeypatch.setattr(jobs_module, "db", db_module.db)
    monkeypatch.setattr(profile_module, "db", db_module.db)
    monkeypatch.setattr(imports_module, "db", db_module.db)

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


class FakeResponse:
    def __init__(self, *, text=None, json_data=None, status_code=200):
        self.text = text
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


JOB_POSTING_HTML = """
<html><head>
<script type="application/ld+json">
{"@type": "JobPosting", "title": "Backend Engineer",
 "hiringOrganization": {"name": "Acme"},
 "jobLocation": {"address": {"addressLocality": "Remote"}},
 "description": "<p>Build things.</p>"}
</script>
</head><body></body></html>
"""


def test_import_from_url(client, monkeypatch):
    import app.routers.imports as imports_module

    monkeypatch.setattr(
        imports_module.httpx, "get", lambda *a, **k: FakeResponse(text=JOB_POSTING_HTML)
    )

    res = client.post("/api/imports/url", json={"url": "https://example.com/job/9"})
    assert res.status_code == 200
    job = res.json()
    assert job["title"] == "Backend Engineer"
    assert job["company"] == "Acme"
    assert job["location"] == "Remote"


def test_import_greenhouse_filters_by_keyword(client, monkeypatch):
    import app.routers.imports as imports_module

    payload = {
        "jobs": [
            {"title": "Backend Engineer", "location": {"name": "Remote"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/1"},
            {"title": "Sales Rep", "location": {"name": "NYC"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/2"},
        ]
    }
    monkeypatch.setattr(
        imports_module.httpx, "get", lambda *a, **k: FakeResponse(json_data=payload)
    )

    res = client.get("/api/imports/greenhouse", params={"board": "acme", "keyword": "engineer"})
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["title"] == "Backend Engineer"
    assert results[0]["company"] == "acme"


def test_import_lever_and_bulk_import(client, monkeypatch):
    import app.routers.imports as imports_module

    payload = [
        {"text": "Platform Engineer", "categories": {"location": "SF"}, "hostedUrl": "https://jobs.lever.co/acme/1"},
    ]
    monkeypatch.setattr(
        imports_module.httpx, "get", lambda *a, **k: FakeResponse(json_data=payload)
    )

    res = client.get("/api/imports/lever", params={"board": "acme"})
    assert res.status_code == 200
    candidates = res.json()
    assert len(candidates) == 1

    res_bulk = client.post("/api/imports/bulk", json={"jobs": candidates})
    assert res_bulk.status_code == 200
    saved = res_bulk.json()
    assert saved[0]["title"] == "Platform Engineer"

    # Re-importing the same URL dedupes rather than duplicating.
    res_bulk2 = client.post("/api/imports/bulk", json={"jobs": candidates})
    assert res_bulk2.json()[0]["id"] == saved[0]["id"]
    assert len(client.get("/api/jobs").json()) == 1


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
