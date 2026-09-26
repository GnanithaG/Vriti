"""Vriti API server: phone app, REST API, scheduled job search, tailoring and apply workers."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Body, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, db, push, workers
from .ai import file_base
from .apply import detect_ats
from .config import get_settings
from .documents import letter_docx, read_resume, resume_docx
from .search import DEFAULT_SEARCH, is_running, run_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vriti")
STATIC = Path(__file__).resolve().parent.parent / "static"
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    db.init_db()
    if s.missing():
        log.warning("Missing settings: %s", ", ".join(s.missing()))

    async def scheduled():
        try:
            await run_search("scheduled")
        except Exception:
            log.exception("scheduled search failed")

    scheduler.add_job(scheduled, CronTrigger.from_crontab(s.search_cron, timezone=s.tz_name), id="search", replace_existing=True)
    scheduler.start()
    workers.resume_queues()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Vriti", lifespan=lifespan)
api = APIRouter(prefix="/api", dependencies=[Depends(auth.require_auth)])


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


def light(j: dict) -> dict:
    """Job without the heavy screenshot, plus which application system it uses."""
    out = {k: v for k, v in j.items() if k != "shot"}
    out["hasShot"] = bool(j.get("shot"))
    out["ats"] = detect_ats(j.get("applyUrl") or j.get("url") or "")
    return out


# ---------- auth ----------
class LoginBody(BaseModel):
    password: str = ""


@app.post("/api/login")
def login(body: LoginBody, request: Request, response: Response):
    auth.login(request, response, body.password)
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    auth.logout(response)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------- status & settings ----------
@api.get("/status")
def status():
    s = get_settings()
    return {
        "missing": s.missing(), "searching": is_running(), "searchState": db.get_setting("searchState") or {},
        "sources": {"jsearch": bool(s.jsearch_api_key), "adzuna": bool(s.adzuna_app_id and s.adzuna_app_key)},
        "applySubmit": s.apply_submit, "push": push.enabled(), "vapidPublic": s.vapid_public_key,
        "schedule": s.search_cron, "timezone": s.tz_name,
    }


SETTINGS = ("profile", "search", "resume")


@api.get("/settings")
def get_settings_all():
    return {k: db.get_setting(k) or (DEFAULT_SEARCH if k == "search" else {}) for k in SETTINGS}


@api.put("/settings/{name}")
def put_setting(name: str, body: dict[str, Any] = Body(...)):
    if name not in SETTINGS:
        raise HTTPException(404, "Unknown setting")
    nxt = {**(db.get_setting(name) or {}), **body, "updatedAt": db.now_iso()}
    return db.set_setting(name, nxt)


@api.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "That file is over 5 MB.")
    text = read_resume(data, file.filename or "")
    if len(text) < 200:
        raise HTTPException(422, "Couldn't read enough text from that file. If it's a scanned PDF, paste the text instead.")
    return db.set_setting("resume", {"text": text, "fileName": file.filename, "updatedAt": db.now_iso()})


# ---------- jobs ----------
@api.get("/jobs")
def list_jobs(status: Optional[str] = None):
    statuses = status.split(",") if status else None
    return [light(j) for j in db.list_jobs(statuses) if statuses or j["status"] != "skipped"]


@api.get("/jobs/{job_id}")
def get_job(job_id: str):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return {**j, "ats": detect_ats(j.get("applyUrl") or j.get("url") or "")}


class NewJob(BaseModel):
    url: str = ""
    jd: str = ""
    title: str = ""
    company: str = ""


@api.post("/jobs")
async def add_job(body: NewJob):
    if len(body.jd) < 150:
        raise HTTPException(400, "Paste the full job description.")
    job_id = "m-" + format(int(db.utcnow().timestamp() * 1000), "x")
    job = db.put_job({"id": job_id, "source": "Added by you", "title": body.title or "New job", "company": body.company,
                      "location": "", "url": body.url, "applyUrl": body.url, "jd": body.jd[:9000], "status": "new", "fit": {}})
    workers.enqueue_tailor([job_id])
    return light(job)


class Ids(BaseModel):
    ids: list[str] = []


@api.post("/jobs/skip")
def skip(body: Ids):
    for i in body.ids:
        db.patch_job(i, status="skipped", jd="")
    return {"ok": True}


@api.post("/jobs/tailor")
async def tailor(body: Ids):
    if len((db.get_setting("resume") or {}).get("text", "")) < 200:
        raise HTTPException(400, "Add your master resume in Settings first.")
    workers.enqueue_tailor(body.ids)
    return {"ok": True}


class JobPatch(BaseModel):
    answers: Optional[list[dict]] = None
    coverLetter: Optional[str] = None
    trackerStatus: Optional[str] = None
    applyUrl: Optional[str] = None
    markSubmitted: bool = False
    status: Optional[str] = None


@api.patch("/jobs/{job_id}")
def patch_job(job_id: str, body: JobPatch):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    patch: dict[str, Any] = {}
    if body.answers is not None or body.coverLetter is not None:
        result = dict(job.get("result") or {})
        if body.answers is not None:
            result["answers"] = body.answers
        if body.coverLetter is not None:
            result["coverLetter"] = body.coverLetter
        patch["result"] = result
    if body.trackerStatus:
        patch["trackerStatus"] = body.trackerStatus
    if body.applyUrl:
        patch["applyUrl"] = body.applyUrl
    if body.markSubmitted:
        patch.update(status="submitted", appliedAt=date.today().isoformat(), followUp=(date.today() + timedelta(days=7)).isoformat(), trackerStatus="Applied", note="")
    if body.status in ("new", "skipped"):
        patch["status"] = body.status
    return light(db.patch_job(job_id, **patch))


class Approval(BaseModel):
    answers: Optional[list[dict]] = None
    coverLetter: Optional[str] = None


@api.post("/jobs/{job_id}/approve")
async def approve(job_id: str, body: Approval):
    job = db.get_job(job_id)
    if not job or not job.get("result"):
        raise HTTPException(400, "Tailor this job before approving it.")
    answers = body.answers if body.answers is not None else job["result"].get("answers", [])
    if any(str(a.get("answer", "")).upper().startswith("ASK ME") for a in answers):
        raise HTTPException(400, "Fill in the answers marked ASK ME first.")
    result = {**job["result"], "answers": answers}
    if body.coverLetter is not None:
        result["coverLetter"] = body.coverLetter
    db.patch_job(job_id, status="ready", approvedAt=db.now_iso(), result=result, note="")
    workers.enqueue_apply([job_id])
    return {"ok": True, "ats": detect_ats(job.get("applyUrl") or job.get("url") or ""), "willSubmit": get_settings().apply_submit}


@api.post("/jobs/{job_id}/retry")
async def retry(job_id: str):
    db.patch_job(job_id, status="ready", note="", possiblySubmitted=False)
    workers.enqueue_apply([job_id])
    return {"ok": True}


@api.get("/jobs/{job_id}/{kind}.docx")
def download(job_id: str, kind: str):
    job = db.get_job(job_id)
    if not job or not job.get("result"):
        raise HTTPException(404, "Not tailored yet")
    profile = db.get_setting("profile") or {}
    base = job["result"].get("fileBase") or file_base(profile.get("name", ""), job.get("company", ""), job.get("title", ""))
    if kind == "cover":
        data, name = letter_docx(job["result"].get("coverLetter", "")), base.replace("_Resume_", "_CoverLetter_")
    else:
        data, name = resume_docx(job["result"].get("resume") or {}, profile.get("name", "")), base
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{name}.docx"'})


# ---------- search & push ----------
@api.post("/search/run")
async def search_now():
    import asyncio

    if not is_running():
        async def go():
            try:
                await run_search("manual")
            except Exception:
                log.exception("manual search failed")
        asyncio.create_task(go())
    return {"ok": True, "started": True}


@api.post("/push/subscribe")
def subscribe(sub: dict[str, Any] = Body(...)):
    if not sub.get("endpoint"):
        raise HTTPException(400, "Bad subscription")
    db.add_push_sub(sub)
    return {"ok": True}


app.include_router(api)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    f = STATIC / path
    if path and f.is_file() and STATIC in f.resolve().parents:
        return FileResponse(f)
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    return FileResponse(STATIC / "index.html")
