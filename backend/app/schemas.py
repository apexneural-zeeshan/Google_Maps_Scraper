from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Job Schemas
# ---------------------------------------------------------------------------

class JobCreate(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=200, examples=["restaurants"])
    location: str = Field(..., min_length=1, max_length=500, examples=["Austin, TX"])
    location_type: str = Field(
        default="address",
        pattern="^(address|pincode|city|state|country|coordinates)$",
        description="Location granularity: address, pincode, city, state, country, or coordinates",
    )
    radius_km: float = Field(default=5.0, gt=0, le=50, description="Search radius in km")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    user_email: str | None = Field(default=None, max_length=255)


class JobCreateResponse(BaseModel):
    """Extended response for job creation that includes grid info."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    keyword: str
    location: str
    location_type: str
    radius_km: float
    latitude: float | None
    longitude: float | None
    user_email: str | None
    batch_id: UUID | None
    progress: int
    current_step: str | None
    total_found: int
    total_unique: int
    layer1_status: str
    layer1_completed_at: datetime | None
    layer2_status: str
    layer2_completed_at: datetime | None
    layer3_status: str
    layer3_completed_at: datetime | None
    places_api_calls: int
    serp_api_calls: int
    estimated_cost_usd: float
    celery_task_id: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    # Grid info (only on creation)
    grid_cells: int = 0
    grid_warning: str | None = None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    keyword: str
    location: str
    location_type: str
    radius_km: float
    latitude: float | None
    longitude: float | None
    user_email: str | None
    batch_id: UUID | None
    progress: int
    current_step: str | None
    total_found: int
    total_unique: int
    # Layer statuses
    layer1_status: str
    layer1_completed_at: datetime | None
    layer2_status: str
    layer2_completed_at: datetime | None
    layer3_status: str
    layer3_completed_at: datetime | None
    # Cost tracking
    places_api_calls: int
    serp_api_calls: int
    estimated_cost_usd: float
    celery_task_id: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    skip: int
    limit: int


class BatchDeleteRequest(BaseModel):
    job_ids: list[UUID] = Field(..., min_length=1, max_length=100)


class BatchDeleteResponse(BaseModel):
    deleted: int
    errors: list[str]


# ---------------------------------------------------------------------------
# Batch Schemas
# ---------------------------------------------------------------------------

class BatchJobInput(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=500)
    location_type: str = Field(default="address", pattern="^(address|pincode|city|state|country|coordinates)$")
    radius_km: float = Field(default=5.0, gt=0, le=50)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class BatchCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    user_email: str | None = Field(default=None, max_length=255)
    jobs: list[BatchJobInput] = Field(..., min_length=1, max_length=100)


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    user_email: str | None
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    status: str
    celery_task_id: str | None
    created_at: datetime
    updated_at: datetime


class BatchDetailResponse(BaseModel):
    batch: BatchResponse
    jobs: list[JobResponse]


class BatchListResponse(BaseModel):
    items: list[BatchResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Lead Schemas
# ---------------------------------------------------------------------------

class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    place_id: str
    name: str
    address: str | None
    phone: str | None
    website: str | None
    rating: float | None
    review_count: int | None
    business_type: str | None
    types: list[str]
    latitude: float | None
    longitude: float | None
    opening_hours: dict | None
    photos: list[dict]
    price_level: int | None
    business_status: str | None
    maps_url: str | None
    description: str | None
    verified: bool | None
    reviews_per_score: dict | None
    primary_email: str | None
    emails: dict | None
    social_links: dict | None
    owner_name: str | None
    employee_count: str | None
    year_established: int | None
    business_age_years: int | None
    is_favorite: bool = False
    is_archived: bool = False
    notes: str | None = None
    tags: list[str] | None = None
    source: str
    created_at: datetime


class LeadUpdate(BaseModel):
    """Partial update for a single lead's user-managed fields."""
    is_favorite: bool | None = None
    is_archived: bool | None = None
    notes: str | None = None
    tags: list[str] | None = None


class LeadBatchUpdateRequest(BaseModel):
    lead_ids: list[UUID] = Field(..., min_length=1, max_length=500)
    update: LeadUpdate


class LeadBatchDeleteRequest(BaseModel):
    lead_ids: list[UUID] = Field(..., min_length=1, max_length=500)


class LeadBatchActionResponse(BaseModel):
    count: int


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Stats Schemas
# ---------------------------------------------------------------------------

class JobStatsResponse(BaseModel):
    job_id: UUID
    total_leads: int
    unique_place_ids: int
    sources: dict[str, int]
    avg_rating: float | None
    with_phone: int
    with_website: int
    with_email: int
    business_types: dict[str, int]


class OverviewStatsResponse(BaseModel):
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    running_jobs: int
    total_leads: int
    total_unique_leads: int
    favorite_leads: int
    total_scraping_time_hours: float
    avg_leads_per_job: float
    success_rate: float


class ApiUsageResponse(BaseModel):
    month: str
    serpapi: dict
    outscraper: dict
    playwright: dict


class RecentActivityItem(BaseModel):
    type: str
    keyword: str | None = None
    location: str | None = None
    leads: int | None = None
    error: str | None = None
    time: str
    job_id: str | None = None
