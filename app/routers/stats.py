from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..db import db
from ..models import VALID_STAGES

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats(user: dict = Depends(get_current_user)):
    with db() as conn:
        rows = conn.execute(
            "SELECT stage, COUNT(*) AS count FROM applications WHERE user_id = ? GROUP BY stage",
            (user["id"],),
        ).fetchall()

    counts_by_stage = {stage: 0 for stage in VALID_STAGES}
    for row in rows:
        counts_by_stage[row["stage"]] = row["count"]

    total = sum(counts_by_stage.values())
    # A job currently sitting at "saved" was never applied to; every other
    # stage implies an application went out at some point.
    applied_or_beyond = total - counts_by_stage["saved"]
    reached_interview_or_beyond = (
        counts_by_stage["interview"] + counts_by_stage["offer"]
    )
    response_rate = (
        round(reached_interview_or_beyond / applied_or_beyond * 100)
        if applied_or_beyond
        else 0
    )

    return {
        "total_jobs": total,
        "counts_by_stage": counts_by_stage,
        "applied_or_beyond": applied_or_beyond,
        "response_rate": response_rate,
    }
