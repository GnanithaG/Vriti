import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..db import db, upsert_application, upsert_job
from ..models import BoardCandidate, BulkImportIn, UrlImportIn
from ..parsing import parse_job_posting_html
from .applications import get_application_row

router = APIRouter(prefix="/api/imports", tags=["imports"])

# A generic-scraper User-Agent like the old "Vriti/0.1" one is an instant
# signal to most job-board WAFs (Cloudflare/PerimeterX-style) to block the
# request outright, even for pages a person can freely view in a real
# browser. This is what a real Chrome-on-Windows request looks like, which
# gets a plain "paste this job URL" fetch (one URL, one request, run from
# the person's own machine — not a crawler) past naive UA sniffing. It does
# nothing against sites that require executing JS or solving a browser
# challenge (LinkedIn in particular) — those still need the extension.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}
REQUEST_TIMEOUT = 15.0


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
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 429):
            raise HTTPException(
                status_code=502,
                detail=(
                    "That site blocked this request (probably anti-bot "
                    "protection) even though the page loads fine in a "
                    "browser. Use the Vriti browser extension's "
                    "\"Capture this job\" button on that page instead — it "
                    "reads the page as your browser rendered it, so it "
                    "isn't affected by this."
                ),
            ) from exc
        raise HTTPException(
            status_code=502, detail=f"Could not fetch that URL: {exc}"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not fetch that URL: {exc}"
        ) from exc

    job = parse_job_posting_html(res.text)
    if not job.get("title") and not job.get("description"):
        raise HTTPException(
            status_code=422,
            detail=(
                "Fetched the page, but couldn't find a job posting in it — "
                "likely a site that renders the listing with JavaScript "
                "rather than sending it in the page itself. Use the Vriti "
                "browser extension's \"Capture this job\" button on that "
                "page instead."
            ),
        )

    with db() as conn:
        catalog_job = upsert_job(
            conn,
            payload.url,
            title=job.get("title"),
            company=job.get("company"),
            location=job.get("location"),
            description=job.get("description"),
            source="url",
            raw_employment_type=job.get("employment_type_raw"),
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
