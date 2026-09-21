"""Employment-type / contract-subtype classification for catalog jobs.

Runs on every job as it enters the catalog (see db.upsert_job). Two-stage:
1. Map schema.org JobPosting `employmentType` (from JSON-LD, when present)
   to one of our coarse buckets.
2. Fall back to (and, for contract sub-type, always run) keyword heuristics
   over the title + description — W2/C2C/C2H has no schema.org equivalent,
   so it's always heuristic.
"""
import re
from typing import Optional

EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "other")
CONTRACT_TYPES = ("w2", "c2c", "c2h")

_SCHEMA_ORG_MAP = {
    "FULL_TIME": "full_time",
    "PART_TIME": "part_time",
    "CONTRACTOR": "contract",
    "TEMPORARY": "contract",
    "INTERN": "internship",
    "INTERNSHIP": "internship",
    "PER_DIEM": "other",
    "VOLUNTEER": "other",
    "OTHER": "other",
}

_FULL_TIME_RE = re.compile(r"\bfull[-\s]?time\b|\bfte\b", re.I)
_PART_TIME_RE = re.compile(r"\bpart[-\s]?time\b", re.I)
_CONTRACT_RE = re.compile(r"\bcontract(or)?\b|\btemp(orary)?\b|\b1099\b", re.I)
_INTERN_RE = re.compile(r"\bintern(ship)?\b", re.I)

# Checked in order — corp-to-corp/contract-to-hire phrasing wins over a bare
# "W2" mention (a posting can say "W2 or C2C" and still mean C2C is on the
# table), so most-specific patterns go first.
_CONTRACT_SUBTYPE_PATTERNS = (
    ("c2h", re.compile(r"\bc2h\b|contract[-\s]?to[-\s]?hire", re.I)),
    ("c2c", re.compile(r"\bc2c\b|corp[-\s]?(to|-)[-\s]?corp", re.I)),
    ("w2", re.compile(r"\bw[-\s]?2\b(?!\s*form)", re.I)),
)


def classify_employment(
    title: Optional[str], description: Optional[str], raw_employment_type: Optional[str] = None
) -> tuple[Optional[str], Optional[str]]:
    """Returns (employment_type, contract_type). Either may be None when
    nothing in the posting text gives a reliable signal."""
    text = " ".join(part for part in (title, description) if part)

    employment_type = None
    if raw_employment_type:
        # Schema.org allows a space-separated list; take the first mapped hit.
        for token in str(raw_employment_type).replace(",", " ").split():
            employment_type = _SCHEMA_ORG_MAP.get(token.strip().upper())
            if employment_type:
                break

    if not employment_type:
        if _CONTRACT_RE.search(text):
            employment_type = "contract"
        elif _FULL_TIME_RE.search(text):
            employment_type = "full_time"
        elif _PART_TIME_RE.search(text):
            employment_type = "part_time"
        elif _INTERN_RE.search(text):
            employment_type = "internship"

    contract_type = None
    if employment_type == "contract":
        for label, pattern in _CONTRACT_SUBTYPE_PATTERNS:
            if pattern.search(text):
                contract_type = label
                break

    return employment_type, contract_type
