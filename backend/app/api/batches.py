import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.job import Batch, Job, JobStatus
from app.schemas import (
    BatchCreate,
    BatchDetailResponse,
    BatchListResponse,
    BatchResponse,
    JobResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batches", tags=["batches"])


@router.post(
    "/",
    response_model=BatchDetailResponse,
    status_code=201,
    summary="Create a batch of scrape jobs",
    description="Creates multiple scrape jobs that process sequentially. Up to 100 jobs per batch.",
)
async def create_batch(
    payload: BatchCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    batch = Batch(
        name=payload.name,
        user_email=payload.user_email,
        total_jobs=len(payload.jobs),
        status="pending",
    )
    db.add(batch)
    await db.flush()
    await db.refresh(batch)

    jobs: list[Job] = []
    for job_input in payload.jobs:
        if job_input.location_type == "coordinates" and (
            job_input.latitude is None or job_input.longitude is None
        ):
            raise HTTPException(
                status_code=400,
                detail=f"latitude and longitude required for coordinates: {job_input.keyword}",
            )

        job = Job(
            keyword=job_input.keyword,
            location=job_input.location,
            location_type=job_input.location_type,
            radius_km=job_input.radius_km,
            latitude=job_input.latitude,
            longitude=job_input.longitude,
            user_email=payload.user_email,
            batch_id=batch.id,
            status=JobStatus.PENDING.value,
        )
        db.add(job)
        jobs.append(job)

    await db.flush()
    for job in jobs:
        await db.refresh(job)

    # Dispatch batch processing task
    from app.tasks.scrape import run_batch

    task = run_batch.delay(str(batch.id))
    batch.celery_task_id = task.id
    batch.status = "running"
    await db.flush()
    await db.refresh(batch)

    logger.info(
        "Created batch %s (%s) with %d jobs, task %s",
        batch.id, batch.name, len(jobs), task.id,
    )

    return {"batch": batch, "jobs": jobs}


@router.get(
    "/",
    response_model=BatchListResponse,
    summary="List all batches",
    description="Returns a paginated list of batches, ordered by creation date descending.",
)
async def list_batches(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    count_result = await db.execute(select(func.count(Batch.id)))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Batch).order_by(Batch.created_at.desc()).offset(skip).limit(limit)
    )
    items = list(result.scalars().all())

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get(
    "/{batch_id}",
    response_model=BatchDetailResponse,
    summary="Get batch details",
    description="Returns batch details with all job statuses.",
)
async def get_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Batch).where(Batch.id == batch_id).options(selectinload(Batch.jobs))
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    return {"batch": batch, "jobs": batch.jobs}


@router.delete(
    "/{batch_id}",
    status_code=204,
    summary="Delete a batch and all its jobs",
    description="Permanently deletes a batch, all associated jobs, and their leads.",
)
async def delete_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Batch).where(Batch.id == batch_id).options(selectinload(Batch.jobs))
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Cancel running Celery task
    if batch.celery_task_id and batch.status == "running":
        from app.tasks import celery_app
        celery_app.control.revoke(batch.celery_task_id, terminate=True)

    # Cancel any running job tasks
    for job in batch.jobs:
        if job.celery_task_id and job.status not in {
            JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value
        }:
            from app.tasks import celery_app
            celery_app.control.revoke(job.celery_task_id, terminate=True)

    await db.delete(batch)
    await db.flush()

    logger.info("Deleted batch %s", batch_id)
