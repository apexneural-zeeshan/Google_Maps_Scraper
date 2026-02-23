import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    GEOCODING = "geocoding"
    GRID_SEARCH = "grid_search"
    PLAYWRIGHT = "playwright"
    SERP_API = "serp_api"
    DEDUP = "dedup"
    ENRICHING = "enriching"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# In-progress job statuses (for counts). Do NOT use "running" — that is Batch/LayerStatus only.
JOB_STATUSES_IN_PROGRESS: tuple[str, ...] = (
    JobStatus.PENDING.value,
    JobStatus.GEOCODING.value,
    JobStatus.GRID_SEARCH.value,
    JobStatus.PLAYWRIGHT.value,
    JobStatus.SERP_API.value,
    JobStatus.DEDUP.value,
    JobStatus.ENRICHING.value,
)


class LayerStatus(str, enum.Enum):
    """Status for each independent scraping layer."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Batch(TimestampMixin, Base):
    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="batch", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Batch {self.id} [{self.status}] {self.name or 'unnamed'}>"


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        Enum(JobStatus, name="job_status", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=JobStatus.PENDING.value,
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    location_type: Mapped[str] = mapped_column(String(20), default="address", nullable=False)
    radius_km: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # User contact (optional)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Batch association (optional)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batches.id"), nullable=True
    )

    # Progress tracking
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    total_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_unique: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Layer statuses (independent scraping layers)
    layer1_status: Mapped[str] = mapped_column(
        String(20), default=LayerStatus.IDLE.value, nullable=False
    )
    layer1_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    layer2_status: Mapped[str] = mapped_column(
        String(20), default=LayerStatus.IDLE.value, nullable=False
    )
    layer2_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    layer3_status: Mapped[str] = mapped_column(
        String(20), default=LayerStatus.IDLE.value, nullable=False
    )
    layer3_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Cost tracking
    places_api_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    serp_api_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Celery integration
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    leads: Mapped[list["Lead"]] = relationship("Lead", back_populates="job", cascade="all, delete-orphan")
    batch: Mapped["Batch | None"] = relationship("Batch", back_populates="jobs")

    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_created_at", "created_at"),
        Index("ix_jobs_batch_id", "batch_id"),
    )

    def __repr__(self) -> str:
        return f"<Job {self.id} [{self.status}] {self.keyword}@{self.location}>"
