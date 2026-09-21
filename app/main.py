from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()  # local .env only — e.g. ANTHROPIC_API_KEY, SECRET_KEY

from .auth import get_or_create_secret_key  # noqa: E402
from .db import init_db  # noqa: E402
from .routers import applications, auth, imports, profile, resumes, stats, tailoring  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="JobPilot", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=get_or_create_secret_key(), same_site="lax")

# The dashboard talks to the API same-origin (no CORS needed). The
# extension's popup is a chrome-extension:// page, which is cross-origin —
# it needs the session cookie included on every request, and CORS can't
# combine a wildcard origin with credentials, so the extension's origin is
# matched by pattern instead.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/login")
def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/register")
def register_page():
    return FileResponse(STATIC_DIR / "register.html")


app.include_router(auth.router)
app.include_router(applications.router)
app.include_router(profile.router)
app.include_router(imports.router)
app.include_router(resumes.router)
app.include_router(stats.router)
app.include_router(tailoring.router)

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
