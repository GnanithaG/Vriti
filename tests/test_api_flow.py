"""End-to-end API flow with mocked Claude, job APIs and browser."""
import time


def wait_for(fn, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("timed out")


def test_full_flow(client):
    assert client.get("/api/jobs").status_code == 401
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401
    assert client.post("/api/login", json={"password": "test-pass"}).status_code == 200

    client.put("/api/settings/profile", json={"name": "Test Person", "email": "t@example.com", "sponsor": "Yes"})
    client.put("/api/settings/resume", json={"text": "Business Analyst " * 40})
    assert client.get("/api/settings").json()["profile"]["name"] == "Test Person"

    # Search: mock boards return one no-sponsorship posting, which must be filtered out.
    client.post("/api/search/run")
    jobs = wait_for(lambda: (not client.get("/api/status").json()["searching"]) and client.get("/api/jobs").json())
    assert len(jobs) >= 2
    assert not any("sponsor" in j["jd"].lower() for j in jobs)
    assert all(j["ats"] == "greenhouse" for j in jobs)

    # Tailor → review
    job_id = jobs[0]["id"]
    client.post("/api/jobs/tailor", json={"ids": [job_id]})
    job = wait_for(lambda: (j := client.get(f"/api/jobs/{job_id}").json())["status"] == "review" and j)
    assert job["result"]["resume"]["name"] == "Test Person"
    assert job["result"]["fileBase"].startswith("Test_Person_Resume_")

    r = client.get(f"/api/jobs/{job_id}/resume.docx")
    assert r.status_code == 200 and r.content[:2] == b"PK" and len(r.content) > 5000

    # Approval is blocked while ASK ME answers remain
    assert client.post(f"/api/jobs/{job_id}/approve", json={"answers": [{"question": "Q", "answer": "ASK ME: x"}]}).status_code == 400

    # Approve → apply worker (test mode: fills, doesn't submit)
    client.post(f"/api/jobs/{job_id}/approve", json={"answers": [{"question": "Sponsorship?", "answer": "Yes"}]})
    job = wait_for(lambda: (j := client.get(f"/api/jobs/{job_id}").json())["status"] not in ("ready", "applying") and j)
    assert job["status"] == "needs_you" and "Dry run" in job["note"]

    # Tracker
    client.patch(f"/api/jobs/{job_id}", json={"markSubmitted": True})
    client.patch(f"/api/jobs/{job_id}", json={"trackerStatus": "Interview"})
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "submitted" and job["trackerStatus"] == "Interview" and job["followUp"]

    # Skip hides a job
    other = jobs[1]["id"]
    client.post("/api/jobs/skip", json={"ids": [other]})
    assert other not in [j["id"] for j in client.get("/api/jobs").json()]


def test_phone_app_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Vriti" in r.text
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200
