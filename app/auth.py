"""Password hashing and session-based auth for Vriti."""
import os
import secrets
from pathlib import Path

from fastapi import HTTPException, Request
from passlib.context import CryptContext

from .db import db

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_or_create_secret_key() -> str:
    """Reads SECRET_KEY from the environment, generating and persisting one
    to .env on first run if it's unset. Session cookies need *some* key to
    sign with, and making that a hard requirement before the app even boots
    would break the one-click local start — anyone who wants a fixed key
    (e.g. so sessions survive deleting .env) can still set their own."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key

    key = secrets.token_hex(32)
    os.environ["SECRET_KEY"] = key

    try:
        if ENV_PATH.exists():
            with ENV_PATH.open("a", encoding="utf-8") as f:
                f.write(f"\nSECRET_KEY={key}\n")
    except OSError:
        pass  # best-effort persistence — the key still works for this run

    return key


def get_user_by_email(conn, email: str):
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn, user_id: int):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_current_user(request: Request) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")

    with db() as conn:
        user = get_user_by_id(conn, user_id)

    if not user:
        # Stale cookie pointing at a user that no longer exists (e.g. a
        # wiped local DB) — clear it rather than staying stuck at 401.
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not logged in")

    return user
