import csv
import io
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.job import Job
from app.models.lead import Lead
from app.schemas import JobStatsResponse, LeadListResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/results", tags=["results"])

SORTABLE_COLUMNS = {
    "name": Lead.name,
    "rating": Lead.rating,
    "review_count": Lead.review_count,
    "created_at": Lead.created_at,
}


@router.get(
    "/{job_id}",
    response_model=LeadListResponse,
    summary="Get job results",
    description="Returns paginated, sortable, filterable leads for a scrape job.",
)
async def get_results(
    job_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    sort_by: str = Query(default="name", pattern="^(name|rating|review_count|created_at)$"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    search: str | None = Query(default=None, max_length=200),
    has_phone: bool | None = Query(default=None),
    has_website: bool | None = Query(default=None),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Verify job exists
    job_result = await db.execute(select(Job.id).where(Job.id == job_id))
    if not job_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")

    # Build query
    query = select(Lead).where(Lead.job_id == job_id)

    if search:
        query = query.where(Lead.name.ilike(f"%{search}%"))
    if has_phone is True:
        query = query.where(Lead.phone.is_not(None))
    elif has_phone is False:
        query = query.where(Lead.phone.is_(None))
    if has_website is True:
        query = query.where(Lead.website.is_not(None))
    elif has_website is False:
        query = query.where(Lead.website.is_(None))
    if min_rating is not None:
        query = query.where(Lead.rating >= min_rating)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    # Sort
    sort_col = SORTABLE_COLUMNS.get(sort_by, Lead.name)
    order = sort_col.desc() if sort_order == "desc" else sort_col.asc()
    query = query.order_by(order.nulls_last()).offset(skip).limit(limit)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get(
    "/{job_id}/export",
    summary="Export results as CSV",
    description="Download leads as CSV. Use template='clay' for Clay-compatible format.",
)
async def export_csv(
    job_id: uuid.UUID,
    template: str = Query(default="default", pattern="^(default|clay)$"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    # Verify job exists
    job_result = await db.execute(select(Job.id).where(Job.id == job_id))
    if not job_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(Lead).where(Lead.job_id == job_id).order_by(Lead.name)
    )
    leads = result.scalars().all()

    output = io.StringIO()

    if template == "clay":
        # Clay-compatible CSV: Company Name, Website, Phone, Address, City
        fieldnames = ["Company Name", "Website", "Phone Number", "Address", "Rating", "Reviews"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            writer.writerow({
                "Company Name": lead.name,
                "Website": lead.website or "",
                "Phone Number": lead.phone or "",
                "Address": lead.address or "",
                "Rating": lead.rating or "",
                "Reviews": lead.review_count or "",
            })
    else:
        # Default full export
        fieldnames = [
            "place_id", "name", "address", "phone", "website",
            "rating", "review_count", "business_type", "types",
            "latitude", "longitude", "price_level", "business_status",
            "maps_url", "source",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            writer.writerow({
                "place_id": lead.place_id,
                "name": lead.name,
                "address": lead.address or "",
                "phone": lead.phone or "",
                "website": lead.website or "",
                "rating": lead.rating or "",
                "review_count": lead.review_count or "",
                "business_type": lead.business_type or "",
                "types": ",".join(lead.types) if lead.types else "",
                "latitude": lead.latitude or "",
                "longitude": lead.longitude or "",
                "price_level": lead.price_level or "",
                "business_status": lead.business_status or "",
                "maps_url": lead.maps_url or "",
                "source": lead.source,
            })

    output.seek(0)
    filename = f"leads_{job_id}_{template}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{job_id}/stats",
    response_model=JobStatsResponse,
    summary="Get job statistics",
    description="Returns aggregate statistics for a job's leads.",
)
async def get_stats(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Verify job exists
    job_result = await db.execute(select(Job.id).where(Job.id == job_id))
    if not job_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")

    base = select(Lead).where(Lead.job_id == job_id)

    # Total leads
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total_leads = total_result.scalar_one()

    # Unique place IDs
    unique_result = await db.execute(
        select(func.count(distinct(Lead.place_id))).where(Lead.job_id == job_id)
    )
    unique_place_ids = unique_result.scalar_one()

    # Source distribution
    source_result = await db.execute(
        select(Lead.source, func.count()).where(Lead.job_id == job_id).group_by(Lead.source)
    )
    sources = dict(source_result.all())

    # Average rating
    avg_result = await db.execute(
        select(func.avg(Lead.rating)).where(Lead.job_id == job_id).where(Lead.rating.is_not(None))
    )
    avg_rating_raw = avg_result.scalar_one()
    avg_rating = round(float(avg_rating_raw), 2) if avg_rating_raw else None

    # Counts for phone, website
    phone_result = await db.execute(
        select(func.count()).where(Lead.job_id == job_id).where(Lead.phone.is_not(None))
    )
    with_phone = phone_result.scalar_one()

    website_result = await db.execute(
        select(func.count()).where(Lead.job_id == job_id).where(Lead.website.is_not(None))
    )
    with_website = website_result.scalar_one()

    # Business type distribution (top 20)
    type_result = await db.execute(
        select(Lead.business_type, func.count())
        .where(Lead.job_id == job_id)
        .where(Lead.business_type.is_not(None))
        .group_by(Lead.business_type)
        .order_by(func.count().desc())
        .limit(20)
    )
    business_types = dict(type_result.all())

    return {
        "job_id": job_id,
        "total_leads": total_leads,
        "unique_place_ids": unique_place_ids,
        "sources": sources,
        "avg_rating": avg_rating,
        "with_phone": with_phone,
        "with_website": with_website,
        "with_email": 0,  # Email not collected yet
        "business_types": business_types,
    }
