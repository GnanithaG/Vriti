"""Resume-to-job fit analysis.

Simple keyword/phrase extraction and overlap scoring — no LLM involved.
Phase 4 can layer AI-assisted tailoring on top of this; this stays a cheap,
deterministic baseline.
"""
import re
from collections import Counter

STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are aren't as at be
    because been before being below between both but by can't cannot could
    couldn't did didn't do does doesn't doing don't down during each few for
    from further had hadn't has hasn't have haven't having he he'd he'll
    he's her here here's hers herself him himself his how how's i i'd i'll
    i'm i've if in into is isn't it it's its itself let's me more most
    mustn't my myself no nor not of off on once only or other ought our
    ours ourselves out over own same shan't she she'd she'll she's should
    shouldn't so some such than that that's the their theirs them
    themselves then there there's these they they'd they'll they're
    they've this those through to too under until up very was wasn't we
    we'd we'll we're we've were weren't what what's when when's where
    where's which while who who's whom why why's with won't would
    wouldn't you you'd you'll you're you've your yours yourself yourselves
    will able across also etc within without
    job role team work working you your our we us company looking
    experience years year strong including plus please apply position
    candidate candidates opportunity
    """.split()
)

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")

MIN_TERM_LENGTH = 3


def extract_key_terms(text: str, max_terms: int = 25) -> list[str]:
    """Ranks distinct, non-stopword tokens by frequency in `text`."""
    counts: Counter[str] = Counter()
    display_form: dict[str, str] = {}

    for match in TOKEN_RE.finditer(text or ""):
        token = match.group().strip(".-")
        lower = token.lower()
        if len(lower) < MIN_TERM_LENGTH or lower in STOPWORDS:
            continue
        counts[lower] += 1
        display_form.setdefault(lower, token)

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [display_form[lower] for lower, _ in ranked[:max_terms]]


def analyze_fit(resume_text: str, job_description: str, max_terms: int = 25) -> dict:
    job_terms = extract_key_terms(job_description, max_terms=max_terms)
    resume_lower = (resume_text or "").lower()

    matched = [term for term in job_terms if term.lower() in resume_lower]
    missing = [term for term in job_terms if term.lower() not in resume_lower]
    score = round(len(matched) / len(job_terms) * 100) if job_terms else 0

    return {
        "score": score,
        "matched_terms": matched,
        "missing_terms": missing,
        "job_terms_count": len(job_terms),
    }
