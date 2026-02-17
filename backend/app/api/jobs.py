import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.job import Job, JobStatus
from app.schemas import JobCreate, JobListResponse, JobResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post(
    "/",
    response_model=JobResponse,
    status_code=201,
    summary="Create a new scrape job",
    description="Submit a new Google Maps scraping job. The job runs asynchronously via Celery.",
)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
) -> Job:
    if payload.location_type == "coordinates" and (payload.latitude is None or payload.longitude is None):
        raise HTTPException(
            status_code=400,
            detail="latitude and longitude are required when location_type is 'coordinates'",
        )

    job = Job(
        keyword=payload.keyword,
        location=payload.location,
        location_type=payload.location_type,
        radius_km=payload.radius_km,
        latitude=payload.latitude,
        longitude=payload.longitude,
        status=JobStatus.PENDING.value,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Dispatch Celery task
    from app.tasks.scrape import run_scrape_job

    task = run_scrape_job.delay(str(job.id))
    job.celery_task_id = task.id
    await db.flush()
    await db.refresh(job)

    logger.info("Created job %s with Celery task %s", job.id, task.id)
    return job


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


@router.delete(
    "/{job_id}",
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
