import csv
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..db import db, upsert_job
from ..fit import analyze_fit
from ..models import VALID_STAGES, JobCreate, JobNotesUpdate, JobStageUpdate

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

JOB_COLUMNS = (
    "id",
    "url",
    "title",
    "company",
    "location",
    "description",
    "stage",
    "notes",
    "created_at",
    "updated_at",
)


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
def list_jobs(q: str = "", stage: str = ""):
    query = "SELECT * FROM jobs WHERE 1=1"
    params: list = []

    if q:
        query += " AND (title LIKE ? OR company LIKE ?)"
        like = f"%{q}%"
        params += [like, like]

    if stage:
        query += " AND stage = ?"
        params.append(stage)

    query += " ORDER BY created_at DESC"

    with db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


@router.get("/export.csv")
def export_jobs_csv():
    with db() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=JOB_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row[col] for col in JOB_COLUMNS})

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobpilot-jobs.csv"},
    )


def _update_job_field(conn, job_id: int, field: str, value: str):
    existing = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="job not found")
    conn.execute(
        f"UPDATE jobs SET {field} = ?, updated_at = datetime('now') WHERE id = ?",
        (value, job_id),
    )
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


@router.patch("/{job_id}/stage")
def update_stage(job_id: int, payload: JobStageUpdate):
    if payload.stage not in VALID_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"stage must be one of {VALID_STAGES}",
        )
    with db() as conn:
        return _update_job_field(conn, job_id, "stage", payload.stage)


@router.patch("/{job_id}/notes")
def update_notes(job_id: int, payload: JobNotesUpdate):
    with db() as conn:
        return _update_job_field(conn, job_id, "notes", payload.notes)


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
