# JobPilot

A job application copilot: register and log in, capture and import job postings, track them
through a pipeline, get keyword-based fit analysis and AI-assisted resume tailoring, and use a
Chrome/Edge extension to preview safe form prefill on real application pages.

**The person always presses Submit — JobPilot never submits an application on its own.**

## What's here

- **Accounts & auth**: register/login/logout with hashed passwords (argon2) and signed session
  cookies. Every endpoint requires being logged in, and every query is scoped to the logged-in
  account — a second account never sees the first account's data.
- **Data model**: `jobs` is a shared catalog (one row per posting regardless of who imported it);
  `applications` is each user's own pipeline state (stage, notes) for a catalog job; `resumes` and
  `profile` are per-user.
- FastAPI backend (`app/main.py`, `app/routers/`) with SQLite (`data/jobpilot.db`).
- Endpoints: auth (`/api/auth/*`), applications pipeline (`/api/applications/*` — create/list/
  search/stage/notes/fit/CSV export), profile, resume upload + fit analysis + AI tailoring,
  job import (paste a URL, or bulk-import from a Greenhouse/Lever board), and stats.
- Dashboard (`app/static/`): login/register pages, profile form, job import, resume upload,
  per-application Fit / Notes / Tailor panels, stats, CSV export.
- Extension (`extension/`): Manifest V3, a popup with "Capture this job" and "Preview prefill"
  buttons (both require being logged in — the popup links to the login page otherwise), a content
  script that reads `JobPosting` JSON-LD (falls back to page text) with site-specific field hints
  for Greenhouse/Lever and multi-step form support, and a prefill-preview function that only fills
  ordinary contact fields, highlights what it filled, skips a sensitive-field blocklist (gender,
  race, disability, veteran status, SSN/DOB, salary, password, etc.), never overwrites a field
  that already has a value, and never touches Submit.

## Running locally

**Windows:** double-click `run.bat` (creates a venv, installs dependencies, starts the server,
opens the dashboard).

**Manual / macOS / Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000 — you'll land on the login page. Register an account to continue.

### Configuration (`.env`)

Copy `.env.example` to `.env`:

- `ANTHROPIC_API_KEY` — required for AI-assisted resume tailoring. Never hardcoded, never sent
  anywhere but Anthropic's API.
- `SECRET_KEY` — signs session cookies. If left blank, JobPilot generates a random one on first
  run and saves it back to `.env`.

### Upgrading from a pre-accounts install

If you have a local `data/jobpilot.db` from before accounts existed, JobPilot detects the old
schema on startup, renames it to `data/jobpilot.pre-auth-<timestamp>.bak` (nothing is deleted),
and starts fresh. Register a new account and re-import/re-upload — local dev data isn't migrated.

## Loading the extension

1. Go to `chrome://extensions` (or `edge://extensions`).
2. Enable "Developer mode".
3. Click "Load unpacked" and select the `extension/` folder.
4. Log in to the dashboard at http://127.0.0.1:8000 first — the extension shares that session.
5. Open a job posting page and click the JobPilot icon to capture the job or preview a prefill.

## Ground rules

- **No auto-submit, ever.** No code clicks a submit button or equivalent.
- **Sensitive fields stay untouched.** New field-detection logic reuses/extends the blocklist
  regex in `extension/content.js`; it never shrinks it.
- **A user only ever sees their own data.** Every query that touches jobs, resumes, profile, or
  applications filters by the logged-in user's id.
- Everything runs locally (SQLite + FastAPI on 127.0.0.1) unless a phase explicitly says
  otherwise. No resume text or job description leaves the machine except to the AI provider
  called for tailoring, and that call is explicit and visible to the user.

## Roadmap

See `PROJECT_PLAN.md` for the full phased plan. Accounts & auth (Phase 1) is done; next up is the
Careers page (Phase 2) — resume upload driving ranked job matches for the logged-in user.
