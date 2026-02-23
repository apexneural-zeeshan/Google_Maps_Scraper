"""Dashboard statistics API."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.job import Job
from app.models.lead import Lead
from app.schemas import (
    ApiUsageResponse,
    OverviewStatsResponse,
    RecentActivityItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get(
    "/overview",
    response_model=OverviewStatsResponse,
    summary="Dashboard overview stats",
)
async def get_overview(
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Job counts by status
    total_jobs_r = await db.execute(select(func.count()).select_from(Job))
    total_jobs = total_jobs_r.scalar_one()

    completed_r = await db.execute(
        select(func.count()).where(Job.status == "completed"),
    )
    completed_jobs = completed_r.scalar_one()

    failed_r = await db.execute(
        select(func.count()).where(Job.status == "failed"),
    )
    failed_jobs = failed_r.scalar_one()

    running_r = await db.execute(
        select(func.count()).where(
            Job.status.in_(["running", "geocoding", "grid_search",
                            "playwright", "serp_api", "enriching",
                            "dedup"]),
        ),
    )
    running_jobs = running_r.scalar_one()

    # Lead counts
    total_leads_r = await db.execute(
        select(func.count()).select_from(Lead),
    )
    total_leads = total_leads_r.scalar_one()

    unique_leads_r = await db.execute(
        select(func.count(distinct(Lead.place_id))),
    )
    total_unique_leads = unique_leads_r.scalar_one()

    favorite_r = await db.execute(
        select(func.count()).where(Lead.is_favorite.is_(True)),
    )
    favorite_leads = favorite_r.scalar_one()

    # Estimate total scraping time from completed jobs
    # (difference between created_at and layer1_completed_at)
    time_r = await db.execute(
        select(
            func.sum(
                func.extract(
                    "epoch",
                    Job.layer1_completed_at - Job.created_at,
                )
            )
        ).where(Job.layer1_completed_at.is_not(None)),
    )
    total_seconds = time_r.scalar_one() or 0
    total_scraping_time_hours = round(float(total_seconds) / 3600, 1)

    # Averages
    avg_leads = (
        round(total_leads / completed_jobs, 1)
        if completed_jobs > 0 else 0.0
    )
    finished = completed_jobs + failed_jobs
    success_rate = (
        round(completed_jobs / finished * 100, 1)
        if finished > 0 else 0.0
    )

    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "running_jobs": running_jobs,
        "total_leads": total_leads,
        "total_unique_leads": total_unique_leads,
        "favorite_leads": favorite_leads,
        "total_scraping_time_hours": total_scraping_time_hours,
        "avg_leads_per_job": avg_leads,
        "success_rate": success_rate,
    }


@router.get(
    "/api-usage",
    response_model=ApiUsageResponse,
    summary="Monthly API usage",
)
async def get_api_usage(
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    month_str = now.strftime("%Y-%m")
    month_start = now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )

    # SerpAPI usage this month
    serp_r = await db.execute(
        select(func.coalesce(func.sum(Job.serp_api_calls), 0))
        .where(Job.created_at >= month_start),
    )
    serp_used = int(serp_r.scalar_one())
    serp_limit = settings.serpapi_monthly_limit

    # Outscraper: estimate from lead count with enrichment
    outscraper_r = await db.execute(
        select(func.count())
        .where(Lead.source == "outscraper")
        .where(Lead.created_at >= month_start),
    )
    outscraper_used = outscraper_r.scalar_one()
    outscraper_limit = settings.outscraper_monthly_limit

    # Playwright pages
    pw_r = await db.execute(
        select(func.coalesce(func.sum(Job.places_api_calls), 0))
        .where(Job.created_at >= month_start),
    )
    pw_pages = int(pw_r.scalar_one())

    return {
        "month": month_str,
        "serpapi": {
            "used": serp_used,
            "limit": serp_limit,
            "remaining": max(0, serp_limit - serp_used),
        },
        "outscraper": {
            "used": outscraper_used,
            "limit": outscraper_limit,
            "remaining": max(0, outscraper_limit - outscraper_used),
        },
        "playwright": {
            "total_pages_scraped": pw_pages,
            "limit": "unlimited",
        },
    }


@router.get(
    "/recent-activity",
    response_model=list[RecentActivityItem],
    summary="Recent activity feed",
)
async def get_recent_activity(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    # Get last 10 completed/failed jobs
    result = await db.execute(
        select(Job)
        .where(Job.status.in_(["completed", "failed"]))
        .order_by(Job.updated_at.desc())
        .limit(10),
    )
    jobs = result.scalars().all()

    now = datetime.now(timezone.utc)
    items = []
    for job in jobs:
        elapsed = now - job.updated_at
        minutes = int(elapsed.total_seconds() / 60)
        if minutes < 1:
            time_ago = "just now"
        elif minutes < 60:
            time_ago = f"{minutes} min ago"
        elif minutes < 1440:
            time_ago = f"{minutes // 60} hours ago"
        else:
            time_ago = f"{minutes // 1440} days ago"

        if job.status == "completed":
            items.append({
                "type": "job_completed",
                "keyword": job.keyword,
                "location": job.location,
                "leads": job.total_unique,
                "time": time_ago,
                "job_id": str(job.id),
            })
        else:
            items.append({
                "type": "job_failed",
                "keyword": job.keyword,
                "location": job.location,
                "error": (
                    job.error_message[:100]
                    if job.error_message else "Unknown error"
                ),
                "time": time_ago,
                "job_id": str(job.id),
            })

    return items
