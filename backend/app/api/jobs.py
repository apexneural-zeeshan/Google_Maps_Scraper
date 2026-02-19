import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.job import Job, JobStatus, LayerStatus
from app.schemas import (
    BatchDeleteRequest,
    BatchDeleteResponse,
    JobCreate,
    JobCreateResponse,
    JobListResponse,
    JobResponse,
)
from app.services.geocoder import geocode_location
from app.services.grid import generate_grid

MAX_GRID_CELLS = 100

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post(
    "/",
    response_model=JobCreateResponse,
    status_code=201,
    summary="Create a new scrape job",
    description=(
        "Submit a new Google Maps scraping job. "
        "Layer 1 (Playwright) runs automatically. "
        "Rejects jobs with >100 grid cells."
    ),
)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    if payload.location_type == "coordinates" and (
        payload.latitude is None or payload.longitude is None
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "latitude and longitude are required "
                "when location_type is 'coordinates'"
            ),
        )

    # Pre-compute grid to check size and provide warnings
    lat = payload.latitude
    lng = payload.longitude
    if lat is None or lng is None:
        try:
            lat, lng = await geocode_location(payload.location)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    grid = generate_grid(lat, lng, payload.radius_km)
    grid_cells = len(grid)

    if grid_cells > MAX_GRID_CELLS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Area too large: {grid_cells} grid cells "
                f"(maximum {MAX_GRID_CELLS}). "
                f"Reduce radius or use a smaller location."
            ),
        )

    grid_warning = None
    if grid_cells > 30:
        est_hours = (grid_cells * 3) / 60
        grid_warning = (
            f"Large area: {grid_cells} cells, "
            f"~{est_hours:.1f} hours. "
            f"Detail pages will be skipped for speed."
        )
    elif grid_cells > 10:
        est_hours = (grid_cells * 5) / 60
        grid_warning = (
            f"{grid_cells} cells, ~{est_hours:.1f} hours. "
            f"Detail pages limited to 20 per cell."
        )

    job = Job(
        keyword=payload.keyword,
        location=payload.location,
        location_type=payload.location_type,
        radius_km=payload.radius_km,
        latitude=lat,
        longitude=lng,
        user_email=payload.user_email,
        status=JobStatus.PENDING.value,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Dispatch Layer 1 (Playwright) automatically
    from app.tasks.scrape import run_layer1_playwright

    task = run_layer1_playwright.delay(str(job.id))
    job.celery_task_id = task.id
    await db.flush()
    await db.refresh(job)

    logger.info(
        "Created job %s (%d grid cells) with task %s",
        job.id, grid_cells, task.id,
    )

    # Build response with grid info
    response = {
        **{c.key: getattr(job, c.key) for c in job.__table__.columns},
        "grid_cells": grid_cells,
        "grid_warning": grid_warning,
    }
    return response


@router.get(
    "/",
    response_model=JobListResponse,
    summary="List all scrape jobs",
    description="Returns a paginated list of scrape jobs, ordered by creation date descending.",
)
async def list_jobs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    count_result = await db.execute(select(func.count(Job.id)))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit)
    )
    items = list(result.scalars().all())

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job details",
    description="Returns details and current status of a scrape job.",
)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    summary="Cancel a running job",
    description="Cancels a running scrape job and revokes the Celery task.",
)
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    terminal_statuses = {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}
    if job.status in terminal_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Job is already in terminal state: {job.status}",
        )

    # Revoke Celery task
    if job.celery_task_id:
        from app.tasks import celery_app

        celery_app.control.revoke(job.celery_task_id, terminate=True)

    job.status = JobStatus.CANCELLED.value
    job.current_step = None
    await db.flush()

    logger.info("Cancelled job %s", job.id)
    return job


@router.delete(
    "/{job_id}",
    status_code=204,
    summary="Delete a job and its leads",
    description="Permanently deletes a job and all associated leads.",
)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Cancel running task if any
    running_statuses = {
        JobStatus.PENDING.value, JobStatus.GEOCODING.value,
        JobStatus.GRID_SEARCH.value, JobStatus.PLAYWRIGHT.value,
        JobStatus.SERP_API.value, JobStatus.DEDUP.value,
        JobStatus.ENRICHING.value,
    }
    if job.status in running_statuses and job.celery_task_id:
        from app.tasks import celery_app
        celery_app.control.revoke(job.celery_task_id, terminate=True)

    await db.delete(job)
    await db.flush()

    logger.info("Deleted job %s", job_id)


@router.post(
    "/batch-delete",
    response_model=BatchDeleteResponse,
    summary="Delete multiple jobs",
    description="Permanently deletes multiple jobs and their leads.",
)
async def batch_delete_jobs(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    deleted = 0
    errors: list[str] = []

    for jid in payload.job_ids:
        result = await db.execute(select(Job).where(Job.id == jid))
        job = result.scalar_one_or_none()
        if not job:
            errors.append(f"Job {jid} not found")
            continue

        # Cancel running task
        if job.celery_task_id and job.status not in {
            JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value
        }:
            from app.tasks import celery_app
            celery_app.control.revoke(job.celery_task_id, terminate=True)

        await db.delete(job)
        deleted += 1

    await db.flush()
    logger.info("Batch deleted %d jobs", deleted)

    return {"deleted": deleted, "errors": errors}


@router.post(
    "/{job_id}/enrich/serpapi",
    response_model=JobResponse,
    summary="Run SerpAPI enrichment (Layer 2)",
    description="Triggers Layer 2 (SerpAPI) to supplement existing Playwright results.",
)
async def enrich_serpapi(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.layer1_status != LayerStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Layer 1 (Playwright) must complete before running Layer 2",
        )

    if job.layer2_status == LayerStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="Layer 2 is already running")

    from app.tasks.scrape import run_layer2_serpapi

    task = run_layer2_serpapi.delay(str(job.id))
    job.layer2_status = LayerStatus.RUNNING.value
    await db.flush()
    await db.refresh(job)

    logger.info("Job %s: dispatched Layer 2 (SerpAPI) task %s", job.id, task.id)
    return job


@router.post(
    "/{job_id}/enrich/outscraper",
    response_model=JobResponse,
    summary="Run Outscraper enrichment (Layer 3)",
    description="Triggers Layer 3 (Outscraper) to add email/social data to existing leads.",
)
async def enrich_outscraper(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.layer1_status != LayerStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Layer 1 (Playwright) must complete before running Layer 3",
        )

    if job.layer3_status == LayerStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="Layer 3 is already running")

    from app.tasks.scrape import run_layer3_outscraper

    task = run_layer3_outscraper.delay(str(job.id))
    job.layer3_status = LayerStatus.RUNNING.value
    await db.flush()
    await db.refresh(job)

    logger.info("Job %s: dispatched Layer 3 (Outscraper) task %s", job.id, task.id)
    return job
