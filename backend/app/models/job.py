import enum
import uuid

from sqlalchemy import Enum, Float, Index, Integer, String, Text
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

    # Progress tracking
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    total_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_unique: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Cost tracking
    places_api_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    serp_api_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Celery integration
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    leads: Mapped[list["Lead"]] = relationship("Lead", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Job {self.id} [{self.status}] {self.keyword}@{self.location}>"
