# JobPilot — Project Plan

Local-first job application copilot: a Chrome/Edge extension that captures job postings and
previews safe form prefill, a FastAPI backend with SQLite storage, a dashboard for managing
your pipeline, and AI-assisted resume tailoring. **The person always presses Submit — JobPilot
never submits an application on its own.**

This plan is written to be handed to Claude Code as a build spec. Each phase is a working,
testable increment — don't start a phase until the previous one runs end-to-end.

## Already built (Phase 0 — MVP)

Located in this repo under `app/` and `extension/`:
- FastAPI backend (`app/main.py`) with SQLite (`data/jobpilot.db`): jobs table, profile table.
- Endpoints: `GET /api/health`, `POST /api/jobs` (dedupes by URL), `GET /api/jobs`,
  `PATCH /api/jobs/{id}/stage`, `GET/PUT /api/profile`, `GET /api/prefill`.
- Dashboard (`app/static/index.html`): profile form + job list with stage dropdown.
- Extension (`extension/`): manifest v3, popup capture button, content script that reads
  `JobPosting` JSON-LD (falls back to page text), and a prefill-preview function that fills
  ordinary contact fields, highlights them, skips a hard-coded sensitive-field blocklist
  (gender, race, disability, veteran status, SSN/DOB, salary, password, etc.), never overwrites
  a filled field, and never touches Submit.
- `run.bat` for one-click local start on Windows.

Treat this as the foundation. Phases below extend it — don't rewrite it.

## Ground rules for every phase

- **No auto-submit, ever.** No phase adds code that clicks a submit button or equivalent.
- **Sensitive fields stay untouched.** Any new field-detection logic reuses/extends the
  existing blocklist regex in `content.js`; it never shrinks it.
- Everything runs locally (SQLite + FastAPI on 127.0.0.1) unless a phase explicitly says
  otherwise. No resume text or job description leaves the machine except to the AI provider
  called for tailoring (Phase 4), and that call is explicit and visible to the user.
- Each phase ends with something you can click through, not just code that compiles.

---

## Phase 1 — Job import beyond paste/capture

**Goal:** get jobs into the system with less manual clicking.

- Add a "paste a URL" box to the dashboard that fetches and parses the page server-side
  (reuse the same JobPosting JSON-LD / fallback-text logic as the extension, ported to Python
  with `httpx` + `beautifulsoup4`).
- Add Greenhouse and Lever board importers: given a company's board URL
  (`boards.greenhouse.io/{company}`, `jobs.lever.co/{company}`), pull their public JSON feed
  and let the user bulk-import matching roles (simple keyword filter).
- Dedupe against the existing `url` unique constraint.

**Definition of done:** paste a Greenhouse board URL, see a list of open roles, select a few,
they land in the dashboard with correct title/company/location.

## Phase 2 — Resume storage + fit analysis

**Goal:** upload a resume once, see how well it matches a given job before applying.

- New table: `resumes` (id, label, file path, extracted_text, created_at). Support `.pdf` and
  `.docx` upload; extract text server-side (`pypdf` / `python-docx`).
- New table: `resume_versions` or reuse `resumes` with a `base_resume_id` for tailored copies
  (needed by Phase 4).
- Fit analysis endpoint: given a resume + job description, extract key terms/skills from the
  job (simple keyword/phrase extraction to start — no LLM needed yet) and return:
  - matched terms (appear in both)
  - terms in the job not evidenced in the resume
  - a rough score (e.g. % of job terms matched)
- Dashboard: resume upload page, and a "Fit" tab on each job showing the matched/missing terms.

**Definition of done:** upload a resume, open a saved job, see a real matched-vs-missing term
breakdown, not a stub.

## Phase 3 — Pipeline & tracking polish

**Goal:** make the dashboard the place you actually manage your search from.

- Search/filter jobs by title, company, stage.
- Notes field per job (free text — interview prep, contact names, etc).
- Timestamps already exist (`created_at`/`updated_at`); surface "days since applied" per job.
- Simple stats: counts per stage, response rate (Applied → Interview).
- CSV export of the jobs table.

**Definition of done:** the dashboard is usable daily without opening the database directly.

## Phase 4 — AI-assisted resume tailoring

**Goal:** suggest resume edits per job, with a review step before anything is saved as "the"
resume for that application.

- Requires an LLM API key (Anthropic or OpenAI) supplied via a local `.env` — never hardcoded,
  never sent anywhere but the chosen provider.
- Endpoint: given a base resume + job description + fit-analysis output from Phase 2, ask the
  model for targeted bullet-point rewrites (evidence-based only — it must not invent
  experience; instruct the model to flag any claim it can't ground in the original resume).
- Dashboard: a before/after review editor — original text and suggested text side by side,
  per-bullet accept/reject/edit, never auto-applied.
- Accepted result saves as a new row in `resume_versions`, linked to that job.

**Definition of done:** pick a job, generate tailored suggestions, accept some and reject
others in the review UI, and end up with a resume version saved and attached to that job —
with no fabricated claims and no silent overwrite of the original.

## Phase 5 — Extension: form prefill hardening

**Goal:** make prefill reliable across more real application forms (Workday, Greenhouse,
Lever, iCIMS all have different form structures).

- Add site-specific field-matching hints for the major ATSs (start with Greenhouse and Lever,
  since Phase 1 already integrates with them) — same "never overwrite / skip sensitive /
  never submit" rules apply, just better field detection.
- Handle multi-step forms (detect and re-run prefill after a "Next" step, without ever
  clicking it automatically — the person still clicks Next).
- Surface the resume version (from Phase 4) relevant to that job as a one-click download/attach
  reminder in the popup (still manual attach — browsers don't allow scripted file uploads for
  security reasons, and JobPilot won't try to work around that).

**Definition of done:** prefill works cleanly on a real Greenhouse and a real Lever application
page without manual fixup, and the popup points you to the right tailored resume file.

---

## Suggested order of work with Claude Code

1. Point Claude Code at this repo, paste this file, ask it to implement Phase 1 first and stop.
2. Review, run it, confirm the definition of done before moving to Phase 2.
3. Repeat per phase. Each phase is scoped to be a single focused session.
4. Keep `data/jobpilot.db` out of git (already in `.gitignore`) — it's local state, not code.

## Suggested repo layout as this grows

```
app/
  main.py            # keep splitting into routers as endpoints grow:
  routers/
    jobs.py
    profile.py
    resumes.py        # Phase 2
    tailoring.py       # Phase 4
    imports.py          # Phase 1 (Greenhouse/Lever)
  models.py            # move Pydantic models out of main.py once it gets crowded
  db.py                # move the db() contextmanager + schema here
  static/
extension/
data/                   # gitignored, local SQLite file lives here
tests/
```
