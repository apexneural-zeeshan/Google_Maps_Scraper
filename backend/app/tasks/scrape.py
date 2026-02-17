"""Celery task for orchestrating the scrape pipeline.

Pipeline (free tier — $0/month):
1. Geocode location (Nominatim) → get coordinates
2. Generate search grid
3. Playwright scraper (primary) → scrape Google Maps directly
4. SerpAPI (supplement, if under 100/month limit)
5. Deduplicate results
6. Outscraper enrichment (optional, if API key configured)
7. Store leads in database
"""

import asyncio
import logging
import uuid

from celery import Celery
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import sync_engine
from app.models.job import Job, JobStatus
from app.models.lead import Lead
from app.services.dedup import deduplicate
from app.services.geocoder import geocode_location
from app.services.grid import generate_grid
from app.services.outscraper_api import enrich_leads
from app.services.playwright_scraper import scrape_google_maps
from app.services.serp_api import search_google_maps

logger = logging.getLogger(__name__)

celery_app = Celery("gmaps_scraper")
celery_app.conf.update(
    broker_url=settings.redis_url,
    result_backend=settings.redis_url,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


def _get_sync_session() -> Session:
    """Create a synchronous database session for Celery tasks."""
    return Session(sync_engine)


def _update_job(session: Session, job_id: str, **kwargs) -> None:
    """Update job fields in the database."""
    session.execute(update(Job).where(Job.id == uuid.UUID(job_id)).values(**kwargs))
    session.commit()


def _run_async(coro):
    """Run an async coroutine in a sync context (Celery worker)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="run_scrape_job", max_retries=1)
def run_scrape_job(self, job_id: str) -> dict:
    """Main scrape pipeline task.

    Orchestrates: geocode (Nominatim) → grid → Playwright → SerpAPI → dedup
                  → Outscraper enrich → store → complete.

    Runs entirely on free-tier services ($0/month).
    """
    session = _get_sync_session()
    total_playwright_pages = 0
    total_serp_calls = 0

    try:
        # ── Step 1: Geocode (Nominatim — free) ───────────────────────────
        _update_job(
            session, job_id,
            status=JobStatus.GEOCODING.value,
            current_step="Geocoding location (Nominatim)",
            progress=5,
        )

        job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).one()

        if job.location_type == "coordinates" and job.latitude and job.longitude:
            lat, lng = job.latitude, job.longitude
        else:
            lat, lng = _run_async(geocode_location(job.location))
            _update_job(session, job_id, latitude=lat, longitude=lng)

        logger.info("Job %s: geocoded to (%.4f, %.4f)", job_id, lat, lng)

        _update_job(session, job_id, progress=15)

        # ── Step 2: Generate Grid ────────────────────────────────────────
        _update_job(
            session, job_id,
            status=JobStatus.GRID_SEARCH.value,
            current_step="Generating search grid",
            progress=15,
        )

        grid = generate_grid(lat, lng, job.radius_km)

        # Free tier: cost is $0
        _update_job(session, job_id, estimated_cost_usd=0.0)
        logger.info("Job %s: %d grid points (free tier — $0)", job_id, len(grid))

        # ── Step 3: Playwright Scraper (primary — free) ──────────────────
        _update_job(
            session, job_id,
            status=JobStatus.PLAYWRIGHT.value,
            current_step="Scraping Google Maps (Playwright)",
            progress=15,
        )

        all_leads: list[dict] = []
        total_grid = len(grid)

        for i, point in enumerate(grid):
            pw_results, pw_pages = _run_async(
                scrape_google_maps(
                    keyword=job.keyword,
                    location=job.location,
                    latitude=point.latitude,
                    longitude=point.longitude,
                    max_results=60,
                )
            )
            all_leads.extend(pw_results)
            total_playwright_pages += pw_pages

            # Update progress (15–65% for Playwright)
            pct = 15 + int(50 * (i + 1) / total_grid)
            _update_job(
                session, job_id,
                progress=pct,
                total_found=len(all_leads),
                places_api_calls=total_playwright_pages,
            )

        logger.info(
            "Job %s: Playwright done — %d results from %d pages",
            job_id, len(all_leads), total_playwright_pages,
        )

        # ── Step 4: SerpAPI Search (supplement — 100 free/month) ─────────
        _update_job(
            session, job_id,
            status=JobStatus.SERP_API.value,
            current_step="Supplementing with SerpAPI",
            progress=65,
        )

        for i, point in enumerate(grid):
            serp_results, serp_calls = _run_async(
                search_google_maps(
                    job.keyword, point.latitude, point.longitude,
                    max_pages=1,
                    skip_if_over_limit=True,
                )
            )
            all_leads.extend(serp_results)
            total_serp_calls += serp_calls

            pct = 65 + int(15 * (i + 1) / total_grid)
            _update_job(
                session, job_id,
                progress=pct,
                total_found=len(all_leads),
                serp_api_calls=total_serp_calls,
            )

        logger.info(
            "Job %s: SerpAPI done — %d total results, %d serp calls",
            job_id, len(all_leads), total_serp_calls,
        )

        # ── Step 5: Deduplication ────────────────────────────────────────
        _update_job(
            session, job_id,
            status=JobStatus.DEDUP.value,
            current_step="Deduplicating results",
            progress=80,
        )

        unique_leads = deduplicate(all_leads)

        _update_job(
            session, job_id,
            total_found=len(all_leads),
            total_unique=len(unique_leads),
            progress=85,
        )

        logger.info(
            "Job %s: dedup — %d → %d unique",
            job_id, len(all_leads), len(unique_leads),
        )

        # ── Step 6: Outscraper Enrichment (optional — 500 free/month) ────
        if settings.outscraper_api_key:
            _update_job(
                session, job_id,
                status=JobStatus.ENRICHING.value,
                current_step="Enriching with Outscraper",
                progress=90,
            )

            unique_leads = _run_async(enrich_leads(unique_leads))

            logger.info("Job %s: enrichment complete", job_id)
        else:
            logger.info("Job %s: Outscraper not configured — skipping enrichment", job_id)

        _update_job(session, job_id, progress=95)

        # ── Step 7: Store Leads ──────────────────────────────────────────
        _update_job(
            session, job_id,
            current_step="Storing results",
            progress=95,
        )

        job_uuid = uuid.UUID(job_id)
        for lead_data in unique_leads:
            lead = Lead(
                job_id=job_uuid,
                place_id=lead_data.get("place_id", f"unknown_{uuid.uuid4().hex[:8]}"),
                name=lead_data.get("name", "Unknown"),
                address=lead_data.get("address"),
                phone=lead_data.get("phone"),
                website=lead_data.get("website"),
                rating=lead_data.get("rating"),
                review_count=lead_data.get("review_count"),
                business_type=lead_data.get("business_type"),
                types=lead_data.get("types", []),
                latitude=lead_data.get("latitude"),
                longitude=lead_data.get("longitude"),
                opening_hours=lead_data.get("opening_hours"),
                photos=lead_data.get("photos", []),
                price_level=lead_data.get("price_level"),
                business_status=lead_data.get("business_status"),
                maps_url=lead_data.get("maps_url"),
                source=lead_data.get("source", "unknown"),
                raw_data=lead_data.get("raw_data"),
            )
            session.add(lead)

        session.commit()

        # ── Step 8: Complete ─────────────────────────────────────────────
        _update_job(
            session, job_id,
            status=JobStatus.COMPLETED.value,
            current_step=None,
            progress=100,
            places_api_calls=total_playwright_pages,
            serp_api_calls=total_serp_calls,
            estimated_cost_usd=0.0,  # Free tier
        )

        logger.info(
            "Job %s: COMPLETED — %d unique leads stored ($0 cost)",
            job_id, len(unique_leads),
        )

        return {
            "job_id": job_id,
            "status": "completed",
            "total_found": len(all_leads),
            "total_unique": len(unique_leads),
            "playwright_pages": total_playwright_pages,
            "serp_api_calls": total_serp_calls,
            "cost_usd": 0.0,
        }

    except Exception as e:
        logger.exception("Job %s FAILED: %s", job_id, e)
        _update_job(
            session, job_id,
            status=JobStatus.FAILED.value,
            current_step=None,
            error_message=str(e)[:2000],
            places_api_calls=total_playwright_pages,
            serp_api_calls=total_serp_calls
        )
        raise

    finally:
        session.close()
