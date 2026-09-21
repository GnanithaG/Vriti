"""SQLite connection and schema for JobPilot."""
import datetime
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "jobpilot.db"
RESUMES_DIR = DATA_DIR / "resumes"

# Phase 1 (accounts & auth) re-keys nearly every table around users.id and
# splits "jobs" into a shared catalog + a per-user "applications" pipeline
# table. Older local databases predate this and can't be migrated in place
# (see _quarantine_pre_auth_db) — this is fine per the project plan, since
# local SQLite data is throwaway dev/test state, not something to migrate.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profile (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    full_name TEXT,
    email TEXT,
    phone TEXT,
    location TEXT,
    linkedin_url TEXT,
    website_url TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    country TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Shared catalog: one row per posting regardless of who imported it.
-- No owner, no pipeline state — that lives in `applications`.
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    source_id TEXT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    company TEXT,
    location TEXT,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-user pipeline state for a catalog job (replaces the old stage/notes
-- columns that used to live directly on jobs).
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    stage TEXT NOT NULL DEFAULT 'saved',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, job_id)
);

CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    label TEXT NOT NULL,
    file_path TEXT NOT NULL,
    extracted_text TEXT,
    base_resume_id INTEGER REFERENCES resumes(id),
    job_id INTEGER REFERENCES jobs(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _quarantine_pre_auth_db():
    """Renames a pre-Phase-1 (single-user, no `users` table) DB out of the
    way instead of trying to migrate it — the project plan calls this out
    explicitly as fine for local dev/test data."""
    if not DB_PATH.exists():
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        has_users_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchone()
    finally:
        conn.close()

    if has_users_table:
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = DB_PATH.with_suffix(f".pre-auth-{stamp}.bak")
    DB_PATH.rename(backup_path)


def init_db():
    RESUMES_DIR.mkdir(exist_ok=True)
    _quarantine_pre_auth_db()
    with db() as conn:
        conn.executescript(SCHEMA)


def upsert_job(
    conn, url, title=None, company=None, location=None, description=None,
    source=None, source_id=None,
):
    """Insert a catalog job, or return the existing row if `url` is already saved."""
    existing = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if existing:
        return dict(existing)

    cur = conn.execute(
        """
        INSERT INTO jobs (url, title, company, location, description, source, source_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (url, title, company, location, description, source, source_id),
    )
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def upsert_application(conn, user_id, job_id):
    """Adds a job to a user's pipeline (stage 'saved'), or returns their
    existing application for it if already saved."""
    existing = conn.execute(
        "SELECT * FROM applications WHERE user_id = ? AND job_id = ?",
        (user_id, job_id),
    ).fetchone()
    if existing:
        return dict(existing)

    cur = conn.execute(
        "INSERT INTO applications (user_id, job_id) VALUES (?, ?)",
        (user_id, job_id),
    )
    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row)
