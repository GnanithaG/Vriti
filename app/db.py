"""SQLite connection and schema for JobPilot."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "jobpilot.db"
RESUMES_DIR = DATA_DIR / "resumes"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    company TEXT,
    location TEXT,
    description TEXT,
    stage TEXT NOT NULL DEFAULT 'saved',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    file_path TEXT NOT NULL,
    extracted_text TEXT,
    base_resume_id INTEGER REFERENCES resumes(id),
    job_id INTEGER REFERENCES jobs(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
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


def _ensure_column(conn, table, column, ddl):
    """Adds `column` to `table` if an older local DB predates it."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db():
    RESUMES_DIR.mkdir(exist_ok=True)
    with db() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO profile (id) VALUES (1)"
        )
        _ensure_column(conn, "resumes", "job_id", "job_id INTEGER REFERENCES jobs(id)")


def upsert_job(conn, url, title=None, company=None, location=None, description=None):
    """Insert a job, or return the existing row if `url` is already saved."""
    existing = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if existing:
        return dict(existing)

    cur = conn.execute(
        """
        INSERT INTO jobs (url, title, company, location, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        (url, title, company, location, description),
    )
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)
