from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.v1.routers import ws, search, auth, pages, actions, downloads
from app.core.config import settings
from fastapi.middleware.cors import CORSMiddleware
import logging
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

app = FastAPI(
    title="Anime Site FastAPI Migration",
    description="Incremental migration to FastAPI backend.",
    version="0.1.0"
)

# Tighten CORS: Allow frontend explicit origin
ORIGINS = [
    "http://localhost:5555",
    "http://127.0.0.1:5555",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.APP_SECRET_KEY,
    max_age=30 * 24 * 60 * 60  # 30 days
)

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include Routers
app.include_router(auth.router, tags=["auth"])
app.include_router(ws.router, tags=["websocket"])
app.include_router(search.router, tags=["search"])
app.include_router(pages.router, tags=["pages"])
app.include_router(actions.router, tags=["actions"])
app.include_router(downloads.router, tags=["downloads"])


@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI application started.")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("FastAPI application shutting down.")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
        request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {
                                          "request": request, "is_dark": request.session.get("is_dark", False)}, status_code=404)
    return templates.TemplateResponse("error.html", {"request": request, "is_dark": request.session.get(
        "is_dark", False), "debug_msg": str(exc.detail) if getattr(settings, "DEBUG", False) else None}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return templates.TemplateResponse("error.html", {"request": request, "is_dark": request.session.get(
        "is_dark", False), "debug_msg": traceback.format_exc() if getattr(settings, "DEBUG", False) else None}, status_code=500)
