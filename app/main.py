from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()  # local .env only — e.g. ANTHROPIC_API_KEY for Phase 4 tailoring

from .db import init_db  # noqa: E402
from .routers import imports, jobs, profile, resumes, stats, tailoring  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="JobPilot", lifespan=lifespan)

# The extension runs as a content/popup script on arbitrary job sites and
# talks to this local API, so it needs CORS allowed from any origin — the
# API only ever binds to 127.0.0.1.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(jobs.router)
app.include_router(profile.router)
app.include_router(imports.router)
app.include_router(resumes.router)
app.include_router(stats.router)
app.include_router(tailoring.router)

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
