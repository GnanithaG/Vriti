import uuid

import anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import RESUMES_DIR, db
from ..fit import analyze_fit
from ..tailoring import TailoringUnavailable, generate_suggestions

router = APIRouter(tags=["tailoring"])


def _get_job_and_resume(conn, job_id: int, resume_id: int):
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    resume = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
    if not resume:
        raise HTTPException(status_code=404, detail="resume not found")

    return job, resume


@router.post("/api/jobs/{job_id}/tailor")
def tailor_resume(job_id: int, resume_id: int):
    with db() as conn:
        job, resume = _get_job_and_resume(conn, job_id, resume_id)

    description = job["description"] or ""
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
    job_id: int
    final_text: str
    label: str | None = None


@router.post("/api/resumes/{resume_id}/versions")
def save_resume_version(resume_id: int, payload: SaveVersionIn):
    with db() as conn:
        base = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="resume not found")

        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (payload.job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        if not payload.final_text.strip():
            raise HTTPException(status_code=400, detail="final_text is empty")

        label = payload.label or f"{base['label']} — tailored for {job['title'] or job['url']}"

        stored_name = f"{uuid.uuid4().hex}.txt"
        (RESUMES_DIR / stored_name).write_text(payload.final_text, encoding="utf-8")

        cur = conn.execute(
            """
            INSERT INTO resumes (label, file_path, extracted_text, base_resume_id, job_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                label,
                str(RESUMES_DIR / stored_name),
                payload.final_text,
                resume_id,
                payload.job_id,
            ),
        )
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
