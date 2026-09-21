import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..db import RESUMES_DIR, db
from ..text_extraction import UnsupportedResumeFormat, extract_text

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
            "SELECT id, label, base_resume_id, created_at FROM resumes ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/{resume_id}")
def get_resume(resume_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="resume not found")
        return dict(row)
