from fastapi import APIRouter, HTTPException

from ..db import db, upsert_job
from ..fit import analyze_fit
from ..models import VALID_STAGES, JobCreate, JobStageUpdate

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("")
def create_job(job: JobCreate):
    with db() as conn:
        return upsert_job(
            conn,
            job.url,
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description,
        )


@router.get("")
def list_jobs():
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


@router.patch("/{job_id}/stage")
def update_stage(job_id: int, payload: JobStageUpdate):
    if payload.stage not in VALID_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"stage must be one of {VALID_STAGES}",
        )
    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="job not found")
        conn.execute(
            """
            UPDATE jobs SET stage = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (payload.stage, job_id),
        )
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row)


@router.get("/{job_id}/fit")
def get_fit(job_id: int, resume_id: int):
    with db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        resume = conn.execute(
            "SELECT * FROM resumes WHERE id = ?", (resume_id,)
        ).fetchone()
        if not resume:
            raise HTTPException(status_code=404, detail="resume not found")

    description = job["description"] or ""
    if not description.strip():
        raise HTTPException(
            status_code=400, detail="This job has no description to analyze yet"
        )

    return analyze_fit(resume["extracted_text"] or "", description)
