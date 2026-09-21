import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..db import RESUMES_DIR, db
from ..text_extraction import UnsupportedResumeFormat, extract_text

_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


@router.post("")
async def upload_resume(label: str = Form(...), file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        extracted_text = extract_text(file.filename or "", content)
    except UnsupportedResumeFormat as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ext = Path(file.filename or "").suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    (RESUMES_DIR / stored_name).write_bytes(content)

    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO resumes (label, file_path, extracted_text)
            VALUES (?, ?, ?)
            """,
            (label, str(RESUMES_DIR / stored_name), extracted_text),
        )
        row = conn.execute(
            "SELECT * FROM resumes WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)


@router.get("")
def list_resumes():
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, label, base_resume_id, job_id, created_at
            FROM resumes ORDER BY created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/{resume_id}")
def get_resume(resume_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="resume not found")
        return dict(row)


@router.get("/{resume_id}/download")
def download_resume(resume_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="resume not found")

    file_path = Path(row["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="resume file is missing on disk")

    safe_label = _UNSAFE_FILENAME_CHARS.sub("_", row["label"]).strip() or "resume"
    filename = f"{safe_label}{file_path.suffix}"
    return FileResponse(file_path, filename=filename)
