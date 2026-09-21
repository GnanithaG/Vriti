from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..db import db
from ..models import ProfileIn

router = APIRouter(tags=["profile"])

PROFILE_FIELDS = (
    "full_name",
    "email",
    "phone",
    "location",
    "linkedin_url",
    "website_url",
    "address",
    "city",
    "state",
    "postal_code",
    "country",
)


@router.get("/api/profile")
def get_profile(user: dict = Depends(get_current_user)):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM profile WHERE user_id = ?", (user["id"],)
        ).fetchone()
        return dict(row)


@router.put("/api/profile")
def put_profile(profile: ProfileIn, user: dict = Depends(get_current_user)):
    with db() as conn:
        conn.execute(
            f"""
            UPDATE profile SET
                {", ".join(f"{f} = ?" for f in PROFILE_FIELDS)},
                updated_at = datetime('now')
            WHERE user_id = ?
            """,
            tuple(getattr(profile, f) for f in PROFILE_FIELDS) + (user["id"],),
        )
        row = conn.execute(
            "SELECT * FROM profile WHERE user_id = ?", (user["id"],)
        ).fetchone()
        return dict(row)


@router.get("/api/prefill")
def get_prefill(user: dict = Depends(get_current_user)):
    """Profile fields formatted for the extension's form-fill preview."""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM profile WHERE user_id = ?", (user["id"],)
        ).fetchone()
        profile = dict(row)

    full_name = profile.get("full_name") or ""
    first_name, _, last_name = full_name.partition(" ")

    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": profile.get("email") or "",
        "phone": profile.get("phone") or "",
        "location": profile.get("location") or "",
        "linkedin_url": profile.get("linkedin_url") or "",
        "website_url": profile.get("website_url") or "",
        "address": profile.get("address") or "",
        "city": profile.get("city") or "",
        "state": profile.get("state") or "",
        "postal_code": profile.get("postal_code") or "",
        "country": profile.get("country") or "",
    }
