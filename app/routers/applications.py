import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
from ..db import db, upsert_application, upsert_job
from ..fit import analyze_fit
from ..models import ApplicationNotesUpdate, ApplicationStageUpdate, JobCreate, VALID_STAGES

router = APIRouter(prefix="/api/applications", tags=["applications"])

APPLICATION_COLUMNS = (
    "id",
    "job_id",
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

_JOINED_SELECT = """
    SELECT
        applications.id AS id,
        jobs.id AS job_id,
        jobs.url AS url,
        jobs.title AS title,
        jobs.company AS company,
        jobs.location AS location,
        jobs.description AS description,
        applications.stage AS stage,
        applications.notes AS notes,
        applications.created_at AS created_at,
        applications.updated_at AS updated_at
    FROM applications
    JOIN jobs ON jobs.id = applications.job_id
"""


def get_application_row(conn, application_id: int, user_id: int):
    row = conn.execute(
        f"{_JOINED_SELECT} WHERE applications.id = ? AND applications.user_id = ?",
        (application_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="application not found")
    return dict(row)


@router.post("")
def create_application(job: JobCreate, user: dict = Depends(get_current_user)):
    with db() as conn:
        catalog_job = upsert_job(
            conn,
            job.url,
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description,
            source="manual",
        )
        application = upsert_application(conn, user["id"], catalog_job["id"])
        return get_application_row(conn, application["id"], user["id"])


@router.get("")
def list_applications(q: str = "", stage: str = "", user: dict = Depends(get_current_user)):
    query = f"{_JOINED_SELECT} WHERE applications.user_id = ?"
    params: list = [user["id"]]

    if q:
        query += " AND (jobs.title LIKE ? OR jobs.company LIKE ?)"
        like = f"%{q}%"
        params += [like, like]

    if stage:
        query += " AND applications.stage = ?"
        params.append(stage)

    query += " ORDER BY applications.created_at DESC"

    with db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


@router.get("/export.csv")
def export_applications_csv(user: dict = Depends(get_current_user)):
    with db() as conn:
        rows = conn.execute(
            f"{_JOINED_SELECT} WHERE applications.user_id = ? ORDER BY applications.created_at DESC",
            (user["id"],),
        ).fetchall()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=APPLICATION_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row[col] for col in APPLICATION_COLUMNS})

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vriti-applications.csv"},
    )


@router.patch("/{application_id}/stage")
def update_stage(
    application_id: int, payload: ApplicationStageUpdate, user: dict = Depends(get_current_user)
):
    if payload.stage not in VALID_STAGES:
        raise HTTPException(
            status_code=400, detail=f"stage must be one of {VALID_STAGES}"
        )
    with db() as conn:
        get_application_row(conn, application_id, user["id"])  # 404s if not owned
        conn.execute(
            "UPDATE applications SET stage = ?, updated_at = datetime('now') WHERE id = ?",
            (payload.stage, application_id),
        )
        return get_application_row(conn, application_id, user["id"])


@router.patch("/{application_id}/notes")
def update_notes(
    application_id: int, payload: ApplicationNotesUpdate, user: dict = Depends(get_current_user)
):
    with db() as conn:
        get_application_row(conn, application_id, user["id"])  # 404s if not owned
        conn.execute(
            "UPDATE applications SET notes = ?, updated_at = datetime('now') WHERE id = ?",
            (payload.notes, application_id),
        )
        return get_application_row(conn, application_id, user["id"])


@router.get("/{application_id}/fit")
def get_fit(application_id: int, resume_id: int, user: dict = Depends(get_current_user)):
    with db() as conn:
        application = get_application_row(conn, application_id, user["id"])

        resume = conn.execute(
            "SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, user["id"])
        ).fetchone()
        if not resume:
            raise HTTPException(status_code=404, detail="resume not found")

    description = application["description"] or ""
    if not description.strip():
        raise HTTPException(
            status_code=400, detail="This job has no description to analyze yet"
        )

    return analyze_fit(resume["extracted_text"] or "", description)
