"""AI-assisted resume tailoring via the Anthropic API.

Only ever called explicitly by the user from the review UI — never on a
schedule, never silently. The model is instructed to rewrite only what the
candidate's resume already supports; nothing here saves or applies a
suggestion without an explicit accept in the dashboard.
"""
import os
from typing import Optional

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5"
MAX_SUGGESTIONS = 8

SYSTEM_PROMPT = f"""You help tailor an existing resume to a specific job posting.

Rules, in order of importance:
1. Never invent experience, employers, job titles, tools, technologies, or
   accomplishments that are not already present in the candidate's resume
   text. You are rewriting existing lines, not adding new claims.
2. Each suggestion's `original` field must be an exact, verbatim substring
   copied from the resume text you were given (same words, punctuation, and
   casing) so it can be located and replaced automatically. Do not
   paraphrase `original`.
3. Rewrite the matched bullet to better reflect the job posting's language
   and priorities, using only what the resume already supports.
4. Set `grounded` to true only if every claim in `suggested` is directly
   verifiable against the original resume text. If you cannot fully verify
   part of a rewrite, set `grounded` to false and explain in
   `ungrounded_note` exactly which part isn't backed by the resume — never
   silently drop the caveat by leaving `grounded` true.
5. Suggest at most {MAX_SUGGESTIONS} bullets, prioritizing resume lines most
   relevant to the job's matched and missing terms.
6. If nothing in the resume is worth rewriting, return an empty list.
"""


class BulletSuggestion(BaseModel):
    original: str
    suggested: str
    rationale: str
    grounded: bool
    ungrounded_note: Optional[str] = None


class TailoringSuggestions(BaseModel):
    suggestions: list[BulletSuggestion]


class TailoringUnavailable(RuntimeError):
    """Raised when tailoring can't run — e.g. no API key configured."""


def _build_user_prompt(
    resume_text: str, job_description: str, matched_terms: list[str], missing_terms: list[str]
) -> str:
    return f"""Job description:
{job_description}

Terms from the job description already evidenced in the resume:
{", ".join(matched_terms) or "(none)"}

Terms from the job description NOT evidenced in the resume:
{", ".join(missing_terms) or "(none)"}

Candidate's current resume text:
{resume_text}
"""


def generate_suggestions(
    resume_text: str,
    job_description: str,
    matched_terms: list[str],
    missing_terms: list[str],
) -> list[BulletSuggestion]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise TailoringUnavailable(
            "Set ANTHROPIC_API_KEY in a local .env file to use AI-assisted tailoring "
            "(see .env.example)."
        )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": _build_user_prompt(
                    resume_text, job_description, matched_terms, missing_terms
                ),
            }
        ],
        output_format=TailoringSuggestions,
    )
    return response.parsed_output.suggestions
