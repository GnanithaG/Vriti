import uuid

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..db import RESUMES_DIR, db
from ..fit import analyze_fit
from ..tailoring import TailoringUnavailable, generate_suggestions
from .applications import get_application_row

router = APIRouter(tags=["tailoring"])


def _get_owned_resume(conn, resume_id: int, user_id: int):
    resume = conn.execute(
        "SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, user_id)
    ).fetchone()
    if not resume:
        raise HTTPException(status_code=404, detail="resume not found")
    return resume


@router.post("/api/applications/{application_id}/tailor")
def tailor_resume(application_id: int, resume_id: int, user: dict = Depends(get_current_user)):
    with db() as conn:
        application = get_application_row(conn, application_id, user["id"])
        resume = _get_owned_resume(conn, resume_id, user["id"])

    description = application["description"] or ""
    if not description.strip():
        raise HTTPException(
            status_code=400, detail="This job has no description to tailor against"
        )

    resume_text = resume["extracted_text"] or ""
    fit = analyze_fit(resume_text, description)

    try:
        suggestions = generate_suggestions(
            resume_text,
            description,
            fit["matched_terms"],
            fit["missing_terms"],
        )
    except TailoringUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except anthropic.AuthenticationError as exc:
        raise HTTPException(
            status_code=500, detail="ANTHROPIC_API_KEY was rejected — check your .env"
        ) from exc
    except anthropic.RateLimitError as exc:
        raise HTTPException(
            status_code=429, detail="Rate limited by the Anthropic API — try again shortly"
        ) from exc
    except anthropic.APIStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Anthropic API error: {exc.message}"
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise HTTPException(
            status_code=502, detail="Could not reach the Anthropic API"
        ) from exc

    return {
        "resume_text": resume_text,
        "fit": fit,
        "suggestions": [s.model_dump() for s in suggestions],
    }


class SaveVersionIn(BaseModel):
    job_id: int  # catalog job id (resumes.job_id), not the application id
    final_text: str
    label: str | None = None


@router.post("/api/resumes/{resume_id}/versions")
def save_resume_version(
    resume_id: int, payload: SaveVersionIn, user: dict = Depends(get_current_user)
):
    with db() as conn:
        base = _get_owned_resume(conn, resume_id, user["id"])

        # The job must actually be in this user's own pipeline — tailoring
        # for a job you haven't saved isn't a thing.
        application = conn.execute(
            """
            SELECT applications.*, jobs.title AS job_title, jobs.url AS job_url
            FROM applications JOIN jobs ON jobs.id = applications.job_id
            WHERE applications.user_id = ? AND applications.job_id = ?
            """,
            (user["id"], payload.job_id),
        ).fetchone()
        if not application:
            raise HTTPException(status_code=404, detail="job not found in your pipeline")

        if not payload.final_text.strip():
            raise HTTPException(status_code=400, detail="final_text is empty")

        label = (
            payload.label
            or f"{base['label']} — tailored for {application['job_title'] or application['job_url']}"
        )

        stored_name = f"{uuid.uuid4().hex}.txt"
        (RESUMES_DIR / stored_name).write_text(payload.final_text, encoding="utf-8")

        cur = conn.execute(
            """
            INSERT INTO resumes (user_id, label, file_path, extracted_text, base_resume_id, job_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                label,
                str(RESUMES_DIR / stored_name),
                payload.final_text,
                resume_id,
                payload.job_id,
            ),
        )
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
