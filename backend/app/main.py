import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.batches import router as batches_router
from app.api.jobs import router as jobs_router
from app.api.results import router as results_router
from app.api.stats import router as stats_router
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Build allowed CORS origins once at startup
_CORS_ORIGINS: list[str] = []
_CORS_ORIGIN_REGEX = re.compile(r"^https://([a-z0-9-]+\.)*apexneural\.cloud$")


def _get_cors_origins() -> list[str]:
    global _CORS_ORIGINS
    if _CORS_ORIGINS:
        return _CORS_ORIGINS
    orig = list(settings.backend_cors_origins) if settings.backend_cors_origins else []
    if settings.cors_production_origin and settings.cors_production_origin not in orig:
        orig.append(settings.cors_production_origin)
    if not orig:
        orig = [settings.cors_production_origin or "https://gmapscraper.apexneural.cloud"]
    _CORS_ORIGINS[:] = orig
    return _CORS_ORIGINS


def _is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    origins = _get_cors_origins()
    if origin in origins:
        return True
    if _CORS_ORIGIN_REGEX.match(origin):
        return True
    return False


class CORSInjectMiddleware(BaseHTTPMiddleware):
    """Ensure every response has CORS headers so browser never sees 'missing header' (e.g. on 404/5xx)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        origin = request.headers.get("origin")
        if not _is_origin_allowed(origin):
            return response
        # If response already has the header, leave it; otherwise add it
        if "access-control-allow-origin" not in (k.lower() for k in response.headers.keys()):
            response.headers["access-control-allow-origin"] = origin
            response.headers["access-control-allow-credentials"] = "true"
            response.headers["vary"] = "Origin"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Google Maps Scraper API")
    _get_cors_origins()
    logger.info("CORS allowed origins: %s", _CORS_ORIGINS)
    yield
    logger.info("Shutting down Google Maps Scraper API")


app = FastAPI(
    title="Google Maps Scraper API",
    description="3-layer Google Maps scraping tool with Places API, SerpAPI, and Playwright.",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS inject first so it runs last on response (adds header if CORSMiddleware didn't)
app.add_middleware(CORSInjectMiddleware)
# Standard CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_origin_regex=r"^https://([a-z0-9-]+\.)*apexneural\.cloud$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)
app.include_router(results_router)
app.include_router(batches_router)
app.include_router(stats_router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


@app.get("/api", tags=["health"])
async def api_info():
    """Confirm backend is reachable at /api (helps debug proxy 404)."""
    return {"service": "Google Maps Scraper API", "docs": "/docs", "health": "/health"}
