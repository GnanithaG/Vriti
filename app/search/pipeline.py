"""Job search pipeline: fetch → filter → score with Claude → save to inbox → notify."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .. import db
from ..ai import score_jobs
from ..config import get_settings
from ..push import notify
from . import adzuna, jsearch
from .filters import blocks_sponsorship, dedupe_key, matches_excludes, title_fits

log = logging.getLogger("upajna.search")

DEFAULT_SEARCH = {
    "titles": ["Business Analyst", "Business Systems Analyst", "IT Business Analyst", "Technical Business Analyst", "Agile Business Analyst"],
    "level": "Mid-Senior",
    "jobTypes": ["Full-time", "Contract (W2)", "Contract-to-hire"],
    "sponsorship": "needs",
    "excludes": "",
    "postedWithinHours": 24,
    "maxPerRun": 20,
    "minScore": 55,
}

_lock = asyncio.Lock()


def is_running() -> bool:
    return _lock.locked()


def _mock_jobs(title: str) -> list[dict]:
    stamp = int(datetime.now().timestamp() * 1000) % 100000
    out = []
    for n in (1, 2, 3):
        out.append({
            "id": f"mock-{''.join(c for c in title if c.isalnum())}-{n}-{stamp}",
            "source": ["LinkedIn", "Indeed", "ZipRecruiter"][n - 1], "title": ("Senior " if n == 3 else "") + title,
            "company": f"Example Co {n}", "location": "Remote", "remote": True, "jobType": "Full-time", "salary": "$95k–$115k/yr",
            "postedAt": db.now_iso(), "url": "https://example.com/job", "applyUrl": f"https://boards.greenhouse.io/example/jobs/{1000 + n}",
            "jd": "Business analyst role. We do not provide visa sponsorship." if n == 2 else
                  "Gather requirements, write user stories and acceptance criteria, run UAT, SQL data validation, Azure DevOps, Visio process maps.",
        })
    return out


async def run_search(reason: str = "scheduled") -> dict:
    if _lock.locked():
        return {"skipped": "already running"}
    async with _lock:
        settings = get_settings()
        search = {**DEFAULT_SEARCH, **(db.get_setting("search") or {})}
        resume = db.get_setting("resume") or {}
        state = db.get_setting("searchState") or {"titleIndex": 0}
        titles = [t for t in search.get("titles") or [] if t]
        if not titles:
            raise ValueError("Add at least one job title in Settings.")
        hours = int(search.get("postedWithinHours") or 24)
        notes: list[str] = []

        # Rotate JSearch titles to stay inside the API plan's monthly request limit.
        n = min(settings.jsearch_queries_per_run, len(titles))
        start = int(state.get("titleIndex", 0))
        js_titles = [titles[(start + i) % len(titles)] for i in range(n)]
        state["titleIndex"] = (start + n) % len(titles)

        found: list[dict] = []
        if settings.mock_external:
            for t in titles[:2]:
                found += _mock_jobs(t)
        else:
            calls = [("JSearch", t, jsearch.search(t, hours)) for t in js_titles] + [("Adzuna", t, adzuna.search(t, hours)) for t in titles]
            results = await asyncio.gather(*(c[2] for c in calls), return_exceptions=True)
            errors = set()
            for (src, t, _), res in zip(calls, results):
                if isinstance(res, Exception):
                    errors.add(f"{src} ({str(res)[:60]})")
                else:
                    found += res
            if settings.jsearch_api_key:
                notes.append("JSearch: " + ", ".join(js_titles))
            if errors:
                notes.append("Errors: " + "; ".join(sorted(errors)))

        # Filter and dedupe.
        existing_ids = db.job_ids()
        seen = {j.get("dedupeKey") or dedupe_key(j) for j in db.list_jobs()}
        dropped = {"dup": 0, "off": 0, "sponsor": 0}
        fresh = []
        for j in found:
            key = dedupe_key(j)
            if j["id"] in existing_ids or key in seen:
                dropped["dup"] += 1
            elif not title_fits(j["title"], titles) or matches_excludes(f"{j['title']} {j['jd']}", search.get("excludes", "")):
                dropped["off"] += 1
            elif search.get("sponsorship") == "needs" and blocks_sponsorship(j["jd"]):
                dropped["sponsor"] += 1
            else:
                seen.add(key)
                fresh.append({**j, "dedupeKey": key})

        # Score with Claude in small batches.
        scored = []
        for i in range(0, len(fresh), 15):
            batch = fresh[i : i + 15]
            try:
                by_id = {s.id: s for s in await score_jobs(batch, resume.get("text", ""), search)}
            except Exception as e:  # keep going; one bad batch shouldn't sink the run
                notes.append(f"Scoring error: {str(e)[:80]}")
                continue
            for j in batch:
                s = by_id.get(j["id"])
                if not s:
                    continue
                if s.exclude_reason:
                    dropped["sponsor"] += 1
                    continue
                scored.append({**j, "fit": {"score": s.score, "level": s.level, "reason": s.reason}})

        keep = sorted((j for j in scored if j["fit"]["score"] >= int(search.get("minScore") or 55)), key=lambda j: -j["fit"]["score"])
        keep = keep[: int(search.get("maxPerRun") or 20)]
        now = db.now_iso()
        for j in keep:
            db.put_job({**j, "foundAt": now, "status": "new"})

        notes.append(f"Skipped {dropped['dup']} duplicates, {dropped['sponsor']} without sponsorship, {dropped['off']} off-target")
        summary = {"lastRunAt": now, "lastRunFound": len(keep), "lastRunReason": reason, "lastRunNote": ". ".join(notes)}
        db.set_setting("searchState", {**state, **summary})
        if keep:
            top = keep[0]
            await notify(f"{len(keep)} new job{'s' if len(keep) > 1 else ''} to review",
                         f"Top match: {top['title']} at {top['company']} ({top['fit']['score']}%)", "/#inbox")
        log.info("search done: %s", summary)
        return summary
