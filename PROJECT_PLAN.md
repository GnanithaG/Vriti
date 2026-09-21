# JobPilot — Project Plan

A job application copilot: people register and log in, land on a Careers page that asks for
their resume, get job matches and tailoring suggestions based on it, track applications through
a pipeline, and use a Chrome/Edge extension to capture postings and preview safe form prefill.
**The person always presses Submit — JobPilot never submits an application on its own.**

This plan is written to be handed to Claude Code as a build spec. Each phase is a working,
testable increment — don't start a phase until the previous one runs end-to-end. **Phase order
matters more than usual here**: Phase 1 (Accounts & Auth) changes the data model everything
else sits on, so it goes first even though earlier work (job import, resumes, stats) already
exists without it.

## Already built (Phase 0 — MVP)

Located in this repo under `app/` and `extension/`, currently **single-user, no auth**:
- FastAPI backend (`app/main.py`) with SQLite (`data/jobpilot.db`): jobs table, profile table.
- Endpoints: health, jobs CRUD + stage, profile GET/PUT, prefill, resumes upload, job-URL and
  Greenhouse/Lever import, stats.
- Dashboard (`app/static/`): profile form, import jobs, resume upload, stats.
- Extension (`extension/`): manifest v3 popup, content script that reads `JobPosting` JSON-LD
  (falls back to page text), and a prefill-preview function that fills ordinary contact fields,
  highlights them, skips a hard-coded sensitive-field blocklist (gender, race, disability,
  veteran status, SSN/DOB, salary, password, etc.), never overwrites a filled field, and never
  touches Submit.
- `run.bat` for one-click local start on Windows.

Treat this as the foundation. Later phases extend and re-key it for multiple users — see
Phase 1's migration notes before touching the schema.

## Ground rules for every phase

- **No auto-submit, ever.** No phase adds code that clicks a submit button or equivalent.
- **Sensitive fields stay untouched.** Any new field-detection logic reuses/extends the
  existing blocklist regex in `content.js`; it never shrinks it.
- **A user only ever sees their own data.** Every query that touches jobs, resumes, profile,
  applications, or tailored resumes filters by the logged-in user's id — no endpoint trusts a
  client-supplied user id.
- Everything runs locally (SQLite + FastAPI on 127.0.0.1) unless a phase explicitly says
  otherwise. No resume text or job description leaves the machine except to the AI provider
  called for tailoring, and that call is explicit and visible to the user.
- Each phase ends with something you can click through, not just code that compiles.

---

## Phase 1 — Accounts & Auth

**Goal:** real registration and login gating everything else. Do this before any other phase
below — it changes who owns a row in every table.

**Data model change:** today `profile` is a single row (`id=1`) and `resumes`/`jobs` aren't
tied to anyone. Split "jobs" into a **shared catalog** (a posting is the same row no matter who
imported it) and a **per-user join table** for pipeline state:

```
users(id, email UNIQUE, password_hash, created_at)
profile(user_id PK/FK -> users.id, first_name, last_name, email, phone, city, state,
        linkedin, portfolio, work_authorization, ...)   -- one row per user now, not id=1
jobs(id, source, source_id, url UNIQUE, title, company, location, description,
     created_at)                                         -- catalog, no owner
applications(id, user_id FK, job_id FK, stage, notes, created_at, updated_at,
             UNIQUE(user_id, job_id))                     -- replaces "stage" living on jobs
resumes(id, user_id FK, label, file_path, extracted_text, created_at)
```

Since current local data is just your own dev/test rows, it's fine to drop and recreate the
SQLite file rather than write a migration — note this explicitly to Claude Code so it doesn't
over-engineer a migration script for throwaway local data.

**Backend:**
- `passlib[bcrypt]` (or `argon2-cffi`) for password hashing — never store or log plaintext.
- Session-based auth via Starlette's `SessionMiddleware` (signed cookie, `SECRET_KEY` from
  `.env`, `httponly`, `samesite=lax`). Simpler and sufficient here than JWT — everything is
  same-origin except the extension, handled below.
- Endpoints: `POST /api/auth/register {email, password}`, `POST /api/auth/login`,
  `POST /api/auth/logout`, `GET /api/auth/me`.
- A `get_current_user` FastAPI dependency that every existing endpoint (jobs, profile, resumes,
  prefill, stats, import) now requires; returns 401 if not logged in. Update those endpoints to
  filter/write by `user_id` instead of the old singleton assumptions.
- Basic password rules (min length) and generic error messages on login failure (don't reveal
  whether the email exists).

**Frontend:**
- `/login` and `/register` pages, separate from the dashboard.
- Dashboard (and the new Careers page in Phase 2) redirect to `/login` if `GET /api/auth/me`
  returns 401.
- Logout control somewhere visible once logged in.

**Extension impact:** the extension calls `127.0.0.1:8000` from a `chrome-extension://` origin,
so it needs the session cookie on every request: `fetch(..., { credentials: "include" })` on
the extension side, and CORS on the backend must allow that specific origin with
`allow_credentials=True` (a wildcard `*` origin won't work with credentials). If the user isn't
logged in, the popup should say so and link to `http://127.0.0.1:8000/login` rather than failing
silently.

**Definition of done:** register a new account, log out, log back in, confirm your profile/jobs/
resumes are scoped to that account (a second account sees none of the first account's data), and
the extension's capture/prefill still work while logged in.

## Phase 2 — Careers page: resume, matching, and suggestions

**Goal:** the page a user lands on after logging in. Ties resume upload directly to job matching
and tailoring, instead of those living as separate disconnected dashboard sections.

**Flow:**
1. After login/register, redirect to `/careers`.
2. If the user has no resume on file: show only a resume upload prompt (reuse Phase-0's PDF/
   DOCX upload + text extraction, now scoped to `user_id`). Nothing else on the page until a
   resume exists.
3. Once a resume exists: run fit analysis (reuse/extend the existing keyword-based matcher)
   between that resume and every job in the shared catalog, and show a ranked list — score,
   matched terms, and the terms the job wants that the resume doesn't evidence. Reuse the
   existing Greenhouse/Lever/URL import so the catalog has something to match against; if it's
   still thin, add a "search more roles" shortcut back to the import tools rather than building
   a second importer.
4. Each result has two actions: **Save to pipeline** (creates an `applications` row, stage
   `Saved`) and **Tailor resume for this job** — which is the entry point into the tailoring
   flow (Phase 4, once built; until then this button can be disabled with a "coming soon" state
   rather than left broken).
5. Let the user upload a replacement/additional resume and re-run matching at any time.

**Definition of done:** log in as a fresh account with no resume, get prompted to upload one,
upload it, and immediately see a real ranked list of matched jobs with matched/missing terms —
not a stub — with a working "Save to pipeline" action.

## Phase 3 — Pipeline & tracking polish

**Goal:** make the dashboard (now reading from `applications`, not a `stage` column on `jobs`)
the place you actually manage your search from.

- Search/filter your applications by title, company, stage.
- Notes field per application (free text — interview prep, contact names, etc).
- Surface "days since applied" per application using existing timestamps.
- Simple stats, scoped to the logged-in user: counts per stage, response rate
  (Applied → Interview).
- CSV export of the current user's applications.

**Definition of done:** the dashboard is usable daily without opening the database directly, and
every number on it is specific to the logged-in account.

## Phase 4 — AI-assisted resume tailoring

**Goal:** suggest resume edits per job, with a review step before anything is saved as "the"
resume for that application. This is what the Phase 2 "Tailor resume for this job" button opens.

- Requires an LLM API key (Anthropic or OpenAI) supplied via a local `.env` — never hardcoded,
  never sent anywhere but the chosen provider.
- New table: `resume_versions(id, resume_id FK, job_id FK, user_id FK, content, created_at)` for
  tailored copies, kept separate from the original uploaded resume.
- Endpoint: given a base resume + job description + Phase 2's fit-analysis output, ask the model
  for targeted bullet-point rewrites (evidence-based only — it must not invent experience;
  instruct the model to flag any claim it can't ground in the original resume).
- Dashboard: a before/after review editor — original text and suggested text side by side,
  per-bullet accept/reject/edit, never auto-applied.
- Accepted result saves as a new `resume_versions` row linked to that job and user.

**Definition of done:** from the Careers page, tailor a resume for a specific job, accept some
suggestions and reject others in the review UI, and end up with a resume version saved and
attached to that job — with no fabricated claims and no silent overwrite of the original.

## Phase 5 — Extension: form prefill hardening

**Goal:** make prefill reliable across more real application forms (Workday, Greenhouse, Lever,
iCIMS all have different form structures).

- Add site-specific field-matching hints for the major ATSs (start with Greenhouse and Lever,
  since Phase 2 already integrates with them) — same "never overwrite / skip sensitive / never
  submit" rules apply, just better field detection.
- Handle multi-step forms (detect and re-run prefill after a "Next" step, without ever clicking
  it automatically — the person still clicks Next).
- Surface the resume version (from Phase 4) relevant to that job as a one-click download/attach
  reminder in the popup (still manual attach — browsers don't allow scripted file uploads for
  security reasons, and JobPilot won't try to work around that).

**Definition of done:** prefill works cleanly on a real Greenhouse and a real Lever application
page without manual fixup, and the popup points you to the right tailored resume file, all while
logged in via the session cookie set up in Phase 1.

---

## Suggested order of work with Claude Code

1. Point Claude Code at this repo, paste this file, ask it to implement **Phase 1 first and
   stop** — it's the one every later phase depends on, including the work already merged.
2. Review, run it, confirm the definition of done before moving to Phase 2.
3. Repeat per phase. Each phase is scoped to be a single focused session.
4. Keep `data/jobpilot.db` and `.env` out of git (already in `.gitignore`) — one is local state,
   the other is secrets (`SECRET_KEY`, LLM API key).

## Suggested repo layout as this grows

```
app/
  main.py
  auth.py              # Phase 1: register/login/logout/me, get_current_user dependency
  routers/
    jobs.py             # catalog + import
    applications.py      # Phase 1: per-user pipeline (replaces stage-on-jobs)
    profile.py
    resumes.py
    careers.py            # Phase 2: matching endpoint feeding /careers
    tailoring.py            # Phase 4
  models.py              # move Pydantic models out of main.py once it gets crowded
  db.py                   # db() contextmanager + schema
  static/
    login.html            # Phase 1
    register.html          # Phase 1
    careers.html            # Phase 2
    index.html                # existing dashboard, now pipeline-focused (Phase 3)
extension/
data/                       # gitignored, local SQLite file lives here
tests/
```
