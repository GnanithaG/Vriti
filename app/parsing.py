"""Server-side job posting extraction.

Python port of extension/content.js's extractJobPosting(): reads JobPosting
JSON-LD when present, falling back to page text. Used by the "paste a URL"
import so the dashboard doesn't depend on the extension being installed.
"""
import json
from typing import Optional

from bs4 import BeautifulSoup

MAX_DESCRIPTION_CHARS = 5000


def _extract_location(job_location) -> Optional[str]:
    if not job_location:
        return None
    loc = job_location[0] if isinstance(job_location, list) else job_location
    if not isinstance(loc, dict):
        return None
    address = loc.get("address")
    if not isinstance(address, dict):
        return None
    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("addressCountry"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def _strip_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return text[:MAX_DESCRIPTION_CHARS] or None


def _extract_json_ld(soup: BeautifulSoup) -> Optional[dict]:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            parsed = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = parsed if isinstance(parsed, list) else [parsed]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            graph = candidate.get("@graph", [candidate])
            for node in graph:
                if isinstance(node, dict) and node.get("@type") == "JobPosting":
                    return {
                        "title": node.get("title") or None,
                        "company": (node.get("hiringOrganization") or {}).get("name")
                        or None,
                        "location": _extract_location(node.get("jobLocation")),
                        "description": _strip_html(node.get("description")),
                    }
    return None


def _extract_fallback(soup: BeautifulSoup) -> dict:
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else None
    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    description = soup.get_text(" ", strip=True)[:MAX_DESCRIPTION_CHARS] or None
    return {"title": title, "company": None, "location": None, "description": description}


def parse_job_posting_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    from_json_ld = _extract_json_ld(soup)
    if from_json_ld and (from_json_ld["title"] or from_json_ld["description"]):
        return from_json_ld

    return _extract_fallback(soup)
