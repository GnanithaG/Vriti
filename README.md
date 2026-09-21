# JobPilot

Local-first job application copilot: a Chrome/Edge extension that captures job postings and
previews safe form prefill, a FastAPI backend with SQLite storage, and a dashboard for managing
your pipeline.

**The person always presses Submit — JobPilot never submits an application on its own.**

## What's here (Phase 0 — MVP foundation)

- FastAPI backend (`app/main.py`, `app/routers/`) with SQLite (`data/jobpilot.db`): `jobs` and
  `profile` tables.
- Endpoints: `GET /api/health`, `POST /api/jobs` (dedupes by URL), `GET /api/jobs`,
  `PATCH /api/jobs/{id}/stage`, `GET /api/profile`, `PUT /api/profile`, `GET /api/prefill`.
- Dashboard (`app/static/`): profile form + job list with a stage dropdown.
- Extension (`extension/`): Manifest V3, a popup with "Capture this job" and "Preview prefill"
  buttons, a content script that reads `JobPosting` JSON-LD (falls back to page text), and a
  prefill-preview function that only fills ordinary contact fields, highlights what it filled,
  skips a sensitive-field blocklist (gender, race, disability, veteran status, SSN/DOB, salary,
  password, etc.), never overwrites a field that already has a value, and never touches Submit.

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

Then open http://127.0.0.1:8000.

## Loading the extension

1. Go to `chrome://extensions` (or `edge://extensions`).
2. Enable "Developer mode".
3. Click "Load unpacked" and select the `extension/` folder.
4. With the backend running locally, open a job posting page and click the JobPilot icon to
   capture the job or preview a prefill.

## Ground rules for every phase

- **No auto-submit, ever.** No code clicks a submit button or equivalent.
- **Sensitive fields stay untouched.** New field-detection logic reuses/extends the blocklist
  regex in `extension/content.js`; it never shrinks it.
- Everything runs locally (SQLite + FastAPI on 127.0.0.1) unless a phase explicitly says
  otherwise.

## Roadmap

See `PROJECT_PLAN.md` for the full phased plan: URL/board import (Phase 1), resume storage and
fit analysis (Phase 2), pipeline polish (Phase 3), AI-assisted resume tailoring (Phase 4), and
extension form-prefill hardening for major ATSs (Phase 5).
