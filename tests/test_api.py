import importlib
import io
from urllib.parse import unquote

import docx
import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-for-production")

    import app.db as db_module

    importlib.reload(db_module)
    resumes_dir = tmp_path / "data" / "resumes"
    monkeypatch.setattr(db_module, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "data" / "jobpilot.db")
    monkeypatch.setattr(db_module, "RESUMES_DIR", resumes_dir)
    db_module.DATA_DIR.mkdir(exist_ok=True)
    resumes_dir.mkdir(exist_ok=True)

    import app.auth as auth_module
    import app.routers.applications as applications_module
    import app.routers.auth as auth_router_module
    import app.routers.careers as careers_module
    import app.routers.imports as imports_module
    import app.routers.profile as profile_module
    import app.routers.resumes as resumes_module
    import app.routers.stats as stats_module
    import app.routers.tailoring as tailoring_module

    monkeypatch.setattr(auth_module, "db", db_module.db)
    monkeypatch.setattr(auth_router_module, "db", db_module.db)
    monkeypatch.setattr(applications_module, "db", db_module.db)
    monkeypatch.setattr(careers_module, "db", db_module.db)
    monkeypatch.setattr(profile_module, "db", db_module.db)
    monkeypatch.setattr(imports_module, "db", db_module.db)
    monkeypatch.setattr(resumes_module, "db", db_module.db)
    monkeypatch.setattr(resumes_module, "RESUMES_DIR", resumes_dir)
    monkeypatch.setattr(stats_module, "db", db_module.db)
    monkeypatch.setattr(tailoring_module, "db", db_module.db)
    monkeypatch.setattr(tailoring_module, "RESUMES_DIR", resumes_dir)

    import app.main as main_module

    importlib.reload(main_module)
    monkeypatch.setattr(main_module, "init_db", db_module.init_db)

    with TestClient(main_module.app) as test_client:
        yield test_client


def register(client, email="user1@example.com", password="password123"):
    res = client.post("/api/auth/register", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def make_docx_bytes(paragraphs):
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# --- Auth --------------------------------------------------------------


def test_register_login_logout_flow(client):
    register(client, email="ada@example.com", password="hunter22")

    res_me = client.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["email"] == "ada@example.com"

    res_logout = client.post("/api/auth/logout")
    assert res_logout.status_code == 200

    res_me_after_logout = client.get("/api/auth/me")
    assert res_me_after_logout.status_code == 401

    res_login = client.post(
        "/api/auth/login", json={"email": "ada@example.com", "password": "hunter22"}
    )
    assert res_login.status_code == 200

    res_me_again = client.get("/api/auth/me")
    assert res_me_again.status_code == 200


def test_register_duplicate_email_rejected(client):
    register(client, email="dupe@example.com")
    res = client.post(
        "/api/auth/register", json={"email": "dupe@example.com", "password": "password123"}
    )
    assert res.status_code == 400


def test_register_short_password_rejected(client):
    res = client.post(
        "/api/auth/register", json={"email": "short@example.com", "password": "abc"}
    )
    assert res.status_code == 400


def test_login_wrong_password_is_generic_error(client):
    register(client, email="ada2@example.com", password="correct-password")
    client.post("/api/auth/logout")

    res_wrong_password = client.post(
        "/api/auth/login", json={"email": "ada2@example.com", "password": "wrong"}
    )
    res_unknown_email = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )
    assert res_wrong_password.status_code == 401
    assert res_unknown_email.status_code == 401
    # Same generic message either way — never reveals whether the email exists.
    assert res_wrong_password.json()["detail"] == res_unknown_email.json()["detail"]


def test_unauthenticated_requests_are_rejected(client):
    for method, path in [
        ("get", "/api/applications"),
        ("get", "/api/profile"),
        ("get", "/api/resumes"),
        ("get", "/api/stats"),
    ]:
        res = getattr(client, method)(path)
        assert res.status_code == 401, f"{method.upper()} {path} should require auth"


def test_two_accounts_do_not_see_each_others_data(client):
    register(client, email="user1@example.com")
    application1 = client.post(
        "/api/applications",
        json={"url": "https://example.com/job/isolation", "title": "User1's job"},
    ).json()
    content = make_docx_bytes(["User1's resume text"])
    resume1 = client.post(
        "/api/resumes",
        data={"label": "User1 resume"},
        files={"file": ("r.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()
    client.put("/api/profile", json={"full_name": "User One", "email": "user1@example.com"})

    client2 = TestClient(client.app)
    register(client2, email="user2@example.com")

    assert client2.get("/api/applications").json() == []
    assert client2.get("/api/resumes").json() == []
    assert client2.get("/api/profile").json()["full_name"] is None

    # user2 can't reach user1's rows even by guessing the id.
    assert client2.get(f"/api/resumes/{resume1['id']}").status_code == 404
    assert client2.get(f"/api/resumes/{resume1['id']}/download").status_code == 404
    assert (
        client2.patch(f"/api/applications/{application1['id']}/notes", json={"notes": "x"}).status_code
        == 404
    )

    # user1's own data is untouched and still theirs.
    assert len(client.get("/api/applications").json()) == 1
    assert len(client.get("/api/resumes").json()) == 1


# --- Applications (per-user pipeline over the shared job catalog) -------


def test_application_create_list_and_dedupe(client):
    register(client)
    payload = {
        "url": "https://example.com/job/1",
        "title": "Engineer",
        "company": "Acme",
        "location": "Remote",
    }
    res = client.post("/api/applications", json=payload)
    assert res.status_code == 200
    application = res.json()
    assert application["title"] == "Engineer"
    assert application["stage"] == "saved"
    assert application["job_id"] is not None

    # Re-capturing the same URL dedupes the application, not just the catalog row.
    res2 = client.post("/api/applications", json=payload)
    assert res2.json()["id"] == application["id"]

    res3 = client.get("/api/applications")
    assert len(res3.json()) == 1


def test_application_stage_update(client):
    register(client)
    application = client.post("/api/applications", json={"url": "https://example.com/job/2"}).json()
    res = client.patch(f"/api/applications/{application['id']}/stage", json={"stage": "applied"})
    assert res.status_code == 200
    assert res.json()["stage"] == "applied"

    res_invalid = client.patch(
        f"/api/applications/{application['id']}/stage", json={"stage": "bogus"}
    )
    assert res_invalid.status_code == 400

    res_missing = client.patch("/api/applications/999/stage", json={"stage": "applied"})
    assert res_missing.status_code == 404


def test_application_search_and_stage_filter(client):
    register(client)
    client.post("/api/applications", json={"url": "https://example.com/a", "title": "Backend Engineer", "company": "Acme"})
    client.post("/api/applications", json={"url": "https://example.com/b", "title": "Sales Rep", "company": "Widgets Inc"})
    application_c = client.post(
        "/api/applications", json={"url": "https://example.com/c", "title": "Frontend Engineer", "company": "Acme"}
    ).json()
    client.patch(f"/api/applications/{application_c['id']}/stage", json={"stage": "applied"})

    res_q = client.get("/api/applications", params={"q": "engineer"})
    titles = {a["title"] for a in res_q.json()}
    assert titles == {"Backend Engineer", "Frontend Engineer"}

    res_company = client.get("/api/applications", params={"q": "Acme"})
    assert len(res_company.json()) == 2

    res_stage = client.get("/api/applications", params={"stage": "applied"})
    assert [a["id"] for a in res_stage.json()] == [application_c["id"]]

    res_combined = client.get("/api/applications", params={"q": "engineer", "stage": "saved"})
    assert [a["title"] for a in res_combined.json()] == ["Backend Engineer"]


def test_application_notes_update(client):
    register(client)
    application = client.post("/api/applications", json={"url": "https://example.com/notes"}).json()
    assert application["notes"] is None

    res = client.patch(
        f"/api/applications/{application['id']}/notes", json={"notes": "Talked to recruiter Jane."}
    )
    assert res.status_code == 200
    assert res.json()["notes"] == "Talked to recruiter Jane."

    res_missing = client.patch("/api/applications/999/notes", json={"notes": "x"})
    assert res_missing.status_code == 404


def test_application_employment_and_contract_type_classified_on_create(client):
    register(client)
    full_time = client.post(
        "/api/applications",
        json={
            "url": "https://example.com/ft",
            "title": "Backend Engineer",
            "description": "This is a full-time role on our platform team.",
        },
    ).json()
    assert full_time["employment_type"] == "full_time"
    assert full_time["contract_type"] is None

    c2c = client.post(
        "/api/applications",
        json={
            "url": "https://example.com/c2c",
            "title": "Java Developer",
            "description": "6 month contract, C2C only.",
        },
    ).json()
    assert c2c["employment_type"] == "contract"
    assert c2c["contract_type"] == "c2c"

    from_schema_org = client.post(
        "/api/applications",
        json={
            "url": "https://example.com/schema-org",
            "title": "Data Analyst",
            "description": "No type hints in the text itself.",
            "employment_type_raw": "CONTRACTOR",
        },
    ).json()
    assert from_schema_org["employment_type"] == "contract"
    assert from_schema_org["contract_type"] is None


def test_application_filter_by_employment_and_contract_type(client):
    register(client)
    client.post(
        "/api/applications",
        json={"url": "https://example.com/w2", "title": "QA", "description": "W2 contract only."},
    )
    client.post(
        "/api/applications",
        json={"url": "https://example.com/c2h", "title": "DevOps", "description": "Contract-to-hire role."},
    )
    client.post(
        "/api/applications",
        json={"url": "https://example.com/perm", "title": "Manager", "description": "Full-time position."},
    )

    contracts = client.get("/api/applications", params={"employment_type": "contract"}).json()
    assert {a["title"] for a in contracts} == {"QA", "DevOps"}

    c2h_only = client.get("/api/applications", params={"contract_type": "c2h"}).json()
    assert [a["title"] for a in c2h_only] == ["DevOps"]

    full_time_only = client.get("/api/applications", params={"employment_type": "full_time"}).json()
    assert [a["title"] for a in full_time_only] == ["Manager"]


def test_stats_counts_and_response_rate(client):
    register(client)
    ids = []
    for i in range(4):
        application = client.post(
            "/api/applications", json={"url": f"https://example.com/stat/{i}"}
        ).json()
        ids.append(application["id"])

    # 1 saved, 1 applied, 2 interview -> applied_or_beyond=3, reached_interview_or_beyond=2
    client.patch(f"/api/applications/{ids[1]}/stage", json={"stage": "applied"})
    client.patch(f"/api/applications/{ids[2]}/stage", json={"stage": "interview"})
    client.patch(f"/api/applications/{ids[3]}/stage", json={"stage": "interview"})

    res = client.get("/api/stats")
    assert res.status_code == 200
    stats = res.json()

    assert stats["total_jobs"] == 4
    assert stats["counts_by_stage"]["saved"] == 1
    assert stats["counts_by_stage"]["applied"] == 1
    assert stats["counts_by_stage"]["interview"] == 2
    assert stats["applied_or_beyond"] == 3
    assert stats["response_rate"] == 67  # round(2/3 * 100)


def test_applications_csv_export(client):
    register(client)
    client.post("/api/applications", json={"url": "https://example.com/csv", "title": "CSV Role", "company": "Acme"})

    res = client.get("/api/applications/export.csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]

    body = res.text
    assert "CSV Role" in body
    assert body.startswith("id,job_id,url,title")


# --- Imports -------------------------------------------------------------


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
    register(client)
    import app.routers.imports as imports_module

    monkeypatch.setattr(
        imports_module.httpx, "get", lambda *a, **k: FakeResponse(text=JOB_POSTING_HTML)
    )

    res = client.post("/api/imports/url", json={"url": "https://example.com/job/9"})
    assert res.status_code == 200
    application = res.json()
    assert application["title"] == "Backend Engineer"
    assert application["company"] == "Acme"
    assert application["location"] == "Remote"


def test_import_from_url_blocked_by_anti_bot_protection(client, monkeypatch):
    register(client)
    import app.routers.imports as imports_module

    monkeypatch.setattr(
        imports_module.httpx,
        "get",
        lambda *a, **k: FakeResponse(text="", status_code=403),
    )

    res = client.post("/api/imports/url", json={"url": "https://example.com/blocked"})
    assert res.status_code == 502
    assert "extension" in res.json()["detail"].lower()


def test_import_from_url_js_rendered_page_with_no_extractable_content(client, monkeypatch):
    register(client)
    import app.routers.imports as imports_module

    monkeypatch.setattr(
        imports_module.httpx,
        "get",
        lambda *a, **k: FakeResponse(text="<html><body><div id='app'></div></body></html>"),
    )

    res = client.post("/api/imports/url", json={"url": "https://example.com/js-app"})
    assert res.status_code == 422
    assert "extension" in res.json()["detail"].lower()


def test_import_greenhouse_filters_by_keyword(client, monkeypatch):
    register(client)
    import app.routers.imports as imports_module

    payload = {
        "jobs": [
            {"id": 111, "title": "Backend Engineer", "location": {"name": "Remote"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/1"},
            {"id": 222, "title": "Sales Rep", "location": {"name": "NYC"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/2"},
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
    assert results[0]["external_id"] == "111"


def test_import_lever_and_bulk_import(client, monkeypatch):
    register(client)
    import app.routers.imports as imports_module

    payload = [
        {"id": "abc", "text": "Platform Engineer", "categories": {"location": "SF"}, "hostedUrl": "https://jobs.lever.co/acme/1"},
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
    assert len(client.get("/api/applications").json()) == 1


# --- Resumes ---------------------------------------------------------------


def test_resume_upload_extracts_text(client):
    register(client)
    content = make_docx_bytes(
        ["Ada Lovelace", "Experienced Python engineer with FastAPI background."]
    )
    res = client.post(
        "/api/resumes",
        data={"label": "Main resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert res.status_code == 200
    resume = res.json()
    assert resume["label"] == "Main resume"
    assert "Python" in resume["extracted_text"]

    res_list = client.get("/api/resumes")
    assert len(res_list.json()) == 1


def test_resume_upload_rejects_unsupported_extension(client):
    register(client)
    res = client.post(
        "/api/resumes",
        data={"label": "Notes"},
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )
    assert res.status_code == 400


def test_resume_download(client):
    register(client)
    content = make_docx_bytes(["Downloadable resume line."])
    resume = client.post(
        "/api/resumes",
        data={"label": "My Résumé!"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    res = client.get(f"/api/resumes/{resume['id']}/download")
    assert res.status_code == 200
    assert res.content == content
    disposition = res.headers["content-disposition"]
    assert "attachment" in disposition
    assert ".docx" in disposition
    assert "My" in unquote(disposition)


def test_resume_download_not_found(client):
    register(client)
    res = client.get("/api/resumes/999/download")
    assert res.status_code == 404


# --- Fit analysis ------------------------------------------------------


def test_fit_analysis(client):
    register(client)
    application = client.post(
        "/api/applications",
        json={
            "url": "https://example.com/job/fit",
            "description": (
                "We need a Python developer with FastAPI and SQLite experience. "
                "Docker and AWS are a plus."
            ),
        },
    ).json()

    content = make_docx_bytes(["Experienced Python engineer with a FastAPI background."])
    resume = client.post(
        "/api/resumes",
        data={"label": "Main resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    res = client.get(f"/api/applications/{application['id']}/fit", params={"resume_id": resume["id"]})
    assert res.status_code == 200
    result = res.json()

    assert "Python" in result["matched_terms"]
    assert "FastAPI" in result["matched_terms"]
    assert "Docker" in result["missing_terms"]
    assert 0 < result["score"] < 100


def test_fit_analysis_missing_description(client):
    register(client)
    application = client.post("/api/applications", json={"url": "https://example.com/job/nodesc"}).json()
    content = make_docx_bytes(["Some resume text"])
    resume = client.post(
        "/api/resumes",
        data={"label": "Resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    res = client.get(f"/api/applications/{application['id']}/fit", params={"resume_id": resume["id"]})
    assert res.status_code == 400


# --- Careers (resume-driven job matching) -------------------------------


def test_careers_matches_empty_catalog(client):
    register(client)
    content = make_docx_bytes(["Experienced Python engineer."])
    resume = client.post(
        "/api/resumes",
        data={"label": "Resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    res = client.get("/api/careers/matches", params={"resume_id": resume["id"]})
    assert res.status_code == 200
    body = res.json()
    assert body["catalog_size"] == 0
    assert body["matches"] == []


def test_careers_matches_ranked_and_save_to_pipeline(client):
    register(client)
    content = make_docx_bytes(["Experienced Python engineer with a FastAPI background."])
    resume = client.post(
        "/api/resumes",
        data={"label": "Resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    # Two catalog jobs, imported without ever being "saved" to this user's
    # pipeline — importing already creates an application, so use a second
    # account to populate the catalog without an application for user1.
    client2 = TestClient(client.app)
    register(client2, email="importer@example.com")
    good_job = client2.post(
        "/api/applications",
        json={
            "url": "https://example.com/job/good-match",
            "title": "Backend Engineer",
            "description": "Python and FastAPI experience required.",
        },
    ).json()
    bad_job = client2.post(
        "/api/applications",
        json={
            "url": "https://example.com/job/bad-match",
            "title": "Marketing Manager",
            "description": "Social media, branding, and content strategy experience.",
        },
    ).json()

    res = client.get("/api/careers/matches", params={"resume_id": resume["id"]})
    assert res.status_code == 200
    body = res.json()
    assert body["catalog_size"] == 2
    assert len(body["matches"]) == 2
    # Ranked best-first.
    assert body["matches"][0]["job_id"] == good_job["job_id"]
    assert body["matches"][0]["score"] > body["matches"][1]["score"]
    assert body["matches"][0]["saved"] is False

    res_save = client.post(f"/api/careers/matches/{good_job['job_id']}/save")
    assert res_save.status_code == 200
    saved_application = res_save.json()
    assert saved_application["job_id"] == good_job["job_id"]

    res_again = client.get("/api/careers/matches", params={"resume_id": resume["id"]})
    matches_by_job = {m["job_id"]: m for m in res_again.json()["matches"]}
    assert matches_by_job[good_job["job_id"]]["saved"] is True
    assert matches_by_job[good_job["job_id"]]["application_id"] == saved_application["id"]
    assert matches_by_job[bad_job["job_id"]]["saved"] is False

    # Saving is idempotent — matches whatever upsert_application already does.
    res_save_again = client.post(f"/api/careers/matches/{good_job['job_id']}/save")
    assert res_save_again.json()["id"] == saved_application["id"]

    # Fresh account's catalog view is unaffected by user1's saves.
    assert client.get("/api/applications").json()[0]["job_id"] == good_job["job_id"]


def test_careers_matches_unknown_resume_404(client):
    register(client)
    res = client.get("/api/careers/matches", params={"resume_id": 999})
    assert res.status_code == 404


def test_careers_matches_filter_by_employment_and_contract_type(client):
    register(client)
    content = make_docx_bytes(["Experienced Python engineer with a FastAPI background."])
    resume = client.post(
        "/api/resumes",
        data={"label": "Resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    client2 = TestClient(client.app)
    register(client2, email="importer2@example.com")
    client2.post(
        "/api/applications",
        json={
            "url": "https://example.com/job/ft",
            "title": "Backend Engineer",
            "description": "Python and FastAPI, full-time role.",
        },
    )
    client2.post(
        "/api/applications",
        json={
            "url": "https://example.com/job/c2c",
            "title": "Backend Contractor",
            "description": "Python and FastAPI, 12 month contract, C2C only.",
        },
    )

    res = client.get(
        "/api/careers/matches",
        params={"resume_id": resume["id"], "employment_type": "contract", "contract_type": "c2c"},
    )
    assert res.status_code == 200
    matches = res.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["title"] == "Backend Contractor"
    assert matches[0]["employment_type"] == "contract"
    assert matches[0]["contract_type"] == "c2c"


def test_careers_save_unknown_job_404(client):
    register(client)
    res = client.post("/api/careers/matches/999/save")
    assert res.status_code == 404


# --- AI-assisted resume tailoring --------------------------------------


def test_tailor_requires_api_key(client, monkeypatch):
    register(client)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    application = client.post(
        "/api/applications",
        json={"url": "https://example.com/job/tailor1", "description": "Python and FastAPI role."},
    ).json()
    content = make_docx_bytes(["Experienced Python engineer."])
    resume = client.post(
        "/api/resumes",
        data={"label": "Resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    res = client.post(
        f"/api/applications/{application['id']}/tailor", params={"resume_id": resume["id"]}
    )
    assert res.status_code == 400
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_tailor_generates_suggestions(client, monkeypatch):
    register(client)
    import app.routers.tailoring as tailoring_module
    from app.tailoring import BulletSuggestion

    monkeypatch.setattr(
        tailoring_module,
        "generate_suggestions",
        lambda *a, **k: [
            BulletSuggestion(
                original="Experienced Python engineer.",
                suggested="Experienced Python engineer specializing in FastAPI.",
                rationale="Job emphasizes FastAPI.",
                grounded=True,
                ungrounded_note=None,
            ),
            BulletSuggestion(
                original="Experienced Python engineer.",
                suggested="Led a team of 10 engineers.",
                rationale="Job wants leadership experience.",
                grounded=False,
                ungrounded_note="Resume does not mention managing a team.",
            ),
        ],
    )

    application = client.post(
        "/api/applications",
        json={"url": "https://example.com/job/tailor2", "description": "Python and FastAPI role."},
    ).json()
    content = make_docx_bytes(["Experienced Python engineer."])
    resume = client.post(
        "/api/resumes",
        data={"label": "Resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    res = client.post(
        f"/api/applications/{application['id']}/tailor", params={"resume_id": resume["id"]}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["resume_text"] == "Experienced Python engineer."
    assert len(body["suggestions"]) == 2
    assert body["suggestions"][0]["grounded"] is True
    assert body["suggestions"][1]["grounded"] is False
    assert "team" in body["suggestions"][1]["ungrounded_note"]


def test_tailor_missing_description(client):
    register(client)
    application = client.post("/api/applications", json={"url": "https://example.com/job/tailor3"}).json()
    content = make_docx_bytes(["Resume text"])
    resume = client.post(
        "/api/resumes",
        data={"label": "Resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    res = client.post(
        f"/api/applications/{application['id']}/tailor", params={"resume_id": resume["id"]}
    )
    assert res.status_code == 400


def test_save_resume_version(client):
    register(client)
    application = client.post(
        "/api/applications", json={"url": "https://example.com/job/tailor4", "title": "Backend Role"}
    ).json()
    content = make_docx_bytes(["Original resume line."])
    resume = client.post(
        "/api/resumes",
        data={"label": "Base resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    res = client.post(
        f"/api/resumes/{resume['id']}/versions",
        json={
            "job_id": application["job_id"],
            "final_text": "Tailored resume line for Backend Role.",
        },
    )
    assert res.status_code == 200
    version = res.json()
    assert version["base_resume_id"] == resume["id"]
    assert version["job_id"] == application["job_id"]
    assert version["extracted_text"] == "Tailored resume line for Backend Role."
    assert "tailored for Backend Role" in version["label"]

    res_list = client.get("/api/resumes")
    resumes_by_id = {r["id"]: r for r in res_list.json()}
    assert len(resumes_by_id) == 2
    assert resumes_by_id[version["id"]]["job_id"] == application["job_id"]
    assert resumes_by_id[resume["id"]]["job_id"] is None


def test_save_resume_version_requires_job_in_pipeline(client):
    register(client)
    content = make_docx_bytes(["Original resume line."])
    resume = client.post(
        "/api/resumes",
        data={"label": "Base resume"},
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()

    res = client.post(
        f"/api/resumes/{resume['id']}/versions",
        json={"job_id": 999, "final_text": "Tailored text."},
    )
    assert res.status_code == 404


# --- Profile -------------------------------------------------------------


def test_profile_roundtrip(client):
    register(client, email="ada3@example.com")
    res = client.put(
        "/api/profile",
        json={"full_name": "Ada Lovelace", "email": "ada3@example.com"},
    )
    assert res.status_code == 200
    assert res.json()["full_name"] == "Ada Lovelace"

    res_prefill = client.get("/api/prefill")
    data = res_prefill.json()
    assert data["first_name"] == "Ada"
    assert data["last_name"] == "Lovelace"
    assert data["email"] == "ada3@example.com"
