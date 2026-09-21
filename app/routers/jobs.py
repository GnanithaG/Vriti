from fastapi import APIRouter, HTTPException

from ..db import db
from ..models import VALID_STAGES, JobCreate, JobStageUpdate

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("")
def create_job(job: JobCreate):
    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM jobs WHERE url = ?", (job.url,)
        ).fetchone()
        if existing:
            return dict(existing)

        cur = conn.execute(
            """
            INSERT INTO jobs (url, title, company, location, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job.url, job.title, job.company, job.location, job.description),
        )
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)


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
