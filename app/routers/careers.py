from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..db import db, upsert_application
from ..fit import analyze_fit
from .applications import get_application_row

router = APIRouter(prefix="/api/careers", tags=["careers"])

MAX_MATCHES = 50


@router.get("/matches")
def get_matches(resume_id: int, user: dict = Depends(get_current_user)):
    with db() as conn:
        resume = conn.execute(
            "SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, user["id"])
        ).fetchone()
        if not resume:
            raise HTTPException(status_code=404, detail="resume not found")

        catalog_jobs = conn.execute(
            "SELECT * FROM jobs WHERE description IS NOT NULL AND description != ''"
        ).fetchall()

        saved_job_ids = {
            row["job_id"]: row["id"]
            for row in conn.execute(
                "SELECT job_id, id FROM applications WHERE user_id = ?", (user["id"],)
            ).fetchall()
        }

    resume_text = resume["extracted_text"] or ""
    matches = []
    for job in catalog_jobs:
        fit = analyze_fit(resume_text, job["description"])
        matches.append(
            {
                "job_id": job["id"],
                "url": job["url"],
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "score": fit["score"],
                "matched_terms": fit["matched_terms"],
                "missing_terms": fit["missing_terms"],
                "saved": job["id"] in saved_job_ids,
                "application_id": saved_job_ids.get(job["id"]),
            }
        )

    matches.sort(key=lambda m: (-m["score"], -len(m["matched_terms"])))

    return {
        "resume_id": resume["id"],
        "resume_label": resume["label"],
        "catalog_size": len(catalog_jobs),
        "matches": matches[:MAX_MATCHES],
    }


@router.post("/matches/{job_id}/save")
def save_match(job_id: int, user: dict = Depends(get_current_user)):
    with db() as conn:
        job = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        application = upsert_application(conn, user["id"], job_id)
        return get_application_row(conn, application["id"], user["id"])
