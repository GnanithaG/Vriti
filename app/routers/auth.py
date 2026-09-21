from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import (
    MIN_PASSWORD_LENGTH,
    get_current_user,
    get_user_by_email,
    hash_password,
    verify_password,
)
from ..db import db
from ..models import LoginIn, RegisterIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public_user(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"]}


@router.post("/register")
def register(payload: RegisterIn, request: Request):
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )

    with db() as conn:
        if get_user_by_email(conn, email):
            raise HTTPException(status_code=400, detail="Email already registered")

        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, hash_password(payload.password)),
        )
        user_id = cur.lastrowid
        conn.execute(
            "INSERT INTO profile (user_id, email) VALUES (?, ?)", (user_id, email)
        )

    request.session["user_id"] = user_id
    return {"id": user_id, "email": email}


@router.post("/login")
def login(payload: LoginIn, request: Request):
    email = payload.email.strip().lower()
    with db() as conn:
        user = get_user_by_email(conn, email)

    if not user or not verify_password(payload.password, user["password_hash"]):
        # Deliberately generic — never reveal whether the email exists.
        raise HTTPException(status_code=401, detail="Invalid email or password")

    request.session["user_id"] = user["id"]
    return _public_user(user)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return _public_user(user)
