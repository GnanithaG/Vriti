from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import jobs, profile

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

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
