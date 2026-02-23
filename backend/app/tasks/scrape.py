"""Celery tasks for orchestrating the scrape pipeline.

Three independent layer tasks + batch processing:
1. Layer 1 (Playwright) — Primary scraper, runs automatically on job creation.
2. Layer 2 (SerpAPI) — Supplement, can be triggered independently.
3. Layer 3 (Outscraper) — Enrichment, can be triggered independently.
4. Batch — Processes multiple jobs sequentially.

Email notifications sent on completion/failure if user_email is set.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import sync_engine
from app.models.job import Batch, Job, JobStatus, LayerStatus
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
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=1,
    worker_max_tasks_per_child=10,
    task_time_limit=14400,       # 4 hours hard limit
    task_soft_time_limit=12600,   # 3.5 hours soft limit (30 min cleanup window)
    broker_connection_retry_on_startup=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_sync_session() -> Session:
    """Create a synchronous database session for Celery tasks."""
    return Session(sync_engine)


def _update_job(job_id: str, **kwargs) -> None:
    """Update job fields in the database using a fresh session."""
    session = _get_sync_session()
    try:
        session.execute(update(Job).where(Job.id == uuid.UUID(job_id)).values(**kwargs))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _update_batch(batch_id: str, **kwargs) -> None:
    """Update batch fields in the database using a fresh session."""
    session = _get_sync_session()
    try:
        session.execute(update(Batch).where(Batch.id == uuid.UUID(batch_id)).values(**kwargs))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _run_async(coro):
    """Run an async coroutine in a sync context (Celery worker)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _read_job(job_id: str) -> dict:
    """Read job data into a plain dict to avoid detached-session issues."""
    session = _get_sync_session()
    try:
        job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).one()
        return {
            "job_id": job_id,
            "keyword": job.keyword,
            "location": job.location,
            "location_type": job.location_type,
            "radius_km": job.radius_km,
            "latitude": job.latitude,
            "longitude": job.longitude,
            "user_email": job.user_email,
            "layer1_status": job.layer1_status,
            "layer2_status": job.layer2_status,
            "layer3_status": job.layer3_status,
            "total_found": job.total_found,
            "total_unique": job.total_unique,
        }
    finally:
        session.close()


def _read_existing_leads(job_id: str) -> list[dict]:
    """Read existing leads for a job as plain dicts (for dedup merging)."""
    session = _get_sync_session()
    try:
        results = session.execute(
            select(Lead).where(Lead.job_id == uuid.UUID(job_id))
        )
        leads = []
        for lead in results.scalars().all():
            leads.append({
                "place_id": lead.place_id,
                "name": lead.name,
                "address": lead.address,
                "phone": lead.phone,
                "website": lead.website,
                "rating": lead.rating,
                "review_count": lead.review_count,
                "business_type": lead.business_type,
                "types": lead.types or [],
                "latitude": lead.latitude,
                "longitude": lead.longitude,
                "opening_hours": lead.opening_hours,
                "photos": lead.photos or [],
                "price_level": lead.price_level,
                "business_status": lead.business_status,
                "maps_url": lead.maps_url,
                "description": lead.description,
                "verified": lead.verified,
                "reviews_per_score": lead.reviews_per_score,
                "primary_email": lead.primary_email,
                "emails": lead.emails,
                "social_links": lead.social_links,
                "owner_name": lead.owner_name,
                "employee_count": lead.employee_count,
                "year_established": lead.year_established,
                "business_age_years": lead.business_age_years,
                "source": lead.source,
                "raw_data": lead.raw_data,
            })
        return leads
    finally:
        session.close()


def _build_lead(job_uuid: uuid.UUID, lead_data: dict) -> Lead:
    """Build a Lead ORM instance from a lead dict."""
    return Lead(
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
        description=lead_data.get("description"),
        verified=lead_data.get("verified"),
        reviews_per_score=lead_data.get("reviews_per_score"),
        primary_email=lead_data.get("primary_email"),
        emails=lead_data.get("emails"),
        social_links=lead_data.get("social_links"),
        owner_name=lead_data.get("owner_name"),
        employee_count=lead_data.get("employee_count"),
        year_established=lead_data.get("year_established"),
        business_age_years=lead_data.get("business_age_years"),
        source=lead_data.get("source", "unknown"),
        raw_data=lead_data.get("raw_data"),
    )


def _store_leads(job_id: str, unique_leads: list[dict]) -> int:
    """Store leads in the database with duplicate safety."""
    job_uuid = uuid.UUID(job_id)

    seen_pids: dict[str, dict] = {}
    for lead_data in unique_leads:
        pid = lead_data.get("place_id", "")
        if pid not in seen_pids:
            seen_pids[pid] = lead_data

    deduped = list(seen_pids.values())
    if len(deduped) < len(unique_leads):
        logger.info(
            "Store safety net: removed %d duplicate place_ids before insert",
            len(unique_leads) - len(deduped),
        )

    session = _get_sync_session()
    try:
        for lead_data in deduped:
            session.add(_build_lead(job_uuid, lead_data))
        session.commit()
        logger.info("Bulk insert succeeded: %d leads", len(deduped))
        return len(deduped)
    except IntegrityError as e:
        logger.warning("Bulk insert failed (%s), falling back to one-by-one", e)
        session.rollback()
    finally:
        session.close()

    stored = 0
    for lead_data in deduped:
        session = _get_sync_session()
        try:
            session.add(_build_lead(job_uuid, lead_data))
            session.commit()
            stored += 1
        except IntegrityError:
            session.rollback()
            logger.debug(
                "Skipped duplicate lead: place_id=%s name=%s",
                lead_data.get("place_id", "?"), lead_data.get("name", "?"),
            )
        finally:
            session.close()

    logger.info("One-by-one insert: %d/%d leads stored", stored, len(deduped))
    return stored


def _delete_job_leads(job_id: str) -> int:
    """Delete all leads for a job. Returns count deleted."""
    session = _get_sync_session()
    try:
        result = session.query(Lead).filter(Lead.job_id == uuid.UUID(job_id)).delete()
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_geocoded(job_id: str, job_data: dict) -> tuple[float, float]:
    """Ensure the job has coordinates. Geocode if needed."""
    is_coords = job_data["location_type"] == "coordinates"
    if is_coords and job_data["latitude"] and job_data["longitude"]:
        return job_data["latitude"], job_data["longitude"]

    lat, lng = _run_async(geocode_location(job_data["location"]))
    _update_job(job_id, latitude=lat, longitude=lng)
    return lat, lng


def _compute_overall_progress(job_id: str) -> int:
    """Compute overall job progress from layer statuses."""
    session = _get_sync_session()
    try:
        job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).one()
        progress = 0
        if job.layer1_status == LayerStatus.COMPLETED.value:
            progress += 60
        elif job.layer1_status == LayerStatus.RUNNING.value:
            progress += 30
        if job.layer2_status == LayerStatus.COMPLETED.value:
            progress += 25
        elif job.layer2_status == LayerStatus.RUNNING.value:
            progress += 12
        if job.layer3_status == LayerStatus.COMPLETED.value:
            progress += 15
        elif job.layer3_status == LayerStatus.RUNNING.value:
            progress += 7
        return min(progress, 100)
    finally:
        session.close()


def _update_overall_status(job_id: str) -> None:
    """Update the overall job status based on layer statuses."""
    session = _get_sync_session()
    try:
        job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).one()
        layers = [job.layer1_status, job.layer2_status, job.layer3_status]

        any_running = any(s == LayerStatus.RUNNING.value for s in layers)
        if any_running:
            return

        progress = _compute_overall_progress(job_id)

        if job.layer1_status == LayerStatus.COMPLETED.value:
            if all(s in (LayerStatus.COMPLETED.value, LayerStatus.IDLE.value) for s in layers):
                _update_job(
                    job_id,
                    status=JobStatus.COMPLETED.value,
                    current_step=None,
                    progress=progress,
                )
        else:
            non_idle = [s for s in layers if s != LayerStatus.IDLE.value]
            all_failed = all(s == LayerStatus.FAILED.value for s in non_idle)
            if all_failed:
                _update_job(job_id, status=JobStatus.FAILED.value, current_step=None)
    finally:
        session.close()


def _format_duration(seconds: float) -> str:
    """Format seconds into human readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}min"
    hours = minutes / 60
    return f"{hours:.1f}h"


def _send_email_sync(
    to_email: str, job_data: dict,
    email_type: str = "completed", error_message: str = "",
) -> None:
    """Send email notification from sync Celery context. Never raises."""
    if not settings.resend_api_key:
        logger.debug("RESEND_API_KEY not set — skipping email")
        return
    if not to_email:
        logger.debug("No user_email on job — skipping email")
        return

    job_id = job_data.get("job_id", "?")
    logger.info(
        "Sending %s email to %s for job %s",
        email_type, to_email, job_id,
    )

    try:
        from app.services.email import (
            send_job_completion_email,
            send_job_failed_email,
        )

        if email_type == "completed":
            _run_async(send_job_completion_email(to_email, job_data))
        elif email_type == "failed":
            _run_async(send_job_failed_email(to_email, job_data, error_message))
    except Exception as e:
        logger.warning("Failed to send %s email to %s: %s", email_type, to_email, e)


# ---------------------------------------------------------------------------
# Layer 1: Playwright (Primary Scraper)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True, name="run_layer1_playwright",
    max_retries=1, time_limit=14400, soft_time_limit=12600,
)
def run_layer1_playwright(self, job_id: str) -> dict:
    """Layer 1: Playwright scraper — primary free scraping layer.

    Features:
    - Per-cell checkpointing: saves leads to DB after each grid cell
    - SoftTimeLimitExceeded: saves partial results on timeout
    - Detail page scaling based on grid size
    """
    total_pages = 0
    total_found = 0
    stored_count = 0
    cells_completed = 0
    start_time = time.monotonic()
    partial = False

    try:
        _update_job(
            job_id,
            layer1_status=LayerStatus.RUNNING.value,
            status=JobStatus.GEOCODING.value,
            current_step="Geocoding location (Nominatim)",
            progress=5,
        )

        job_data = _read_job(job_id)
        lat, lng = _ensure_geocoded(job_id, job_data)

        logger.info(
            "Job %s Layer1: geocoded to (%.4f, %.4f)",
            job_id, lat, lng,
        )

        _update_job(
            job_id,
            status=JobStatus.GRID_SEARCH.value,
            current_step="Generating search grid",
            progress=10,
        )
        grid = generate_grid(lat, lng, job_data["radius_km"])
        total_grid = len(grid)
        logger.info("Job %s Layer1: %d grid cells", job_id, total_grid)

        # Determine detail scraping strategy based on grid size
        if total_grid <= 10:
            detail_limit = None  # scrape ALL detail pages
        elif total_grid <= 30:
            detail_limit = 20   # first 20 per cell
        else:
            detail_limit = 0    # skip details entirely

        logger.info(
            "Job %s Layer1: detail_limit=%s for %d cells",
            job_id, detail_limit, total_grid,
        )

        _update_job(
            job_id,
            status=JobStatus.PLAYWRIGHT.value,
            current_step=f"Scraping Google Maps ({total_grid} cells)",
            progress=15,
        )

        # Clear existing leads before first cell (fresh run)
        _delete_job_leads(job_id)

        try:
            for i, point in enumerate(grid):
                pw_results, pw_pages = _run_async(
                    scrape_google_maps(
                        keyword=job_data["keyword"],
                        location=job_data["location"],
                        latitude=point.latitude,
                        longitude=point.longitude,
                        max_results=60,
                        detail_limit=detail_limit,
                    )
                )
                total_pages += pw_pages
                total_found += len(pw_results)

                # Dedup + save after EACH cell (checkpoint)
                if pw_results:
                    existing = _read_existing_leads(job_id)
                    combined = existing + pw_results
                    unique = deduplicate(combined)
                    _delete_job_leads(job_id)
                    stored_count = _store_leads(job_id, unique)

                cells_completed = i + 1
                pct = 15 + int(45 * cells_completed / total_grid)
                _update_job(
                    job_id,
                    progress=pct,
                    total_found=total_found,
                    total_unique=stored_count,
                    places_api_calls=total_pages,
                    current_step=(
                        f"Cell {cells_completed}/{total_grid} done"
                        f" — {stored_count} leads"
                    ),
                )

                logger.info(
                    "Job %s: cell %d/%d done, %d leads so far",
                    job_id, cells_completed, total_grid, stored_count,
                )

        except SoftTimeLimitExceeded:
            partial = True
            logger.warning(
                "Job %s: soft time limit after %d/%d cells."
                " Saving %d partial results.",
                job_id, cells_completed, total_grid, stored_count,
            )

        elapsed = time.monotonic() - start_time
        now = datetime.now(timezone.utc)

        if partial:
            _update_job(
                job_id,
                layer1_status=LayerStatus.COMPLETED.value,
                layer1_completed_at=now,
                status=JobStatus.COMPLETED.value,
                current_step=None,
                progress=60,
                total_found=total_found,
                total_unique=stored_count,
                places_api_calls=total_pages,
                estimated_cost_usd=0.0,
                error_message=(
                    f"Partial: completed {cells_completed}/{total_grid}"
                    f" cells before time limit"
                ),
            )
        else:
            _update_job(
                job_id,
                layer1_status=LayerStatus.COMPLETED.value,
                layer1_completed_at=now,
                status=JobStatus.COMPLETED.value,
                current_step=None,
                progress=60,
                total_found=total_found,
                total_unique=stored_count,
                places_api_calls=total_pages,
                estimated_cost_usd=0.0,
            )

        _update_overall_status(job_id)

        logger.info(
            "Job %s Layer1: %s — %d leads in %s (%d/%d cells)",
            job_id,
            "PARTIAL" if partial else "COMPLETED",
            stored_count, _format_duration(elapsed),
            cells_completed, total_grid,
        )

        # Send completion email
        job_data_fresh = _read_job(job_id)
        job_data_fresh["time_taken"] = _format_duration(elapsed)
        _send_email_sync(
            job_data_fresh.get("user_email", ""),
            job_data_fresh, "completed",
        )

        return {
            "job_id": job_id,
            "layer": "playwright",
            "status": "partial" if partial else "completed",
            "total_found": total_found,
            "total_unique": stored_count,
            "playwright_pages": total_pages,
            "cells_completed": cells_completed,
            "cells_total": total_grid,
        }

    except Exception as e:
        logger.exception("Job %s Layer1 FAILED: %s", job_id, e)
        error_msg = f"Layer 1 (Playwright): {str(e)[:1900]}"
        try:
            _update_job(
                job_id,
                layer1_status=LayerStatus.FAILED.value,
                status=JobStatus.FAILED.value,
                current_step=None,
                error_message=error_msg,
                places_api_calls=total_pages,
            )
        except Exception as update_err:
            logger.error(
                "Job %s: failed to update status: %s",
                job_id, update_err,
            )

        # Send failure email
        try:
            job_data = _read_job(job_id)
            _send_email_sync(
                job_data.get("user_email", ""),
                job_data, "failed", error_msg,
            )
        except Exception:
            pass

        raise


# ---------------------------------------------------------------------------
# Layer 2: SerpAPI (Supplement)
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="run_layer2_serpapi", max_retries=1)
def run_layer2_serpapi(self, job_id: str) -> dict:
    """Layer 2: SerpAPI — supplements Playwright results."""
    total_serp_calls = 0
    start_time = time.monotonic()

    try:
        _update_job(
            job_id,
            layer2_status=LayerStatus.RUNNING.value,
            status=JobStatus.SERP_API.value,
            current_step="Supplementing with SerpAPI",
        )

        job_data = _read_job(job_id)
        lat, lng = _ensure_geocoded(job_id, job_data)
        grid = generate_grid(lat, lng, job_data["radius_km"])
        existing_leads = _read_existing_leads(job_id)

        all_new_leads: list[dict] = []
        total_grid = len(grid)

        for i, point in enumerate(grid):
            serp_results, serp_calls = _run_async(
                search_google_maps(
                    job_data["keyword"], point.latitude, point.longitude,
                    max_pages=1,
                    skip_if_over_limit=True,
                )
            )
            all_new_leads.extend(serp_results)
            total_serp_calls += serp_calls

            pct = 60 + int(20 * (i + 1) / total_grid)
            _update_job(job_id, progress=pct, serp_api_calls=total_serp_calls)

        combined = existing_leads + all_new_leads
        unique_leads = deduplicate(combined)

        _delete_job_leads(job_id)
        stored_count = _store_leads(job_id, unique_leads)

        now = datetime.now(timezone.utc)
        elapsed = time.monotonic() - start_time
        _update_job(
            job_id,
            layer2_status=LayerStatus.COMPLETED.value,
            layer2_completed_at=now,
            current_step=None,
            total_found=len(combined),
            total_unique=stored_count,
            serp_api_calls=total_serp_calls,
        )

        _update_overall_status(job_id)

        logger.info(
            "Job %s Layer2: COMPLETED — %d leads in %s",
            job_id, stored_count, _format_duration(elapsed),
        )

        job_data_fresh = _read_job(job_id)
        job_data_fresh["time_taken"] = _format_duration(elapsed)
        _send_email_sync(
            job_data_fresh.get("user_email", ""),
            job_data_fresh, "completed",
        )

        return {
            "job_id": job_id,
            "layer": "serpapi",
            "status": "completed",
            "new_results": len(all_new_leads),
            "total_unique": stored_count,
            "serp_api_calls": total_serp_calls,
        }

    except Exception as e:
        logger.exception("Job %s Layer2 FAILED: %s", job_id, e)
        error_msg = f"Layer 2 (SerpAPI): {str(e)[:1900]}"
        try:
            _update_job(
                job_id,
                layer2_status=LayerStatus.FAILED.value,
                current_step=None,
                error_message=error_msg,
                serp_api_calls=total_serp_calls,
            )
            _update_overall_status(job_id)
        except Exception as update_err:
            logger.error(
                "Job %s: failed to update: %s",
                job_id, update_err,
            )

        try:
            job_data = _read_job(job_id)
            _send_email_sync(
                job_data.get("user_email", ""),
                job_data, "failed", error_msg,
            )
        except Exception:
            pass

        raise


# ---------------------------------------------------------------------------
# Layer 3: Outscraper (Enrichment)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True, name="run_layer3_outscraper", max_retries=1,
)
def run_layer3_outscraper(self, job_id: str) -> dict:
    """Layer 3: Outscraper — enriches leads with email/social."""
    start_time = time.monotonic()

    try:
        if not settings.outscraper_api_key:
            _update_job(
                job_id,
                layer3_status=LayerStatus.FAILED.value,
                error_message="Outscraper API key not configured",
            )
            return {
                "job_id": job_id, "layer": "outscraper",
                "status": "failed", "error": "No API key",
            }

        _update_job(
            job_id,
            layer3_status=LayerStatus.RUNNING.value,
            status=JobStatus.ENRICHING.value,
            current_step="Enriching with Outscraper",
            progress=85,
        )

        existing_leads = _read_existing_leads(job_id)
        if not existing_leads:
            _update_job(
                job_id,
                layer3_status=LayerStatus.FAILED.value,
                current_step=None,
                error_message="No leads to enrich — run Layer 1 first",
            )
            return {"job_id": job_id, "layer": "outscraper", "status": "failed", "error": "No leads"}

        logger.info("Job %s Layer3: enriching %d leads", job_id, len(existing_leads))

        enriched_leads = _run_async(enrich_leads(existing_leads))

        _update_job(job_id, progress=95, current_step="Storing enriched results")

        _delete_job_leads(job_id)
        stored_count = _store_leads(job_id, enriched_leads)

        now = datetime.now(timezone.utc)
        elapsed = time.monotonic() - start_time
        _update_job(
            job_id,
            layer3_status=LayerStatus.COMPLETED.value,
            layer3_completed_at=now,
            current_step=None,
            total_unique=stored_count,
        )

        _update_overall_status(job_id)

        logger.info(
            "Job %s Layer3: COMPLETED — %d leads in %s",
            job_id, stored_count, _format_duration(elapsed),
        )

        job_data_fresh = _read_job(job_id)
        job_data_fresh["time_taken"] = _format_duration(elapsed)
        _send_email_sync(
            job_data_fresh.get("user_email", ""),
            job_data_fresh, "completed",
        )

        return {
            "job_id": job_id, "layer": "outscraper",
            "status": "completed", "total_enriched": stored_count,
        }

    except Exception as e:
        logger.exception("Job %s Layer3 FAILED: %s", job_id, e)
        error_msg = f"Layer 3 (Outscraper): {str(e)[:1900]}"
        try:
            _update_job(
                job_id,
                layer3_status=LayerStatus.FAILED.value,
                current_step=None,
                error_message=error_msg,
            )
            _update_overall_status(job_id)
        except Exception as update_err:
            logger.error(
                "Job %s: failed to update: %s",
                job_id, update_err,
            )

        try:
            job_data = _read_job(job_id)
            _send_email_sync(
                job_data.get("user_email", ""),
                job_data, "failed", error_msg,
            )
        except Exception:
            pass

        raise


# ---------------------------------------------------------------------------
# Batch Processing
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="run_batch", max_retries=0, time_limit=36000, soft_time_limit=35000)
def run_batch(self, batch_id: str) -> dict:
    """Process all jobs in a batch sequentially.

    10-hour time limit for large batches. Each job runs Layer 1 inline
    (not dispatched as a separate task) to ensure sequential execution.
    """
    start_time = time.monotonic()

    # Read batch info
    session = _get_sync_session()
    try:
        batch = session.query(Batch).filter(
            Batch.id == uuid.UUID(batch_id),
        ).one()
        jobs_q = (
            session.query(Job)
            .filter(Job.batch_id == batch.id)
            .order_by(Job.created_at)
            .all()
        )
        job_ids = [str(j.id) for j in jobs_q]
        user_email = batch.user_email
        batch_name = batch.name or "Unnamed Batch"
    finally:
        session.close()

    total_jobs = len(job_ids)
    completed_jobs = 0
    failed_jobs = 0
    total_leads = 0

    logger.info("Batch %s: starting %d jobs sequentially", batch_id, total_jobs)

    _update_batch(batch_id, status="running")

    for i, job_id in enumerate(job_ids):
        logger.info(
            "Batch %s: job %d/%d (%s)",
            batch_id, i + 1, total_jobs, job_id,
        )

        try:
            # Run Layer 1 inline (synchronous, not Celery dispatch)
            result = run_layer1_playwright.apply(
                args=[job_id],
            ).get()
            completed_jobs += 1
            total_leads += result.get("total_unique", 0)
        except Exception as e:
            logger.error("Batch %s: job %s failed: %s", batch_id, job_id, e)
            failed_jobs += 1
            # Continue to next job — don't stop the batch

        _update_batch(
            batch_id,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
        )

    # Determine final batch status
    elapsed = time.monotonic() - start_time
    if failed_jobs == 0:
        final_status = "completed"
    elif completed_jobs == 0:
        final_status = "failed"
    else:
        final_status = "partially_failed"

    _update_batch(batch_id, status=final_status)

    logger.info(
        "Batch %s: DONE — %d/%d completed, %d failed, %d leads in %s",
        batch_id, completed_jobs, total_jobs, failed_jobs, total_leads,
        _format_duration(elapsed),
    )

    # Send batch summary email
    if user_email and settings.resend_api_key:
        try:
            from app.services.email import send_batch_completion_email

            _run_async(send_batch_completion_email(user_email, {
                "batch_id": batch_id,
                "name": batch_name,
                "total_jobs": total_jobs,
                "completed_jobs": completed_jobs,
                "failed_jobs": failed_jobs,
                "total_leads": total_leads,
                "time_taken": _format_duration(elapsed),
            }))
        except Exception as e:
            logger.warning("Failed to send batch email: %s", e)

    return {
        "batch_id": batch_id,
        "status": final_status,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "total_leads": total_leads,
    }


# ---------------------------------------------------------------------------
# Legacy: run_scrape_job (dispatches Layer 1 automatically)
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="run_scrape_job", max_retries=1)
def run_scrape_job(self, job_id: str) -> dict:
    """Main entry point — dispatches Layer 1 (Playwright).

    Kept for backward compatibility with existing job creation flow.
    """
    return run_layer1_playwright.apply(
        args=[job_id],
    ).get()
