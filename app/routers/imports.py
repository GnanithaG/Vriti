import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..db import db, upsert_application, upsert_job
from ..models import BoardCandidate, BulkImportIn, UrlImportIn
from ..parsing import parse_job_posting_html
from .applications import get_application_row

router = APIRouter(prefix="/api/imports", tags=["imports"])

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Vriti/0.1)"}
REQUEST_TIMEOUT = 10.0


@router.post("/url")
def import_from_url(payload: UrlImportIn, user: dict = Depends(get_current_user)):
    try:
        res = httpx.get(
            payload.url,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        res.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not fetch that URL: {exc}"
        ) from exc

    job = parse_job_posting_html(res.text)
    with db() as conn:
        catalog_job = upsert_job(
            conn,
            payload.url,
            title=job.get("title"),
            company=job.get("company"),
            location=job.get("location"),
            description=job.get("description"),
            source="url",
        )
        application = upsert_application(conn, user["id"], catalog_job["id"])
        return get_application_row(conn, application["id"], user["id"])


@router.get("/greenhouse", response_model=list[BoardCandidate])
def search_greenhouse(board: str, keyword: str = "", user: dict = Depends(get_current_user)):
    try:
        res = httpx.get(
            f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        res.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not fetch Greenhouse board '{board}': {exc}"
        ) from exc

    data = res.json()
    keyword_lower = keyword.lower()
    candidates = []
    for job in data.get("jobs", []):
        title = job.get("title") or ""
        if keyword_lower and keyword_lower not in title.lower():
            continue
        candidates.append(
            BoardCandidate(
                url=job.get("absolute_url"),
                title=title or None,
                company=board,
                location=(job.get("location") or {}).get("name"),
                external_id=str(job.get("id")) if job.get("id") is not None else None,
            )
        )
    return candidates


@router.get("/lever", response_model=list[BoardCandidate])
def search_lever(board: str, keyword: str = "", user: dict = Depends(get_current_user)):
    try:
        res = httpx.get(
            f"https://api.lever.co/v0/postings/{board}",
            params={"mode": "json"},
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        res.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not fetch Lever board '{board}': {exc}"
        ) from exc

    data = res.json()
    keyword_lower = keyword.lower()
    candidates = []
    for job in data:
        title = job.get("text") or ""
        if keyword_lower and keyword_lower not in title.lower():
            continue
        candidates.append(
            BoardCandidate(
                url=job.get("hostedUrl"),
                title=title or None,
                company=board,
                location=(job.get("categories") or {}).get("location"),
                external_id=str(job.get("id")) if job.get("id") is not None else None,
            )
        )
    return candidates


@router.post("/bulk")
def import_bulk(payload: BulkImportIn, user: dict = Depends(get_current_user)):
    with db() as conn:
        rows = []
        for job in payload.jobs:
            source = "greenhouse" if "greenhouse.io" in job.url else (
                "lever" if "lever.co" in job.url else "manual"
            )
            catalog_job = upsert_job(
                conn,
                job.url,
                title=job.title,
                company=job.company,
                location=job.location,
                source=source,
                source_id=job.external_id,
            )
            application = upsert_application(conn, user["id"], catalog_job["id"])
            rows.append(get_application_row(conn, application["id"], user["id"]))
        return rows
