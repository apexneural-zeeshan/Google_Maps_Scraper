import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.batches import router as batches_router
from app.api.jobs import router as jobs_router
from app.api.results import router as results_router
from app.api.stats import router as stats_router
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Google Maps Scraper API")
    yield
    logger.info("Shutting down Google Maps Scraper API")


app = FastAPI(
    title="Google Maps Scraper API",
    description="3-layer Google Maps scraping tool with Places API, SerpAPI, and Playwright.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
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
